from handler_registry import HandlerRegistry


def test_handler_registry_registers_and_lists_handlers():
    registry = HandlerRegistry()

    def handler(request):
        return {"ok": True}

    registry.register("echo", handler)

    assert registry.list_handlers() == ["echo"]
    assert registry.get("echo") is handler


def test_handler_registry_rejects_duplicate_registration():
    registry = HandlerRegistry()

    def handler(request):
        return {"ok": True}

    registry.register("echo", handler)

    try:
        registry.register("echo", handler)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_handler_registry_unregisters_handler():
    registry = HandlerRegistry()

    def handler(request):
        return {"ok": True}

    registry.register("echo", handler)
    removed = registry.unregister("echo")

    assert removed is handler
    assert registry.list_handlers() == []


def test_handler_registry_lookup_rejects_unknown_task_type():
    registry = HandlerRegistry()

    try:
        registry.get("missing")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_handler_registry_rejects_invalid_input():
    registry = HandlerRegistry()

    try:
        registry.register("", lambda request: None)
        assert False, "expected ValueError"
    except ValueError:
        pass

    try:
        registry.get(123)
        assert False, "expected ValueError"
    except ValueError:
        pass
