"""
Compares FCFS, SJF, Priority, Round Robin, and MLFQ on the SAME workload.

Directly demonstrates every scheduling algorithm named in the syllabus
(Unit 2), separate from the self-healing pipeline's own scheduler.py, which
is validated independently against the anomaly detection pipeline.
"""

from pcb import PCB
from classic_schedulers import (fcfs_schedule, sjf_schedule,
                                 priority_schedule, round_robin_schedule)
from mlfq import MLFQScheduler


def build_workload():
    # Staggered arrivals + varied burst/priority so every algorithm actually
    # has to make different decisions on the same workload.
    return [
        PCB(pid=1, arrival_tick=0, total_burst=8, priority=2),
        PCB(pid=2, arrival_tick=1, total_burst=4, priority=1),
        PCB(pid=3, arrival_tick=2, total_burst=9, priority=3),
        PCB(pid=4, arrival_tick=3, total_burst=5, priority=0),
        PCB(pid=5, arrival_tick=4, total_burst=2, priority=1),
    ]


def run_mlfq(processes):
    sched = MLFQScheduler(processes)
    sched.run()
    waiting, turnaround = {}, {}
    for p in processes:
        turnaround[p.pid] = p.finish_tick - p.arrival_tick
        waiting[p.pid] = turnaround[p.pid] - p.total_burst
    avg_w = sum(waiting.values()) / len(waiting)
    avg_t = sum(turnaround.values()) / len(turnaround)
    return avg_w, avg_t, waiting, turnaround


def main():
    results = {}
    per_process = {}

    for name, fn in [("FCFS", fcfs_schedule), ("SJF", sjf_schedule),
                      ("Priority", priority_schedule)]:
        r = fn(build_workload())
        results[name] = (r.avg_waiting(), r.avg_turnaround())
        per_process[name] = (r.waiting, r.turnaround)

    r = round_robin_schedule(build_workload(), quantum=4)
    results["Round Robin (q=4)"] = (r.avg_waiting(), r.avg_turnaround())
    per_process["Round Robin (q=4)"] = (r.waiting, r.turnaround)

    avg_w, avg_t, waiting, turnaround = run_mlfq(build_workload())
    results["MLFQ (3-level, aging)"] = (avg_w, avg_t)
    per_process["MLFQ (3-level, aging)"] = (waiting, turnaround)

    print("Workload: pid(arrival, burst, priority)")
    print("  P1(0,8,2)  P2(1,4,1)  P3(2,9,3)  P4(3,5,0)  P5(4,2,1)")
    print()
    print(f"{'Algorithm':<22}{'Avg Waiting':>14}{'Avg Turnaround':>18}")
    print("-" * 54)
    for name, (w, t) in results.items():
        print(f"{name:<22}{w:>14.2f}{t:>18.2f}")

    print()
    print("Per-process waiting time by algorithm:")
    header = "pid".ljust(6) + "".join(name.ljust(22) for name in results)
    print(header)
    for pid in [1, 2, 3, 4, 5]:
        row = str(pid).ljust(6)
        for name in results:
            row += str(per_process[name][0][pid]).ljust(22)
        print(row)


if __name__ == "__main__":
    main()
