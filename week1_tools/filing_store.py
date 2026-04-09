# filing_store.py
from pathlib import Path

FILINGS_ROOT = Path("10-K")

def get_filing_path(ticker: str, year: int) -> Path | None:
    """
    Scans 10-K/{ticker}/ for a folder whose accession number contains the year,
    and returns the path to full-submission.txt inside it.
    
    Folder structure expected:
        10-K/AMAT/0000006951-21-000043/full-submission.txt
    """
    ticker = ticker.upper()
    ticker_dir = FILINGS_ROOT / ticker

    if not ticker_dir.exists():
        return None

    # accession numbers encode the year as 2 digits e.g. "-21-" for 2021
    year_suffix = str(year)[2:]  # 2021 -> "21"

    for accession_dir in ticker_dir.iterdir():
        if not accession_dir.is_dir():
            continue
        if f"-{year_suffix}-" in accession_dir.name:
            candidate = accession_dir / "full-submission.txt"
            if candidate.exists():
                return candidate

    return None


def list_available_filings() -> list[dict]:
    """Returns all filings currently on disk -- useful for debugging."""
    filings = []
    if not FILINGS_ROOT.exists():
        return filings

    for ticker_dir in FILINGS_ROOT.iterdir():
        if not ticker_dir.is_dir():
            continue
        for accession_dir in ticker_dir.iterdir():
            candidate = accession_dir / "full-submission.txt"
            if candidate.exists():
                filings.append({
                    "ticker": ticker_dir.name,
                    "accession": accession_dir.name,
                    "path": str(candidate)
                })

    return filings


if __name__ == "__main__":
    for f in list_available_filings():
        print(f)