import os
from pathlib import Path

from sentinel.remediation_execution_identity import (
    RemediationExecutionIdentityJournal,
)


def test_default_execution_identity_journal_is_test_isolated():
    configured = Path(
        os.environ["AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR"]
    )

    repository_default = (
        Path(__file__).resolve().parents[1]
        / "var"
        / "execution_identity"
    )

    journal = RemediationExecutionIdentityJournal()

    assert journal.root == configured
    assert journal.root.resolve() != repository_default.resolve()


def test_test_journal_path_is_not_repository_runtime():
    configured = Path(
        os.environ["AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR"]
    ).resolve()

    repository_runtime = (
        Path(__file__).resolve().parents[1]
        / "var"
        / "execution_identity"
    ).resolve()

    assert configured != repository_runtime
    assert repository_runtime not in configured.parents
