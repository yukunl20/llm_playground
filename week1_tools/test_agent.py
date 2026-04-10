from pydantic import BaseModel, Field, model_validator
from typing import Any, Literal
import logging
from agent import run_agent
import json

logging.basicConfig(
    filename="agent_failures.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

CheckKey = Literal["answer", "confidence", "caveats", "value"]

class TestCase(BaseModel):
    question: str
    expected: Any
    check_key: CheckKey
    tolerance: float = Field(default=0.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def tolerance_only_for_numeric(self) -> "TestCase":
        if self.tolerance > 0 and not isinstance(self.expected, (int, float)):
            raise ValueError(
                f"tolerance={self.tolerance} set but expected is {type(self.expected).__name__}, "
                "tolerance only applies to numeric expected values"
            )
        return self
    


TEST_CASES = [
    # --- direct metric retrieval ---
    TestCase(
        question="What was LRCX's total revenue in 2023?",
        expected=17428516000,
        check_key="value",
        tolerance=0.01,
        tags=["revenue", "direct"]
    ),
    TestCase(
        question="What was LRCX's net income in 2023?",
        expected=4488029000,
        check_key="value",
        tolerance=0.01,
        tags=["net_income", "direct"]
    ),
    TestCase(
        question="What was LRCX's EPS in 2023?",
        expected=33.00,
        check_key="value",
        tolerance=0.02,
        tags=["eps", "direct"]
    ),
    TestCase(
        question="What was AMAT's total revenue in 2023?",
        expected=26517000000,
        check_key="value",
        tolerance=0.01,
        tags=["revenue", "direct"]
    ),
    TestCase(
        question="What was AMAT's net income in 2023?",
        expected=6856000000,
        check_key="value",
        tolerance=0.01,
        tags=["net_income", "direct"]
    ),
    TestCase(
        question="What was AMAT's EPS in 2023?",
        expected=8.11,
        check_key="value",
        tolerance=0.02,
        tags=["eps", "direct"]
    ),

    # --- year over year ---
    TestCase(
        question="Did LRCX's revenue grow or decline from 2022 to 2023?",
        expected="grow",
        check_key="answer",
        tags=["yoy", "direction"]
    ),
    TestCase(
        question="Did AMAT's revenue grow or decline from 2022 to 2023?",
        expected="grow",
        check_key="answer",
        tags=["yoy", "direction"]
    ),

    # --- calculated ratios ---
    TestCase(
        question="What is AMAT's P/E ratio given a price of $415 and 7.43 billion shares in 2023?",
        expected=51.17,
        check_key="value",
        tolerance=0.03,
        tags=["ratio", "calculated"]
    ),
    TestCase(
        question="What is LRCX's P/E ratio given a price of $750 and 136 million shares in 2023?",
        expected=22.73,
        check_key="value",
        tolerance=0.03,
        tags=["ratio", "calculated"]
    ),
    TestCase(
        question="What is AMAT's net profit margin in 2023?",
        expected=25.8,
        check_key="value",
        tolerance=0.03,
        tags=["margin", "calculated"]
    ),
    TestCase(
        question="What is LRCX's net profit margin in 2023?",
        expected=25.7,
        check_key="value",
        tolerance=0.03,
        tags=["margin", "calculated"]
    ),

    # --- confidence signal ---
    TestCase(
        question="What was AMAT's EBITDA in 2023?",
        expected="low",
        check_key="confidence",
        tags=["ebitda", "confidence"]
    ),

    # --- graceful failure ---
    TestCase(
        question="What was LRCX's revenue in 2019?",
        expected="insufficient",
        check_key="answer",
        tags=["missing_data", "failure_mode"]
    ),
    TestCase(
        question="What was LRCX's revenue in Q3 2023?",
        expected="insufficient",
        check_key="answer",
        tags=["quarterly", "failure_mode"]
    ),
]


def extract_check_value(result: dict, check_key: str) -> Any:
    if check_key in ("answer", "confidence", "caveats"):
        return result[check_key]
    if check_key == "value":
        # prefer ratio evidence over raw metric evidence
        for item in result["evidence"]:
            if item.get("metric_name") in ("net_margin", "pe_ratio", "ps_ratio",
                                            "gross_margin", "op_margin"):
                return item["value"]
        # fall back to first evidence item
        if result["evidence"]:
            return result["evidence"][0]["value"]
    return None


def check_pass(actual: Any, expected: Any, tolerance: float) -> bool:
    if isinstance(expected, (float, int)):
        if actual is None:
            return False
        return abs(actual - expected) / expected <= tolerance
    if isinstance(expected, str):
        synonyms = {
            "insufficient": [
                "insufficient",
                "not available",
                "unable to provide",
                "no filing",
                "not found",
                "don't have",
                "do not have",
            ],
            "grow":    ["grow", "grew", "increase", "increased", "higher", "rose"],
            "decline": ["decline", "declined", "decrease", "decreased", "lower", "fell"],
        }
        targets = synonyms.get(expected.lower(), [expected.lower()])
        return any(t in str(actual).lower() for t in targets)
    return actual == expected


def run_tests():
    passed = 0
    failed = 0
    failures = []

    for i, tc in enumerate(TEST_CASES):
        print(f"\n[{i+1}/{len(TEST_CASES)}] {tc.question}")
        try:
            result = run_agent(tc.question)
            actual = extract_check_value(result, tc.check_key)
            ok = check_pass(actual, tc.expected, tc.tolerance)

            if ok:
                passed += 1
                print(f"  PASS | expected={tc.expected} actual={actual}")
            else:
                failed += 1
                failure = {
                    "question": tc.question,
                    "tags": tc.tags,
                    "expected": tc.expected,
                    "actual": actual,
                    "full_response": result
                }
                failures.append(failure)
                print(f"  FAIL | expected={tc.expected} actual={actual}")
                logging.info(f"FAIL | {json.dumps(failure, indent=2)}")

        except Exception as e:
            failed += 1
            failure = {
                "question": tc.question,
                "tags": tc.tags,
                "expected": tc.expected,
                "actual": None,
                "error": str(e)
            }
            failures.append(failure)
            print(f"  ERROR | {e}")
            logging.error(f"ERROR | {json.dumps(failure, indent=2)}")

    # summary
    print(f"\n{'='*40}")
    print(f"Results: {passed}/{len(TEST_CASES)} passed")
    print(f"Failed:  {failed}/{len(TEST_CASES)}")

    if failures:
        print("\nFailure breakdown by tag:")
        tag_counts: dict[str, int] = {}
        for f in failures:
            for tag in (f.get("tags") or []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
            print(f"  {tag}: {count}")

    return passed, failed, failures


if __name__ == "__main__":
    run_tests()