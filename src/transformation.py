"""
transformation.py
------------------
"""

import hashlib
import logging
import re
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Duration & overnight-flight handling
# ---------------------------------------------------------------------------

def repair_overnight_and_compute_duration(flights: pd.DataFrame) -> pd.DataFrame:
    """
    Repair broken overnight records and compute an authoritative duration.

    Two distinct concepts are handled:

    1. Data-quality repair: if arrival_time <= departure_time, the record's
       date did not roll over correctly for a flight that actually crosses
       midnight. The arrival date is advanced by one day before duration is
       calculated.
    2. Operational flag (is_overnight): True whenever departure and arrival
       fall on different calendar dates, regardless of whether a repair was
       needed. This is a genuine attribute of the flight, not an error.

    duration_minutes is always recomputed as
    (arrival_time - departure_time).total_seconds() / 60 from the *repaired*
    timestamps — any pre-existing 'duration' column in the source is ignored,
    since it may have been computed before repair and would then be wrong.
    """
    f = flights.copy()

    broken_mask = f["arrival_time"] <= f["departure_time"]
    logger.info("Broken overnight records repaired (arrival <= departure): %d", broken_mask.sum())
    f.loc[broken_mask, "arrival_time"] = f.loc[broken_mask, "arrival_time"] + pd.Timedelta(days=1)

    f["duration_minutes"] = (f["arrival_time"] - f["departure_time"]).dt.total_seconds() / 60
    f["is_overnight"] = f["departure_time"].dt.date != f["arrival_time"].dt.date

    before = len(f)
    f = f[f["duration_minutes"] > 0]
    logger.info("Unrecoverable non-positive-duration rows dropped: %d", before - len(f))
    logger.info("Genuine overnight (cross-midnight) flights: %d", f["is_overnight"].sum())

    return f.reset_index(drop=True)


def flag_route_duration_anomalies(flights: pd.DataFrame, min_route_flights: int = 3, z: float = 2.0) -> pd.DataFrame:
    """
    Flag flights whose duration deviates more than `z` standard deviations
    from their own route's (source -> destination) mean duration.

    The dataset has no separate 'scheduled time' field, so actual-vs-scheduled
    delay can't be computed directly. This route-relative statistical outlier
    is used as a practical substitute for 'delay / anomaly' reporting, and
    adapts to each route's typical flight time rather than one fixed
    threshold across very different route lengths. Routes with fewer than
    `min_route_flights` flights are not judged (too little data).
    """
    f = flights.copy()
    route_stats = (
        f.groupby(["source", "destination"])["duration_minutes"]
         .agg(["mean", "std", "count"])
         .reset_index()
         .rename(columns={"mean": "route_mean_duration", "std": "route_std_duration", "count": "route_flight_count"})
    )
    f = f.merge(route_stats, on=["source", "destination"], how="left")
    f["anomaly_duration_outlier"] = (
        (f["route_flight_count"] >= min_route_flights) &
        (f["route_std_duration"] > 0) &
        ((f["duration_minutes"] - f["route_mean_duration"]).abs() > z * f["route_std_duration"])
    )
    logger.info("Route-level duration anomalies flagged: %d", f["anomaly_duration_outlier"].sum())
    return f.drop(columns=["route_mean_duration", "route_std_duration", "route_flight_count"])


# ---------------------------------------------------------------------------
# PII masking
# ---------------------------------------------------------------------------

def mask_email(val) -> str | None:
    """Partial mask: first char + asterisks + @domain (e.g. 'j***@gmail.com')."""
    if pd.isna(val):
        return None
    parts = str(val).split("@")
    if len(parts) != 2:
        return "***"
    user, domain = parts
    return user[0] + "*" * max(len(user) - 1, 1) + "@" + domain


def mask_phone(val) -> str | None:
    """Partial mask: all but the last 4 digits replaced with '*'."""
    if pd.isna(val):
        return None
    return re.sub(r"\d(?=\d{4})", "*", str(val))


def sha256_short(val, length: int = 16) -> str | None:
    """One-way SHA-256 hash (truncated), used for government ID numbers with no reporting use."""
    if pd.isna(val) or str(val).strip() == "":
        return None
    return hashlib.sha256(str(val).strip().encode()).hexdigest()[:length]


def mask_passenger_pii(passengers: pd.DataFrame) -> pd.DataFrame:
    """
    Mask/hash passenger PII and drop the raw columns.

    email     -> email_masked   (partial mask)
    phone     -> phone_masked   (partial mask)
    aadhaar_id -> aadhaar_hash  (SHA-256, irreversible)
    """
    p = passengers.copy()
    p["email_masked"] = p["email"].apply(mask_email)
    p["phone_masked"] = p["phone"].apply(mask_phone)
    p["aadhaar_hash"] = p["aadhaar_id"].apply(sha256_short)
    return p.drop(columns=["email", "phone", "aadhaar_id"])


def mask_booking_pii(bookings: pd.DataFrame) -> pd.DataFrame:
    """
    Mask/hash booking-level PII and drop the raw columns.

    passport_number        -> passport_hash (SHA-256, irreversible)
    emergency_contact_phone -> emergency_contact_phone_masked (partial mask)
    """
    b = bookings.copy()
    b["passport_hash"] = b["passport_number"].apply(sha256_short)
    b["emergency_contact_phone_masked"] = b["emergency_contact_phone"].apply(mask_phone)
    return b.drop(columns=["passport_number", "emergency_contact_phone"])


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def compute_kpis(flights: pd.DataFrame, bookings: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Compute the business KPIs required by the brief, plus booking status
    distribution as an additional metric.

    Returns a dict of small summary DataFrames, keyed by KPI name.
    """
    avg_duration = pd.DataFrame({
        "metric": ["avg_flight_duration_minutes"],
        "value": [round(flights["duration_minutes"].mean(), 2)],
    })

    route_traffic = (
        flights.groupby(["source", "destination"])
        .size()
        .reset_index(name="flight_count")
        .sort_values("flight_count", ascending=False)
        .reset_index(drop=True)
    )

    airline_distribution = (
        flights.groupby("airline")
        .size()
        .reset_index(name="flight_count")
        .sort_values("flight_count", ascending=False)
        .reset_index(drop=True)
    )

    anomaly_summary = pd.DataFrame({
        "metric": ["overnight_flights", "route_level_duration_outliers"],
        "count": [int(flights["is_overnight"].sum()), int(flights["anomaly_duration_outlier"].sum())],
    })

    booking_status_distribution = (
        bookings.groupby("status").size().reset_index(name="count").sort_values("count", ascending=False)
    )

    return {
        "avg_duration": avg_duration,
        "route_traffic": route_traffic,
        "airline_distribution": airline_distribution,
        "anomaly_summary": anomaly_summary,
        "booking_status_distribution": booking_status_distribution,
    }
