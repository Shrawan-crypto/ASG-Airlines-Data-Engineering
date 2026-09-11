"""
validation.py
--------------
Data quality checks used both before cleaning (to profile the raw data and
decide on cleaning rules) and after cleaning (to make sure the pipeline
actually produced usable, referentially-consistent output before it's handed
to Power BI).
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def profile_raw(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Produce a simple data-quality profile of the raw ingested tables:
    row count, null counts per column, and duplicate row/key counts.

    Returns a tidy DataFrame (one row per table) suitable for logging or
    saving alongside the raw snapshot as an audit record.
    """
    rows = []
    for name, df in data.items():
        rows.append({
            "table": name,
            "row_count": len(df),
            "duplicate_rows": int(df.duplicated().sum()),
            "total_nulls": int(df.isna().sum().sum()),
            "columns_with_nulls": int((df.isna().sum() > 0).sum()),
        })
    profile = pd.DataFrame(rows)
    logger.info("Raw data profile:\n%s", profile.to_string(index=False))
    return profile


def validate_cleaned_flights(flights: pd.DataFrame) -> list[str]:
    """Sanity-check the cleaned flights table. Returns a list of issue descriptions (empty if clean)."""
    issues = []
    if flights["flight_id"].duplicated().any():
        issues.append("Duplicate flight_id values remain after cleaning.")
    if (flights["duration_minutes"] <= 0).any():
        issues.append("Non-positive duration_minutes values remain after cleaning.")
    if flights[["flight_id", "airline", "source", "destination"]].isna().any().any():
        issues.append("Null values remain in required flight identifier/route columns.")
    if (flights["source"] == flights["destination"]).any():
        issues.append("Rows with source == destination remain after cleaning.")
    _log_issues("flights", issues)
    return issues


def validate_cleaned_bookings(bookings: pd.DataFrame, valid_flight_ids: set, valid_passenger_ids: set) -> list[str]:
    """Sanity-check the cleaned bookings table for referential integrity."""
    issues = []
    if bookings[["booking_id", "passenger_id", "flight_id"]].isna().any().any():
        issues.append("Null key values remain in bookings.")
    if bookings["booking_id"].duplicated().any():
        issues.append("Duplicate booking_id values found.")
    orphan_flights = ~bookings["flight_id"].isin(valid_flight_ids)
    if orphan_flights.any():
        issues.append(f"{orphan_flights.sum()} bookings reference a flight_id not present in cleaned flights.")
    orphan_passengers = ~bookings["passenger_id"].isin(valid_passenger_ids)
    if orphan_passengers.any():
        issues.append(f"{orphan_passengers.sum()} bookings reference a passenger_id not present in cleaned passengers.")
    _log_issues("bookings", issues)
    return issues


def validate_cleaned_passengers(passengers: pd.DataFrame) -> list[str]:
    """Sanity-check the cleaned passengers table, including confirming raw PII columns are gone."""
    issues = []
    if passengers["passenger_id"].duplicated().any():
        issues.append("Duplicate passenger_id values remain after cleaning.")
    for raw_pii_col in ("email", "phone", "aadhaar_id"):
        if raw_pii_col in passengers.columns:
            issues.append(f"Raw PII column '{raw_pii_col}' was not dropped after masking.")
    _log_issues("passengers", issues)
    return issues


def validate_cleaned_payments(payments: pd.DataFrame, valid_booking_ids: set) -> list[str]:
    """Sanity-check the cleaned payments table."""
    issues = []
    if (payments["amount"] <= 0).any():
        issues.append("Non-positive payment amounts remain after cleaning.")
    orphan = ~payments["booking_id"].isin(valid_booking_ids)
    if orphan.any():
        issues.append(f"{orphan.sum()} payments reference a booking_id not present in cleaned bookings.")
    _log_issues("payments", issues)
    return issues


def _log_issues(table_name: str, issues: list[str]) -> None:
    if issues:
        for issue in issues:
            logger.warning("[%s] %s", table_name, issue)
    else:
        logger.info("[%s] passed all validation checks.", table_name)
