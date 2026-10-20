from dataclasses import dataclass, field
from typing import Any, Literal


NodeType = Literal["subtask", "aggregation", "synthesis"]
NodeStatus = Literal["pending", "running", "success", "failed", "skipped"]


@dataclass
class DAGNode:
    id: str
    type: NodeType
    description: str
    depends_on: list[str] = field(default_factory=list)
    input_refs: list[str] = field(default_factory=list)
    output_ref: str | None = None
    state: NodeStatus = "pending"
    selected_worker: str | None = None
    retry_count: int = 0
    timeout_seconds: int = 120
    priority: int = 0
    estimated_cost: float | None = None
    estimated_latency_ms: int | None = None
    failure_state: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None
    allow_partial_input: bool = False


@dataclass
class TaskDAG:
    task_id: str
    nodes: list[DAGNode]

    def node_map(self) -> dict[str, DAGNode]:
        return {node.id: node for node in self.nodes}
