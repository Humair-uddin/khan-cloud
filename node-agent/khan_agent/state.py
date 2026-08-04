from __future__ import annotations

from enum import StrEnum


class AgentState(StrEnum):
    INSTALLED = "installed"
    CONFIGURED = "configured"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    MAINTENANCE = "maintenance"
    STOPPED = "stopped"


_ALLOWED_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.INSTALLED: {AgentState.CONFIGURED, AgentState.STOPPED},
    AgentState.CONFIGURED: {
        AgentState.CONNECTING,
        AgentState.MAINTENANCE,
        AgentState.STOPPED,
    },
    AgentState.CONNECTING: {
        AgentState.CONNECTED,
        AgentState.DISCONNECTED,
        AgentState.DEGRADED,
        AgentState.STOPPED,
    },
    AgentState.CONNECTED: {
        AgentState.DEGRADED,
        AgentState.DISCONNECTED,
        AgentState.MAINTENANCE,
        AgentState.STOPPED,
    },
    AgentState.DEGRADED: {
        AgentState.CONNECTING,
        AgentState.CONNECTED,
        AgentState.DISCONNECTED,
        AgentState.MAINTENANCE,
        AgentState.STOPPED,
    },
    AgentState.DISCONNECTED: {
        AgentState.CONNECTING,
        AgentState.MAINTENANCE,
        AgentState.STOPPED,
    },
    AgentState.MAINTENANCE: {
        AgentState.CONFIGURED,
        AgentState.STOPPED,
    },
    AgentState.STOPPED: set(),
}


class InvalidStateTransition(RuntimeError):
    pass


class StateMachine:
    def __init__(self) -> None:
        self.current = AgentState.INSTALLED

    def transition(self, new_state: AgentState) -> None:
        if new_state == self.current:
            return
        if new_state not in _ALLOWED_TRANSITIONS[self.current]:
            raise InvalidStateTransition(f"{self.current} -> {new_state} is not allowed")
        self.current = new_state
