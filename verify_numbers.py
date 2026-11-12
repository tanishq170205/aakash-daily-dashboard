"""Independent check: re-computes the headline numbers in plain SQL (sqlite) straight from the CSVs
and compares them with metrics.py.  Run:  python verify_numbers.py   (exit code 1 if any check fails)"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

import metrics as M

D = Path(__file__).parent / "data"
con = sqlite3.connect(":memory:")
for name in ("students", "events", "campaigns"):
    pd.read_csv(D / f"{name}.csv", dtype=str).to_sql(name, con, index=False)  # raw strings, no pandas date logic
con.execute("UPDATE campaigns SET spend_inr = CAST(spend_inr AS REAL), installs_attributed = CAST(installs_attributed AS INTEGER)")

LEARN = "('practice_test_submitted','capsule_completed','video_completed')"
LEARNED_IN_7 = f"""EXISTS (SELECT 1 FROM events e WHERE e.student_id = s.student_id AND e.event_name IN {LEARN}
                  AND julianday(substr(e.event_time,1,10)) - julianday(s.install_date) <= 7)"""


def q(sql):
    return con.execute(sql).fetchone()[0]


sql = {}
sql["Weekly Learners, week of 19 Oct"] = q(f"""SELECT COUNT(DISTINCT student_id) FROM events
    WHERE event_name IN {LEARN} AND substr(event_time,1,10) BETWEEN '2026-10-19' AND '2026-10-25'""")
sql["Weekly actives, week of 19 Oct"] = q("""SELECT COUNT(DISTINCT student_id) FROM events
    WHERE substr(event_time,1,10) BETWEEN '2026-10-19' AND '2026-10-25'""")
sql["Weekly Learners, week of 12 Oct"] = q(f"""SELECT COUNT(DISTINCT student_id) FROM events
    WHERE event_name IN {LEARN} AND substr(event_time,1,10) BETWEEN '2026-10-12' AND '2026-10-18'""")
sql["7-day activation, installs 11-24 Oct"] = q(f"""SELECT AVG(CASE WHEN {LEARNED_IN_7} THEN 1.0 ELSE 0 END)
    FROM students s WHERE install_date BETWEEN '2026-10-11' AND '2026-10-24'""")
sql["7-day activation, installs 1 Sep-4 Oct"] = q(f"""SELECT AVG(CASE WHEN {LEARNED_IN_7} THEN 1.0 ELSE 0 END)
    FROM students s WHERE install_date BETWEEN '2026-09-01' AND '2026-10-04'""")
sql["7-day activation, installs 5-24 Oct"] = q(f"""SELECT AVG(CASE WHEN {LEARNED_IN_7} THEN 1.0 ELSE 0 END)
    FROM students s WHERE install_date BETWEEN '2026-10-05' AND '2026-10-24'""")
sql["WhatsApp Rs per activated student"] = q(f"""SELECT
    (SELECT SUM(CAST(spend_inr AS REAL)) FROM campaigns WHERE channel='whatsapp' AND date <= '2026-10-24') /
    (SELECT SUM(CASE WHEN {LEARNED_IN_7} THEN 1 ELSE 0 END) FROM students s
       WHERE source='whatsapp' AND install_date <= '2026-10-24')""")
sql["Paid Rs per activated student"] = q(f"""SELECT
    (SELECT SUM(CAST(spend_inr AS REAL)) FROM campaigns WHERE date <= '2026-10-24') /
    (SELECT SUM(CASE WHEN {LEARNED_IN_7} THEN 1 ELSE 0 END) FROM students s
       WHERE source IN ('whatsapp','branch_link','centre_qr') AND install_date <= '2026-10-24')""")
sql["Day-7 retention, all installs <= 24 Oct"] = q("""SELECT AVG(CASE WHEN EXISTS (SELECT 1 FROM events e
    WHERE e.student_id = s.student_id AND julianday(substr(e.event_time,1,10)) - julianday(s.install_date) = 7)
    THEN 1.0 ELSE 0 END) FROM students s WHERE julianday('2026-10-31') - julianday(install_date) >= 7""")
sql["Test submit rate (all)"] = q("""SELECT 1.0 * SUM(event_name='practice_test_submitted') /
    SUM(event_name='practice_test_created') FROM events""")
sql["Learn capsule completion"] = q("""SELECT 1.0 * SUM(event_name='capsule_completed' AND capsule_type='Learn') /
    SUM(event_name='capsule_started' AND capsule_type='Learn') FROM events""")
sql["Revise capsule completion"] = q("""SELECT 1.0 * SUM(event_name='capsule_completed' AND capsule_type='Revise') /
    SUM(event_name='capsule_started' AND capsule_type='Revise') FROM events""")
sql["Weekly Learners, partial week 26-31 Oct"] = q(f"""SELECT COUNT(DISTINCT student_id) FROM events
    WHERE event_name IN {LEARN} AND substr(event_time,1,10) BETWEEN '2026-10-26' AND '2026-10-31'""")
sql["Weekly Learners, partial week 1-6 Sep"] = q(f"""SELECT COUNT(DISTINCT student_id) FROM events
    WHERE event_name IN {LEARN} AND substr(event_time,1,10) BETWEEN '2026-09-01' AND '2026-09-06'""")
sql["7-day activation, prior window 27 Sep-10 Oct"] = q(f"""SELECT AVG(CASE WHEN {LEARNED_IN_7} THEN 1.0 ELSE 0 END)
    FROM students s WHERE install_date BETWEEN '2026-09-27' AND '2026-10-10'""")
for ch_ in ("branch_link", "centre_qr"):
    sql[f"{ch_} Rs per activated student"] = q(f"""SELECT
        (SELECT SUM(CAST(spend_inr AS REAL)) FROM campaigns WHERE channel='{ch_}' AND date <= '2026-10-24') /
        (SELECT SUM(CASE WHEN {LEARNED_IN_7} THEN 1 ELSE 0 END) FROM students s
           WHERE source='{ch_}' AND install_date <= '2026-10-24')""")
TRIED = "('practice_test_created','capsule_started','video_started','content_viewed','doubt_submitted','practice_test_submitted','capsule_completed','video_completed')"
def funnel_sql(extra):
    return q(f"""SELECT COUNT(*) FROM students s WHERE install_date <= '2026-10-24' AND {extra}""")
EV7 = "julianday(substr(e.event_time,1,10)) - julianday(s.install_date)"
sql["Funnel: started something within 7 days"] = funnel_sql(
    f"EXISTS (SELECT 1 FROM events e WHERE e.student_id=s.student_id AND e.event_name IN {TRIED} AND {EV7} <= 7)")
sql["Funnel: came back on a later day (of activated)"] = funnel_sql(
    f"{LEARNED_IN_7} AND EXISTS (SELECT 1 FROM events e WHERE e.student_id=s.student_id AND {EV7} BETWEEN 1 AND 7)")
reconcile = q("""SELECT COUNT(*) FROM campaigns c LEFT JOIN
    (SELECT install_date d, source ch, COUNT(*) n FROM students GROUP BY 1,2) x ON x.d = c.date AND x.ch = c.channel
    WHERE CAST(c.installs_attributed AS INTEGER) <> COALESCE(x.n, 0)""")

# ---- the same numbers from metrics.py
s, e, c = M.load()
v = M.build_view(s, e, c)
ns, ar, ch = M.north_star(v), M.activation_recent(v), M.channel_table(v).set_index("source")
w = M.weekly(v)
f = M.findings(s, e, c)
comp = M.completion(v).set_index("item")
d7 = M.retention_table(v, days=(7,), by=None)["rate"].iloc[0]
py = {
    "Weekly Learners, week of 19 Oct": ns["learners"],
    "Weekly actives, week of 19 Oct": int(w.loc["2026-10-19", "active"]),
    "Weekly Learners, week of 12 Oct": ns["prev_learners"],
    "7-day activation, installs 11-24 Oct": ar["rate"],
    "7-day activation, installs 1 Sep-4 Oct": f["act_pre"],
    "7-day activation, installs 5-24 Oct": f["act_post"],
    "WhatsApp Rs per activated student": ch.loc["whatsapp", "cost_per_activated"],
    "Paid Rs per activated student": M.paid_cost_per_activated(v),
    "Day-7 retention, all installs <= 24 Oct": d7,
    "Test submit rate (all)": comp.loc["Practice test", "rate"],
    "Learn capsule completion": comp.loc["Learn capsule", "rate"],
    "Revise capsule completion": comp.loc["Revise capsule", "rate"],
    "Weekly Learners, partial week 26-31 Oct": int(w.loc["2026-10-26", "learners"]),
    "Weekly Learners, partial week 1-6 Sep": int(w.iloc[0]["learners"]),
    "7-day activation, prior window 27 Sep-10 Oct": ar["prev_rate"],
    "branch_link Rs per activated student": ch.loc["branch_link", "cost_per_activated"],
    "centre_qr Rs per activated student": ch.loc["centre_qr", "cost_per_activated"],
    "Funnel: started something within 7 days": int(M.conversion_funnel(v)["students"].iloc[1]),
    "Funnel: came back on a later day (of activated)": int(M.conversion_funnel(v)["students"].iloc[3]),
}

ok = True
print(f"{'check':45s} {'SQL':>12s} {'metrics.py':>12s}  result")
for k, sv in sql.items():
    pv = py[k]
    good = abs(float(sv) - float(pv)) < 1e-9 * max(1, abs(float(sv)))
    ok &= good
    print(f"{k:45s} {float(sv):12.4f} {float(pv):12.4f}  {'PASS' if good else 'FAIL'}")
good = reconcile == 0
ok &= good
print(f"{'campaign installs vs student sources (mismatching day-channel rows)':45s} {reconcile:12d} {0:12d}  {'PASS' if good else 'FAIL'}")
print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
