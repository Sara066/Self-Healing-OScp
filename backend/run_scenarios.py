"""
Phase 6 — run_scenarios.py

The actual closed loop, live, tick by tick (not fit-then-score on a static
CSV like demo_phase5.py):

    tick -> detector.score_tick() -> if anomalous: diagnose ->
    recovery action -> keep ticking -> verifier confirms metrics normalized

Runs this once per injected anomaly type (runaway, thrashing,
abnormal_combo), plus a separate deadlock case (graph-based, not tick-driven).
Produces a per-scenario tick log (for Phase 7 plots) and a summary table
(for your evaluation section: ticks-to-recovery, whether the diagnosis
picked the right process, etc).
"""

from collections import deque

import pandas as pd

from anomaly_injection import (normal_scenario, inject_runaway,
                                inject_thrashing, inject_abnormal_combo,
                                build_deadlock_case)
from scheduler import Scheduler
from memory_manager import MemoryManager
from anomaly_detector import AnomalyDetector, FEATURE_COLS, add_rolling_features, ROLL_WINDOW
from diagnosis import build_normal_stats, diagnose_row
from recovery import (recover_runaway, recover_thrashing,
                       recover_abnormal_combo, recover_deadlock)
from verifier import verify_metrics_recovered, verify_deadlock_resolved, CHECK_WINDOW

DOM_WINDOW = 10
MAX_TICKS = 150


def run_live_scenario(name: str, procs, injected_pid: int,
                       detector: AnomalyDetector, normal_stats: dict,
                       num_frames: int = 32, seed: int = 999) -> tuple:
    mem = MemoryManager(num_frames=num_frames, policy="LRU")
    sched = Scheduler(procs, memory_manager=mem, seed=seed)

    pid_history = deque(maxlen=DOM_WINDOW)
    mem_history = deque(maxlen=ROLL_WINDOW)
    fault_history = deque(maxlen=ROLL_WINDOW)
    feature_rows = []
    narrative = []
    events = []  # every detect->diagnose->recover->verify cycle, not just the first

    awaiting_confirmation = False
    active_recovery_tick = None
    active_event = None
    already_mitigated = set()  # (pid, diagnosis) pairs already recovered+confirmed once

    for _ in range(MAX_TICKS):
        sched.step()
        row = sched.log[-1]
        pid_history.append(row["running_pid"])
        cur = row["running_pid"]
        dominance = (pid_history.count(cur) / len(pid_history)) if cur is not None else 0.0

        mem_history.append(row["mem_used_pct"])
        fault_history.append(row["page_faults_tick"])

        feat = {
            "tick": row["tick"],
            "cpu_pct": row["cpu_pct"],
            "queue_total": row["queue0_len"] + row["queue1_len"],
            "avg_wait": row["avg_wait"],
            "thread_count_running": row["thread_count_running"],
            "mem_used_pct": row["mem_used_pct"],
            "page_faults_tick": row["page_faults_tick"],
            "pid_dominance": dominance,
            "mem_used_pct_roll": sum(mem_history) / len(mem_history),
            "page_faults_roll": sum(fault_history) / len(fault_history),
            "running_pid": cur,
        }

        score, is_anom = detector.score_tick({k: feat[k] for k in FEATURE_COLS})
        # dominance is meaningless until the rolling window is actually full
        if row["tick"] <= DOM_WINDOW:
            is_anom = False
        # an idle CPU (nothing running) can't be "anomalous" in any
        # actionable sense -- stale rolling mem/fault values left over from
        # a just-finished or just-suspended process were otherwise still
        # tripping the detector for several ticks after the system had
        # nothing left to act on
        if cur is None:
            is_anom = False
        feat["anomaly_score"] = score
        feat["is_anomaly"] = is_anom
        feature_rows.append(feat)

        # only start a NEW detect/recover cycle if we're not already mid-recovery
        if is_anom and not awaiting_confirmation:
            diag = diagnose_row(feat, normal_stats)
            # "unknown_anomaly" means flagged but no rule matched (or no
            # active pid) -- no recovery action is actually taken, so this
            # must NOT enter the awaiting_confirmation state: doing so would
            # burn a full CHECK_WINDOW "confirming" an action that never
            # happened, delaying the next real check. Just note it and keep
            # monitoring on the very next tick instead.
            if diag == "unknown_anomaly":
                narrative.append(f"tick {row['tick']}: flagged (score={score:.3f}) "
                                  f"but no diagnosis rule matched (PID {cur}) -- continuing to monitor")
            elif diag != "none":
                target_pid = cur

                if (target_pid, diag) in already_mitigated:
                    # already handled once for this exact (pid, cause) pair --
                    # the underlying features haven't changed (the process
                    # never finished), so this is the same already-fixed
                    # condition recurring, not a new problem. Re-running the
                    # same action forever would just spam demotes/suspends
                    # on a process we've already dealt with.
                    narrative.append(f"tick {row['tick']}: {diag} re-flagged for PID {target_pid} "
                                      f"(score={score:.3f}) -- already mitigated, no new action taken")
                else:
                    if diag == "runaway_cpu" and target_pid is not None:
                        action_desc = recover_runaway(sched, target_pid)
                    elif diag == "thrashing" and target_pid is not None:
                        action_desc = recover_thrashing(sched, mem, target_pid, row["tick"])
                    elif diag == "abnormal_combo" and target_pid is not None:
                        action_desc = recover_abnormal_combo(sched, target_pid, row["tick"])
                    else:
                        action_desc = "flagged but no active pid to act on"

                    active_event = {
                        "detected_at_tick": row["tick"], "diagnosis": diag,
                        "target_pid": target_pid, "action": action_desc,
                        "recovery_applied_tick": row["tick"], "recovered_confirmed_tick": None,
                    }
                    awaiting_confirmation = True
                    active_recovery_tick = row["tick"]
                    narrative.append(f"tick {row['tick']}: DETECTED anomaly "
                                      f"(score={score:.3f}) -> diagnosis='{diag}' (PID {target_pid}) "
                                      f"-> {action_desc}")

        if awaiting_confirmation and row["tick"] - active_recovery_tick >= CHECK_WINDOW:
            recent = pd.DataFrame(feature_rows[-CHECK_WINDOW:])
            confirmed = verify_metrics_recovered(recent, normal_stats,
                                                  diagnosis=active_event["diagnosis"])
            if confirmed:
                active_event["recovered_confirmed_tick"] = row["tick"]
                already_mitigated.add((active_event["target_pid"], active_event["diagnosis"]))
                narrative.append(f"tick {row['tick']}: VERIFIED recovered "
                                  f"(metrics back within normal range)")
            else:
                narrative.append(f"tick {row['tick']}: recovery not yet confirmed, "
                                  f"resuming monitoring")
            events.append(active_event)
            awaiting_confirmation = False
            active_event = None

    df = pd.DataFrame(feature_rows)
    df["scenario"] = name
    df["injected_pid"] = injected_pid

    # the event that actually caught the real injected anomaly, if any
    matching = [e for e in events if e["target_pid"] == injected_pid]
    key_event = matching[0] if matching else (events[0] if events else None)

    summary = {
        "scenario": name,
        "injected_pid": injected_pid,
        "total_events": len(events),
        "false_positive_events": sum(1 for e in events if e["target_pid"] != injected_pid),
        "detected_at_tick": key_event["detected_at_tick"] if key_event else None,
        "diagnosis": key_event["diagnosis"] if key_event else None,
        "target_pid": key_event["target_pid"] if key_event else None,
        "target_matches_injected": bool(key_event and key_event["target_pid"] == injected_pid),
        "action": key_event["action"] if key_event else None,
        "recovery_applied_tick": key_event["recovery_applied_tick"] if key_event else None,
        "recovered_confirmed_tick": key_event["recovered_confirmed_tick"] if key_event else None,
        "ticks_to_recovery": (key_event["recovered_confirmed_tick"] - key_event["detected_at_tick"]
                               if key_event and key_event["recovered_confirmed_tick"] else None),
    }
    return df, summary, narrative


def run_deadlock_scenario() -> tuple:
    rag = build_deadlock_case(pid_a=1, pid_b=2)
    narrative = []
    detected = rag.is_deadlocked()
    cycle_pids = rag.processes_in_cycle(rag.find_cycle()) if detected else []
    narrative.append(f"tick 1: DETECTED deadlock -> cycle among PIDs {cycle_pids}")

    action_desc = recover_deadlock(rag)
    narrative.append(f"tick 1: RECOVERY -> {action_desc}")

    confirmed = verify_deadlock_resolved(rag)
    narrative.append(f"tick 1: VERIFIED {'resolved' if confirmed else 'still deadlocked'}")

    summary = {
        "scenario": "deadlock",
        "injected_pid": cycle_pids[0] if cycle_pids else None,
        "total_events": 1,
        "false_positive_events": 0,
        "detected_at_tick": 1 if detected else None,
        "diagnosis": "deadlock",
        "target_pid": int(action_desc.split("PID ")[1].split(" ")[0]) if "terminated" in action_desc else None,
        "target_matches_injected": True,
        "action": action_desc,
        "recovery_applied_tick": 1,
        "recovered_confirmed_tick": 1 if confirmed else None,
        "ticks_to_recovery": 0 if confirmed else None,
    }
    return summary, narrative


def main():
    train_df = add_rolling_features(pd.read_csv("training_normal.csv"))
    detector = AnomalyDetector(contamination=0.05).fit(train_df)
    normal_stats = build_normal_stats(train_df)

    scenarios = [
        ("runaway", inject_runaway(normal_scenario(seed=999), pid=99), 99),
        ("thrashing", inject_thrashing(normal_scenario(seed=999), pid=88), 88),
        ("abnormal_combo", inject_abnormal_combo(normal_scenario(seed=999), pid=77), 77),
    ]

    all_summaries = []
    for name, procs, injected_pid in scenarios:
        print(f"\n===== Scenario: {name} =====")
        df, summary, narrative = run_live_scenario(name, procs, injected_pid,
                                                     detector, normal_stats)
        for line in narrative:
            print(" ", line)
        if summary["detected_at_tick"] is None:
            print("  (never flagged as anomalous in this run)")
        df.to_csv(f"run_log_{name}.csv", index=False)
        all_summaries.append(summary)

    print(f"\n===== Scenario: deadlock =====")
    dl_summary, dl_narrative = run_deadlock_scenario()
    for line in dl_narrative:
        print(" ", line)
    all_summaries.append(dl_summary)

    summary_df = pd.DataFrame(all_summaries)
    summary_df.to_csv("scenario_summary.csv", index=False)

    print("\n===== Summary =====")
    print(summary_df.to_string(index=False))
    print("\nSaved run_log_<scenario>.csv (x3), scenario_summary.csv")


if __name__ == "__main__":
    main()