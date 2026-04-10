import re
import math
from pathlib import Path
from bs4 import BeautifulSoup
from pydantic import BaseModel, field_validator

# ---------- models ----------

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


# ---------- constants ----------
# map unit to multiplier
SCALE = {
    "billion": 1_000_000_000, "billions": 1_000_000_000,
    "million": 1_000_000,     "millions": 1_000_000,
    "thousand": 1_000,        "thousands": 1_000,
    "b": 1_000_000_000, "m": 1_000_000, "k": 1_000,
}

# normalize the label
LABEL_MAP = {
    "revenue":                    "revenue",
    "net revenues":               "revenue",
    "net sales":                  "revenue",
    "total net revenue":          "revenue",
    "net income":                 "net_income",
    "net earnings":               "net_income",
    "net loss":                   "net_income",
    "ebitda":                     "ebitda",
    "diluted net income per share":   "eps",
    "diluted earnings per share":     "eps",
    "net income per diluted share":   "eps",
    "earnings per diluted share":     "eps",
    "basic earnings per share":       "eps",   
    "earnings per share":             "eps",   
    "gross margin":               "gross_margin",
    "operating margin":           "op_margin",
}

# capture patterns
PATTERNS = [
    ("revenue",      r'(?:total\s+)?revenue[s]?\s+(?:of\s+)?\$?([\d,\.]+)\s*(billion|million|thousand|[BMK])?'),
    ("net_income",   r'net\s+(?:income|earnings|loss)\s+(?:of\s+|was\s+)?\$?([\d,\.]+)\s*(billion|million|[BMK])?'),
    ("ebitda",       r'ebitda\s+(?:of\s+|was\s+)?\$?([\d,\.]+)\s*(billion|million|[BMK])?'),
    ("eps",          r'(?:diluted\s+)?(?:eps|earnings\s+per\s+share)\s+(?:of\s+)?\$?([\d,\.]+)'),
    ("gross_margin", r'gross\s+(?:profit\s+)?margin\s+(?:of\s+|was\s+)?([\d\.]+)\s*%'),
    ("op_margin",    r'operating\s+margin\s+(?:of\s+|was\s+)?([\d\.]+)\s*%'),
]


# ---------- helpers ----------

def parse_number(raw_value: str, scale_word: str = "") -> float:
    cleaned = re.sub(r'[,$\s]', '', raw_value) # strip commas, $, space. $1,234 -> 1234
    cleaned = cleaned.replace('(', '-').replace(')', '') # accounting style: (123) -> -123
    return float(cleaned) * SCALE.get(scale_word.lower().strip(), 1)


def extract_scale_from_tag(tag) -> int:
    #extract scale from a specific table or nearby caption, not the whole doc.
    scale_re = re.compile(r'in\s+(billions?|millions?|thousands?)', re.I)
    # check the table's own text (captions, header rows, etc.)
    text = tag.get_text(" ")
    match = scale_re.search(text)
    if match:
        word = match.group(1).lower()
        return SCALE.get(word, 1)
    return 1


def clean_cell(cell_text: str) -> tuple[str, bool]:
    # strip spaces and indicate if it is negative
    c = cell_text.replace(',', '').replace('$', '').replace('\xa0', '').strip()
    is_neg = c.startswith('(') and c.endswith(')')
    return c.strip('()'), is_neg


# ---------- extractors ----------

"""
HTML input
    │
    ├─► parse_financial_tables()   ← primary: reads table structure
    │       fills `found` dict
    │
    └─► if still missing metrics:
            html_to_clean_text()   ← converts HTML to readable prose
            parse_metrics()        ← runs regex patterns on that prose
            fills gaps in `found`
"""



EPS_PRIORITY = {
    "diluted net income per share":  3,
    "net income per diluted share":  3,
    "diluted earnings per share":    3,
    "earnings per diluted share":    3,
    "basic net income per share":    1,
    "basic earnings per share":      1,
    "earnings per share":            1,
}

def parse_financial_tables(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    eps_best_priority = -1  # track the best EPS row seen so far

    for table in soup.find_all("table"):
        table_scale = extract_scale_from_tag(table)

        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            label_cell = cells[0].lower().strip().rstrip(':')
            canonical = LABEL_MAP.get(label_cell)
            if not canonical:
                continue

            # EPS priority filter: skip if we already have a better row
            if canonical == "eps":
                priority = EPS_PRIORITY.get(label_cell, 0)
                # print(f"EPS candidate: label_cell={label_cell!r} priority={priority}")
                if priority <= eps_best_priority:
                    continue
            
            for cell in cells[1:]:
                cleaned, is_neg = clean_cell(cell)
                try:
                    value = float(cleaned)
                    if is_neg:
                        value = -value

                    if "margin" in canonical:
                        unit = "percent"
                    elif canonical == "eps":
                        unit = "EPS_usd"
                        eps_best_priority = EPS_PRIORITY.get(label_cell, 0)
                        # print(f"EPS accepted: {label_cell!r} = {value}")
                    else:
                        value = value * table_scale
                        unit = "USD_units"

                    # remove any previous eps row if this one is better
                    if canonical == "eps":
                        rows = [r for r in rows if r["label"] != "eps"]

                    rows.append({
                        "label": canonical,
                        "value": round(value, 4),
                        "unit": unit,
                        "raw": cell,
                    })
                    break
                except ValueError:
                    continue

    return rows


def html_to_clean_text(html: str) -> str:
    # convert html to text
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "header", "footer", "nav"]):
        tag.decompose()
    for tag in soup.find_all(["td", "th"]):
        tag.insert_after(" | ")
    for tag in soup.find_all("tr"):
        tag.insert_after("\n")
    text = soup.get_text(separator=" ")
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


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
                unit = "percent" if "margin" in label else "USD_units"
                results.append(Metric(label=label, value=value, unit=unit, raw=match.group(0)))
            except Exception as e:
                print(f"skipped match for '{label}': {e}")
    return results


def parse_metrics_from_html(html: str) -> list[Metric]:
    found: dict[str, Metric] = {}

    # prioritize table parsing
    for row in parse_financial_tables(html):
        label = row["label"]
        if label not in found:
            try:
                found[label] = Metric(**row)
            except Exception as e:
                print(f"skipped table row for '{label}': {e}")

    # parse text if label is missing
    if len(found) < len(PATTERNS):
        clean_text = html_to_clean_text(html)
        for m in parse_metrics(clean_text):
            if m.label not in found:
                found[m.label] = m

    return list(found.values())


# ---------- Fix 4: updated __main__ ----------

if __name__ == "__main__":
    path = Path("10-K/AMAT/0000006951-21-000043/full-submission.txt")

    if not path.exists():
        print(f"file not found: {path}")
    else:
        # Read as plain text -- BeautifulSoup handles HTML regardless of file extension
        html = path.read_text(encoding="utf-8", errors="replace")
        print(f"loaded {len(html):,} characters")

        metrics = parse_metrics_from_html(html)
        print(f"found {len(metrics)} metrics\n")

        for m in metrics:
            print(m.to_agent_dict())
