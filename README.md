# Aakash Daily - Monday view (analytics assignment, Part 2)

Tested on Python 3.12. Needs Python 3.11+.

## Run it
```bash
pip install -r requirements.txt
python -m streamlit run app.py   # interactive dashboard (opens at http://localhost:8501)
python make_report.py            # rewrites dashboard.pdf / dashboard.png (static copy of the Overview page)
python verify_numbers.py         # re-computes the headline numbers in SQL and compares (all should PASS)
```
The three CSVs are in `data/` (students.csv, events.csv, campaigns.csv, unchanged).

## Files
| File | What it is |
|---|---|
| `app.py` | Streamlit dashboard: Overview (what a product head reads on Monday), Acquisition and channels, Engagement and retention, Definitions and assumptions |
| `metrics.py` | The only place metrics are computed. `app.py`, `make_report.py` and `verify_numbers.py` all use it |
| `make_report.py` | Draws the Overview page as a static PDF and PNG |
| `verify_numbers.py` | Independent SQL (sqlite) re-computation of 19 headline numbers (incl. partial weeks, per-channel cost, funnel) plus the campaigns-vs-students reconciliation: 20 checks |
| `dashboard.pdf` | 2 pages: the Overview (main page) and Engagement and retention (funnel, retention by source, test starts, hour of day) |
| `dashboard.png` / `dashboard_page2.png` | The same two pages as images |

## Filters
Date range, source, class, stream, platform, city tier. Spend is only known per channel and day, so cost
metrics switch off when a class, stream, platform or tier filter is on. The "What I see" box always uses the
full data.
