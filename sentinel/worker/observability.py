"""Process evidence for completed capability cycles; no runtime authority.

The journal covers Incident results returned by the runtime, not every sensor
sample. Correlation reads the existing store, including terminal investigations.
Identical correlation records are suppressed for this writer's lifetime.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile


logger = logging.getLogger(__name__)
REPOSITORY_ROOT = Path(os.path.realpath(__file__)).parents[2]


class LiveEvidenceObservability:
    def __init__(self, root: str | Path | None = None) -> None:
        selected = Path(root if root is not None else os.environ.get(
            "AIRIV_SENTINEL_RUNTIME_DIR",
            str(REPOSITORY_ROOT / "var" / "runtime"),
        ))
        self.root = Path(os.path.realpath(REPOSITORY_ROOT / selected))
        if not self.root.is_relative_to(REPOSITORY_ROOT):
            raise ValueError("Runtime evidence directory must be repository-local")
        self.pid = os.getpid()
        self.invocation_id = os.environ.get("INVOCATION_ID")
        self._last_records: dict[tuple, dict] = {}

    def _prepare_directory(self) -> None:
        """Reject redirected or foreign-owned evidence paths before writing."""
        if Path(os.path.realpath(self.root)) != self.root:
            raise ValueError("Runtime evidence directory was redirected")
        for path in (self.root, *self.root.parents):
            if path.exists() and path.stat().st_uid != os.getuid():
                raise ValueError("Runtime evidence directory must be user-owned")
            if path == REPOSITORY_ROOT:
                break
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in ("capability_status.json", "live_observations.jsonl",
                     "commander_decisions.jsonl"):
            path = self.root / name
            if path.is_symlink() or (path.exists() and path.stat().st_uid != os.getuid()):
                raise ValueError("Runtime evidence file must be user-owned and local")

    def _identity(self, worker_id: str) -> dict:
        return dict(schema_version=1, pid=self.pid,
                    invocation_id=self.invocation_id, worker_id=worker_id)

    def commander_decision(self, facts: dict) -> None:
        """Append facts supplied by the canonical decision pipeline only."""
        record = dict(facts, schema_version=1, pid=os.getpid(),
                      invocation_id=os.environ.get("INVOCATION_ID"),
                      timestamp=datetime.now(timezone.utc).isoformat())
        try:
            self._prepare_directory()
            with (self.root / "commander_decisions.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except Exception as error:
            logger.warning("Commander evidence persistence failed: %s", type(error).__name__)

    def status(self, *, worker_id, state, iteration, last_cycle_at,
               last_cycle_status, last_error_type) -> None:
        """Atomic replacement lets concurrent readers see complete JSON only."""
        record = self._identity(worker_id)
        record.update(state=state, iteration=iteration,
                      last_cycle_at=last_cycle_at.isoformat() if last_cycle_at else None,
                      last_cycle_status=last_cycle_status,
                      last_error_type=last_error_type)
        temporary = None
        try:
            self._prepare_directory()
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                             dir=self.root, delete=False) as handle:
                temporary = handle.name
                json.dump(record, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.root / "capability_status.json")
        except Exception as error:
            logger.warning("Capability status persistence failed: %s", type(error).__name__)
        finally:
            if temporary is not None and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError as error:
                    logger.warning("Status temporary cleanup failed: %s", type(error).__name__)

    def observations(self, runtime, results, *, worker_id, iteration) -> None:
        """Called only after the single canonical cycle has returned."""
        if not results:
            return
        try:
            investigations = runtime.diagnostic.store.recover()
            lookup_status = "INVESTIGATION_UNAVAILABLE"
        except Exception:
            investigations = []
            lookup_status = "INVESTIGATION_LOOKUP_FAILED"
        try:
            for result in results:
                component_id = getattr(result, "component_id", None)
                incident_id = getattr(result, "incident_id", None)
                matches = [item.investigation_id for item in investigations
                           if incident_id is not None and component_id is not None
                           and item.incident_id == incident_id
                           and item.component_id == component_id]
                investigation_id = matches[0] if len(matches) == 1 else None
                correlation_status = (
                    "INCIDENT_UNAVAILABLE" if incident_id is None else
                    "COMPONENT_UNAVAILABLE" if component_id is None else
                    "CORRELATED" if investigation_id is not None else
                    "INVESTIGATION_AMBIGUOUS" if len(matches) > 1 else lookup_status
                )
                record = self._identity(worker_id)
                # Exclude sampling timestamps and evidence sequence IDs. Only a
                # digest of selected sensor facts leaves the canonical evidence.
                evidence = result.get_evidence_records() if hasattr(result, "get_evidence_records") else ()
                # Diagnostics may append lifecycle evidence after submission.
                # Retain the latest actual pane observation, not a later note.
                snapshot = next((entry.observation_snapshot
                                 for entry in reversed(evidence)
                                 if component_id is not None
                                 and entry.observation_snapshot.get("pane_id") == component_id), {})
                facts = {name: snapshot.get(name) for name in (
                    "pane_id", "pane_dead", "capture_ok", "current_command",
                    "activity_state", "output_sha256", "agent_identity",
                )}
                facts["anomaly_type"] = getattr(result, "anomaly_type", None)
                fingerprint = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()
                record.update(source=snapshot.get("source") or "runtime.run_once", component_id=component_id,
                              incident_id=incident_id, investigation_id=investigation_id,
                              correlation_status=correlation_status,
                              observation_fingerprint=fingerprint)
                key = (worker_id, component_id, incident_id)
                if self._last_records.get(key) == record:
                    continue
                line = dict(record, iteration=iteration,
                            timestamp=datetime.now(timezone.utc).isoformat())
                self._prepare_directory()
                with (self.root / "live_observations.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(line, sort_keys=True) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                self._last_records[key] = record
        except Exception as error:
            logger.warning("Live observation persistence failed: %s", type(error).__name__)
