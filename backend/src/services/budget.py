"""
Hierarchical Budget Governance, Hard Spend Caps & Circuit Breaker Engine.

Provides real-time financial controls inspired by LiteLLM Enterprise and Portkey:
- Hard spend caps per Gateway API Key (e.g. $10.00 / $50.00 limits)
- Spend velocity circuit breakers to halt runaway loops (e.g. max $5 in 5 mins)
- Periodic budget reset windows (monthly, weekly, daily, total)
- Dynamic fallback to Free-Tier routing when paid budget limit is reached
- Atomic spend & market-value-saved balance attribution
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import GatewayApiKey

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SpendVelocityTracker:
    """High-performance in-memory rolling-window spend velocity tracker.
    
    Protects against runaway agent loops, accidental parallel bursts, and high-frequency
    expensive frontier model calls draining budgets before hourly alerts fire.
    """

    def __init__(self) -> None:
        # key_id -> list of (timestamp_float, spend_usd)
        self._records: dict[str, list[tuple[float, float]]] = {}

    def record_spend(self, key_id: str, cost_usd: float, timestamp: float | None = None) -> None:
        """Record an out-of-pocket spend event for a key."""
        if cost_usd <= 0:
            return
        ts = timestamp or time.time()
        if key_id not in self._records:
            self._records[key_id] = []
        self._records[key_id].append((ts, cost_usd))
        # Keep clean: prune events older than 1 hour (3600s)
        cutoff = ts - 3600
        self._records[key_id] = [r for r in self._records[key_id] if r[0] >= cutoff]

    def check_velocity(
        self, key_id: str, limit_usd: float, window_sec: int, timestamp: float | None = None
    ) -> tuple[bool, float]:
        """Check if spend within rolling window exceeds velocity limit.
        
        Returns (is_tripped, current_window_spend).
        """
        if limit_usd is None or limit_usd <= 0:
            return False, 0.0

        ts = timestamp or time.time()
        cutoff = ts - max(1, window_sec)
        events = self._records.get(key_id, [])
        window_spend = sum(cost for t, cost in events if t >= cutoff)

        is_tripped = window_spend >= limit_usd
        return is_tripped, round(window_spend, 6)

    def reset_key(self, key_id: str) -> None:
        """Clear spend velocity records for a key."""
        self._records.pop(key_id, None)


# Global singleton instance
spend_velocity_tracker = SpendVelocityTracker()


@dataclass
class BudgetCheckResult:
    allowed: bool
    status_code: int = 200
    action: str = "proceed"  # "proceed" | "hard_cap" | "fallback_to_free"
    error_type: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    current_spend_usd: float = 0.0
    max_budget_usd: float | None = None
    spend_velocity_usd: float = 0.0


class BudgetService:
    """Enterprise spend management and enforcement service."""

    @staticmethod
    def _compute_next_reset(period: str, from_date: datetime) -> datetime:
        """Calculate next scheduled reset timestamp based on period."""
        if period == "daily":
            return from_date + timedelta(days=1)
        elif period == "weekly":
            return from_date + timedelta(days=7)
        elif period == "monthly":
            # Approximate next month
            year = from_date.year + (1 if from_date.month == 12 else 0)
            month = 1 if from_date.month == 12 else from_date.month + 1
            day = min(from_date.day, 28)
            return datetime(year, month, day, from_date.hour, from_date.minute, tzinfo=timezone.utc)
        return from_date + timedelta(days=3650)  # total / no reset

    @classmethod
    def check_key_budget(cls, key: GatewayApiKey) -> BudgetCheckResult:
        """Pre-flight check verifying if key has available budget and is within velocity limits."""
        now = utcnow()

        # 1. Evaluate Periodic Budget Reset Cycle
        reset_period = getattr(key, "budget_reset_period", "monthly") or "monthly"
        reset_at = getattr(key, "budget_reset_at", None)

        if reset_period != "total" and reset_at is not None and now >= reset_at:
            # Budget window elapsed: reset spend balance
            key.spend_usd = 0.0
            key.budget_reset_at = cls._compute_next_reset(reset_period, now)
            spend_velocity_tracker.reset_key(str(key.id))
            logger.info("Budget reset cycle triggered for key %s (period: %s)", key.name, reset_period)

        current_spend = getattr(key, "spend_usd", 0.0) or 0.0
        max_budget = getattr(key, "max_budget_usd", None)

        # 2. Check Spend Velocity Circuit Breaker (Runaway loop protection)
        velocity_limit = getattr(key, "spend_velocity_limit_usd", None)
        velocity_window = getattr(key, "spend_velocity_window_sec", 300) or 300

        if velocity_limit is not None and velocity_limit > 0:
            is_tripped, window_spend = spend_velocity_tracker.check_velocity(
                str(key.id), velocity_limit, velocity_window
            )
            if is_tripped:
                return BudgetCheckResult(
                    allowed=False,
                    status_code=429,
                    action="hard_cap",
                    error_type="circuit_breaker_tripped",
                    error_code="spend_velocity_exceeded",
                    error_message=(
                        f"Circuit breaker tripped for key '{key.name}': spend velocity of "
                        f"${window_spend:.4f} within {velocity_window}s exceeded the configured limit "
                        f"of ${velocity_limit:.4f}. Runaway loop protection active."
                    ),
                    current_spend_usd=current_spend,
                    max_budget_usd=max_budget,
                    spend_velocity_usd=window_spend,
                )

        # 3. Check Hard Spend Cap
        if max_budget is not None and max_budget >= 0:
            if current_spend >= max_budget:
                action = getattr(key, "budget_exceeded_action", "hard_cap") or "hard_cap"
                if action == "fallback_to_free":
                    return BudgetCheckResult(
                        allowed=True,
                        action="fallback_to_free",
                        current_spend_usd=current_spend,
                        max_budget_usd=max_budget,
                    )
                else:
                    return BudgetCheckResult(
                        allowed=False,
                        status_code=429,
                        action="hard_cap",
                        error_type="budget_exceeded",
                        error_code="budget_cap_exceeded",
                        error_message=(
                            f"Hard budget cap exceeded: key '{key.name}' has reached its spend limit "
                            f"of ${max_budget:.4f} (current spend: ${current_spend:.4f}). "
                            f"Reset spend or increase limit in WRAP Settings."
                        ),
                        current_spend_usd=current_spend,
                        max_budget_usd=max_budget,
                    )

        # 4. Budget OK
        return BudgetCheckResult(
            allowed=True,
            action="proceed",
            current_spend_usd=current_spend,
            max_budget_usd=max_budget,
        )

    @classmethod
    async def record_key_spend(
        cls,
        session: AsyncSession,
        key_id: UUID,
        actual_cost_usd: float,
        value_saved_usd: float,
    ) -> None:
        """Atomically record financial attribution on key."""
        try:
            stmt = select(GatewayApiKey).where(GatewayApiKey.id == key_id)
            result = await session.execute(stmt)
            key = result.scalar_one_or_none()
            if not key:
                return

            if actual_cost_usd > 0:
                current_spend = getattr(key, "spend_usd", 0.0) or 0.0
                key.spend_usd = round(current_spend + actual_cost_usd, 6)
                spend_velocity_tracker.record_spend(str(key_id), actual_cost_usd)

            if value_saved_usd > 0:
                current_saved = getattr(key, "value_saved_usd", 0.0) or 0.0
                key.value_saved_usd = round(current_saved + value_saved_usd, 6)

            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Failed to record key spend attribution for key %s", key_id)
