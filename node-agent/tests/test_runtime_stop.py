from khan_agent.runtime import AgentRuntime


class FakeEvent:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class FakeRunningLoop:
    def __init__(self):
        self.callbacks = []

    def is_running(self):
        return True

    def call_soon_threadsafe(self, callback):
        self.callbacks.append(callback)


def test_runtime_request_stop_uses_event_loop_threadsafe_callback():
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.stop_event = FakeEvent()
    runtime._event_loop = FakeRunningLoop()

    runtime.request_stop()

    assert runtime.stop_event.was_set is False
    assert len(runtime._event_loop.callbacks) == 1

    runtime._event_loop.callbacks[0]()

    assert runtime.stop_event.was_set is True


def test_runtime_request_stop_sets_event_directly_before_loop_available():
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.stop_event = FakeEvent()
    runtime._event_loop = None

    runtime.request_stop()

    assert runtime.stop_event.was_set is True


def test_signal_handler_installation_is_skipped_on_windows(monkeypatch):
    runtime = AgentRuntime.__new__(AgentRuntime)

    monkeypatch.setattr(
        "khan_agent.runtime.platform.system",
        lambda: "Windows",
    )

    class LoopThatMustNotReceiveSignalHandlers:
        def add_signal_handler(self, *args, **kwargs):
            raise AssertionError(
                "Windows runtime must not install Unix asyncio signal handlers"
            )

    monkeypatch.setattr(
        "khan_agent.runtime.asyncio.get_running_loop",
        lambda: LoopThatMustNotReceiveSignalHandlers(),
    )

    runtime._install_signal_handlers()
