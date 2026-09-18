from io import StringIO
from types import SimpleNamespace

import runtime_cli


class FakeRuntime:
    report = None
    instances = []

    def __init__(self, queue_path):
        self.queue_path = queue_path
        self.run_count = 0
        type(self).instances.append(self)

    def run_once(self):
        self.run_count += 1
        return self.report


def test_main_reports_success_and_returns_zero(monkeypatch):
    FakeRuntime.instances = []
    FakeRuntime.report = SimpleNamespace(
        status="success",
        task_id="TASK-1",
        task_name="first",
        verification="PASS",
    )
    monkeypatch.setattr(runtime_cli, "Runtime", FakeRuntime)
    output = StringIO()

    result = runtime_cli.main(("queue.yaml",), output)

    assert result == 0
    assert output.getvalue() == "STATUS=PASS TASK_ID=TASK-1 TASK_NAME=first VERIFICATION=PASS\n"
    assert len(FakeRuntime.instances) == 1
    assert FakeRuntime.instances[0].run_count == 1


def test_main_reports_failure_and_returns_one(monkeypatch):
    FakeRuntime.instances = []
    FakeRuntime.report = SimpleNamespace(
        status="failed",
        task_id="TASK-2",
        task_name="second",
        verification="FAIL",
    )
    monkeypatch.setattr(runtime_cli, "Runtime", FakeRuntime)
    output = StringIO()

    result = runtime_cli.main(("queue.yaml",), output)

    assert result == 1
    assert output.getvalue() == "STATUS=FAIL TASK_ID=TASK-2 TASK_NAME=second VERIFICATION=FAIL\n"
    assert len(FakeRuntime.instances) == 1
    assert FakeRuntime.instances[0].run_count == 1


def test_main_rejects_missing_queue_path_without_creating_runtime(monkeypatch):
    FakeRuntime.instances = []
    monkeypatch.setattr(runtime_cli, "Runtime", FakeRuntime)
    output = StringIO()

    result = runtime_cli.main((), output)

    assert result == 1
    assert output.getvalue() == "usage: runtime_cli.py <queue-path>\n"
    assert FakeRuntime.instances == []
