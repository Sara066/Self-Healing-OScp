"""
Phase 1 — Process Control Block (PCB)

Minimal PCB: just the fields the scheduler / memory manager / ML layer
actually need. No over-engineering.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProcState(Enum):
    NEW = "new"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    TERMINATED = "terminated"


@dataclass
class PCB:
    pid: int
    priority: int = 0          # 0 = high queue, 1 = low/demoted queue
    total_burst: int = 10      # total CPU ticks this process needs, ever
    burst_remaining: int = 10
    memory_footprint: int = 4  # in "pages" — used from Phase 2 onward
    thread_count: int = 1
    io_prob: float = 0.0       # chance per tick this process does I/O instead of CPU
    is_runaway: bool = False   # injected anomaly flag: never finishes normally

    state: ProcState = ProcState.NEW
    arrival_tick: int = 0
    start_tick: Optional[int] = None
    finish_tick: Optional[int] = None
    wait_ticks: int = 0
    suspended_until: Optional[int] = None  # used by recovery actions later

    def __post_init__(self):
        self.burst_remaining = self.total_burst

    def is_alive(self) -> bool:
        return self.state != ProcState.TERMINATED

    def __repr__(self):
        return (f"PCB(pid={self.pid}, state={self.state.value}, "
                f"prio={self.priority}, burst_left={self.burst_remaining}, "
                f"mem={self.memory_footprint})")
