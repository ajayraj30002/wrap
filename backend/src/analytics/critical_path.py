"""Deterministic iterative critical-path algorithm for DAG workflows."""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CriticalPathResult:
    critical_path_duration_ms: int
    critical_path_nodes: list[str] = field(default_factory=list)
    node_earliest_starts: dict[str, int] = field(default_factory=dict)
    node_finish_times: dict[str, int] = field(default_factory=dict)


def calculate_critical_path(
    nodes: dict[str, dict[str, Any]] | list[dict[str, Any]],
    only_successful: bool = False,
) -> CriticalPathResult:
    """Calculate the critical-path duration and nodes deterministically and iteratively.
    
    Given nodes where each item has:
      - 'id' (or 'node_id')
      - 'depends_on' (list of dependent node IDs)
      - 'duration_ms' (or 'latency_ms')
      - 'status' (optional, e.g. 'success'/'SUCCEEDED')
    """
    # Normalize input into dict: id -> dict
    node_map: dict[str, dict[str, Any]] = {}
    if isinstance(nodes, list):
        for n in nodes:
            nid = n.get("id") or n.get("node_id")
            if nid:
                node_map[str(nid)] = n
    else:
        node_map = {str(k): v for k, v in nodes.items()}

    if not node_map:
        return CriticalPathResult(critical_path_duration_ms=0, critical_path_nodes=[])

    if only_successful:
        # Filter for successful nodes only
        successful_ids = {
            nid for nid, n in node_map.items()
            if str(n.get("status", "")).lower() in ("success", "succeeded")
        }
        # Keep only nodes whose dependencies are also successful
        filtered_map = {}
        for nid in successful_ids:
            n = node_map[nid]
            deps = [d for d in n.get("depends_on", []) or [] if d in successful_ids]
            filtered_map[nid] = {**n, "depends_on": deps}
        node_map = filtered_map

    if not node_map:
        return CriticalPathResult(critical_path_duration_ms=0, critical_path_nodes=[])

    # Build adjacency list and in-degrees
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {nid: 0 for nid in node_map}

    for nid, node_data in node_map.items():
        deps = node_data.get("depends_on") or []
        for dep in deps:
            dep_id = str(dep)
            if dep_id in node_map:
                adj[dep_id].append(nid)
                in_degree[nid] += 1

    # Deterministic Kahn's algorithm using sorted queue for deterministic tie-breaking
    queue: list[str] = sorted([nid for nid, deg in in_degree.items() if deg == 0])
    topo_order: list[str] = []

    while queue:
        # Pick smallest node ID for deterministic processing
        curr = queue.pop(0)
        topo_order.append(curr)

        for neighbor in sorted(adj[curr]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                # Insert keeping sorted order
                queue.append(neighbor)
                queue.sort()

    if len(topo_order) < len(node_map):
        raise ValueError("Cycle detected in DAG; topological sort incomplete")

    # Iterative forward pass: compute earliest starts and finish times
    earliest_start: dict[str, int] = {}
    finish_time: dict[str, int] = {}
    predecessor: dict[str, str | None] = {}

    for nid in topo_order:
        node_data = node_map[nid]
        duration = node_data.get("duration_ms")
        if duration is None:
            duration = node_data.get("latency_ms", 0)
        duration = max(0, int(duration or 0))

        deps = [str(d) for d in (node_data.get("depends_on") or []) if str(d) in finish_time]

        if not deps:
            earliest_start[nid] = 0
            predecessor[nid] = None
        else:
            best_dep = None
            max_dep_finish = -1
            # Deterministic tie-breaking on predecessor
            for dep in sorted(deps):
                dep_finish = finish_time[dep]
                if dep_finish > max_dep_finish:
                    max_dep_finish = dep_finish
                    best_dep = dep
            earliest_start[nid] = max(0, max_dep_finish)
            predecessor[nid] = best_dep

        finish_time[nid] = earliest_start[nid] + duration

    # Find the maximum finish time across all sink nodes (or any nodes)
    max_finish = -1
    max_node: str | None = None

    for nid in sorted(finish_time.keys()):
        if finish_time[nid] > max_finish:
            max_finish = finish_time[nid]
            max_node = nid

    if max_node is None or max_finish <= 0:
        # If all durations are 0
        return CriticalPathResult(
            critical_path_duration_ms=0,
            critical_path_nodes=[topo_order[0]] if topo_order else [],
            node_earliest_starts=earliest_start,
            node_finish_times=finish_time,
        )

    # Backtrack from max_node to construct critical path
    path: list[str] = []
    curr_node: str | None = max_node
    while curr_node is not None:
        path.append(curr_node)
        curr_node = predecessor.get(curr_node)

    path.reverse()

    return CriticalPathResult(
        critical_path_duration_ms=max_finish,
        critical_path_nodes=path,
        node_earliest_starts=earliest_start,
        node_finish_times=finish_time,
    )
