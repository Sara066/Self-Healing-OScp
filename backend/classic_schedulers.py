"""
Classic CPU scheduling algorithms — Unit 2 syllabus coverage.

These are separate from scheduler.py (the tick-based 2-level MLFQ-lite used
inside the self-healing pipeline, where demotion is driven by anomaly
recovery, not automatic scheduling policy). That scheduler is already
validated end-to-end against the anomaly detection/diagnosis/recovery
pipeline, so it's deliberately left untouched here to avoid re-breaking
those tuned results.

This module instead implements the algorithms directly, as arrival-aware
batch schedulers (not tick-simulated) — the standard, hand-verifiable way
these are taught. Used for the algorithm-comparison demo
(demo_scheduling_comparison.py), not wired into the self-healing loop.

Note: PCB.priority here means the classic scheduling sense (lower number =
runs first, arbitrary range) -- different from scheduler.py's PCB.priority,
which is just a binary 0/1 queue-level flag. Same dataclass, different use.
"""

from dataclasses import dataclass
from typing import List, Dict
from pcb import PCB


@dataclass
class ScheduleResult:
    order: List[int]     # pids in the order they ran (Gantt chart sequence)
    start: Dict[int, int]
    finish: Dict[int, int]
    waiting: Dict[int, int]
    turnaround: Dict[int, int]

    def avg_waiting(self) -> float:
        return sum(self.waiting.values()) / len(self.waiting)

    def avg_turnaround(self) -> float:
        return sum(self.turnaround.values()) / len(self.turnaround)


def _finalize(order, start, finish, arrival, burst) -> ScheduleResult:
    waiting, turnaround = {}, {}
    for pid in start:
        turnaround[pid] = finish[pid] - arrival[pid]
        waiting[pid] = turnaround[pid] - burst[pid]
    return ScheduleResult(order, start, finish, waiting, turnaround)


def fcfs_schedule(processes: List[PCB]) -> ScheduleResult:
    """First-Come-First-Served: run in arrival order, no preemption."""
    procs = sorted(processes, key=lambda p: p.arrival_tick)
    arrival = {p.pid: p.arrival_tick for p in procs}
    burst = {p.pid: p.total_burst for p in procs}

    time = 0
    order, start, finish = [], {}, {}
    for p in procs:
        time = max(time, p.arrival_tick)
        start[p.pid] = time
        time += p.total_burst
        finish[p.pid] = time
        order.append(p.pid)

    return _finalize(order, start, finish, arrival, burst)


def sjf_schedule(processes: List[PCB]) -> ScheduleResult:
    """Non-preemptive Shortest-Job-First: among arrived, unfinished
    processes, always run the one with the smallest total burst next."""
    remaining = list(processes)
    arrival = {p.pid: p.arrival_tick for p in processes}
    burst = {p.pid: p.total_burst for p in processes}

    time = 0
    order, start, finish = [], {}, {}
    while remaining:
        ready = [p for p in remaining if p.arrival_tick <= time]
        if not ready:
            time = min(p.arrival_tick for p in remaining)
            continue
        nxt = min(ready, key=lambda p: (p.total_burst, p.arrival_tick))
        start[nxt.pid] = time
        time += nxt.total_burst
        finish[nxt.pid] = time
        order.append(nxt.pid)
        remaining.remove(nxt)

    return _finalize(order, start, finish, arrival, burst)


def priority_schedule(processes: List[PCB]) -> ScheduleResult:
    """Non-preemptive priority scheduling: lower `priority` number runs
    first among arrived, unfinished processes. Ties broken by arrival."""
    remaining = list(processes)
    arrival = {p.pid: p.arrival_tick for p in processes}
    burst = {p.pid: p.total_burst for p in processes}

    time = 0
    order, start, finish = [], {}, {}
    while remaining:
        ready = [p for p in remaining if p.arrival_tick <= time]
        if not ready:
            time = min(p.arrival_tick for p in remaining)
            continue
        nxt = min(ready, key=lambda p: (p.priority, p.arrival_tick))
        start[nxt.pid] = time
        time += nxt.total_burst
        finish[nxt.pid] = time
        order.append(nxt.pid)
        remaining.remove(nxt)

    return _finalize(order, start, finish, arrival, burst)


def round_robin_schedule(processes: List[PCB], quantum: int) -> ScheduleResult:
    """Preemptive Round Robin with arrival-time support. Independent
    reference implementation for the comparison table (separate from the
    tick-based scheduler.py, which additionally integrates memory
    management and anomaly recovery)."""
    from collections import deque

    procs = sorted(processes, key=lambda p: p.arrival_tick)
    arrival = {p.pid: p.arrival_tick for p in processes}
    burst = {p.pid: p.total_burst for p in processes}
    remaining_burst = {p.pid: p.total_burst for p in processes}

    time = 0
    queue = deque()
    order, start, finish = [], {}, {}
    not_yet_arrived = list(procs)

    def admit():
        while not_yet_arrived and not_yet_arrived[0].arrival_tick <= time:
            queue.append(not_yet_arrived.pop(0).pid)

    admit()
    while queue or not_yet_arrived:
        if not queue:
            time = not_yet_arrived[0].arrival_tick
            admit()
            continue
        pid = queue.popleft()
        if pid not in start:
            start[pid] = time
        run_for = min(quantum, remaining_burst[pid])
        time += run_for
        remaining_burst[pid] -= run_for
        order.append(pid)
        admit()
        if remaining_burst[pid] == 0:
            finish[pid] = time
        else:
            queue.append(pid)

    return _finalize(order, start, finish, arrival, burst)
