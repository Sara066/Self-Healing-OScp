"""
Phase 1 — Scheduler + tick loop

2-level MLFQ-lite:
  queue 0 (high priority) — quantum = HIGH_QUANTUM, round robin
  queue 1 (low priority)  — quantum = LOW_QUANTUM,  round robin
A process that gets demoted (recovery action, Phase 6) drops from
queue 0 -> queue 1 and stays there.

Each tick we:
  1. pick the next process to run (queue 0 first, else queue 1)
  2. run it for min(quantum, burst_remaining) ticks -> but since this is a
     tick-based sim, "run for 1 tick" per call keeps the loop simple and
     still produces correct RR behavior when driven N times.
  3. update state / requeue
  4. log system-wide metrics for this tick (this row IS your synthetic /proc)
"""

import random
from collections import deque
from typing import List, Dict, Any

from pcb import PCB, ProcState


class Scheduler:
    HIGH_QUANTUM = 4
    LOW_QUANTUM = 8

    def __init__(self, processes: List[PCB], seed: int = 42, memory_manager=None):
        self.tick = 0
        self.all_processes: Dict[int, PCB] = {p.pid: p for p in processes}
        self.queue0 = deque()   # high priority
        self.queue1 = deque()   # low priority (demoted or born low)
        self.rng = random.Random(seed)
        self.log: List[Dict[str, Any]] = []
        self.mem = memory_manager  # optional: Phase 2 memory_manager.MemoryManager

        for p in processes:
            p.state = ProcState.READY
            (self.queue0 if p.priority == 0 else self.queue1).append(p.pid)
            if self.mem is not None:
                self.mem.register_process(p.pid)

        self._quantum_left: Dict[int, int] = {}

    # ---------- recovery hooks (used from Phase 6 onward) ----------

    def demote(self, pid: int):
        """Move a runaway process to the low-priority queue."""
        p = self.all_processes[pid]
        if p.priority == 0:
            p.priority = 1
            if pid in self.queue0:
                self.queue0.remove(pid)
            if p.state != ProcState.TERMINATED and pid not in self.queue1:
                self.queue1.append(pid)

    def suspend(self, pid: int, until_tick: int):
        """Pull a process out of scheduling entirely for a while."""
        p = self.all_processes[pid]
        p.suspended_until = until_tick
        p.state = ProcState.WAITING
        for q in (self.queue0, self.queue1):
            if pid in q:
                q.remove(pid)

    # ---------- core loop ----------

    def _pick_queue(self):
        if self.queue0:
            return self.queue0, 0
        if self.queue1:
            return self.queue1, 1
        return None, None

    def step(self):
        """Advance the simulation by exactly one tick."""
        self.tick += 1
        if self.mem is not None:
            self.mem.tick_reset()

        # wake up anyone whose suspension has expired
        for p in self.all_processes.values():
            if (p.suspended_until is not None and self.tick >= p.suspended_until
                    and p.state == ProcState.WAITING):
                p.suspended_until = None
                p.state = ProcState.READY
                (self.queue0 if p.priority == 0 else self.queue1).append(p.pid)

        queue, qlevel = self._pick_queue()
        running_pid = None

        if queue:
            pid = queue.popleft()
            p = self.all_processes[pid]

            if p.state == ProcState.WAITING:
                # picked up mid-suspension edge case, skip this tick
                queue.append(pid)
            else:
                p.state = ProcState.RUNNING
                running_pid = pid
                if p.start_tick is None:
                    p.start_tick = self.tick

                if self.mem is not None and p.memory_footprint > 0:
                    page = self.rng.randrange(p.memory_footprint)
                    self.mem.access(pid, page)

                # a runaway process misbehaves: it "does work" but its
                # burst_remaining doesn't drop the normal way
                if p.is_runaway:
                    p.burst_remaining = max(p.burst_remaining, p.total_burst)
                else:
                    p.burst_remaining -= 1

                quantum = self.HIGH_QUANTUM if qlevel == 0 else self.LOW_QUANTUM
                used = self._quantum_left.get(pid, quantum) - 1

                if p.burst_remaining <= 0 and not p.is_runaway:
                    p.state = ProcState.TERMINATED
                    p.finish_tick = self.tick
                    self._quantum_left.pop(pid, None)
                    if self.mem is not None:
                        self.mem.release_process(pid)
                elif used <= 0:
                    # quantum expired -> back of its own queue
                    self._quantum_left[pid] = quantum
                    p.state = ProcState.READY
                    queue.append(pid)
                else:
                    self._quantum_left[pid] = used
                    p.state = ProcState.READY
                    queue.append(pid)

        # everyone else still alive & not running this tick accrues wait time
        for p in self.all_processes.values():
            if p.is_alive() and p.pid != running_pid and p.state != ProcState.WAITING:
                p.wait_ticks += 1

        self._log_tick(running_pid)

    def _log_tick(self, running_pid):
        alive = [p for p in self.all_processes.values() if p.is_alive()]
        cpu_pct = 100.0 if running_pid is not None else 0.0
        row = {
            "tick": self.tick,
            "running_pid": running_pid,
            "cpu_pct": cpu_pct,
            "queue0_len": len(self.queue0),
            "queue1_len": len(self.queue1),
            "num_alive": len(alive),
            "avg_wait": (sum(p.wait_ticks for p in alive) / len(alive)) if alive else 0.0,
            "thread_count_running": (self.all_processes[running_pid].thread_count
                                      if running_pid is not None else 0),
        }
        if self.mem is not None:
            row.update(self.mem.snapshot())
        self.log.append(row)

    def run(self, max_ticks: int = 200):
        for _ in range(max_ticks):
            if not self.queue0 and not self.queue1:
                if all(not p.is_alive() for p in self.all_processes.values()):
                    break
            self.step()
        return self.log