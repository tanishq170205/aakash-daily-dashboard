"""Aakash Daily - Monday view.  Run:  python -m streamlit run app.py"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import metrics as M

st.set_page_config(page_title="Aakash Daily - Monday view", page_icon="📊", layout="wide")

NAVY, LIGHT, ORANGE, RED, GREEN, GREY = "#1F3A5F", "#A9BCD6", "#E8743B", "#D64545", "#1B9E5A", "#8A94A6"
st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1400px;}
.kpi {border-left: 6px solid var(--c); background: rgba(128,128,128,.10); padding: 10px 14px; border-radius: 8px; height: 100%;}
.kpi .t {font-size: .78rem; opacity: .75;}
.kpi .v {font-size: 1.9rem; font-weight: 700; line-height: 1.15;}
.kpi .s {font-size: .78rem; opacity: .8;}
</style>""", unsafe_allow_html=True)


@st.cache_data
def get_data():
    return M.load()


@st.cache_data
def get_findings():
    s, e, c = get_data()
    return M.findings(s, e, c)


s, e, c = get_data()

# ---------------------------------------------------------------- sidebar filters
st.sidebar.header("Filters")
rng = st.sidebar.date_input("Date range", (M.DATA_START.date(), M.DATA_END.date()),
                            min_value=M.DATA_START.date(), max_value=M.DATA_END.date())
if not isinstance(rng, tuple) or len(rng) != 2:
    st.info("Pick both a start and an end date.")
    st.stop()


def multi(label, col):
    opts = sorted(s[col].unique(), key=str) if col != "source" else M.SOURCES
    sel = st.sidebar.multiselect(label, opts, default=opts)
    return None if (not sel or len(sel) == len(opts)) else sel


sources, classes = multi("Source / channel", "source"), multi("Class", "class")
streams, platforms, tiers = multi("Stream", "stream"), multi("Platform", "platform"), multi("City tier", "city_tier")
st.sidebar.caption("Spend is only known per channel and day, so cost metrics switch off when a class, "
                   "stream, platform or tier filter is active. Targets are ASSUMED (see Definitions tab).")

v = M.build_view(s, e, c, rng[0], rng[1], sources, classes, streams, platforms, tiers)
if v.new.empty or v.e.empty:
    st.warning("No students match these filters.")
    st.stop()


# ---------------------------------------------------------------- helpers
def kpi(title, value, sub, status="flat"):
    color = {"good": GREEN, "bad": RED, "flat": GREY}[status]
    return (f'<div class="kpi" style="--c:{color}"><div class="t">{title}</div>'
            f'<div class="v">{value}</div><div class="s">{sub}</div></div>')


def pct(x, d=0):
    return "n/a" if pd.isna(x) else f"{x:.{d}%}"


def wk_label(idx, partial):
    return [d.strftime("%d %b") + ("*" if p else "") for d, p in zip(idx, partial)]


def style(fig, h=330, title=None):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=44 if title else 10, b=10), title=title,
                      legend=dict(orientation="h", y=-0.2), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig


# ---------------------------------------------------------------- figures
def fig_north_star():
    t = M.weekly(v)
    x = wk_label(t.index, t["partial"])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=x, y=t["learners"], name="Weekly Learners", text=t["learners"], textposition="outside",
                marker_color=[LIGHT if p else NAVY for p in t["partial"]])
    fig.add_scatter(x=x, y=t["share"], name="Learners as % of weekly actives", mode="lines+markers",
                    line=dict(color=ORANGE, width=3), secondary_y=True)
    fig.add_scatter(x=x, y=[M.TARGETS["learner_share"]] * len(x), name="Share floor (assumed)", mode="lines",
                    line=dict(color=ORANGE, dash="dot", width=1), secondary_y=True)
    fig.update_yaxes(tickformat=".0%", range=[0, 0.6], secondary_y=True, showgrid=False)
    fig.update_yaxes(range=[0, max(t["learners"].max() * 1.2, 10)], secondary_y=False)
    return style(fig, title="North Star: Weekly Learners (bars) and their share of weekly actives (line)")


def fig_activation():
    a = M.activation_by_week(v)
    x = wk_label(a.index, a["partial"])
    fig = go.Figure()
    fig.add_scatter(x=x, y=a["rate"], mode="lines+markers+text", text=[f"{r:.0%}" for r in a["rate"]],
                    textposition="top center", line=dict(color=NAVY, width=3), name="7-day activation",
                    customdata=a["n"], hovertemplate="%{x}: %{y:.1%} of %{customdata} students<extra></extra>")
    fig.add_hline(y=M.TARGETS["activation"], line_dash="dot", line_color=GREEN,
                  annotation_text="target 45% (assumed)", annotation_position="bottom right")
    fig.update_yaxes(tickformat=".0%", range=[0, max(0.7, a["rate"].max() * 1.15)])
    return style(fig, title="Did new students start learning? 7-day activation by install week")


def fig_channel_cpa():
    t = M.channel_table(v)
    t = t[t["source"].isin(M.PAID) & t["cost_per_activated"].notna()].sort_values("cost_per_activated")
    if t.empty or not v.spend_ok:
        return None
    fig = go.Figure(go.Bar(
        y=t["source"], x=t["cost_per_activated"], orientation="h", marker_color=NAVY,
        text=[f"₹{r.cost_per_activated:,.0f}  |  {r.activation:.0%} activate  |  n={r.mature_installs}"
              for r in t.itertuples()], textposition="outside", cliponaxis=False))
    fig.add_vline(x=M.TARGETS["cost_per_activated"], line_dash="dot", line_color=GREEN,
                  annotation_text="target ₹1,500 (assumed)", annotation_position="top")
    fig.update_xaxes(range=[0, t["cost_per_activated"].max() * 1.75], tickprefix="₹")
    return style(fig, title="What does an activated student cost? (paid channels)")


def fig_completion():
    t = M.completion(v).sort_values("rate")
    fig = go.Figure(go.Bar(
        y=t["item"], x=t["rate"], orientation="h", text=[f"{r:.0%}  ({c:,} of {s:,})" for r, c, s in
                                                           zip(t["rate"], t["completed"], t["started"])],
        textposition="outside", cliponaxis=False, marker_color=[RED if r < .4 else NAVY for r in t["rate"]]))
    fig.update_xaxes(tickformat=".0%", range=[0, 1.05])
    return style(fig, title="Where do students leave? Finished / started")


# ---------------------------------------------------------------- header
st.title("Aakash Daily - Monday view")
filt = [f"{k}: {', '.join(map(str, x))}" for k, x in
        [("source", sources), ("class", classes), ("stream", streams), ("platform", platforms), ("tier", tiers)] if x]
st.caption(f"{v.start:%d %b} - {v.end:%d %b %Y} (IST)  |  {len(v.new):,} installs  |  "
           f"{' | '.join(filt) if filt else 'all students'}  |  dummy data, targets are assumed")

tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Acquisition and channels", "Engagement and retention",
                                  "Definitions and assumptions"])

# ================================================================ OVERVIEW
with tab1:
    cards_data, bad = M.kpi_cards(v)
    cards = [kpi(c_["title"], c_["value"], c_["sub"], c_["status"]) for c_ in cards_data]
    for col, card in zip(st.columns(5), cards):
        col.markdown(card, unsafe_allow_html=True)
    st.caption(f"{bad} metric(s) off target (red).  Latest full week = Mon-Sun week with 7 days of data; "
               f"* = partial week.")

    # ---- What I see
    f = get_findings()
    found, acts = M.narrative(f)
    with st.container(border=True):
        st.subheader("What I see")
        st.caption("Computed on the full 1 Sep - 31 Oct data (filters do not change this box).")
        cols = st.columns(3)
        for i, (col, txt) in enumerate(zip(cols, found), 1):
            col.markdown(f"**Finding {i}.** {txt}")
        st.markdown(f"**Action 1.** {acts[0]}")
        st.markdown(f"**Action 2.** {acts[1]}")

    left, right = st.columns(2)
    left.plotly_chart(fig_north_star(), width="stretch")
    right.plotly_chart(fig_activation(), width="stretch")
    left, right = st.columns(2)
    fc = fig_channel_cpa()
    if fc:
        left.plotly_chart(fc, width="stretch")
    else:
        left.info("Cost per activated student is hidden: it needs paid channels in the filter and no "
                  "class / stream / platform / tier filter.")
    right.plotly_chart(fig_completion(), width="stretch")

# ================================================================ CHANNELS
with tab2:
    t = M.channel_table(v)
    show = t.rename(columns={
        "source": "Channel", "installs": "Installs", "install_share": "Share of installs", "spend": "Spend (₹)",
        "cost_per_install": "₹ / install", "activation": "7-day activation", "cost_per_activated": "₹ / activated",
        "d7": "D7 retention", "mature_installs": "Installs with full 7-day window"})
    cols = ["Channel", "Installs", "Share of installs", "Spend (₹)", "₹ / install", "Installs with full 7-day window",
            "7-day activation", "₹ / activated", "D7 retention"]
    if not v.spend_ok:
        cols = [x for x in cols if x not in ("Spend (₹)", "₹ / install", "₹ / activated")]
    st.dataframe(show[cols], hide_index=True, width="stretch", column_config={
        "Share of installs": st.column_config.NumberColumn(format="percent"),
        "7-day activation": st.column_config.NumberColumn(format="percent"),
        "D7 retention": st.column_config.NumberColumn(format="percent"),
        "Spend (₹)": st.column_config.NumberColumn(format="₹%d"),
        "₹ / install": st.column_config.NumberColumn(format="₹%d"),
        "₹ / activated": st.column_config.NumberColumn(format="₹%d")})
    st.caption("₹ / activated = spend on days up to 24 Oct / students installed up to 24 Oct who learned within 7 days "
               "(same window on both sides). Organic and website QR have no spend in the data, so no cost is shown. "
               "Branch-link and centre-QR rows are small samples.")
    a, b = st.columns(2)
    w = M.whatsapp_weekly(v)
    if len(w):
        x = wk_label(w.index, w["days"] < 7)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_bar(x=x, y=w["spend"], name="WhatsApp spend (₹)", marker_color=NAVY)
        fig.add_scatter(x=x, y=w["cost_per_install"], name="₹ per install", mode="lines+markers",
                        line=dict(color=ORANGE, width=3), secondary_y=True)
        fig.update_yaxes(showgrid=False, secondary_y=True)
        a.plotly_chart(style(fig, title="WhatsApp: spend and cost per install by week"), width="stretch")
        fig = go.Figure(go.Scatter(x=x, y=w["click_to_install"], mode="lines+markers",
                                   line=dict(color=NAVY, width=3)))
        fig.update_yaxes(tickformat=".0%", rangemode="tozero")
        b.plotly_chart(style(fig, title="WhatsApp: click-to-install rate (message price is flat at ₹1,120 / 1,000)"),
                       width="stretch")
    mix = M.install_mix_weekly(v)
    fig = go.Figure()
    for src in M.SOURCES:
        if src in mix:
            fig.add_bar(x=wk_label(mix.index, [False] * len(mix)), y=mix[src], name=src)
    fig.update_layout(barmode="stack")
    st.plotly_chart(style(fig, 300, "Installs by week and source"), width="stretch")

# ================================================================ ENGAGEMENT
with tab3:
    fu = M.conversion_funnel(v)
    if len(fu):
        fig = go.Figure(go.Bar(
            y=fu["step"], x=fu["students"], orientation="h", marker_color=NAVY,
            text=[f"{n:,}  ({p:.0%} of installs)" for n, p in zip(fu["students"], fu["pct_of_installs"])],
            textposition="outside", cliponaxis=False))
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(range=[0, fu["students"].max() * 1.35])
        st.plotly_chart(style(fig, 260, "Student funnel: what happens in the first 7 days after install"), width="stretch")
        st.caption("Installs up to 24 Oct (full 7-day window). Each step is nested inside the one above it.")
    a, b = st.columns(2)
    rt = M.retention_table(v, by="source")
    fig = go.Figure()
    for g, d in rt.groupby("group", sort=False):
        d = d.dropna(subset=["rate"])
        if len(d):
            fig.add_scatter(x=d["day"], y=d["rate"], mode="lines+markers", name=g,
                            line=dict(width=4 if g == "All" else 2, color=NAVY if g == "All" else None))
    fig.update_xaxes(title="days since install", tickvals=list(M.RET_DAYS))
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    a.plotly_chart(style(fig, title="Retention: share of installs active exactly N days later"), width="stretch")
    a.caption("A day is shown only for cohorts old enough to have been observed, and only if n >= 50 students.")

    ts = M.test_start_rate_weekly(v)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    x = wk_label(ts.index, ts["days"] < 7)
    fig.add_scatter(x=x, y=ts["tests_started_per_100_opens"], name="Tests started per 100 app opens",
                    mode="lines+markers", line=dict(color=NAVY, width=3))
    fig.add_scatter(x=x, y=ts["test_submit_rate"], name="Submitted / started", mode="lines+markers",
                    line=dict(color=ORANGE, width=2), secondary_y=True)
    fig.update_yaxes(tickformat=".0%", range=[0, 1], secondary_y=True, showgrid=False)
    fig.update_yaxes(rangemode="tozero", secondary_y=False)
    b.plotly_chart(style(fig, title="Why activation fell: fewer test starts, same finish rate"),
                   width="stretch")

    a, b = st.columns(2)
    ad = M.activation_daily(v)
    fig = go.Figure(go.Scatter(x=ad.index, y=ad["rate"], mode="lines", line=dict(color=NAVY, width=3)))
    fig.add_hline(y=M.TARGETS["activation"], line_dash="dot", line_color=GREEN)
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    a.plotly_chart(style(fig, title="7-day activation by install day (7-day rolling)"), width="stretch")
    hrs = M.events_by_hour(v)
    fig = go.Figure(go.Bar(x=hrs.index, y=hrs.values, marker_color=NAVY))
    fig.update_xaxes(title="hour of day (IST)", dtick=2)
    b.plotly_chart(style(fig, title="When do students use the app?"), width="stretch")

    dim = st.radio("Segment table", ["class", "stream", "platform", "city_tier", "source"], horizontal=True)
    seg = M.segment_table(v, dim)
    st.dataframe(seg, hide_index=True, width="stretch", column_config={
        "activation": st.column_config.NumberColumn("7-day activation", format="percent"),
        "d7": st.column_config.NumberColumn("D7 retention", format="percent")})
    st.caption("Small groups are noisy (iOS is about 5% of students). Do not read differences of a few points.")

# ================================================================ DEFINITIONS
with tab4:
    st.markdown(f"""
### North Star: Weekly Learners
Distinct students with at least one **learning action** in a Mon-Sun week (IST).
Learning action = `practice_test_submitted`, `capsule_completed` or `video_completed`.
Guardrails: learners on 2+ days in the week, 7-day activation, D7 retention.

### Definitions
- **Active student**: any event on that day. **Weekly actives** = distinct active students in the week.
- **Learner share** = Weekly Learners / weekly actives, on full Mon-Sun weeks only. Trend direction
  matters as much as the absolute level — a rising learner count on a falling share means growth is
  acquisition-driven, not engagement-driven.
- **7-day activation (inclusive)**: a learning action on days 0 through 7 after install (8 calendar days).
  Only installs on or before **24 Oct** are counted (later installs have not had 7 days yet).
- **Retention DN**: share of an install cohort with any event exactly N days after install. Cohorts too young
  for N are excluded; groups under 50 students are hidden.
- **Cost per activated student** = spend on days up to 24 Oct / activated students installed up to 24 Oct,
  paid channels only (WhatsApp, branch link, centre QR). Organic and website QR have no spend in the data.
- **Completion** = completed events / started events (event counts, not students).
- **Latest full week**: the last Mon-Sun week with 7 days of data. The first (1-6 Sep) and last (26-31 Oct)
  weeks have 6 days and are drawn lighter and marked with *.

### Assumptions (not in the data)
- Targets: Weekly Learners +10% week over week; learner share >= 30%; 7-day activation >= 45%
  (the pre-October level was about 48%); cost per activated student <= ₹1,500. Replace with real targets.
- Aakash Daily is free, so there is no revenue; value = students actually learning.
- Spend is matched to installs on the same day (no lag). Campaign installs match student sources exactly.
- The before/after split for the activation drop is 5 Oct (a Monday), so both groups hold whole weeks.

### Data notes
- No duplicates, orphan events, events before install, or missing scores. Times are IST, not converted.
- Subject mix is identical across streams (JEE students do as much Biology as NEET), so no content-gap
  finding is drawn from it. iOS is 315 students, too few for conclusions.
- Run `python verify_numbers.py` to re-compute the headline numbers independently in SQL.
""")
