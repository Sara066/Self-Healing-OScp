"""
Standalone, textbook-style Multi-Level Feedback Queue -- Unit 2 syllabus.

Independent of scheduler.py (the 2-level MLFQ-lite inside the self-healing
pipeline, where a process only ever moves to the low queue via an explicit
anomaly-recovery action, not automatic scheduling policy). That scheduler's
behavior is already tuned and validated against the anomaly detection
pipeline's eval numbers, so it's deliberately left untouched.

This module implements genuine MLFQ feedback instead:
  - a process that exhausts its full quantum without finishing is demoted
    one level (assumed CPU-bound) -- automatic, not anomaly-triggered
  - a process that's waited too long without running is promoted back up
    one level (aging), preventing starvation at the bottom level

3 levels, decreasing priority, increasing quantum (standard textbook shape):
  level 0: quantum 4   (highest priority, shortest slice)
  level 1: quantum 8
  level 2: quantum 16  (effectively long-running/CPU-bound jobs)
"""

from collections import deque
from typing import List, Dict

from pcb import PCB, ProcState

QUANTUMS = [4, 8, 16]
AGING_THRESHOLD = 20  # ticks waited without running before promotion


class MLFQScheduler:
    def __init__(self, processes: List[PCB]):
        self.tick = 0
        self.all_processes: Dict[int, PCB] = {p.pid: p for p in processes}
        self.queues = [deque() for _ in QUANTUMS]
        self.level: Dict[int, int] = {}
        self.quantum_left: Dict[int, int] = {}
        self.wait_since_ran: Dict[int, int] = {p.pid: 0 for p in processes}
        self.log = []

        self._pending = sorted([p for p in processes if p.arrival_tick > 0],
                                key=lambda p: p.arrival_tick)
        for p in processes:
            if p.arrival_tick <= 0:
                self._admit(p, level=0)

    def _admit(self, p: PCB, level: int):
        p.state = ProcState.READY
        self.level[p.pid] = level
        self.quantum_left[p.pid] = QUANTUMS[level]
        self.queues[level].append(p.pid)

    def _pick(self):
        for lvl, q in enumerate(self.queues):
            if q:
                return lvl, q
        return None, None

    def step(self):
        self.tick += 1

        while self._pending and self._pending[0].arrival_tick <= self.tick:
            self._admit(self._pending.pop(0), level=0)

        # aging: promote anyone who's waited too long below the top level
        for pid, waited in list(self.wait_since_ran.items()):
            p = self.all_processes[pid]
            if p.is_alive() and self.level.get(pid, 0) > 0 and waited >= AGING_THRESHOLD:
                old_level = self.level[pid]
                if pid in self.queues[old_level]:
                    self.queues[old_level].remove(pid)
                    self.level[pid] = old_level - 1
                    self.quantum_left[pid] = QUANTUMS[self.level[pid]]
                    self.queues[self.level[pid]].append(pid)
                    self.wait_since_ran[pid] = 0

        level, queue = self._pick()
        running_pid = None

        if queue:
            pid = queue.popleft()
            p = self.all_processes[pid]
            p.state = ProcState.RUNNING
            running_pid = pid
            if p.start_tick is None:
                p.start_tick = self.tick

            p.burst_remaining -= 1
            self.quantum_left[pid] -= 1
            self.wait_since_ran[pid] = 0

            if p.burst_remaining <= 0:
                p.state = ProcState.TERMINATED
                p.finish_tick = self.tick
            elif self.quantum_left[pid] <= 0:
                # used the full quantum without finishing -> demote one level
                new_level = min(level + 1, len(QUANTUMS) - 1)
                self.level[pid] = new_level
                self.quantum_left[pid] = QUANTUMS[new_level]
                p.state = ProcState.READY
                self.queues[new_level].append(pid)
            else:
                p.state = ProcState.READY
                queue.append(pid)

        for pid, p in self.all_processes.items():
            if p.is_alive() and pid != running_pid:
                p.wait_ticks += 1
                self.wait_since_ran[pid] = self.wait_since_ran.get(pid, 0) + 1

        self.log.append({
            "tick": self.tick,
            "running_pid": running_pid,
            "level": level,
            "queue_lens": [len(q) for q in self.queues],
        })

    def run(self, max_ticks: int = 500):
        for _ in range(max_ticks):
            if not any(self.queues) and not self._pending:
                if all(not p.is_alive() for p in self.all_processes.values()):
                    break
            self.step()
        return self.log
