# 📊 SEC Filing Financial Agent — Week 1

Tool-calling LLM agent that answers financial questions from SEC 10-K filings.  
Built **without LangChain** to deeply understand the raw function-calling loop and system design tradeoffs.

---

## 🚀 Overview

This project implements a **from-scratch financial QA agent** that:

- Parses SEC 10-K filings (HTML)
- Extracts structured financial metrics
- Uses an LLM to reason and decide when to call tools
- Returns **validated, structured JSON outputs**
- Evaluates performance using a custom test suite

The focus is on **system correctness, transparency, and debuggability**, not just model output quality.

---

## 🧠 Key Concepts

- Manual tool-calling loop (ReAct-style)
- Structured output with JSON schema enforcement
- Financial data parsing (tables + regex fallback)
- Unit normalization challenges (millions vs USD)
- LLM evaluation with ground-truth test cases

---

## 🛠️ Stack

- **LLM**: `openai/gpt-4o` via OpenRouter (Azure backend)
- **API**: Raw OpenAI `/v1/chat/completions` with `tools`
- **Parsing**: BeautifulSoup + regex fallback on SEC HTML
- **Validation**: Pydantic v2
- **Output**: Structured JSON via `response_format` / `json_schema`
- **Logging**: Python logging (failure tracking)

---

## 📁 File Structure

    week1_tools/
      agent.py          # run_agent() loop, dispatch(), TOOLS schema, SYSTEM prompt
      metric_parser.py  # HTML table parser + regex fallback, Metric model
      calculator.py     # FinancialCalculator, RatioResult, MarketInputs
      filing_store.py   # Maps (ticker, year) -> local file path

    tests/
      test_agent.py     # 15 TestCase definitions, evaluator, failure logger

    10-K/
      LRCX/             # Raw HTML filings
      AMAT/

---

## ⚙️ How to Run

    # run a single query
    python agent.py

    # run evaluation suite
    python tests/test_agent.py

---

## 🔁 Agent Loop

    User question
          ↓
    messages = [system, user]
          ↓
    API call (tools=TOOLS)
          ↓
    tool_calls?
       ├── YES → dispatch(tool_name, args)
       │            ↓
       │      append tool result
       │            ↓
       │        loop back
       │
       └── NO → final API call (response_format=SCHEMA)
                        ↓
               return structured JSON

Key details:

- The loop continues until **no `tool_calls` are returned**
- Final answer formatting is done in a **separate API call**
- Tools and structured output **cannot be used simultaneously**

---

## 🔧 Tools

| Tool | Required args | Optional args | Returns |
|-----|-------------|--------------|--------|
| `parse_metrics` | ticker, year | — | List of metrics (label, value, unit, raw) |
| `calculate_ratios` | ticker, year | price, shares_outstanding | List of ratios (label, value, formula) |

---

## 📊 Answer Schema

    {
      "answer": "LRCX revenue in 2023 was $17,428,516,000.",
      "evidence": [
        {
          "ticker": "LRCX",
          "year": 2023,
          "metric_name": "revenue",
          "value": 17428516000,
          "unit": "USD_units"
        }
      ],
      "confidence": "high",
      "caveats": ""
    }

### Confidence Levels

- **high** → directly extracted from filing  
- **medium** → derived/calculated  
- **low** → estimated or incomplete data  

---

## 🧪 Evaluation

- 15 test cases covering:
  - Direct metric retrieval
  - Year-over-year reasoning
  - Ratio calculations
  - Failure handling
- Each test validates:
  - Selected field (`answer`, `value`, `confidence`)
  - Numeric tolerance (for calculations)
- Failures are logged to:

    agent_failures.log

---

