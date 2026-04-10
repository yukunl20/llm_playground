TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "parse_metrics",
            "description": (
                "Extracts financial metrics (revenue, net income, EPS, margins, EBITDA) "
                "from a 10-K HTML filing. Call this first before calculating any ratios. "
                "Returns a list of labeled metric objects with values and units."
                "To compare across years, call this tool twice with different year values."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Company ticker symbol e.g. AMAT, AAPL"
                    },
                    "year": {
                        "type": "integer",
                        "description": "Fiscal year of the 10-K e.g. 2021"
                    }
                },
                "required": ["ticker", "year"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_ratios",
            "description": (
                "Computes derived ratios that DO NOT exist in raw filings: "
                "P/E, P/S, EV/EBITDA, net profit margin, gross margin, earnings yield. "
                "parse_metrics returns raw dollar figures only. "
                "You MUST call calculate_ratios for any question involving a margin or ratio."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "year": {"type": "integer"},
                    "price": {
                        "type": "number",
                        "description": "Stock price at time of filing"
                    },
                    "shares_outstanding": {
                        "type": "number",
                        "description": "Total shares outstanding, absolute number e.g. 876000000"
                    }
                },
                "required": ["ticker", "year"]
            }
        }
    }
]