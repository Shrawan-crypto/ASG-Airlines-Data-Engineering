"""
cleaning.py
-----------

Strategy: repair over deletion where the intended value can be reasonably
inferred (overnight timestamps, blank airline names); delete only when a
record is structurally unusable (missing keys, orphaned foreign keys,
unparseable amounts). Every function returns the cleaned DataFrame and logs
what it changed, so cleaning is auditable from the pipeline run log.
"""

import logging
import re
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FLIGHT_ID_PATTERN = re.compile(r"^[A-Z0-9]{2,3}\d{2,4}$")
VALID_BOOKING_STATUSES = {"CONFIRMED", "CANCELLED", "PENDING"}


def clean_flights(flights: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the flights table.

    - Standardize flight_id casing/whitespace; validate against carrier-code pattern.
    - Drop exact duplicate rows, then drop residual duplicate flight_id rows (keep first).
    - Standardize airline: blank / 'UNKNOWN' (any case) -> 'Unknown'.
    - Uppercase source/destination; drop impossible routes (source == destination).
    - Parse timestamps; drop rows where either timestamp fails to parse.

    Overnight-flight repair and duration calculation are handled separately in
    transformation.py, since they depend on the fully-cleaned timestamp columns.
    """
    f = flights.copy()
    f.columns = [c.strip().lower() for c in f.columns]

    f["flight_id"] = f["flight_id"].astype(str).str.strip().str.upper()
    invalid_id_count = (~f["flight_id"].apply(lambda x: bool(FLIGHT_ID_PATTERN.match(x)))).sum()
    logger.info("Flight IDs not matching expected carrier-code pattern: %d", invalid_id_count)

    before = len(f)
    f = f.drop_duplicates()
    logger.info("Exact duplicate flight rows dropped: %d", before - len(f))

    dup_mask = f.duplicated(subset="flight_id", keep="first")
    logger.info("Residual duplicate flight_id rows dropped (kept first): %d", dup_mask.sum())
    f = f[~dup_mask]

    f["airline"] = f["airline"].astype(str).str.strip()
    f.loc[f["airline"].isin(["nan", "", "None"]), "airline"] = np.nan
    f["airline"] = f["airline"].fillna("Unknown")
    f.loc[f["airline"].str.upper() == "UNKNOWN", "airline"] = "Unknown"

    f["source"] = f["source"].astype(str).str.strip().str.upper()
    f["destination"] = f["destination"].astype(str).str.strip().str.upper()
    before = len(f)
    f = f[f["source"] != f["destination"]]
    logger.info("Impossible routes (source == destination) dropped: %d", before - len(f))

    f["departure_time"] = pd.to_datetime(f["departure_time"], errors="coerce")
    f["arrival_time"] = pd.to_datetime(f["arrival_time"], errors="coerce")
    before = len(f)
    f = f.dropna(subset=["departure_time", "arrival_time"])
    logger.info("Rows dropped for unparseable timestamps: %d", before - len(f))

    # The source 'duration' column is a pre-computed Excel formula that may
    # have been calculated before an overnight repair (and could be wrong or
    # negative). It is dropped here; transformation.py recomputes an
    # authoritative duration_minutes from the repaired timestamps instead.
    if "duration" in f.columns:
        f = f.drop(columns=["duration"])

    return f.reset_index(drop=True)


def clean_passengers(passengers: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the passengers table.

    - De-duplicate on passenger_id (keep first).
    - Title-case names; lower-case email; upper-case gender.
    - Null out biologically implausible ages (<0 or >110).
    """
    p = passengers.copy()
    p.columns = [c.strip().lower() for c in p.columns]

    before = len(p)
    p = p.drop_duplicates(subset="passenger_id")
    logger.info("Duplicate passenger_id rows dropped: %d", before - len(p))

    p["first_name"] = p["first_name"].astype(str).str.strip().str.title()
    p["last_name"] = p["last_name"].fillna("").astype(str).str.strip().str.title()
    p["email"] = p["email"].astype(str).str.strip().str.lower()
    p["gender"] = p["gender"].astype(str).str.strip().str.upper()

    bad_age = (p["age"] < 0) | (p["age"] > 110)
    p.loc[bad_age, "age"] = np.nan
    logger.info("Passenger ages outside 0-110 set to null: %d", bad_age.sum())

    return p.reset_index(drop=True)


def clean_bookings(bookings: pd.DataFrame, valid_flight_ids: set) -> pd.DataFrame:
    """
    Clean the bookings table.

    - Drop rows missing booking_id, passenger_id, or flight_id.
    - Drop bookings referencing a flight_id absent from the cleaned flights table (orphan FK).
    - Standardize status to CONFIRMED / CANCELLED / PENDING; anything else -> 'UNKNOWN'.

    Parameters
    ----------
    valid_flight_ids : set
        The set of flight_id values remaining after clean_flights() has run.
    """
    b = bookings.copy()
    b.columns = [c.strip().lower() for c in b.columns]

    before = len(b)
    b = b.dropna(subset=["booking_id", "passenger_id", "flight_id"])
    logger.info("Bookings dropped for missing key fields: %d", before - len(b))

    orphan_mask = ~b["flight_id"].isin(valid_flight_ids)
    logger.info("Orphan bookings (flight_id not in cleaned flights): %d", orphan_mask.sum())
    b = b[~orphan_mask]

    b["status"] = b["status"].astype(str).str.strip().str.upper()
    b.loc[~b["status"].isin(VALID_BOOKING_STATUSES), "status"] = "UNKNOWN"

    return b.reset_index(drop=True)


def clean_payments(payments: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the payments table.

    - Coerce amount to numeric (some values arrive as text).
    - Drop rows with a missing/unparseable/non-positive amount.
    """
    pay = payments.copy()
    pay.columns = [c.strip().lower() for c in pay.columns]

    before = len(pay)
    pay["amount"] = pd.to_numeric(pay["amount"], errors="coerce")
    pay = pay.dropna(subset=["payment_id", "booking_id", "amount"])
    pay = pay[pay["amount"] > 0]
    logger.info("Payments dropped for missing/invalid amount: %d", before - len(pay))

    return pay.reset_index(drop=True)
