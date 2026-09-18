from worker import Worker


def test_worker_executes_one_task_deterministically():
    worker = Worker()

    report = worker.execute({"id": "TASK-1", "name": "queue update"})

    assert report.task_id == "TASK-1"
    assert report.task_name == "queue update"
    assert report.status == "completed"
    assert report.result == {"status": "ok"}
    assert report.evidence["dispatch"]["dispatched"] is True


def test_worker_rejects_invalid_task():
    worker = Worker()

    try:
        worker.execute({"id": "", "name": "bad"})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_worker_dispatch_is_deterministic():
    worker = Worker()
    task = {"id": "TASK-2", "name": "read queue"}

    first = worker.dispatch(task)
    second = worker.dispatch(task)

    assert first == second == {
        "task_id": "TASK-2",
        "task_name": "read queue",
        "dispatched": True,
        "kind": "deterministic",
    }


def test_worker_result_is_deterministic_for_same_task():
    worker = Worker()
    task = {"id": "TASK-3", "name": "persist state"}

    first = worker.execute(task)
    second = worker.execute(task)

    assert first.to_dict() == second.to_dict()
