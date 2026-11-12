"""Renders the Overview page as a static PDF + PNG (same numbers as the app: both use metrics.py).
Run:  python make_report.py   ->  dashboard.pdf, dashboard.png"""
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
from matplotlib.patches import FancyBboxPatch

import metrics as M

NAVY, LIGHT, ORANGE, RED, GREEN, GREY = "#1F3A5F", "#A9BCD6", "#E8743B", "#D64545", "#1B9E5A", "#8A94A6"
W, H = 14.0, 15.1                       # figure size in inches
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False})

s, e, c = M.load()
v = M.build_view(s, e, c)
fig = plt.figure(figsize=(W, H))


def box(l, t, w, h, **kw):
    """Axes placed by inches from the top-left corner."""
    return fig.add_axes([l / W, 1 - (t + h) / H, w / W, h / H], **kw)


def wk(idx, partial):
    return [d.strftime("%d %b") + ("*" if p else "") for d, p in zip(idx, partial)]


# ------------------------------------------------------------------ title
fig.text(0.5 / W * 1, 1 - 0.45 / H, "Aakash Daily - Monday view", fontsize=22, fontweight="bold", va="center")
fig.text(0.5 / W, 1 - 0.85 / H, f"{v.start:%d %b} - {v.end:%d %b %Y} (IST)  |  {len(v.new):,} installs  |  all students  |  "
         "dummy data; targets are ASSUMED; * = partial week (6 of 7 days)", fontsize=9.5, color="#555", va="center")

# ------------------------------------------------------------------ KPI cards
cards, bad = M.kpi_cards(v)
cw, gap, top = (W - 1.0 - 4 * 0.15) / 5, 0.15, 1.15
for i, k in enumerate(cards):
    ax = box(0.5 + i * (cw + gap), top, cw, 1.15)
    ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.04", fc="#F3F5F8", ec="none",
                                transform=ax.transAxes))
    ax.add_patch(plt.Rectangle((0, 0), 0.025, 1, fc={"good": GREEN, "bad": RED, "flat": GREY}[k["status"]],
                               transform=ax.transAxes))
    ax.text(0.07, 0.86, textwrap.fill(k["title"], 34), fontsize=6.3,
            color="#444", va="top", transform=ax.transAxes)
    ax.text(0.07, 0.36, k["value"], fontsize=21, fontweight="bold", va="center", transform=ax.transAxes)
    ax.text(0.07, 0.08, textwrap.fill(k["sub"], 38), fontsize=6.3, color="#555", va="bottom", transform=ax.transAxes)
fig.text(0.5 / W, 1 - 2.45 / H, f"{bad} metric(s) off target (red). Latest full week = Mon-Sun week with 7 days of data.",
         fontsize=8, color="#555")

# ------------------------------------------------------------------ What I see
found, acts = M.narrative(M.findings(s, e, c))
ax = box(0.5, 2.65, W - 1.0, 2.7)
ax.set_axis_off()
ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.02", fc="white", ec=NAVY, lw=1.4,
                            transform=ax.transAxes))
ax.text(0.015, 0.95, "What I see", fontsize=13, fontweight="bold", color=NAVY, va="top", transform=ax.transAxes)
ax.text(0.14, 0.945, "(full data, 1 Sep - 31 Oct)", fontsize=7.5, color="#666", va="top", transform=ax.transAxes)
colw = (1 - 0.03) / 3
for i, txt in enumerate(found):
    ax.text(0.015 + i * colw, 0.84, f"Finding {i + 1}", fontsize=9, fontweight="bold", va="top", transform=ax.transAxes)
    ax.text(0.015 + i * colw, 0.765, textwrap.fill(txt, 56), fontsize=8.2, va="top", linespacing=1.35,
            transform=ax.transAxes)
for i, txt in enumerate(acts):
    y = 0.36 - i * 0.16
    ax.text(0.015, y, f"Action {i + 1}", fontsize=9, fontweight="bold", color=ORANGE, va="top", transform=ax.transAxes)
    ax.text(0.095, y, textwrap.fill(txt, 150), fontsize=8.2, va="top", linespacing=1.3, transform=ax.transAxes)

# ------------------------------------------------------------------ charts
CW, CH, T1, T2, L1, L2 = 5.95, 3.55, 5.75, 9.95, 0.5, 7.6

# A. North Star
t = M.weekly(v)
ax = box(L1, T1 + 0.35, CW, CH - 0.45)
x = np.arange(len(t))
ax.bar(x, t["learners"], color=[LIGHT if p else NAVY for p in t["partial"]])
for xi, val, p in zip(x, t["learners"], t["partial"]):
    ax.text(xi, t["learners"].max() * 0.015, f"{val:,}", ha="center", va="bottom", fontsize=8.5,
            fontweight="bold", color=NAVY if p else "white")
ax.set_xticks(x, wk(t.index, t["partial"]), fontsize=8)
ax.set_ylim(0, t["learners"].max() * 1.2)
ax.set_ylabel("Weekly Learners", fontsize=8)
ax2 = ax.twinx()
ax2.spines["right"].set_visible(True)
ax2.plot(x, t["share"], color=ORANGE, marker="o", lw=2.5, label="Learners as % of weekly actives")
ax2.axhline(M.TARGETS["learner_share"], color=ORANGE, ls=":", lw=1)
ax2.set_ylim(0, 0.6)
ax2.yaxis.set_major_formatter(lambda y, _: f"{y:.0%}")
ax2.tick_params(labelsize=8)
ax2.legend(loc="upper right", fontsize=7.5, frameon=False)
ax.text(0.01, 0.97, "KPI uses the last FULL week (19 Oct). * = 6-day week, shown lighter.", transform=ax.transAxes,
        fontsize=7.5, style="italic", color="#555", va="top")
fig.text(L1 / W, 1 - (T1 + 0.12) / H, "North Star: Weekly Learners (bars) and share of weekly actives (line)",
         fontsize=10, fontweight="bold")

# B. Activation
a = M.activation_by_week(v)
ax = box(L2, T1 + 0.35, CW, CH - 0.45)
x = np.arange(len(a))
ax.plot(x, a["rate"], color=NAVY, marker="o", lw=2.8)
for xi, r in zip(x, a["rate"]):
    ax.text(xi, r + 0.025, f"{r:.0%}", ha="center", fontsize=8.5)
ax.axhline(M.TARGETS["activation"], color=GREEN, ls=":", lw=1.2)
ax.text(len(a) - 0.5, M.TARGETS["activation"] + 0.012, "target 45% (assumed)", ha="right", fontsize=7.5, color=GREEN)
ax.set_xticks(x, wk(a.index, a["partial"]), fontsize=8)
ax.set_ylim(0, 0.75)
ax.yaxis.set_major_formatter(lambda y, _: f"{y:.0%}")
ax.tick_params(labelsize=8)
fig.text(L2 / W, 1 - (T1 + 0.12) / H, "Did new students start learning? 7-day activation by install week",
         fontsize=10, fontweight="bold")

# C. Cost per activated student
ch = M.channel_table(v)
ch = ch[ch["source"].isin(M.PAID) & ch["cost_per_activated"].notna()].sort_values("cost_per_activated", ascending=True)
ax = box(L1 + 0.9, T2 + 0.35, CW - 0.95, CH - 0.55)
ax.barh(ch["source"], ch["cost_per_activated"], color=NAVY, height=0.55)
mx = ch["cost_per_activated"].max()
for i, r in enumerate(ch.itertuples()):
    ax.text(r.cost_per_activated + mx * 0.02, i, f"₹{r.cost_per_activated:,.0f}\n{r.activation:.0%} activate, n={r.mature_installs}",
            va="center", fontsize=8)
ax.axvline(M.TARGETS["cost_per_activated"], color=GREEN, ls=":", lw=1.2)
ax.text(M.TARGETS["cost_per_activated"] + mx * 0.02, -0.5, "target ₹1,500 (assumed)", fontsize=7.5, color=GREEN, ha="left")
ax.set_ylim(-0.6, len(ch) - 0.4)
ax.set_xlim(0, mx * 1.6)
ax.xaxis.set_major_formatter(lambda y, _: f"₹{y:,.0f}")
ax.tick_params(labelsize=8)
fig.text(L1 / W, 1 - (T2 + 0.12) / H, "What does an activated student cost? (paid channels)", fontsize=10, fontweight="bold")

# D. Completion
cp = M.completion(v).sort_values("rate", ascending=True)
ax = box(L2 + 1.1, T2 + 0.35, CW - 1.15, CH - 0.55)
ax.barh(cp["item"], cp["rate"], color=[RED if r < .4 else NAVY for r in cp["rate"]], height=0.55)
for i, r in enumerate(cp.itertuples()):
    ax.text(r.rate + 0.02, i, f"{r.rate:.0%}  ({r.completed:,} of {r.started:,})", va="center", fontsize=8.5)
ax.set_xlim(0, 1.15)
ax.xaxis.set_major_formatter(lambda y, _: f"{y:.0%}")
ax.tick_params(labelsize=8.5)
fig.text(L2 / W, 1 - (T2 + 0.12) / H, "Where do students leave? Finished / started", fontsize=10, fontweight="bold")

notes = [
    "North Star = Weekly Learners: distinct students with at least one practice test submitted, capsule completed or video completed in a Mon-Sun week. "
    "The KPI uses the last full week (19 Oct: 923); the 26 Oct bar (1,036) covers only 6 days and is not used for the KPI.",
    "7-day activation = a learning action within 7 days of the install date, for installs 1 Sep-24 Oct only (later installs have no full 7-day window). "
    "Cost per activated student = channel spend on those same days / activated students whose source is that channel "
    "(campaign installs match student sources exactly); organic and website QR have no spend in the data.",
    "Completion = completed / started events (the data has no session id to pair them); the student-level funnel is on page 2. "
    "All targets are ASSUMED, not benchmarks. Numbers cross-checked in SQL (verify_numbers.py, 20 checks).",
]
fig.text(0.5 / W, 1 - 13.75 / H, "\n".join(textwrap.fill(n, 190) for n in notes), fontsize=7.2, color="#444", va="top", linespacing=1.5)

# ------------------------------------------------------------------ page 2: engagement and retention
H2 = 10.6
fig2 = plt.figure(figsize=(W, H2))


def box2(l, t_, w, h):
    return fig2.add_axes([l / W, 1 - (t_ + h) / H2, w / W, h / H2])


fig2.text(0.5 / W, 1 - 0.45 / H2, "Aakash Daily - Engagement and retention (page 2)", fontsize=18, fontweight="bold", va="center")
fig2.text(0.5 / W, 1 - 0.85 / H2, "Supporting evidence for the findings on page 1. Same filters: all students, 1 Sep - 31 Oct 2026.",
          fontsize=9.5, color="#555", va="center")
P1, P2 = 1.3, 5.9

fu = M.conversion_funnel(v)
ax = box2(L1 + 2.9, P1 + 0.4, CW - 2.95, CH - 0.6)
ax.barh(range(len(fu)), fu["students"], color=NAVY, height=0.55)
ax.set_yticks(range(len(fu)), fu["step"], fontsize=8)
ax.invert_yaxis()
for i, r in enumerate(fu.itertuples()):
    ax.text(r.students + fu["students"].max() * 0.02, i, f"{r.students:,} ({r.pct_of_installs:.0%})", va="center", fontsize=8.5)
ax.set_xlim(0, fu["students"].max() * 1.35)
ax.tick_params(axis="x", labelsize=8)
fig2.text(L1 / W, 1 - (P1 + 0.12) / H2, "Student funnel, first 7 days after install", fontsize=10, fontweight="bold")
fig2.text(L1 / W, 1 - (P1 + CH + 0.3) / H2, "Installs up to 24 Oct (full 7-day window); each step is nested in the one above.", fontsize=7.5, color="#555")

rt = M.retention_table(v, by="source")
ax = box2(L2, P1 + 0.4, CW, CH - 0.6)
for g, d in rt.groupby("group", sort=False):
    d = d.dropna(subset=["rate"])
    if len(d):
        ax.plot(d["day"], d["rate"], marker="o", lw=3.2 if g == "All" else 1.6, color=NAVY if g == "All" else None, label=g)
ax.set_xticks(list(M.RET_DAYS))
ax.yaxis.set_major_formatter(lambda y, _: f"{y:.0%}")
ax.set_ylim(bottom=0)
ax.legend(fontsize=7.5, frameon=False, ncol=2)
ax.tick_params(labelsize=8)
ax.set_xlabel("days since install", fontsize=8)
fig2.text(L2 / W, 1 - (P1 + 0.12) / H2, "Retention: share of installs active exactly N days later", fontsize=10, fontweight="bold")

ts = M.test_start_rate_weekly(v)
ax = box2(L1, P2 + 0.4, CW, CH - 0.6)
x = np.arange(len(ts))
ax.plot(x, ts["tests_started_per_100_opens"], color=NAVY, marker="o", lw=2.8)
ax.set_ylim(0, 60)
ax.set_ylabel("tests started per 100 opens", fontsize=8)
ax.set_xticks(x, wk(ts.index, ts["days"] < 7), fontsize=8)
ax3 = ax.twinx()
ax3.spines["right"].set_visible(True)
ax3.plot(x, ts["test_submit_rate"], color=ORANGE, marker="o", lw=1.8)
ax3.set_ylim(0, 1)
ax3.yaxis.set_major_formatter(lambda y, _: f"{y:.0%}")
ax3.tick_params(labelsize=8)
fig2.text(L1 / W, 1 - (P2 + 0.12) / H2, "Why activation fell: fewer test starts (navy), same finish rate (orange)", fontsize=10, fontweight="bold")

hrs = M.events_by_hour(v)
ax = box2(L2, P2 + 0.4, CW, CH - 0.6)
ax.bar(hrs.index, hrs.values, color=[ORANGE if 18 <= h <= 22 else NAVY for h in hrs.index])
ax.set_xticks(range(0, 24, 2))
ax.set_xlabel("hour of day (IST); orange = 6-11pm", fontsize=8)
ax.tick_params(labelsize=8)
share = hrs.loc[18:22].sum() / hrs.sum()
fig2.text(L2 / W, 1 - (P2 + 0.12) / H2, f"When do students use the app? {share:.0%} of activity is 6-11pm", fontsize=10, fontweight="bold")

with PdfPages("dashboard.pdf") as pdf:
    pdf.savefig(fig)
    pdf.savefig(fig2)
fig.savefig("dashboard.png", dpi=130)
fig2.savefig("dashboard_page2.png", dpi=130)
print("wrote dashboard.pdf (2 pages), dashboard.png, dashboard_page2.png")
