from collections import defaultdict, deque

from src.orchestration.models import TaskDAG


VALID_NODE_TYPES = {"subtask", "aggregation", "synthesis"}


class InvalidDAGError(ValueError):
    pass


class DAGValidator:
    def __init__(self, *, max_nodes: int, max_depth: int, max_parallel_nodes: int, max_total_execution_time: int) -> None:
        self.max_nodes = max_nodes
        self.max_depth = max_depth
        self.max_parallel_nodes = max_parallel_nodes
        self.max_total_execution_time = max_total_execution_time

    def validate(self, dag: TaskDAG) -> None:
        if not dag.nodes:
            raise InvalidDAGError("DAG must contain at least one node")
        if len(dag.nodes) > self.max_nodes:
            raise InvalidDAGError("DAG exceeds maximum node count")
        ids = [node.id for node in dag.nodes]
        if len(ids) != len(set(ids)):
            raise InvalidDAGError("DAG contains duplicate node IDs")
        known = set(ids)
        for node in dag.nodes:
            if node.type not in VALID_NODE_TYPES:
                raise InvalidDAGError(f"Invalid node type: {node.type}")
            if node.id in node.depends_on:
                raise InvalidDAGError(f"Node {node.id} depends on itself")
            missing = [dep for dep in node.depends_on if dep not in known]
            if missing:
                raise InvalidDAGError(f"Node {node.id} has missing dependencies: {missing}")
        self._assert_acyclic_and_depth(dag)

    def _assert_acyclic_and_depth(self, dag: TaskDAG) -> None:
        children: dict[str, list[str]] = defaultdict(list)
        indegree = {node.id: 0 for node in dag.nodes}
        for node in dag.nodes:
            for dep in node.depends_on:
                children[dep].append(node.id)
                indegree[node.id] += 1
        queue = deque([(node_id, 1) for node_id, degree in indegree.items() if degree == 0])
        visited = 0
        max_depth_seen = 0
        while queue:
            node_id, depth = queue.popleft()
            visited += 1
            max_depth_seen = max(max_depth_seen, depth)
            if max_depth_seen > self.max_depth:
                raise InvalidDAGError("DAG exceeds maximum depth")
            for child in children[node_id]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append((child, depth + 1))
        if visited != len(dag.nodes):
            raise InvalidDAGError("DAG contains a cycle")
