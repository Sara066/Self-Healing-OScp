"""
Phase 5 — Diagnosis

Detection only says "something is off" (is_anomaly). This module answers
"what, probably" using simple rule-based logic over which metrics are
driving the anomaly -- deliberately NOT ML, per the design: rule-based is
easier to justify, easier to demo, and needs no labeled multi-class
training set.

Rules (checked in order, first match wins):
  1. thread count more than double normal ceiling -> "abnormal_combo"
     (most exclusive signal -- never true for genuine thrashing/runaway)
  2. memory usage AND page-fault rate both above their normal-range
     ceiling -> "thrashing"
  3. one pid dominating the CPU almost every tick in a recent window
     -> "runaway_cpu" (least specific -- checked last since ANY
     long-lived process ends up dominating once others finish)
  4. anomaly flagged but none of the above fit -> "unknown_anomaly"
"""

import pandas as pd

FEATURE_COLS = ["cpu_pct", "queue_total", "avg_wait",
                "thread_count_running", "mem_used_pct", "page_faults_tick",
                "mem_used_pct_roll", "page_faults_roll"]


def build_normal_stats(train_df: pd.DataFrame, feature_cols=FEATURE_COLS) -> dict:
    """Baseline stats from the normal-only training set -- the 'what's typical' reference."""
    stats = {}
    for c in feature_cols:
        s = train_df[c]
        stats[c] = {
            "mean": s.mean(), "std": s.std(),
            "p75": s.quantile(0.75), "p95": s.quantile(0.95),
        }
    return stats


def add_pid_dominance(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """
    For each tick, what fraction of the last `window` ticks (within the
    same run_id) had the same running_pid. Near 1.0 = one process is
    monopolizing the CPU, the runaway-CPU signature.
    """
    df = df.copy()
    dom = pd.Series(0.0, index=df.index)
    for run_id, grp in df.groupby("run_id"):
        pids = grp["running_pid"].tolist()
        idxs = grp.index.tolist()
        for i, idx in enumerate(idxs):
            start = max(0, i - window + 1)
            chunk = pids[start:i + 1]
            cur = pids[i]
            dom.at[idx] = chunk.count(cur) / len(chunk) if cur is not None else 0.0
    df["pid_dominance"] = dom
    return df


def diagnose_row(row, normal_stats: dict) -> str:
    if not row.get("is_anomaly", False):
        return "none"

    runaway = row["pid_dominance"] >= 0.9
    # thread_count_running more than double the normal p95 is decisive on its
    # own and never occurs for genuine thrashing (thread_count=1 there) --
    # mem_used_pct is dropped from this condition because it's a
    # system-wide figure that fluctuates with unrelated processes finishing,
    # not a property of the flagged process itself, so it made this rule
    # flicker on/off mid-run even while thread_count stayed constant.
    combo = row["thread_count_running"] >= normal_stats["thread_count_running"]["p95"] * 2
    # Rolling-smoothed versions, matching what the detector now scores on --
    # using raw single-tick values here would flag ticks as anomalous
    # (via the smoothed signal) that then fail this raw-valued check,
    # falling through to "unknown_anomaly" even though thrashing is
    # exactly what's happening.
    thrashing = (row["mem_used_pct_roll"] >= normal_stats["mem_used_pct_roll"]["p95"] and
                 row["page_faults_roll"] >= normal_stats["page_faults_roll"]["p75"] * 2)

    # Check the most exclusive signal first. combo's thread-count signature
    # (>2x normal ceiling) never occurs for genuine thrashing or runaway
    # processes, so it's checked before thrashing -- otherwise the combo
    # process's own elevated memory footprint can coincidentally also clear
    # the thrashing threshold and steal the diagnosis. Dominance is checked
    # last since it's the least specific signal: ANY long-lived process
    # (true runaway, thrashing, or combo) ends up with dominance near 1.0
    # once every other process in the run has finished.
    if combo:
        return "abnormal_combo"
    if thrashing:
        return "thrashing"
    if runaway:
        return "runaway_cpu"
    return "unknown_anomaly"


def diagnose_dataframe(df: pd.DataFrame, normal_stats: dict) -> pd.DataFrame:
    df = add_pid_dominance(df)
    df["diagnosis"] = df.apply(lambda r: diagnose_row(r, normal_stats), axis=1)
    return df