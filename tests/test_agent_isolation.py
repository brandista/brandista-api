"""Tests for agent instance isolation between concurrent runs."""
import pytest
from agents.orchestrator import GrowthEngineOrchestrator


def test_run_analysis_creates_fresh_agents():
    """Each call to _create_agents_for_run must return fresh agent instances."""
    orchestrator = GrowthEngineOrchestrator()

    agents_run1 = orchestrator._create_agents_for_run()
    agents_run2 = orchestrator._create_agents_for_run()

    assert len(agents_run1) > 0, "Expected at least one agent"
    for agent_id in agents_run1:
        assert agents_run1[agent_id] is not agents_run2[agent_id], \
            f"Agent {agent_id} is the same instance across runs — state leak risk"


def test_orchestrator_has_is_running_property():
    """orchestrator.is_running must exist and return a bool."""
    orchestrator = GrowthEngineOrchestrator()
    result = orchestrator.is_running
    assert isinstance(result, bool)
    assert result is False  # No runs active when freshly created
