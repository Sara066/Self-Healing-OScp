"""
Phase 6 — Recovery

Once diagnosis names a probable cause, apply the matching corrective
action to the simulation's own state. Each function returns a short
description string for the run's narrative log.

  runaway_cpu     -> demote the offending PCB to the low-priority queue
                      (MLFQ-lite recovery action, not a kill -- it's still
                      allowed to run, just no longer starves everyone else)
  thrashing        -> suspend the heaviest-memory process for N ticks and
                      free its frames, letting the fault rate settle
  abnormal_combo   -> same demotion as runaway (it's still fundamentally
                      a scheduling-fairness problem, just with an odd
                      feature signature), plus a shorter suspension
  deadlock         -> terminate one process in the resource-allocation
                      cycle, breaking the circular wait
"""

from scheduler import Scheduler
from memory_manager import MemoryManager
from deadlock import ResourceAllocationGraph

SUSPEND_TICKS_THRASHING = 15
SUSPEND_TICKS_COMBO = 8


def recover_runaway(sched: Scheduler, pid: int) -> str:
    sched.demote(pid)
    return f"demoted PID {pid} to low-priority queue"


def recover_thrashing(sched: Scheduler, mem: MemoryManager, pid: int, now_tick: int) -> str:
    mem.release_process(pid)          # free its frames immediately
    sched.suspend(pid, now_tick + SUSPEND_TICKS_THRASHING)
    return (f"suspended PID {pid} for {SUSPEND_TICKS_THRASHING} ticks "
            f"and freed its resident pages")


def recover_abnormal_combo(sched: Scheduler, pid: int, now_tick: int) -> str:
    sched.demote(pid)
    sched.suspend(pid, now_tick + SUSPEND_TICKS_COMBO)
    return (f"demoted PID {pid} and suspended it for {SUSPEND_TICKS_COMBO} ticks "
            f"(odd CPU+memory+thread combination)")


def recover_deadlock(rag: ResourceAllocationGraph) -> str:
    victim = rag.break_deadlock()
    if victim is None:
        return "no deadlock present, nothing to recover"
    return f"terminated PID {victim} to break the circular wait"


RECOVERY_DISPATCH = {
    "runaway_cpu": recover_runaway,
    "thrashing": recover_thrashing,
    "abnormal_combo": recover_abnormal_combo,
}