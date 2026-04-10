import json
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from metric_parser import parse_metrics_from_html
from calculator import FinancialCalculator, CalculatorInputs, MarketInputs
from filing_store import get_filing_path
import os
from tools import TOOLS


# load env file
load_dotenv()
api_key = os.environ.get("OPENAI_API_KEY")
# connect to api
client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"    
)

# cache parsed metrics so we don't re-parse the same file twice
_metrics_cache: dict[tuple, list] = {}


def run_parse_metrics(ticker: str, year: int) -> dict:
    key = (ticker.upper(), year)

    path = get_filing_path(ticker, year)
    if path is None:
        return {"error": f"no filing found for {ticker} {year}"}
    
    if not Path(path).exists():
        return {"error": f"file not found {path}"}
    
    if key not in _metrics_cache:
        html = Path(path).read_text(encoding="utf-8", errors="replace")
        metrics = parse_metrics_from_html(html)
        _metrics_cache[key] = metrics
    
    metrics = _metrics_cache[key]

    return {
        "ticker": ticker,
        "year": year,
        "metrics": [m.to_agent_dict() for m in metrics]
    }


def run_calculate_ratios(ticker: str, year: int, price: float = 0.0, shares_outstanding: float = 0.0) -> dict:
    key = (ticker.upper(), year)

    if key not in _metrics_cache:
        result = run_parse_metrics(ticker, year)
        if "error" in result:
            return result
    
    metrics =  _metrics_cache[key]

    try:
        inputs = CalculatorInputs(
            metrics = metrics,
            market = MarketInputs(price=price, shares_outstanding=shares_outstanding)
        )
    except Exception as e:
        return {"error": f"input validation failed: {e}"}

    calc = FinancialCalculator(inputs)
    ratios = calc.run_all()

    return {
        "ticker": ticker,
        "year": year,
        "price": price,
        "ratios": [r.model_dump() for r in ratios]
    }


def dispatch(tool_name: str, tool_input: dict) -> str:
    """Execute the tool and return result as a JSON string."""
    print(f"TOOL CALL: {tool_name}({tool_input})")  # temporary
    if tool_name == "parse_metrics":
        result = run_parse_metrics(
            ticker=tool_input["ticker"],
            year=tool_input["year"]
        )
    elif tool_name == "calculate_ratios":
        result = run_calculate_ratios(
            ticker=tool_input["ticker"],
            year=tool_input["year"],
            price=tool_input.get("price", 0.0),
            shares_outstanding=tool_input.get("shares_outstanding", 0.0)
        )
    else:
        result = {"error": f"unknown tool: {tool_name}"}

    return json.dumps(result)

# system prompt
SYSTEM = """
You are a financial analyst with expertise in reading SEC filings, 
earnings reports, and financial statements. You must use tools when the question requires external data.
Do NOT make up answers.

When answering questions:
- Always cite the ticker, fiscal year, and metric name you are drawing from
- Quote exact numbers rather than approximating
- Flag any data that seems inconsistent or unusual
- f a question cannot be answered from available data, respond with only:
  "ANSWER: Insufficient data. [what is missing and why]"
  Do not speculate or use prior training knowledge to fill gaps.
- Structure answers with a direct answer first, then supporting evidence
- If a metric was flagged as missing or derived during tool execution, 
  confidence must be "low". Never return "high" for estimated values.

When analyzing financial metrics:
- Calculate year-over-year changes when relevant
- Put numbers in context using data available in the same filing 
  (e.g. compare to prior year figures, or to other segments in the same report)
- Distinguish between GAAP and non-GAAP figures when both appear
- Never infer year-over-year direction from a single year's data. Always retrieve both years before making comparisons.
- Margin questions (net profit margin, gross margin, operating margin) always 
  require calculate_ratios. Never return a raw dollar figure as a margin answer.
- When calculate_ratios is called, the evidence array must contain the computed 
  ratio result (e.g. pe_ratio=22.58), not the raw inputs used to compute it 
  (e.g. eps=33.21). Never put raw metrics in evidence when a ratio was computed.
  
Format your responses as:
ANSWER: [direct answer in 1-2 sentences]
EVIDENCE: [specific data points with ticker, year, and metric name]
CONTEXT: [caveats, GAAP vs non-GAAP distinctions, or year-over-year changes if relevant]

For compound questions, repeat this structure once per sub-question.
"""

# answer schema
ANSWER_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "financial_answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "Direct answer in 1-2 sentences"
                },
                "evidence": {
                    "type": "array",
                    "items":{
                        "type": "object",
                        "properties":{
                            "ticker":      {"type": "string"},
                            "year":        {"type": "integer"},
                            "metric_name": {"type": "string"},
                            "value":       {"type": "number"},
                            "unit":        {"type": "string"}
                        },
                        "required": ["ticker", "year", "metric_name", "value", "unit"],
                        "additionalProperties": False
                    }
                },
                "confidence":{
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "high = pulled directly from filing. medium = derived/calculated. low = estimated or data was missing"
                },
                "caveats": {
                    "type": "string",
                    "description": "GAAP vs non-GAAP distinctions, missing data, or anything unusual. Empty string if none."
                }
            },
            "required": ["answer", "evidence", "confidence", "caveats"],
            "additionalProperties": False
            }
        }
}


def run_agent(user_question: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_question}
    ]

    while True:
        response = client.chat.completions.create(
            model="openai/gpt-4o",
            tools=TOOLS,
            messages=messages
        )

        msg = response.choices[0].message
        messages.append(msg)

        # final call with structured output
        if not msg.tool_calls:
            final = client.chat.completions.create(
                model="openai/gpt-4o",
                response_format=ANSWER_SCHEMA,
                messages=messages
            )
            return json.loads(final.choices[0].message.content)
        
        for tc in msg.tool_calls:
            tool_input = json.loads(tc.function.arguments)
            result_str = dispatch(tc.function.name, tool_input)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str
            })

if __name__ == "__main__":
    questions = [
        "What was LAM's revenue in 2023?",
        "What is AMAT's P/E ratio given a price of $415 and 7.43 billion shares in 2023?",
    ]
    for q in questions:
        print(f"\nQ: {q}")
        result = run_agent(q)
        print(f"A: {result['answer']}")
        print(f"Confidence: {result['confidence']}")
        print(f"Evidence: {result['evidence']}")
        if result['caveats']:
            print(f"Caveats: {result['caveats']}")