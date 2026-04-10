import math
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator
from metric_parser import Metric

# ---------- unit normalization ----------

UNIT_MULTIPLIER = {
    "USD_billion":  1_000_000_000,
    "USD_million":  1_000_000,
    "USD_thousand": 1_000,
    "USD_units":    1,
}


def to_absolute(value: float, unit: str) -> float:
    """Convert a stored metric value to absolute dollars."""
    multiplier = UNIT_MULTIPLIER.get(unit, 1)
    return value * multiplier


# ---------- models ----------

class MarketInputs(BaseModel):
    """External inputs not available in the 10-K."""
    price: float = 0.0
    shares_outstanding: float = 0.0

    @field_validator("price", "shares_outstanding")
    @classmethod
    def must_be_non_negative(cls, v):  # was must_be_positive
        if v < 0:
            raise ValueError(f"must be non-negative, got {v}")
        return v

    @property
    def market_cap(self) -> float:
        return self.price * self.shares_outstanding

    @property
    def has_market_data(self) -> bool:
        return self.price > 0 and self.shares_outstanding > 0


class RatioResult(BaseModel):
    label: str
    value: float
    formula: str
    inputs: dict

    @field_validator("value")
    @classmethod
    def must_be_finite(cls, v):
        if not math.isfinite(v):
            raise ValueError(f"ratio must be finite, got {v}")
        return round(v, 4)


class CalculatorInputs(BaseModel):
    """Validates the full set of inputs before any calculation runs."""
    metrics: list[Metric]
    market: MarketInputs

    @model_validator(mode="after")
    def must_have_at_least_one_metric(self):
        if not self.metrics:
            raise ValueError("metrics list is empty -- run the parser first")
        return self

    def get(self, label: str) -> Optional[tuple[float, str]]:
        """
        Returns (absolute_value, unit) for a label, or None if not found.
        Handles unit normalization so all values are in absolute dollars.
        """
        for m in self.metrics:
            if m.label == label:
                # percentages and EPS are already in natural units, don't scale
                if m.unit in ("percent", "EPS_usd"):
                    return m.value, m.unit
                return to_absolute(m.value, m.unit), m.unit
        return None


# ---------- calculator ----------

class FinancialCalculator:
    def __init__(self, inputs: CalculatorInputs):
        self.inputs = inputs
        self.market = inputs.market
        self.results: list[RatioResult] = []

    def _record(self, label: str, value: float, formula: str, raw_inputs: dict):
        """Validate and store a ratio result. Skips silently if invalid."""
        try:
            result = RatioResult(label=label, value=value, formula=formula, inputs=raw_inputs)
            self.results.append(result)
        except Exception as e:
            print(f"skipped '{label}': {e}")

    def _get(self, label: str) -> Optional[float]:
        """Get absolute value for a metric, or None if missing."""
        result = self.inputs.get(label)
        if result is None:
            print(f"missing metric '{label}' -- skipping dependent ratios")
            return None
        return result[0]

    # ---------- ratio methods ----------

    def pe_ratio(self):
        if not self.market.has_market_data:
            # print("pe_ratio skipped: no market data")
            return
        eps = self._get("eps")
        # print(f"pe_ratio: price={self.market.price} eps={eps}")
        if eps is None or eps == 0:
            return
        self._record(
            label="pe_ratio",
            value=self.market.price / eps,
            formula="price / eps",
            raw_inputs={"price": self.market.price, "eps": eps},
        )

    def ps_ratio(self):
        if not self.market.has_market_data:
            return
        revenue = self._get("revenue")
        if revenue is None or revenue == 0:
            return
        self._record(
            label="ps_ratio",
            value=self.market.market_cap / revenue,
            formula="market_cap / revenue",
            raw_inputs={"market_cap": self.market.market_cap, "revenue": revenue},
        )

    def ev_ebitda(self):
        if not self.market.has_market_data:
            return
        ebitda = self._get("ebitda")
        if ebitda is None or ebitda == 0:
            return
        self._record(
            label="ev_ebitda",
            value=self.market.market_cap / ebitda,
            formula="market_cap / ebitda (simplified)",
            raw_inputs={"market_cap": self.market.market_cap, "ebitda": ebitda},
        )

    def earnings_yield(self):
        if not self.market.has_market_data:
            return
        eps = self._get("eps")
        if eps is None:
            return
        self._record(
            label="earnings_yield",
            value=(eps / self.market.price) * 100,
            formula="(eps / price) * 100",
            raw_inputs={"eps": eps, "price": self.market.price},
        )

    def net_margin(self):
        revenue = self._get("revenue")
        net_income = self._get("net_income")
        if revenue is None or net_income is None or revenue == 0:
            # print(f"net_margin skipped: revenue={revenue} net_income={net_income}")
            return
        # print(f"net_margin computing: {net_income} / {revenue}")
        self._record(
            label="net_margin",
            value=(net_income / revenue) * 100,
            formula="(net_income / revenue) * 100",
            raw_inputs={"net_income": net_income, "revenue": revenue},
        )

    def gross_margin(self):
        """Gross margin is already extracted as a percent -- just pass it through."""
        gm = self._get("gross_margin")
        if gm is None:
            return
        self._record(
            label="gross_margin",
            value=gm,
            formula="extracted directly from filing",
            raw_inputs={"gross_margin": gm},
        )

    def op_margin(self):
        """Same as gross margin -- already a percent in the filing."""
        om = self._get("op_margin")
        if om is None:
            return
        self._record(
            label="op_margin",
            value=om,
            formula="extracted directly from filing",
            raw_inputs={"op_margin": om},
        )



    def run_all(self) -> list[RatioResult]:
        self.pe_ratio()
        self.ps_ratio()
        self.ev_ebitda()
        self.net_margin()
        self.gross_margin()
        self.op_margin()
        self.earnings_yield()
        return self.results


# ---------- main ----------

if __name__ == "__main__":
    from pathlib import Path
    from metric_parser import parse_metrics_from_html

    html = Path("10-K/AMAT/0000006951-21-000043/full-submission.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    metrics = parse_metrics_from_html(html)

    try:
        inputs = CalculatorInputs(
            metrics=metrics,
            market=MarketInputs(
                price=134.0,
                shares_outstanding=876_000_000,
            ),
        )
    except Exception as e:
        print(f"input validation failed: {e}")
        exit(1)

    calc = FinancialCalculator(inputs)
    ratios = calc.run_all()

    print(f"\ncomputed {len(ratios)} ratios\n")
    for r in ratios:
        print(f"{r.label:20} {r.value:>10.4f}   ({r.formula})")