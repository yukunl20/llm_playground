import json
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from metric_parser import parse_metrics_from_html
from calculator import FinancialCalculator, CalculatorInputs, MarketInputs
from filing_store import get_filing_path
import os


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


def run_calculate_ratios(ticker: str, year: int, price: float, shares_outstanding: float) -> dict:
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
    if tool_name == "parse_metrics":
        result = run_parse_metrics(
            ticker=tool_input["ticker"],
            year=tool_input["year"]
        )
    elif tool_name == "calculate_ratios":
        result = run_calculate_ratios(
            ticker=tool_input["ticker"],
            year=tool_input["year"],
            price=tool_input["price"],
            shares_outstanding=tool_input["shares_outstanding"]
        )
    else:
        result = {"error": f"unknown tool: {tool_name}"}

    return json.dumps(result)

