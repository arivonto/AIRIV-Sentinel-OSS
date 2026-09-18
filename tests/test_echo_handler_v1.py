from handlers.echo_handler import ExecutionResult, echo, echo_handler


def test_echo_returns_successful_result_with_original_message():
    result = echo("hello")

    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.message == "hello"


def test_echo_handler_delegates_to_echo():
    result = echo_handler("deterministic")

    assert result.success is True
    assert result.message == "deterministic"


def test_echo_rejects_non_string_input():
    try:
        echo(123)
        assert False, "expected TypeError"
    except TypeError:
        pass
