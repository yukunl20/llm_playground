import re 
from pydantic import BaseModel, field_validator, model_validator
import math

class Metric(BaseModel):
    label: str
    value: float
    unit: str
    raw: str

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, v):
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"value must be a finite number, got {v}")
        return round(v, 4)
    
    @field_validator("unit")
    @classmethod
    def unit_must_be_valid(cls, v):
        allowed_prefixes = ("USD_", "percent", "ratio", "EPS", "units")
        if not any(v.startswith(p) for p in allowed_prefixes):
            raise ValueError(f"unrecognized unit '{v}'")
        return v
    
    @field_validator("label")
    @classmethod
    def label_must_be_known(cls, v):
        known = {"revenue", "net_income", "ebitda", "eps", "gross_margin", "op_margin"}
        if v not in known:
            raise ValueError(f"unknown label '{v}'")
        return v
    
    def to_agent_dict(self) -> dict:
        return self.model_dump()


SCALE = {"billion": 1_000_000_000, "million": 1_000_000, "thousand": 1_000,
         "b": 1_000_000_000, "m": 1_000_000, "k": 1_000}


def parse_number(raw_value: str, scale_word: str = "") -> float:
    """Convert '$1.23 billion' style strings to floats."""
    cleaned = re.sub(r'[,$\s]', '', raw_value)
    cleaned = cleaned.replace('(', '-').replace(')', '')  # handle (losses)
    num = float(cleaned)
    multiplier = SCALE.get(scale_word.lower().strip(), 1)
    return num * multiplier


PATTERNS = [
    ("revenue",     r'(?:total\s+)?revenue[s]?\s+(?:of\s+)?\$?([\d,\.]+)\s*(billion|million|thousand|[BMK])?'),
    ("net_income",  r'net\s+(?:income|earnings|loss)\s+(?:of\s+|was\s+)?\$?([\d,\.]+)\s*(billion|million|[BMK])?'),
    ("ebitda",      r'ebitda\s+(?:of\s+|was\s+)?\$?([\d,\.]+)\s*(billion|million|[BMK])?'),
    ("eps",         r'(?:diluted\s+)?(?:eps|earnings\s+per\s+share)\s+(?:of\s+)?\$?([\d,\.]+)'),
    ("gross_margin",r'gross\s+(?:profit\s+)?margin\s+(?:of\s+|was\s+)?([\d\.]+)\s*%'),
    ("op_margin",   r'operating\s+margin\s+(?:of\s+|was\s+)?([\d\.]+)\s*%'),
]


def parse_metrics(text: str) -> list[Metric]:
    results = []
    text_lower = text.lower()

    for label, pattern in PATTERNS:
        for match in re.finditer(pattern, text_lower):
            groups = match.groups()
            raw_val = groups[0]
            scale = groups[1] if len(groups) > 1 and groups[1] else ""

            try:
                value = parse_number(raw_val, scale)
                unit = "percent" if "margin" in label else f"USD_{scale or 'units'}"
                results.append(
                    Metric(label=label, value=value, unit=unit, raw=match.group(0))
                )
            except (ValueError, Exception) as e:
                print(f"skipped match for '{label}': {e}")
                continue
    
    return results

if __name__ == "__main__":
    from pathlib import Path
    from load_txt import load_text_file

    path = "10-K/AMAT/0000006951-21-000043/full-submission.txt"
    
    if not Path(path).exists():
        print(f"file not found: {path}")
    else:
        result = load_text_file(source=path)
        
        if result["error"]:
            print(f"load error: {result['error']}")
        else:
            text = result["text"]
            print(f"loaded {len(text):,} characters")
            
            metrics = parse_metrics(text)
            print(f"found {len(metrics)} metrics\n")
            
            for m in metrics:
                print(m.to_agent_dict())