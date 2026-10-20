import pytest
import uuid
from datetime import datetime, timezone

from src.schemas.openai import ChatCompletionRequest, ChatMessage
from src.intelligence.analysis.feature_extractor import extract_features
from src.intelligence.analysis.request_analyzer import RequestAnalyzer
from src.intelligence.resources.worker_state import WorkerState
from src.intelligence.resources.quota_manager import QuotaManager
from src.intelligence.scheduling.hard_constraint_filter import HardEligibilityFilter
from src.intelligence.scheduling.policy_engine import PolicyEngine
from src.intelligence.resources.capability_engine import CapabilityEngine
from src.intelligence.resources.performance_engine import PerformanceEngine
from src.intelligence.scheduling.allocation_optimizer import AllocationOptimizer
from src.intelligence.scheduling.candidate_selector import CandidateSelector


def test_feature_extractor_simple():
    features = extract_features(
        model="auto",
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        stream=False,
    )
    assert features.is_auto_model
    assert features.requested_model == "auto"
    assert not features.streaming
    assert features.message_count == 1
    assert features.question_count > 0
    assert features.code_ratio < 0.1
    assert features.has_tool_requirement is False


def test_feature_extractor_coding():
    content = "Write a python script\n```python\ndef foo():\n    pass\n```"
    features = extract_features(
        model="gpt-4",
        messages=[{"role": "user", "content": content}],
        stream=True,
    )
    assert not features.is_auto_model
    assert features.streaming
    assert features.code_ratio > 0.0
    assert features.instruction_count > 0


def test_request_analyzer():
    analyzer = RequestAnalyzer()
    req = ChatCompletionRequest(
        model="auto",
        messages=[ChatMessage(role="user", content="Write a quick python script\n```python\nprint(1)\n```")]
    )
    profile = analyzer.analyze(req, request_id="test_req")
    
    assert profile.request_id == "test_req"
    assert profile.is_auto_model
    assert profile.coding_demand > 0.0
    assert profile.complexity > 0.0


def test_candidate_selector_explicit_model():
    selector = CandidateSelector()
    workers = [
        WorkerState(worker_id=uuid.uuid4(), provider="groq", credential_id=uuid.uuid4(), model="llama-3"),
        WorkerState(worker_id=uuid.uuid4(), provider="gemini", credential_id=uuid.uuid4(), model="gemini-1.5"),
    ]
    
    # Explicit model
    req = ChatCompletionRequest(model="llama-3", messages=[ChatMessage(role="user", content="hi")])
    profile = RequestAnalyzer().analyze(req, request_id="test")
    candidates = selector.select(profile, workers)
    
    assert len(candidates) == 1
    assert candidates[0].model == "llama-3"
    
    # Auto model
    req_auto = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="hi")])
    profile_auto = RequestAnalyzer().analyze(req_auto, request_id="test")
    candidates_auto = selector.select(profile_auto, workers)
    
    assert len(candidates_auto) == 2


def test_hard_eligibility_filter():
    filter_eng = HardEligibilityFilter()
    req = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="hi")])
    profile = RequestAnalyzer().analyze(req, request_id="test")
    
    # Enabled and healthy
    w1 = WorkerState(worker_id=uuid.uuid4(), provider="groq", credential_id=uuid.uuid4(), model="llama", enabled=True, healthy=True)
    # Disabled
    w2 = WorkerState(worker_id=uuid.uuid4(), provider="groq", credential_id=uuid.uuid4(), model="llama", enabled=False, healthy=True)
    # Unhealthy
    w3 = WorkerState(worker_id=uuid.uuid4(), provider="groq", credential_id=uuid.uuid4(), model="llama", enabled=True, healthy=False)
    # Quota exhausted
    w4 = WorkerState(worker_id=uuid.uuid4(), provider="groq", credential_id=uuid.uuid4(), model="llama", enabled=True, healthy=True, quota_requests_remaining=0, quota_source="provider_reported")
    
    res = filter_eng.filter(profile, [w1, w2, w3, w4])
    
    assert len(res.eligible) == 1
    assert res.eligible[0].worker_id == w1.worker_id
    assert len(res.rejected) == 3
    
    reasons = [r.reason for r in res.rejected]
    assert "disabled" in reasons
    assert "unhealthy" in reasons
    assert "quota_exhausted" in reasons


def test_performance_prediction():
    eng = PerformanceEngine()
    req = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="hi")])
    profile = RequestAnalyzer().analyze(req, request_id="test")
    
    w_fast = WorkerState(worker_id=uuid.uuid4(), provider="p1", credential_id=uuid.uuid4(), model="m1", ttft_p50_ms=100.0, tps_p50=100.0, sample_count=100)
    w_slow = WorkerState(worker_id=uuid.uuid4(), provider="p2", credential_id=uuid.uuid4(), model="m2", ttft_p50_ms=1000.0, tps_p50=10.0, sample_count=100)
    w_loaded = WorkerState(worker_id=uuid.uuid4(), provider="p3", credential_id=uuid.uuid4(), model="m3", ttft_p50_ms=100.0, tps_p50=100.0, sample_count=100, active_requests=10)
    
    pred_fast = eng.predict(profile, w_fast)
    pred_slow = eng.predict(profile, w_slow)
    pred_loaded = eng.predict(profile, w_loaded)
    
    assert pred_fast.predicted_latency_ms < pred_slow.predicted_latency_ms
    assert pred_fast.predicted_latency_ms < pred_loaded.predicted_latency_ms
    assert pred_fast.confidence > 0.8
    
    score_fast = eng.latency_score(pred_fast)
    score_slow = eng.latency_score(pred_slow)
    assert score_fast > score_slow


def test_allocation_optimizer():
    opt = AllocationOptimizer()
    pe = PolicyEngine()
    req = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="hi")])
    profile = RequestAnalyzer().analyze(req, request_id="test")
    
    w1 = WorkerState(worker_id=uuid.uuid4(), provider="p1", credential_id=uuid.uuid4(), model="m1", ttft_p50_ms=100.0, tps_p50=100.0, sample_count=100)
    w2 = WorkerState(worker_id=uuid.uuid4(), provider="p2", credential_id=uuid.uuid4(), model="m2", ttft_p50_ms=1000.0, tps_p50=10.0, sample_count=100)
    
    weights = pe.get_weights("fastest")
    selected, all_scored = opt.score_and_select(profile, [w1, w2], weights)
    
    assert selected is not None
    assert selected.worker_id == w1.worker_id
    assert selected.scores.latency > all_scored[1].scores.latency
