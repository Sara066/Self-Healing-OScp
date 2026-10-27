"""
Phase 3 — Deadlock detection via Resource-Allocation Graph (RAG)

Processes request/hold simulated resources (locks, files, whatever
abstraction). We build a directed graph:
    process -> resource   : process is WAITING (requesting) that resource
    resource -> process   : resource is HELD by that process

A cycle in this graph = deadlock (Coffman's four conditions all hold
by construction: mutual exclusion, hold-and-wait, no preemption,
circular wait). Cycle detection uses networkx, not a hand-rolled DFS,
per the compressed scope.

This module is independent of scheduler.py / memory_manager.py — it
only needs pids and resource ids, so it doesn't import pcb.py.
"""

import networkx as nx
from typing import List, Optional


class ResourceAllocationGraph:
    def __init__(self):
        self.g = nx.DiGraph()

    # ---------- graph mutation ----------

    def request(self, pid: int, resource: str):
        """Process pid asks for `resource` it doesn't currently hold."""
        p_node, r_node = f"P{pid}", f"R{resource}"
        self.g.add_node(p_node, kind="process")
        self.g.add_node(r_node, kind="resource")
        self.g.add_edge(p_node, r_node)  # process -> resource = waiting

    def allocate(self, pid: int, resource: str):
        """Grant `resource` to pid: request edge flips to a hold edge."""
        p_node, r_node = f"P{pid}", f"R{resource}"
        if self.g.has_edge(p_node, r_node):
            self.g.remove_edge(p_node, r_node)
        self.g.add_edge(r_node, p_node)  # resource -> process = held

    def release(self, pid: int, resource: str):
        """pid gives up `resource` entirely (no longer holding or waiting)."""
        p_node, r_node = f"P{pid}", f"R{resource}"
        for a, b in [(r_node, p_node), (p_node, r_node)]:
            if self.g.has_edge(a, b):
                self.g.remove_edge(a, b)

    def remove_process(self, pid: int):
        """Terminate pid: drop it and every edge touching it (recovery action)."""
        p_node = f"P{pid}"
        if p_node in self.g:
            self.g.remove_node(p_node)

    # ---------- detection ----------

    def find_cycle(self) -> Optional[List[str]]:
        """Return the first detected cycle (list of node names), or None."""
        try:
            cycle_edges = nx.find_cycle(self.g, orientation="original")
            nodes = [u for u, v, *_ in cycle_edges]
            nodes.append(cycle_edges[-1][1])
            return nodes
        except nx.NetworkXNoCycle:
            return None

    def is_deadlocked(self) -> bool:
        return self.find_cycle() is not None

    def processes_in_cycle(self, cycle: List[str]) -> List[int]:
        seen = []
        for n in cycle:
            if n.startswith("P"):
                pid = int(n[1:])
                if pid not in seen:
                    seen.append(pid)
        return seen

    # ---------- recovery ----------

    def break_deadlock(self) -> Optional[int]:
        """
        Recovery action: terminate one process involved in the cycle
        (the one holding the resource another cycle member is waiting on),
        removing it from the graph. Returns the pid terminated, or None
        if there was no deadlock.
        """
        cycle = self.find_cycle()
        if cycle is None:
            return None
        victim_pid = self.processes_in_cycle(cycle)[0]
        self.remove_process(victim_pid)
        return victim_pid

    def snapshot(self) -> dict:
        cycle = self.find_cycle()
        return {
            "num_resource_nodes": sum(1 for _, d in self.g.nodes(data=True)
                                       if d.get("kind") == "resource"),
            "num_wait_edges": self.g.number_of_edges(),
            "deadlocked": cycle is not None,
            "cycle_pids": self.processes_in_cycle(cycle) if cycle else [],
        }