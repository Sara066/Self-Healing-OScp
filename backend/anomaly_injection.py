"""
Phase 4 — Anomaly injection

Scenario builders. Every scenario returns a list of PCBs; "normal" ones
are randomized within sane ranges, "bad" ones are deliberately injected
with a parameter that pushes them outside the normal feature distribution
(so Isolation Forest in Phase 5 has something real to flag).

Deadlock is NOT included here as a PCB thing — per the design, deadlock
is detected deterministically via the resource-allocation graph
(deadlock.py), not statistically. build_deadlock_case() below builds a
RAG directly, mirroring demo_phase3.py.
"""

import random
from typing import List, Tuple

from pcb import PCB
from deadlock import ResourceAllocationGraph


# ---------- normal population ----------

def normal_scenario(num_procs: int = 5, seed: int = 0) -> List[PCB]:
    rng = random.Random(seed)
    procs = []
    for i in range(num_procs):
        pid = i + 1
        procs.append(PCB(
            pid=pid,
            priority=0,
            total_burst=rng.randint(6, 20),
            memory_footprint=rng.randint(1, 3),
            thread_count=rng.randint(1, 3),
        ))
    return procs


# ---------- injected anomalies (CPU/memory-visible, ML-detectable) ----------

def inject_runaway(procs: List[PCB], pid: int = 99) -> List[PCB]:
    """One process whose burst never decreases -> CPU% pinned high forever."""
    procs = list(procs)
    procs.append(PCB(pid=pid, priority=0, total_burst=999,
                      memory_footprint=2, thread_count=1, is_runaway=True))
    return procs


def inject_thrashing(procs: List[PCB], pid: int = 88, footprint: int = 50) -> List[PCB]:
    """One process wanting far more pages than fit -> constant fault/evict."""
    procs = list(procs)
    procs.append(PCB(pid=pid, priority=0, total_burst=40,
                      memory_footprint=footprint, thread_count=1))
    return procs


def inject_abnormal_combo(procs: List[PCB], pid: int = 77) -> List[PCB]:
    """
    Odd combination that doesn't match any normal profile: long-running,
    memory-heavy AND thread-heavy at once. No single feature is extreme,
    but the combination is — this is the case rule-based diagnosis (Phase 5)
    has to reason about beyond "which single metric spiked".
    """
    procs = list(procs)
    procs.append(PCB(pid=pid, priority=0, total_burst=60,
                      memory_footprint=10, thread_count=12))
    return procs


# ---------- deadlock (graph-based, not ML) ----------

def build_deadlock_case(pid_a: int = 1, pid_b: int = 2,
                         res_a: str = "lockA", res_b: str = "lockB"
                         ) -> ResourceAllocationGraph:
    """Two processes in a genuine circular wait over two resources."""
    rag = ResourceAllocationGraph()
    rag.request(pid_a, res_a)
    rag.allocate(pid_a, res_a)
    rag.request(pid_a, res_b)

    rag.request(pid_b, res_b)
    rag.allocate(pid_b, res_b)
    rag.request(pid_b, res_a)
    return rag


SCENARIOS = {
    "normal": lambda seed=0: normal_scenario(seed=seed),
    "runaway": lambda seed=0: inject_runaway(normal_scenario(seed=seed)),
    "thrashing": lambda seed=0: inject_thrashing(normal_scenario(seed=seed)),
    "abnormal_combo": lambda seed=0: inject_abnormal_combo(normal_scenario(seed=seed)),
}