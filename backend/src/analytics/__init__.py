"""Analytics subsystem for WRAP.

Provides historical execution tracking, event sourcing, deterministic replay,
critical-path calculation, retry/concurrency aggregation, and analytics APIs.
"""

from src.analytics.enums import TaskStatus, WorkflowEventType, WorkflowStatus
from src.analytics.models import TaskAttempt, WorkflowEvent, WorkflowMetrics, WorkflowRun
from src.analytics.event_logger import EventLogger
from src.analytics.critical_path import calculate_critical_path, CriticalPathResult
from src.analytics.state_machine import WorkflowReplayMachine, InvalidStateTransitionError
from src.analytics.calculator import compute_all_metrics, compute_concurrency_metrics, compute_retry_metrics
from src.analytics.service import AnalyticsService

__all__ = [
    "WorkflowEventType",
    "WorkflowStatus",
    "TaskStatus",
    "WorkflowRun",
    "WorkflowEvent",
    "TaskAttempt",
    "WorkflowMetrics",
    "EventLogger",
    "calculate_critical_path",
    "CriticalPathResult",
    "WorkflowReplayMachine",
    "InvalidStateTransitionError",
    "compute_all_metrics",
    "compute_concurrency_metrics",
    "compute_retry_metrics",
    "AnalyticsService",
]
