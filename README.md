# ASG Airlines — Data Engineering Case Study

End-to-end pipeline that ingests ASG Airlines' raw flight, booking, payment, and
passenger data; cleans and standardizes it; masks passenger PII; calculates
operational KPIs; and powers a 5-page Power BI dashboard.

## Repository Structure

```
ASG-Airlines-Data-Engineering/
├── README.md
├── requirements.txt
├── .gitignore
├── data/
│   ├── raw/                     Source workbook (as received)
│   └── processed/                cleaned_flights.csv, cleaned_bookings.csv,
│                                 cleaned_payments.csv, cleaned_passengers.csv
├── notebooks/
│   └── airline_data_pipeline.ipynb   Orchestrates src/ end-to-end, with markdown
├── src/
│   ├── ingestion.py               Load raw sheets
│   ├── cleaning.py                Per-table cleaning rules
│   ├── transformation.py          Overnight/duration, anomalies, PII masking, KPIs
│   └── validation.py              Pre- and post-clean data quality checks
├── powerbi/
│   └── ASG_Airlines_Dashboard.pbix   5-page interactive dashboard
├── docs/
│   ├── Project_Documentation.docx    Full write-up: dataset, architecture,
│   │                                 assumptions, cleaning logic, KPIs, dashboard, privacy
│   ├── architecture.png
│   ├── data_flow.png
│   └── data_model.png
└── screenshots/                  Preview of each dashboard page
    ├── dashboard_overview.png
    ├── duration_analysis.png
    ├── route_analysis.png
    └── anomaly_analysis.png
```

## Pipeline

Business logic lives in `src/` — not just inside the notebook — so it's
unit-testable and reusable outside a notebook context (e.g. as an Azure
Databricks job):

| Module | Responsibility |
|---|---|
| `ingestion.py` | Load the 4 raw sheets from the source workbook |
| `cleaning.py` | Per-table cleaning: dedup, standardize, drop orphans |
| `transformation.py` | Overnight-flight repair, duration calc, route-level anomaly detection, PII masking, KPI aggregation |
| `validation.py` | Data-quality profiling (pre-clean) and referential-integrity checks (post-clean) |

`notebooks/airline_data_pipeline.ipynb` orchestrates these modules end to end
and has already been run — `data/processed/*.csv` reflects its output.

**Result:** 1,020 raw flight records → 1,004 cleaned; 1,039 raw passengers →
1,000 cleaned; 1,000 bookings → 1,000 (12 dropped for missing keys, replaced
by the pre-clean total); 1,000 payments → 922 with a valid amount. All
passenger PII (email, phone, Aadhaar ID, passport number, emergency contact
phone) is masked or one-way hashed before reaching `data/processed/` — see
`src/transformation.py` and Section 6.4 / 8 of the documentation.

## KPIs Delivered

| KPI | Result |
|---|---|
| Average Flight Duration | 164.8 minutes |
| Busiest Route | BOM → CCU (90 flights) |
| Overnight Flights | 122 of 1,004 |
| Route-Level Duration Anomalies | 1 flight |
| Flights by Airline | IndiGo 249 · SpiceJet 236 · Air India 233 · Vistara 218 · Unknown 68 |
| Booking Status Distribution | Confirmed 320 · Cancelled 314 · Pending 291 · Unknown 75 |

## Power BI Dashboard

`powerbi/ASG_Airlines_Dashboard.pbix` — 5 pages, all filterable by Airline,
Origin, Destination, and Booking Status:

| Page | Highlights |
|---|---|
| **Executive Overview** | Total Bookings/Flights, Avg Duration, Total Revenue cards; duration distribution; flights by airline & source airport |
| **Duration Analysis** | Min/Avg/Max duration cards; duration-by-category and by-airline breakdowns; overnight split; route-level anomaly chart |
| **Route Performance** | Flights & bookings by route; average duration by route; Top Route card (DAX measure) |
| **Airline Trends** | Flights/bookings/duration by airline; booking status mix |
| **Delay & Anomaly Insights** | Anomaly and overnight flags, cross-checked against the two donut charts on the same page |

Previews of all 5 pages are in `screenshots/`. Full visual-by-visual
breakdown, the calculated columns (`Route`, `Duration Category`) and the one
DAX measure (`Top Route`) are documented in Section 10 of
`docs/Project_Documentation.docx`, along with an implementation note on the
Delay & Anomaly Insights page: two cards and one chart there currently
aggregate via `CountNonNull()` with no `TRUE`-only filter, so they display
the total flight count rather than the anomaly-only subset — the two donut
charts on the same page compute the correct, authoritative figures (1
anomalous flight, 122 overnight flights). Section 10.3 documents this in
full, including the equivalent corrected DAX.

## Privacy

Raw PII never reaches `data/processed/` or the dashboard — only masked
emails/phones and SHA-256 hashes of Aadhaar/passport numbers do. Recommended
production access-control model (raw-zone RBAC, Azure AD groups, RLS) is in
Section 8 of the documentation.

## Reproducing the Pipeline

```bash
pip install -r requirements.txt
jupyter nbconvert --to notebook --execute notebooks/airline_data_pipeline.ipynb
```

This re-runs ingestion → validation → cleaning → transformation → validation
→ export against `data/raw/UseCase_-_Airlines.xlsx`, regenerating
`data/processed/*.csv` with a full audit log of what was dropped or repaired
at each stage. Reopen `powerbi/ASG_Airlines_Dashboard.pbix` and hit
**Refresh** to pull in updated data.
