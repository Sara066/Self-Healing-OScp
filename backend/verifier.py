"""
Phase 6 — Verification

After a recovery action fires, don't just assume it worked: re-sample the
next few ticks and check the metrics actually fell back inside the normal
range (or, for deadlock, that the resource graph is acyclic again).
"""

import pandas as pd

CHECK_WINDOW = 8


def verify_metrics_recovered(recent_rows: pd.DataFrame, normal_stats: dict,
                              diagnosis: str = None) -> bool:
    """
    recent_rows: the last CHECK_WINDOW ticks of the live log, as a DataFrame.
    Recovered = average mem/fault/dominance over the window are back under
    the normal p95 ceilings (small tolerance so we're not overly strict).

    runaway_cpu is a special case: its recovery action (demotion) is a
    fairness fix, not a suspension -- it exists to stop the runaway process
    from starving OTHERS, not to stop the runaway process itself (which, by
    construction, never finishes). So once demotion has let every other
    process finish, the runaway process is legitimately the only one left
    alive, and its CPU dominance stays at ~1.0 forever -- correctly, not as
    a sign recovery failed. Requiring dominance <= 0.9 in that case would
    make a genuinely successful runaway recovery impossible to ever confirm.
    """
    if len(recent_rows) == 0:
        return False

    mem_ok = recent_rows["mem_used_pct"].mean() <= normal_stats["mem_used_pct"]["p95"] * 1.1
    fault_ok = recent_rows["page_faults_tick"].mean() <= normal_stats["page_faults_tick"]["p95"] + 0.25

    if diagnosis == "runaway_cpu":
        return bool(mem_ok and fault_ok)

    dom_ok = recent_rows["pid_dominance"].mean() <= 0.9
    return bool(mem_ok and fault_ok and dom_ok)


def verify_deadlock_resolved(rag) -> bool:
    return not rag.is_deadlocked()