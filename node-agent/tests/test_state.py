import pytest

from khan_agent.state import AgentState, InvalidStateTransition, StateMachine


def test_valid_agent_lifecycle() -> None:
    machine = StateMachine()
    machine.transition(AgentState.CONFIGURED)
    machine.transition(AgentState.CONNECTING)
    machine.transition(AgentState.CONNECTED)
    machine.transition(AgentState.STOPPED)
    assert machine.current is AgentState.STOPPED


def test_invalid_transition_is_rejected() -> None:
    machine = StateMachine()
    with pytest.raises(InvalidStateTransition):
        machine.transition(AgentState.CONNECTED)
