"""PolicyEngine — maps routing policy names to weight vectors.

Supported policies:
- balanced:      equal emphasis on all dimensions
- fastest:       strongly prefer low latency
- quality_first: prefer capability match and reliability
- quota_saver:   prefer workers with abundant quota

Each policy provides a weight vector for the five scoring dimensions:
capability, latency, reliability, quota, load.

Architecture supports future runtime configuration, but Phase 2A uses
static policy definitions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyWeights:
    """Weight vector for multi-objective allocation.

    All weights are positive. They don't need to sum to 1.0 — the
    AllocationOptimizer normalizes them.
    """
    capability: float
    latency: float
    reliability: float
    quota: float
    load: float

    @property
    def total(self) -> float:
        return self.capability + self.latency + self.reliability + self.quota + self.load


# Policy definitions
_POLICIES: dict[str, PolicyWeights] = {
    "balanced": PolicyWeights(
        capability=1.0,
        latency=1.0,
        reliability=1.0,
        quota=0.8,
        load=0.8,
    ),
    "fastest": PolicyWeights(
        capability=0.3,
        latency=2.0,
        reliability=0.8,
        quota=0.3,
        load=1.5,
    ),
    "quality_first": PolicyWeights(
        capability=2.0,
        latency=0.5,
        reliability=1.5,
        quota=0.5,
        load=0.3,
    ),
    "quota_saver": PolicyWeights(
        capability=0.5,
        latency=0.5,
        reliability=0.8,
        quota=2.0,
        load=0.5,
    ),
}

# Default policy when none specified
DEFAULT_POLICY = "balanced"

# All valid policy names
VALID_POLICIES = frozenset(_POLICIES.keys())


class PolicyEngine:
    """Maps policy names to weight vectors."""

    def get_weights(self, policy: str) -> PolicyWeights:
        """Get the weight vector for a routing policy.

        Falls back to 'balanced' for unknown policy names.
        """
        return _POLICIES.get(policy, _POLICIES[DEFAULT_POLICY])

    def get_policy_name(self, policy: str | None) -> str:
        """Normalize and validate a policy name."""
        if policy is None:
            return DEFAULT_POLICY
        if policy in VALID_POLICIES:
            return policy
        return DEFAULT_POLICY
