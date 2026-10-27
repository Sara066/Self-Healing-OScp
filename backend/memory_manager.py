"""
Phase 2 — Memory Manager

Simulated physical memory as a fixed pool of frames. Each process has its
own page table (virtual page -> frame, or None if not resident). On every
CPU tick, the currently-running process "touches" one of its pages; if
that page isn't resident, it's a page fault and the replacement policy
(LRU or FIFO) picks a victim frame to evict.

This is deliberately process-agnostic (keyed by pid + footprint), so it
doesn't need to import pcb.py — memory_manager.py and deadlock.py can be
built in parallel off Phase 1 without touching each other.
"""

from collections import deque
from typing import Dict, Optional, List


class MemoryManager:
    def __init__(self, num_frames: int = 20, policy: str = "LRU", seed: int = 7):
        assert policy in ("LRU", "FIFO")
        self.num_frames = num_frames
        self.policy = policy
        self.rng_state = seed

        # frame_table[frame_idx] = (pid, page) or None if free
        self.frame_table: List[Optional[tuple]] = [None] * num_frames
        self.free_frames: deque = deque(range(num_frames))

        # per-process page table: pid -> {page_num: frame_idx}
        self.page_tables: Dict[int, Dict[int, int]] = {}

        # eviction bookkeeping
        self.fifo_order: deque = deque()          # frame indices, oldest first
        self.lru_order: List[int] = []            # frame indices, most-recent last

        self.total_faults = 0
        self.faults_this_tick = 0
        self.faults_per_pid: Dict[int, int] = {}

    # ---------- process lifecycle ----------

    def register_process(self, pid: int):
        self.page_tables.setdefault(pid, {})
        self.faults_per_pid.setdefault(pid, 0)

    def release_process(self, pid: int):
        """Free all frames held by a terminated/swapped-out process."""
        pt = self.page_tables.get(pid, {})
        for page, frame in list(pt.items()):
            self._free_frame(frame)
        self.page_tables[pid] = {}

    def _free_frame(self, frame: int):
        self.frame_table[frame] = None
        self.free_frames.append(frame)
        if frame in self.fifo_order:
            self.fifo_order.remove(frame)
        if frame in self.lru_order:
            self.lru_order.remove(frame)

    # ---------- core access path ----------

    def access(self, pid: int, page: int) -> bool:
        """
        Simulate one memory access. Returns True on page fault, False on hit.
        """
        self.register_process(pid)
        pt = self.page_tables[pid]

        if page in pt:
            frame = pt[page]
            self._touch(frame)
            return False  # hit

        # page fault
        self.total_faults += 1
        self.faults_this_tick += 1
        self.faults_per_pid[pid] = self.faults_per_pid.get(pid, 0) + 1

        if self.free_frames:
            frame = self.free_frames.popleft()
        else:
            frame = self._evict()

        old = self.frame_table[frame]
        if old is not None:
            old_pid, old_page = old
            self.page_tables.get(old_pid, {}).pop(old_page, None)

        self.frame_table[frame] = (pid, page)
        pt[page] = frame
        self._touch(frame, new=True)
        return True

    def _touch(self, frame: int, new: bool = False):
        if self.policy == "LRU":
            if frame in self.lru_order:
                self.lru_order.remove(frame)
            self.lru_order.append(frame)
        elif self.policy == "FIFO" and new:
            self.fifo_order.append(frame)

    def _evict(self) -> int:
        if self.policy == "LRU":
            victim = self.lru_order.pop(0)
        else:  # FIFO
            victim = self.fifo_order.popleft()
        return victim

    # ---------- per-tick metrics ----------

    def tick_reset(self):
        self.faults_this_tick = 0

    def snapshot(self) -> dict:
        used = self.num_frames - len(self.free_frames)
        return {
            "mem_used_frames": used,
            "mem_free_frames": len(self.free_frames),
            "mem_used_pct": 100.0 * used / self.num_frames,
            "page_faults_tick": self.faults_this_tick,
            "page_faults_total": self.total_faults,
        }