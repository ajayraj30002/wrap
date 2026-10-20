import re
from dataclasses import dataclass, field
from typing import Any

from src.orchestration.models import DAGNode, TaskDAG
from src.schemas.openai import ChatCompletionRequest


@dataclass
class DecompositionDecision:
    should_decompose: bool
    execution_mode: str  # "SINGLE" | "DAG"
    reason: str
    confidence: float
    decomposition_version: str = "phase2b-v2"
    workstreams: list[str] = field(default_factory=list)
    detected_pattern: str = "none"


class TaskAnalyzer:
    """Intelligent task decomposability assessment and structured DAG planner.

    Evaluates whether an incoming request represents separable work that benefits
    from multi-worker DAG orchestration versus single-worker execution.
    """

    VERSION = "phase2b-v2"

    COMPARATIVE_HINTS = (
        "compare",
        "versus",
        " vs ",
        "pros and cons",
        "tradeoffs between",
        "analyze each",
        "evaluate each",
        "recommendation between",
    )

    SW_ENGINEERING_DOMAINS = {
        "database": {
            "keywords": ("database", "schema", "models", "data model", "sql", "orm", "migrations", "storage", "postgres", "sqlite"),
            "title": "Database & Data Layer",
            "desc": "Design database models, relational schema, migrations, and data access layer",
        },
        "api": {
            "keywords": ("rest api", "api", "endpoints", "routes", "controller", "backend", "fastapi", "flask", "server", "crud"),
            "title": "REST API & Routing",
            "desc": "Design REST API endpoints, request/response validation schemas, and service routes",
        },
        "analytics": {
            "keywords": ("analytics", "metrics", "data processing", "reporting", "aggregation", "telemetry", "tracking", "pipeline"),
            "title": "Analytics & Metrics Processing",
            "desc": "Design analytics data pipeline, aggregation calculations, and metrics reporting",
        },
        "frontend": {
            "keywords": ("frontend", "dashboard", "web ui", "ui", "interface", "views", "components", "client", "html", "react"),
            "title": "Frontend & Dashboard UI",
            "desc": "Design web UI layout, dashboard views, and interactive client components",
        },
        "tests": {
            "keywords": ("tests", "testing", "test suite", "unit tests", "integration tests", "pytest", "verification", "automated tests"),
            "title": "Testing & Verification",
            "desc": "Develop automated test suite, integration tests, mock fixtures, and validation test cases",
        },
        "documentation": {
            "keywords": ("documentation", "docs", "readme", "api spec", "user guide", "architecture guide"),
            "title": "Documentation & Specifications",
            "desc": "Write system documentation, architecture overview, API specifications, and setup instructions",
        },
        "auth": {
            "keywords": ("auth", "authentication", "authorization", "jwt", "permissions", "security", "login"),
            "title": "Authentication & Security",
            "desc": "Design authentication protocols, permission models, security controls, and session management",
        },
    }

    AUTONOMOUS_ALIASES = {
        "auto",
        "wrap-auto",
        "default",
        "wrap",
        "",
        "intelligent",
    }

    FRONTIER_DECOMPOSITION_ALIASES = {
        "gpt-4o",
        "gpt-4o-2024-08-06",
        "gpt-4o-2024-05-13",
        "chatgpt-4o-latest",
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4-turbo-preview",
        "o1",
        "o1-preview",
        "o1-mini",
        "o3",
        "o3-mini",
        "claude-3-7-sonnet",
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet",
        "claude-3-5-sonnet-latest",
        "claude-3-opus",
        "claude-3-opus-latest",
        "deepseek-reasoner",
        "deepseek-chat",
    }

    @classmethod
    def is_decomposable_model(cls, model_str: str) -> bool:
        """Check if model is eligible for autonomous DAG decomposition.
        
        Permits:
        1. Autonomous aliases ('auto', 'wrap-auto', 'wrap', etc.)
        2. Common frontier aliases ('gpt-4o', 'claude-3-5-sonnet', 'o1', etc.) used by
           OpenAI SDK clients/IDEs that do not expose an 'auto' option in their model dropdown.
        """
        norm = (model_str or "").lower().strip().removeprefix("openai/").removeprefix("anthropic/")
        if norm in cls.AUTONOMOUS_ALIASES:
            return True
        if norm in cls.FRONTIER_DECOMPOSITION_ALIASES:
            return True
        if any(norm.startswith(p) for p in ("gpt-4o", "chatgpt-4o", "claude-3-5-sonnet", "claude-3-7-sonnet", "o1", "o3")):
            return True
        return False

    def assess(self, request: ChatCompletionRequest) -> DecompositionDecision:
        """Evaluate whether a request should be decomposed into a DAG.
        
        DAG eligibility is determined by the nature of the task:
        - Multi-workstream software engineering workloads, comparative research, and
          multi-objective deliverables decompose into a DAG across all models and aliases.
        - Function calling (tools), simple queries, code edits, and explicit single-mode
          requests remain on SINGLE.
        """
        # 1. Requests requiring tools/function-calling must remain SINGLE for tool dispatch
        if getattr(request, "tools", None):
            return DecompositionDecision(
                should_decompose=False,
                execution_mode="SINGLE",
                reason="Request requires function/tool calling; preserving single worker agent execution",
                confidence=1.0,
                decomposition_version=self.VERSION,
            )

        # 2. Check if caller explicitly requested single execution mode
        model_lower = (request.model or "").lower()
        extra = getattr(request, "__pydantic_extra__", {}) or {}
        if (
            model_lower.endswith(":single")
            or model_lower.endswith("-single")
            or extra.get("execution_mode") == "single"
            or extra.get("decompose") is False
        ):
            return DecompositionDecision(
                should_decompose=False,
                execution_mode="SINGLE",
                reason="Explicit single execution requested; preserving single worker execution",
                confidence=1.0,
                decomposition_version=self.VERSION,
            )

        text = self._last_user_text(request).strip()
        text_lower = text.lower()
        words = text.split()

        # 2. Short / trivial requests remain SINGLE (Section 6)
        if len(words) < 10 and not self._has_explicit_list(text):
            return DecompositionDecision(
                should_decompose=False,
                execution_mode="SINGLE",
                reason="Brief single-objective request; DAG overhead outweighs benefits",
                confidence=0.95,
                decomposition_version=self.VERSION,
            )

        # 3. Simple conversational / factual queries remain SINGLE
        if self._is_simple_query(text_lower):
            return DecompositionDecision(
                should_decompose=False,
                execution_mode="SINGLE",
                reason="Single informational query; optimal on single worker",
                confidence=0.95,
                decomposition_version=self.VERSION,
            )

        # 4. Simple code edits / bug fixes remain SINGLE
        if self._is_simple_code_edit(text_lower, words):
            return DecompositionDecision(
                should_decompose=False,
                execution_mode="SINGLE",
                reason="Targeted code edit; optimal on single worker",
                confidence=0.90,
                decomposition_version=self.VERSION,
            )

        # 5. Check Software Engineering Workloads (Section 5)
        detected_sw = self._detect_sw_workstreams(text)
        if len(detected_sw) >= 2:
            return DecompositionDecision(
                should_decompose=True,
                execution_mode="DAG",
                reason=f"Software engineering workload with {len(detected_sw)} separable workstreams: {', '.join(detected_sw)}",
                confidence=min(0.95, 0.65 + len(detected_sw) * 0.06),
                decomposition_version=self.VERSION,
                workstreams=detected_sw,
                detected_pattern="software_engineering",
            )

        # 6. Check Comparative / Research Workloads
        if any(hint in text_lower for hint in self.COMPARATIVE_HINTS):
            subjects = self._extract_subjects(text)
            if len(subjects) >= 2:
                return DecompositionDecision(
                    should_decompose=True,
                    execution_mode="DAG",
                    reason=f"Comparative evaluation across {len(subjects)} subjects: {', '.join(subjects)}",
                    confidence=0.88,
                    decomposition_version=self.VERSION,
                    workstreams=subjects,
                    detected_pattern="comparative_research",
                )

        # 7. Check General Multi-Objective Requests (explicit lists with distinct deliverables)
        list_items = self._extract_list_items(text)
        if len(list_items) >= 3 and len(words) >= 25:
            return DecompositionDecision(
                should_decompose=True,
                execution_mode="DAG",
                reason=f"Multi-objective task with {len(list_items)} independent deliverables",
                confidence=0.80,
                decomposition_version=self.VERSION,
                workstreams=[f"objective_{i}" for i in range(1, len(list_items) + 1)],
                detected_pattern="multi_objective",
            )

        # Default: Single worker
        return DecompositionDecision(
            should_decompose=False,
            execution_mode="SINGLE",
            reason="Cohesive single-deliverable request; serial execution is optimal",
            confidence=0.85,
            decomposition_version=self.VERSION,
        )

    def should_decompose(self, request: ChatCompletionRequest) -> bool:
        """Backward-compatible boolean method."""
        return self.assess(request).should_decompose

    def build_dag(self, request: ChatCompletionRequest, *, task_id: str) -> TaskDAG:
        """Generate a validated structured TaskDAG."""
        decision = self.assess(request)
        text = self._last_user_text(request)

        if decision.detected_pattern == "software_engineering":
            return self._build_sw_engineering_dag(decision.workstreams[:6], text, task_id=task_id)

        if decision.detected_pattern == "comparative_research":
            subjects = decision.workstreams if len(decision.workstreams) >= 2 else self._extract_subjects(text)
            if len(subjects) < 2:
                subjects = ["option A", "option B"]
            return self._build_comparative_dag(subjects[:4], text, task_id=task_id)

        # Fallback or multi_objective
        list_items = self._extract_list_items(text)
        if len(list_items) >= 2:
            return self._build_multi_objective_dag(list_items[:5], text, task_id=task_id)

        # Default 2-subtask + aggregate + synthesis
        return self._build_comparative_dag(["Task Area A", "Task Area B"], text, task_id=task_id)

    def _build_sw_engineering_dag(self, workstreams: list[str], prompt: str, *, task_id: str) -> TaskDAG:
        """Build DAG for software engineering workloads with independent layers and integration."""
        nodes: list[DAGNode] = []
        subtask_ids: list[str] = []

        # Cap at 6 workstreams so subtasks + integration + synthesis <= 8 nodes
        workstreams = workstreams[:6]

        # Create subtask node for each domain
        for idx, domain in enumerate(workstreams, start=1):
            info = self.SW_ENGINEERING_DOMAINS.get(
                domain,
                {"title": domain.capitalize(), "desc": f"Plan and implement {domain}"},
            )
            node_id = f"n{idx}_{domain}"
            subtask_ids.append(node_id)
            nodes.append(
                DAGNode(
                    id=node_id,
                    type="subtask",
                    description=info["desc"],
                    output_ref=f"{task_id}.{node_id}.result",
                    priority=2,
                )
            )

        # Core engineering nodes wait for integration; docs can proceed independently
        core_node_ids = [nid for nid in subtask_ids if not nid.endswith("_documentation")]
        if not core_node_ids:
            core_node_ids = list(subtask_ids)

        integration_id = f"n{len(nodes) + 1}_integration"
        nodes.append(
            DAGNode(
                id=integration_id,
                type="aggregation",
                description="Integrate the subtask architecture designs, contracts, schemas, and components into a cohesive system.",
                depends_on=core_node_ids,
                input_refs=[f"{task_id}.{nid}.result" for nid in core_node_ids],
                output_ref=f"{task_id}.{integration_id}.result",
                priority=5,
                allow_partial_input=True,
            )
        )

        # Final synthesis node
        synthesis_deps = [integration_id]
        doc_node_ids = [nid for nid in subtask_ids if nid.endswith("_documentation")]
        if doc_node_ids:
            synthesis_deps.extend(doc_node_ids)

        synthesis_id = f"n{len(nodes) + 1}_synthesis"
        nodes.append(
            DAGNode(
                id=synthesis_id,
                type="synthesis",
                description="Produce the complete, working production implementation and response for user request",
                depends_on=synthesis_deps,
                input_refs=[f"{task_id}.{dep}.result" for dep in synthesis_deps],
                output_ref=f"{task_id}.final",
                priority=10,
                allow_partial_input=True,
            )
        )

        return TaskDAG(task_id=task_id, nodes=nodes)

    def _build_comparative_dag(self, subjects: list[str], prompt: str, *, task_id: str) -> TaskDAG:
        """Build DAG for comparative research with parallel subjects, aggregation, and synthesis."""
        nodes: list[DAGNode] = []
        for index, subject in enumerate(subjects, start=1):
            nodes.append(
                DAGNode(
                    id=f"n{index}",
                    type="subtask",
                    description=f"Analyze {subject.strip()}",
                    output_ref=f"{task_id}.n{index}.result",
                    priority=1,
                )
            )
        aggregate_id = f"n{len(nodes) + 1}"
        nodes.append(
            DAGNode(
                id=aggregate_id,
                type="aggregation",
                description="Compare the upstream findings and identify tradeoffs, risks, and decision criteria.",
                depends_on=[node.id for node in nodes],
                input_refs=[node.output_ref or node.id for node in nodes],
                output_ref=f"{task_id}.{aggregate_id}.result",
                priority=5,
                allow_partial_input=True,
            )
        )
        synthesis_id = f"n{len(nodes) + 1}"
        nodes.append(
            DAGNode(
                id=synthesis_id,
                type="synthesis",
                description="Produce the final synthesis comparing all subjects and recommendation",
                depends_on=[aggregate_id],
                input_refs=[f"{task_id}.{aggregate_id}.result"],
                output_ref=f"{task_id}.final",
                priority=10,
                allow_partial_input=True,
            )
        )
        return TaskDAG(task_id=task_id, nodes=nodes)

    def _build_multi_objective_dag(self, items: list[str], prompt: str, *, task_id: str) -> TaskDAG:
        """Build DAG for multi-objective requests."""
        nodes: list[DAGNode] = []
        for index, item in enumerate(items, start=1):
            nodes.append(
                DAGNode(
                    id=f"n{index}",
                    type="subtask",
                    description=f"Address objective ({item.strip()}) for request: {prompt}",
                    output_ref=f"{task_id}.n{index}.result",
                    priority=1,
                )
            )
        aggregate_id = f"n{len(nodes) + 1}"
        nodes.append(
            DAGNode(
                id=aggregate_id,
                type="aggregation",
                description="Synthesize results from all individual objective workstreams.",
                depends_on=[node.id for node in nodes],
                input_refs=[node.output_ref or node.id for node in nodes],
                output_ref=f"{task_id}.{aggregate_id}.result",
                priority=5,
                allow_partial_input=True,
            )
        )
        synthesis_id = f"n{len(nodes) + 1}"
        nodes.append(
            DAGNode(
                id=synthesis_id,
                type="synthesis",
                description=f"Produce the unified final response: {prompt}",
                depends_on=[aggregate_id],
                input_refs=[f"{task_id}.{aggregate_id}.result"],
                output_ref=f"{task_id}.final",
                priority=10,
                allow_partial_input=True,
            )
        )
        return TaskDAG(task_id=task_id, nodes=nodes)

    def _detect_sw_workstreams(self, text: str) -> list[str]:
        """Detect distinct software engineering domains mentioned in prompt."""
        text_lower = text.lower()
        # Must have an overall building/engineering intent
        intent_indicators = (
            "build",
            "create",
            "implement",
            "develop",
            "architect",
            "from scratch",
            "service",
            "application",
            "project",
            "system",
            "component",
            "module",
        )
        has_intent = any(indicator in text_lower for indicator in intent_indicators)
        has_list = self._has_explicit_list(text)

        if not (has_intent or has_list or len(text.split()) > 35):
            return []

        detected: list[str] = []
        for domain, info in self.SW_ENGINEERING_DOMAINS.items():
            for kw in info["keywords"]:
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, text_lower):
                    detected.append(domain)
                    break
        return detected

    def _has_explicit_list(self, text: str) -> bool:
        """Check if prompt contains bullet or numbered lists."""
        return bool(re.search(r"(?:^|\n)\s*(?:[-*•]|\d+\.)\s+", text))

    def _extract_list_items(self, text: str) -> list[str]:
        """Extract lines that are part of a bulleted/numbered list."""
        items = []
        for line in text.splitlines():
            m = re.match(r"^\s*(?:[-*•]|\d+\.)\s+(.+)$", line)
            if m:
                item_text = m.group(1).strip()
                if len(item_text) >= 3:
                    items.append(item_text)
        return items

    def _is_simple_query(self, text_lower: str) -> bool:
        """Check if request is an informational single-fact query."""
        if re.match(r"^(what|who|when|where|why|how)\s+(is|are|was|were|do|does|did)\b", text_lower):
            # If it doesn't have multiple clauses or comparisons
            if not any(sep in text_lower for sep in (" and also ", " compare ", " vs ", "\n", " - ")):
                return True
        if text_lower.startswith(("explain ", "define ", "summarize this ", "translate ")):
            if len(text_lower.split()) < 35 and not self._has_explicit_list(text_lower):
                return True
        return False

    def _is_simple_code_edit(self, text_lower: str, words: list[str]) -> bool:
        """Check if request is a localized code edit / bug fix."""
        edit_patterns = (
            "fix this typo",
            "fix the typo",
            "syntax error",
            "fix this bug",
            "write a function to",
            "write a two-line",
            "write a one-line",
            "add a comment",
            "rename this",
        )
        if any(p in text_lower for p in edit_patterns) and len(words) < 50:
            return True
        return False

    def _last_user_text(self, request: ChatCompletionRequest) -> str:
        for message in reversed(request.messages):
            if message.role == "user":
                return message.content if isinstance(message.content, str) else str(message.content)
        return ""

    def _extract_subjects(self, text: str) -> list[str]:
        cleaned = re.sub(r"\s+", " ", text)
        match = re.search(r"compare\s+(.+?)(?:\s+for\s+|\s+in\s+|\s+and\s+provide|\.)", cleaned, re.I)
        segment = match.group(1) if match else cleaned
        segment = re.sub(r"\b(compare|research|evaluate|analyze)\b", "", segment, flags=re.I)
        parts = re.split(r",|\bversus\b|\bvs\.?\b|\band\b", segment, flags=re.I)
        subjects = [part.strip(" .:;-") for part in parts if 2 <= len(part.strip()) <= 80]
        return [subject for subject in subjects if subject.lower() not in {"pros", "cons", "recommendation"}]
