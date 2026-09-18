"""Lane 1 tests for trustworthy TMUX sensor history semantics."""

from sentinel.sensors.tmux.parser import TmuxStateParserV11


SOCKET = "/tmp/tmux-1000/default"
GEN_A = "uid=1000;pid=321;start=654"
GEN_B = "uid=1000;pid=654;start=987"
PANE_LINE = (
    "$1\tairiv\t@1\t0\tworker-a\t0\t%1\t"
    "1\t0\tbash\t100\n"
)


def configure_parser(
    parser,
    monkeypatch,
    *,
    generations,
    captures,
    generation_matches=None,
):
    generation_iter = iter(generations)
    capture_iter = iter(captures)
    match_iter = (
        iter(generation_matches)
        if generation_matches is not None
        else None
    )

    monkeypatch.setattr(
        parser,
        "_list_panes",
        lambda *, server_socket=None: PANE_LINE,
    )

    def resolve():
        generation = next(generation_iter)
        if generation is None:
            return None
        return SOCKET, generation

    monkeypatch.setattr(
        parser,
        "_resolve_server_identity",
        resolve,
    )
    monkeypatch.setattr(
        parser,
        "capture_pane_content",
        lambda pane_id, *, server_socket=None: next(capture_iter),
    )
    monkeypatch.setattr(
        parser,
        "_server_generation_matches",
        (
            (lambda socket, generation: next(match_iter))
            if match_iter is not None
            else (lambda socket, generation: True)
        ),
    )


def test_failed_capture_is_unknown_and_does_not_poison_history(monkeypatch):
    parser = TmuxStateParserV11()
    configure_parser(
        parser,
        monkeypatch,
        generations=[GEN_A, GEN_A, GEN_A],
        captures=["steady-output", None, "steady-output"],
    )

    first = parser.inspect_panes()[0]
    failed = parser.inspect_panes()[0]
    recovered = parser.inspect_panes()[0]

    assert first["capture_ok"] is True
    assert first["first_observation"] is True
    assert first["output_changed"] is False

    assert failed["capture_ok"] is False
    assert failed["output_length"] is None
    assert failed["output_sha256"] is None
    assert failed["output_changed"] is None

    # The failed capture must not replace the prior successful baseline with
    # an empty-output hash. Returning to the same observed output is unchanged.
    assert recovered["capture_ok"] is True
    assert recovered["first_observation"] is False
    assert recovered["output_changed"] is False


def test_reused_pane_id_in_new_server_generation_starts_new_history(monkeypatch):
    parser = TmuxStateParserV11()
    configure_parser(
        parser,
        monkeypatch,
        generations=[GEN_A, GEN_B],
        captures=["generation-a", "generation-b"],
    )

    generation_a = parser.inspect_panes()[0]
    generation_b = parser.inspect_panes()[0]

    assert generation_a["server_generation"] == GEN_A
    assert generation_a["first_observation"] is True
    assert generation_a["output_changed"] is False

    # TMUX may reuse pane_id after restart. Strong generation identity must
    # prevent old content/command history from being attached to the new pane.
    assert generation_b["server_generation"] == GEN_B
    assert generation_b["pane_id"] == generation_a["pane_id"]
    assert generation_b["first_observation"] is True
    assert generation_b["previous_command"] is None
    assert generation_b["output_changed"] is False


def test_unresolved_identity_does_not_seed_later_strong_history(monkeypatch):
    parser = TmuxStateParserV11()
    configure_parser(
        parser,
        monkeypatch,
        generations=[None, GEN_A],
        captures=["weak-observation", "strong-observation"],
        generation_matches=[True],
    )

    unresolved = parser.inspect_panes()[0]
    strong = parser.inspect_panes()[0]

    assert unresolved["tmux_identity_valid"] is False
    assert unresolved["server_generation"] is None
    assert unresolved["output_changed"] is None
    assert unresolved["first_observation"] is None

    assert strong["tmux_identity_valid"] is True
    assert strong["server_generation"] == GEN_A
    assert strong["first_observation"] is True
    assert strong["previous_command"] is None
    assert strong["output_changed"] is False


def test_generation_race_invalidates_correlation_and_does_not_commit_history(
    monkeypatch,
):
    parser = TmuxStateParserV11()
    configure_parser(
        parser,
        monkeypatch,
        generations=[GEN_A, GEN_A, GEN_B],
        captures=["baseline", "racing-output", "new-generation"],
        generation_matches=[True, False, True],
    )

    baseline = parser.inspect_panes()[0]
    raced = parser.inspect_panes()[0]
    after_restart = parser.inspect_panes()[0]

    assert baseline["tmux_identity_valid"] is True
    assert baseline["first_observation"] is True

    assert raced["tmux_identity_valid"] is False
    assert raced["server_generation"] is None
    assert raced["previous_command"] is None
    assert raced["output_changed"] is None
    assert raced["first_observation"] is None

    # The raced batch is never committed. The stable new server generation
    # therefore begins with a clean, identity-correct activity baseline.
    assert after_restart["tmux_identity_valid"] is True
    assert after_restart["server_generation"] == GEN_B
    assert after_restart["first_observation"] is True
    assert after_restart["previous_command"] is None
    assert after_restart["output_changed"] is False
