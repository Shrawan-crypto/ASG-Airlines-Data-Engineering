"""
ingestion.py
------------

In production this would be swapped for a connector to the real booking
platform / scheduling system / airport log feeds (or, on Azure, an ADF copy
activity landing the same sheets into a raw/staging zone). The function
signatures are deliberately narrow (path in, DataFrame out) so that swap is a
one-file change.
"""

import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

SHEET_NAMES = ["flights", "bookings", "payments", "passengers"]


def load_source_workbook(path: str | Path) -> dict[str, pd.DataFrame]:
    """
    Load every required sheet from the raw ASG Airlines workbook.

    Parameters
    ----------
    path : str | Path
        Path to the raw .xlsx file (expected at data/raw/).

    Returns
    -------
    dict[str, pd.DataFrame]
        Keys: "flights", "bookings", "payments", "passengers".

    Raises
    ------
    FileNotFoundError
        If the workbook does not exist.
    ValueError
        If any expected sheet is missing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Raw source workbook not found at {path}")

    xls = pd.ExcelFile(path)
    missing = [s for s in SHEET_NAMES if s not in xls.sheet_names]
    if missing:
        raise ValueError(f"Source workbook is missing expected sheet(s): {missing}")

    data = {}
    for sheet in SHEET_NAMES:
        df = pd.read_excel(xls, sheet_name=sheet)
        df.columns = [c.strip().lower() for c in df.columns]
        data[sheet] = df
        logger.info("Loaded sheet '%s' with %d rows, %d columns", sheet, *df.shape)

    return data


def save_raw_snapshot(data: dict[str, pd.DataFrame], out_dir: str | Path) -> None:
    """Persist an as-ingested copy of each sheet to data/raw/ as CSV (audit trail)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in data.items():
        df.to_csv(out_dir / f"raw_{name}.csv", index=False)
        logger.info("Snapshotted raw '%s' -> %s", name, out_dir / f"raw_{name}.csv")
