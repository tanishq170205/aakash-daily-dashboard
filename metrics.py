"""metrics.py - the ONE place where every dashboard number is computed.

app.py (Streamlit) and make_report.py (static PDF) both import from here,
and verify_numbers.py re-computes the headline numbers independently in SQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Constants and definitions
# ----------------------------------------------------------------------------
DATA_START = pd.Timestamp("2026-09-01")
DATA_END = pd.Timestamp("2026-10-31")
LEARN = ["practice_test_submitted", "capsule_completed", "video_completed"]  # "learning action"
ACT_DAYS = 7                                    # activation window (days after install date)
CUTOFF = DATA_END - pd.Timedelta(days=ACT_DAYS)  # last install date with a full window = 24 Oct
BREAK_DATE = pd.Timestamp("2026-10-05")         # Monday: week-aligned before/after split
SOURCES = ["whatsapp", "organic", "branch_link", "centre_qr", "website_qr"]
PAID = ["whatsapp", "branch_link", "centre_qr"]  # channels with spend > 0
RET_DAYS = (1, 2, 3, 5, 7, 10, 14, 21, 28)
MAX_AGE = 60

# ASSUMED targets (not in the data) - see "Definitions & assumptions" tab
TARGETS = {
    "learner_wow": 0.10,        # Weekly Learners growth, week over week
    "learner_share": 0.30,      # floor for learners as a share of weekly actives
    "activation": 0.45,         # 7-day activation (pre-October baseline was ~48%)
    "cost_per_activated": 1500,  # INR per activated student, paid channels
}


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def load(data_dir: str | Path | None = None):
    d = Path(data_dir) if data_dir else Path(__file__).parent / "data"
    s = pd.read_csv(d / "students.csv", parse_dates=["install_date"])
    e = pd.read_csv(d / "events.csv", parse_dates=["event_time"])
    c = pd.read_csv(d / "campaigns.csv", parse_dates=["date"])

    e["date"] = e["event_time"].dt.normalize()           # times are already IST
    e = e.merge(s[["student_id", "install_date"]], on="student_id", how="left")
    e["age"] = (e["date"] - e["install_date"]).dt.days   # days since install date
    assert e["age"].notna().all() and (e["age"] >= 0).all(), "event before install / orphan event"
    e["week"] = e["date"] - pd.to_timedelta(e["date"].dt.weekday, unit="D")  # Monday start

    s["install_week"] = s["install_date"] - pd.to_timedelta(s["install_date"].dt.weekday, unit="D")
    first_learn = e[e["event_name"].isin(LEARN)].groupby("student_id")["age"].min()
    s["activated"] = s["student_id"].map(first_learn).le(ACT_DAYS)   # NaN (never learned) -> False
    c["week"] = c["date"] - pd.to_timedelta(c["date"].dt.weekday, unit="D")
    return s, e, c


# ----------------------------------------------------------------------------
# Filtered view
# ----------------------------------------------------------------------------
@dataclass
class View:
    s: pd.DataFrame       # students passing the segment filters (any install date)
    e: pd.DataFrame       # their events inside the date range
    e_all: pd.DataFrame   # their events, whole data period (for retention, which needs the future)
    c: pd.DataFrame       # campaign rows inside the date range (+ channel filter)
    start: pd.Timestamp
    end: pd.Timestamp
    spend_ok: bool        # False when a segment filter makes spend-per-student meaningless

    @property
    def new(self) -> pd.DataFrame:
        """Students who installed inside the date range."""
        return self.s[self.s["install_date"].between(self.start, self.end)]

    @property
    def mature(self) -> pd.DataFrame:
        """Installs in range that have a full 7-day window (install date <= CUTOFF)."""
        return self.s[self.s["install_date"].between(self.start, min(self.end, CUTOFF))]


def build_view(s, e, c, start=DATA_START, end=DATA_END, sources=None, classes=None,
               streams=None, platforms=None, tiers=None) -> View:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    mask = pd.Series(True, index=s.index)
    for col, vals in [("source", sources), ("class", classes), ("stream", streams),
                      ("platform", platforms), ("city_tier", tiers)]:
        if vals:
            mask &= s[col].isin(vals)
    sf = s[mask]
    e_all = e[e["student_id"].isin(sf["student_id"])]
    ef = e_all[e_all["date"].between(start, end)]
    cf = c[c["date"].between(start, end)]
    if sources:
        cf = cf[cf["channel"].isin(sources)]
    spend_ok = not any([classes, streams, platforms, tiers])
    return View(sf, ef, e_all, cf, start, end, spend_ok)


# ----------------------------------------------------------------------------
# North Star: Weekly Learners
# ----------------------------------------------------------------------------
def _days_in_range(week_start, lo, hi):
    a, b = max(week_start, lo), min(week_start + pd.Timedelta(days=6), hi)
    return max((b - a).days + 1, 0)


def weekly(v: View) -> pd.DataFrame:
    """Mon-Sun weeks: active students, Weekly Learners, habit learners, learner share."""
    if v.e.empty:
        return pd.DataFrame(columns=["active", "learners", "habit", "share", "days", "partial"])
    active = v.e.groupby("week")["student_id"].nunique()
    L = v.e[v.e["event_name"].isin(LEARN)]
    learners = L.groupby("week")["student_id"].nunique()
    per = L.groupby(["week", "student_id"])["date"].nunique()
    habit = (per >= 2).groupby(level=0).sum()
    t = pd.DataFrame({"active": active, "learners": learners, "habit": habit}).fillna(0).astype(int)
    t["share"] = t["learners"] / t["active"]
    t["days"] = [_days_in_range(w, v.start, v.end) for w in t.index]
    t["partial"] = t["days"] < 7
    return t.sort_index()


def north_star(v: View):
    t = weekly(v)
    full = t[~t["partial"]]
    if full.empty:
        return None
    cur = full.iloc[-1]
    prev = full.iloc[-2] if len(full) > 1 else None
    return {
        "week": full.index[-1],
        "learners": int(cur["learners"]),
        "prev_learners": int(prev["learners"]) if prev is not None else None,
        "wow": (cur["learners"] / prev["learners"] - 1) if prev is not None else np.nan,
        "share": float(cur["share"]),
        "prev_share": float(prev["share"]) if prev is not None else np.nan,
    }


# ----------------------------------------------------------------------------
# Activation
# ----------------------------------------------------------------------------
def activation_by_week(v: View) -> pd.DataFrame:
    m = v.mature
    if m.empty:
        return pd.DataFrame(columns=["rate", "n", "days", "partial"])
    g = m.groupby("install_week")["activated"].agg(["mean", "size"])
    g.columns = ["rate", "n"]
    hi = min(v.end, CUTOFF)
    g["days"] = [_days_in_range(w, v.start, hi) for w in g.index]
    g["partial"] = g["days"] < 7
    return g


def activation_recent(v: View, days: int = 14):
    """Activation of the last `days` mature install days vs the `days` before them."""
    hi = min(v.end, CUTOFF)
    cur_lo = hi - pd.Timedelta(days=days - 1)
    prev_hi = cur_lo - pd.Timedelta(days=1)
    prev_lo = prev_hi - pd.Timedelta(days=days - 1)
    cur = v.s[v.s["install_date"].between(max(cur_lo, v.start), hi)]
    prev = v.s[v.s["install_date"].between(max(prev_lo, v.start), prev_hi)]
    return {
        "rate": cur["activated"].mean() if len(cur) else np.nan, "n": len(cur),
        "prev_rate": prev["activated"].mean() if len(prev) else np.nan, "prev_n": len(prev),
        "lo": max(cur_lo, v.start), "hi": hi,
    }


def activation_daily(v: View, roll: int = 7) -> pd.DataFrame:
    m = v.mature
    if m.empty:
        return pd.DataFrame(columns=["rate"])
    idx = pd.date_range(v.start, min(v.end, CUTOFF))
    g = m.groupby("install_date")["activated"].agg(["sum", "size"]).reindex(idx, fill_value=0)
    out = pd.DataFrame({"rate": g["sum"].rolling(roll).sum() / g["size"].rolling(roll).sum()})
    return out.dropna()


# ----------------------------------------------------------------------------
# Retention (share of an install cohort active exactly N days after install)
# ----------------------------------------------------------------------------
def _activity_matrix(e_all: pd.DataFrame, ids: pd.Series) -> pd.DataFrame:
    pa = e_all[["student_id", "age"]].drop_duplicates()
    pa = pa[pa["age"].between(0, MAX_AGE)]
    m = pd.crosstab(pa["student_id"], pa["age"])
    return m.reindex(index=ids, columns=range(0, MAX_AGE + 1), fill_value=0) > 0


def retention_table(v: View, days=RET_DAYS, by: str | None = "source", min_n: int = 50) -> pd.DataFrame:
    base = v.new
    if base.empty:
        return pd.DataFrame(columns=["group", "day", "rate", "n"])
    mat = _activity_matrix(v.e_all, base["student_id"])
    groups = [("All", base)]
    if by:
        groups += list(base.groupby(by))
    rows = []
    for name, g in groups:
        for n in days:
            mt = g[(DATA_END - g["install_date"]).dt.days >= n]   # only cohorts old enough
            rate = mat.loc[mt["student_id"], n].mean() if len(mt) >= min_n else np.nan
            rows.append((str(name), n, rate, len(mt)))
    return pd.DataFrame(rows, columns=["group", "day", "rate", "n"])


def conversion_funnel(v: View) -> pd.DataFrame:
    """Student-level funnel, installs with a full 7-day window, everything within 7 days of install:
    installed -> tried something -> completed a learning action (= activated) -> active again on a later day."""
    m = v.mature
    if m.empty:
        return pd.DataFrame(columns=["step", "students", "pct_of_installs", "pct_of_prev"])
    e = v.e_all[v.e_all["student_id"].isin(m["student_id"]) & (v.e_all["age"] <= ACT_DAYS)]
    TRY = ["practice_test_created", "capsule_started", "video_started", "content_viewed", "doubt_submitted"]
    tried = set(e[e["event_name"].isin(TRY + LEARN)]["student_id"])
    learned = set(e[e["event_name"].isin(LEARN)]["student_id"])
    back = set(e[e["age"].between(1, ACT_DAYS)]["student_id"]) & learned
    counts = [("Installed", len(m)), ("Started a test, capsule, video or doubt", len(tried)),
              ("Finished a learning action (activated)", len(learned)), ("Came back on a later day", len(back))]
    out = pd.DataFrame(counts, columns=["step", "students"])
    out["pct_of_installs"] = out["students"] / out["students"].iloc[0]
    out["pct_of_prev"] = out["students"] / out["students"].shift(1)
    return out


# ----------------------------------------------------------------------------
# Channels
# ----------------------------------------------------------------------------
def channel_table(v: View) -> pd.DataFrame:
    hi = min(v.end, CUTOFF)
    ins, mat = v.new, v.mature
    d7 = retention_table(v, days=(7,), by="source").query("day == 7").set_index("group")["rate"]
    rows = []
    for src in SOURCES:
        a, m = ins[ins["source"] == src], mat[mat["source"] == src]
        cdf = v.c[v.c["channel"] == src]
        spend_all = float(cdf["spend_inr"].sum())
        spend_m = float(cdf[cdf["date"] <= hi]["spend_inr"].sum())   # same window as activation
        act = int(m["activated"].sum())
        rows.append({
            "source": src, "installs": len(a), "spend": spend_all,
            "clicks": int(cdf["clicks"].sum()), "messages": int(cdf["messages_delivered"].sum()),
            "mature_installs": len(m), "activated": act,
            "activation": m["activated"].mean() if len(m) else np.nan,
            "d7": d7.get(src, np.nan),
            "cost_per_install": spend_all / len(a) if (len(a) and spend_all > 0) else np.nan,
            "cost_per_activated": spend_m / act if (spend_m > 0 and act > 0) else np.nan,
            "spend_matured": spend_m,
        })
    t = pd.DataFrame(rows)
    t["install_share"] = t["installs"] / t["installs"].sum() if t["installs"].sum() else np.nan
    return t


def paid_cost_per_activated(v: View):
    """Blended cost per activated student across paid channels (spend and students in the same window)."""
    t = channel_table(v)
    p = t[t["source"].isin(PAID)]
    act, sp = p["activated"].sum(), p["spend_matured"].sum()
    return sp / act if (act > 0 and sp > 0) else np.nan


def whatsapp_weekly(v: View) -> pd.DataFrame:
    w = v.c[v.c["channel"] == "whatsapp"].groupby("week").agg(
        spend=("spend_inr", "sum"), messages=("messages_delivered", "sum"),
        clicks=("clicks", "sum"), installs=("installs_attributed", "sum"))
    w["cost_per_install"] = w["spend"] / w["installs"]
    w["click_to_install"] = w["installs"] / w["clicks"]
    w["days"] = [_days_in_range(x, v.start, v.end) for x in w.index]
    return w


def install_mix_weekly(v: View) -> pd.DataFrame:
    return v.new.groupby(["install_week", "source"]).size().unstack(fill_value=0)


# ----------------------------------------------------------------------------
# Engagement / content
# ----------------------------------------------------------------------------
def completion(v: View) -> pd.DataFrame:
    e = v.e
    def n(name, ctype=None):
        x = e[e["event_name"] == name]
        return int(len(x if ctype is None else x[x["capsule_type"] == ctype]))
    rows = [
        ("Practice test", n("practice_test_created"), n("practice_test_submitted")),
        ("Revise capsule", n("capsule_started", "Revise"), n("capsule_completed", "Revise")),
        ("Learn capsule", n("capsule_started", "Learn"), n("capsule_completed", "Learn")),
        ("Video", n("video_started"), n("video_completed")),
    ]
    t = pd.DataFrame(rows, columns=["item", "started", "completed"])
    t["rate"] = t["completed"] / t["started"].replace(0, np.nan)
    return t


def test_start_rate_weekly(v: View) -> pd.DataFrame:
    p = v.e.pivot_table(index="week", columns="event_name", values="student_id", aggfunc="count").fillna(0)
    for col in ("app_open", "practice_test_created", "practice_test_submitted"):
        if col not in p:
            p[col] = 0
    out = pd.DataFrame({
        "tests_started_per_100_opens": 100 * p["practice_test_created"] / p["app_open"].replace(0, np.nan),
        "test_submit_rate": p["practice_test_submitted"] / p["practice_test_created"].replace(0, np.nan)})
    out["days"] = [_days_in_range(w, v.start, v.end) for w in out.index]
    return out


def events_by_hour(v: View) -> pd.Series:
    return v.e.groupby(v.e["event_time"].dt.hour).size().reindex(range(24), fill_value=0)


def segment_table(v: View, col: str) -> pd.DataFrame:
    mat, new = v.mature, v.new
    d7 = retention_table(v, days=(7,), by=col).query("day == 7").set_index("group")["rate"]
    rows = []
    for val, g in new.groupby(col):
        m = mat[mat[col] == val]
        rows.append({col: str(val), "installs": len(g), "activation": m["activated"].mean() if len(m) else np.nan,
                     "d7": d7.get(str(val), np.nan)})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Findings ("What I see") - computed on the FULL data, never hard-coded
# ----------------------------------------------------------------------------
def findings(s, e, c) -> dict:
    v = build_view(s, e, c)
    m = v.mature
    pre, post = m[m["install_date"] < BREAK_DATE], m[m["install_date"] >= BREAK_DATE]
    f = {"act_pre": pre["activated"].mean(), "act_post": post["activated"].mean(),
         "n_pre": len(pre), "n_post": len(post)}

    fell, total = 0, 0                      # did activation fall inside each segment value?
    for col in ["source", "class", "stream", "platform", "city_tier"]:
        for val in m[col].unique():
            a, b = pre[pre[col] == val], post[post[col] == val]
            if len(a) >= 30 and len(b) >= 30:
                total += 1
                fell += int(b["activated"].mean() < a["activated"].mean())
    f["seg_fell"], f["seg_total"] = fell, total

    ts = test_start_rate_weekly(v)
    ev = v.e
    for tag, sel in (("pre", ev["week"] < BREAK_DATE), ("post", ev["week"] >= BREAK_DATE)):
        x = ev[sel]
        opens, created = (x["event_name"] == "app_open").sum(), (x["event_name"] == "practice_test_created").sum()
        subm = (x["event_name"] == "practice_test_submitted").sum()
        f[f"tests_per_100_{tag}"] = 100 * created / opens
        f[f"submit_{tag}"] = subm / created
    f["weekly_ts"] = ts

    ch = channel_table(v).set_index("source")
    paid_spend = ch.loc[PAID, "spend"].sum()
    f["wa_spend_share"] = ch.loc["whatsapp", "spend"] / paid_spend
    f["wa_install_share"] = ch.loc["whatsapp", "installs"] / ch["installs"].sum()
    f["wa_cpa"], f["wa_act"], f["wa_d7"] = (ch.loc["whatsapp", "cost_per_activated"],
                                           ch.loc["whatsapp", "activation"], ch.loc["whatsapp", "d7"])
    f["bl_cpa"], f["cq_cpa"] = ch.loc["branch_link", "cost_per_activated"], ch.loc["centre_qr", "cost_per_activated"]
    f["cq_act"], f["org_d7"] = ch.loc["centre_qr", "activation"], ch.loc["organic", "d7"]
    f["bl_n"], f["cq_n"] = int(ch.loc["branch_link", "mature_installs"]), int(ch.loc["centre_qr", "mature_installs"])

    comp = completion(v).set_index("item")
    f["test_submit"] = comp.loc["Practice test", "rate"]
    f["learn_cap"], f["revise_cap"], f["video"] = (comp.loc["Learn capsule", "rate"],
                                                   comp.loc["Revise capsule", "rate"], comp.loc["Video", "rate"])
    caps = comp.loc[["Learn capsule", "Revise capsule"]]
    f["capsule"] = caps["completed"].sum() / caps["started"].sum()

    # Learner share trend: first full week vs last full week
    wk = weekly(v)
    full_wk = wk[~wk["partial"]]
    if len(full_wk) >= 2:
        f["learners_first"] = int(full_wk.iloc[0]["learners"])
        f["learners_last"]  = int(full_wk.iloc[-1]["learners"])
        f["active_first"]   = int(full_wk.iloc[0]["active"])
        f["active_last"]    = int(full_wk.iloc[-1]["active"])
        f["share_first"]    = float(full_wk.iloc[0]["share"])
        f["share_last"]     = float(full_wk.iloc[-1]["share"])
        # e.g. "7 Sep", "19 Oct" — no leading zero
        f["week_first_lbl"] = (str(full_wk.index[0].day) + " " +
                               full_wk.index[0].strftime("%b"))
        f["week_last_lbl"]  = (str(full_wk.index[-1].day) + " " +
                               full_wk.index[-1].strftime("%b"))
    else:
        f["learners_first"] = f["learners_last"] = 0
        f["active_first"] = f["active_last"] = 0
        f["share_first"] = f["share_last"] = np.nan
        f["week_first_lbl"] = f["week_last_lbl"] = ""

    # Doubt subject breakdown
    doubts = e[e["event_name"] == "doubt_submitted"]
    if len(doubts):
        top = doubts["subject"].value_counts()
        f["doubt_top_subject"] = top.index[0]
        f["doubt_top_pct"] = top.iloc[0] / top.sum()
    else:
        f["doubt_top_subject"], f["doubt_top_pct"] = "Physics", np.nan

    return f


def narrative(f: dict):
    """(three findings, two actions) as plain strings - used by the app and the PDF."""
    rs = lambda x: f"₹{x:,.0f}"
    found = [
        # F1: activation drop + learner share merged
        (f"Activation fell from {f['act_pre']:.0%} to {f['act_post']:.0%} for installs from 5 Oct, "
         f"in {f['seg_fell']} of {f['seg_total']} segments, so it is not channel mix. "
         f"Tests started per 100 app opens dropped {f['tests_per_100_pre']:.0f} to "
         f"{f['tests_per_100_post']:.0f} while the submit rate held at ~{f['submit_post']:.0%}: "
         f"students stopped starting, not finishing. "
         f"Learners also fell from {f['share_first']:.0%} to {f['share_last']:.0%} of weekly actives, "
         f"so Weekly Learners ({f['learners_first']:,} to {f['learners_last']:,}) grew by adding users, "
         f"not by getting each user to learn."),
        # F2: WhatsApp CPA — evidence only, no recommendation sentence
        (f"WhatsApp is {f['wa_spend_share']:.0%} of paid spend and {f['wa_install_share']:.0%} of installs, "
         f"but costs {rs(f['wa_cpa'])} per activated student vs {rs(f['bl_cpa'])} (branch link) and "
         f"{rs(f['cq_cpa'])} (centre QR). Activation is {f['wa_act']:.0%} vs {f['cq_act']:.0%} for "
         f"centre QR; D7 retention {f['wa_d7']:.0%} vs organic {f['org_d7']:.0%}. "
         f"(Branch/QR samples are small: {f['bl_n']}/{f['cq_n']} students.)"),
        # F3: content completion — original wording
        (f"Learning content is where students leave: capsules are finished {f['capsule']:.0%} of the time "
         f"(Learn {f['learn_cap']:.0%}, Revise {f['revise_cap']:.0%}) and videos {f['video']:.0%}, "
         f"against {f['test_submit']:.0%} of started tests submitted."),
    ]
    acts = [
        # A1: activation incident only
        (f"Treat the October activation drop as an incident: diff the release and UX log for 3–8 Oct "
         f"(home screen, test entry point), then roll back or A/B the suspect change. "
         f"Goal: activation back to >= {TARGETS['activation']:.0%} within two weeks."),
        # A2: channel spend reallocation — WhatsApp context here
        (f"WhatsApp brings {f['wa_install_share']:.0%} of installs — do not cut it. "
         f"Hold its spend flat and pilot moving 10–15% of paid budget to branch-link and centre-QR; "
         f"judge every channel on cost per activated student, not cost per install. "
         f"Re-check once those channels reach 500+ installs."),
    ]
    return found, acts


# ----------------------------------------------------------------------------
# KPI cards (shared by the Streamlit app and the PDF report)
# ----------------------------------------------------------------------------
def _pct(x, d=0):
    return "n/a" if pd.isna(x) else f"{x:.{d}%}"


def kpi_cards(v: View):
    """Return ([{title, value, sub, status}], number_off_target). status: good | bad | flat."""
    T, cards, bad = TARGETS, [], 0
    ns, ar = north_star(v), activation_recent(v)
    if ns:
        ok = (not pd.isna(ns["wow"])) and ns["wow"] >= T["learner_wow"]
        bad += not ok
        wow = "" if pd.isna(ns["wow"]) else f"{ns['wow']:+.0%} vs prior week  |  "
        cards.append(dict(title=f"WEEKLY LEARNERS (North Star), week of {ns['week']:%d %b}",
                          value=f"{ns['learners']:,}", sub=f"{wow}target {T['learner_wow']:+.0%} (assumed)",
                          status="good" if ok else "bad"))
        ok = ns["share"] >= T["learner_share"]
        bad += not ok
        cards.append(dict(title="LEARNERS AS % OF WEEKLY ACTIVES", value=_pct(ns["share"]),
                          sub=f"prior week {_pct(ns['prev_share'])}  |  floor {T['learner_share']:.0%} (assumed)",
                          status="good" if ok else "bad"))
    else:
        for t_ in ("WEEKLY LEARNERS", "LEARNERS AS % OF WEEKLY ACTIVES"):
            cards.append(dict(title=t_, value="n/a", sub="needs a full Mon-Sun week in range", status="flat"))
    ok = (not pd.isna(ar["rate"])) and ar["rate"] >= T["activation"]
    bad += (not ok) and not pd.isna(ar["rate"])
    cards.append(dict(title=f"7-DAY ACTIVATION, installs {ar['lo']:%d %b}-{ar['hi']:%d %b}", value=_pct(ar["rate"], 1),
                      sub=f"prior 14 days {_pct(ar['prev_rate'], 1)}  |  target {T['activation']:.0%} (assumed)",
                      status="flat" if pd.isna(ar["rate"]) else ("good" if ok else "bad")))
    r = retention_table(v, days=(7,), by=None)
    cards.append(dict(title="DAY-7 RETENTION", value=_pct(r["rate"].iloc[0] if len(r) else np.nan, 1),
                      sub="share of installs active exactly 7 days later", status="flat"))
    cpa = paid_cost_per_activated(v) if v.spend_ok else np.nan
    if not pd.isna(cpa):
        ok = cpa <= T["cost_per_activated"]
        bad += not ok
        cards.append(dict(title="COST PER ACTIVATED STUDENT (paid)", value=f"₹{cpa:,.0f}",
                          sub=f"target ≤ ₹{T['cost_per_activated']:,} (assumed)", status="good" if ok else "bad"))
    else:
        cards.append(dict(title="COST PER ACTIVATED STUDENT (paid)", value="n/a",
                          sub="needs paid channels and no segment filter", status="flat"))
    return cards, bad
