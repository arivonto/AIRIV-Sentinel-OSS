"""Evidence-complete, read-only incident diagnostics reporting for S1.

This boundary correlates existing canonical Incident evidence with existing
Diagnostic Engine persistence. It does not create Incident lifecycle authority,
Commander authority, remediation policy, execution authority, or verification
authority.

The resulting report remains compatible with AIRIV_SENTINEL_INCIDENT_REPORT_V1
and can therefore be persisted by IncidentReportStore. Additive S1 fields provide
explicit evidence completeness, correlation, deterministic ordering, and a
SHA-256 timeline integrity chain.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from sentinel.incident_reporting import IncidentReport, IncidentReportBuilder


_EVIDENCE_PROFILE = "AIRIV_SENTINEL_EVIDENCE_COMPLETE_S1_V1"
_EMPTY_TIMELINE_SHA256 = hashlib.sha256(b"").hexdigest()


def _json_value(value: Any) -> Any:
    """Convert canonical model values into deterministic JSON-compatible data."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence timestamps must include timezone information")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_json_value(item) for item in sorted(value, key=repr)]
    return deepcopy(value)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return deepcopy(value)


def _parse_timestamp(value: Any, field: str = "timestamp") -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    else:
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _signal_type(value: Any) -> str:
    return str(value or "UNKNOWN").strip().upper()


def _category(signal_type: str) -> str:
    if (
        "COMMANDER" in signal_type
        or "HANDOFF" in signal_type
        or "ESCALAT" in signal_type
    ):
        return "commander"
    if (
        signal_type in {"ANOMALY", "CONTRACT_VIOLATION", "OBSERVATION"}
        or "DETECT" in signal_type
    ):
        return "detection"
    if any(
        token in signal_type
        for token in (
            "DIAG",
            "INVESTIG",
            "HYPOTHESIS",
            "UNDERSTAND",
        )
    ):
        return "diagnostic"
    if any(
        token in signal_type
        for token in ("VERIFY", "VERIFICATION", "RECOVERY")
    ):
        return "verification"
    if any(
        token in signal_type
        for token in ("REMEDIAT", "EXECUTION", "ACTION")
    ):
        return "remediation"
    return "other"


def _is_remediation_event(event: Mapping[str, Any]) -> bool:
    """Return True for events that carry canonical remediation evidence."""
    signal_type = _signal_type(event.get("signal_type"))
    return event.get("category") == "remediation" or "REMEDIAT" in signal_type


def _is_verification_event(event: Mapping[str, Any]) -> bool:
    """Return True for explicit verification facts, including compound signals."""
    signal_type = _signal_type(event.get("signal_type"))
    if event.get("category") == "verification":
        return True
    if "VERIFICATION" in signal_type:
        return True
    return signal_type.endswith("_VERIFIED") and "UNVERIFIED" not in signal_type


def _is_decision_event(event: Mapping[str, Any]) -> bool:
    signal_type = _signal_type(event.get("signal_type"))
    if any(token in signal_type for token in ("DECISION", "COMMANDER", "HANDOFF", "POLICY")):
        return True
    signal = event.get("signal_snapshot") or {}
    if not isinstance(signal, Mapping):
        return False
    return any(
        key in signal
        for key in (
            "decision",
            "commander_intent",
            "remediation_policy_decision",
            "commander_required",
            "commander_action_required",
        )
    )


def _commander_required(event: Mapping[str, Any]) -> bool:
    signal = event.get("signal_snapshot") or {}
    if not isinstance(signal, Mapping):
        return False
    return any(
        signal.get(key) is True
        for key in (
            "commander_required",
            "requires_commander",
            "approval_required",
            "authorization_required",
            "commander_action_required",
        )
    )


def _observed_state(event: Mapping[str, Any]) -> Any:
    observation = event.get("observation_snapshot") or {}
    signal = event.get("signal_snapshot") or {}
    for mapping in (observation, signal):
        if not isinstance(mapping, Mapping):
            continue
        for key in (
            "activity_state",
            "observed_state",
            "current_state",
            "state",
        ):
            value = mapping.get(key)
            if value not in (None, ""):
                return _json_value(value)
    return None


def _normalized_inputs(event: Mapping[str, Any]) -> dict[str, Any]:
    observation = event.get("observation_snapshot") or {}
    if not isinstance(observation, Mapping):
        return {}
    return _json_value(observation)


def _terminal_final_status_recorded(base: Mapping[str, Any]) -> bool:
    """Return True only when canonical terminal lifecycle has a final outcome."""
    lifecycle_state = str(base.get("lifecycle_state") or "").strip().upper()
    final_outcome = str(base.get("final_outcome") or "").strip()
    return lifecycle_state in {"TERMINAL", "RESOLVED"} and bool(final_outcome)


def _base_incident_events(source: Any, base: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Prefer canonical EvidenceRecord objects; fall back to serialized history."""
    records_method = getattr(source, "get_evidence_records", None)
    if callable(records_method):
        records = records_method()
        events: list[dict[str, Any]] = []
        for record in records:
            if record.incident_id != base["incident_id"]:
                raise ValueError("incident evidence incident_id mismatch")
            if record.component_id != base["component_id"]:
                raise ValueError("incident evidence component_id mismatch")
            events.append(
                {
                    "source": "INCIDENT_EVIDENCE",
                    "source_id": record.evidence_id,
                    "timestamp": record.timestamp,
                    "signal_type": _signal_type(record.evidence_type),
                    "reason": record.reason,
                    "observation_snapshot": _json_value(record.observation_snapshot),
                    "signal_snapshot": _json_value(record.signal_snapshot),
                    "correlation": {
                        "incident_id": record.incident_id,
                        "component_id": record.component_id,
                        "evidence_id": record.evidence_id,
                    },
                }
            )
        return events

    events = []
    for position, event in enumerate(base.get("timeline") or (), start=1):
        events.append(
            {
                "source": "INCIDENT_HISTORY",
                "source_id": f"legacy:{base['incident_id']}:{position:08d}",
                "timestamp": event.get("timestamp"),
                "signal_type": _signal_type(event.get("signal_type")),
                "reason": event.get("reason") or "",
                "observation_snapshot": _json_value(
                    event.get("observation_snapshot") or {}
                ),
                "signal_snapshot": _json_value(event.get("signal_snapshot") or {}),
                "correlation": {
                    "incident_id": base["incident_id"],
                    "component_id": base["component_id"],
                },
            }
        )
    return events


def _diagnostic_events(
    diagnostic_store: Any,
    incident_id: str,
    component_id: str,
) -> list[dict[str, Any]]:
    """Read canonical diagnostic persistence and correlate it to one Incident."""
    if diagnostic_store is None:
        return []
    recover = getattr(diagnostic_store, "recover", None)
    if not callable(recover):
        raise TypeError("diagnostic_store must provide callable recover()")

    investigations = []
    for investigation in recover():
        if investigation.incident_id != incident_id:
            continue
        if investigation.component_id != component_id:
            raise ValueError("diagnostic component_id mismatch for incident_id")
        investigations.append(investigation)

    investigations.sort(
        key=lambda item: (
            _parse_timestamp(item.created_at, "investigation.created_at"),
            item.investigation_id,
        )
    )

    events: list[dict[str, Any]] = []
    for investigation in investigations:
        correlation = {
            "incident_id": incident_id,
            "component_id": component_id,
            "investigation_id": investigation.investigation_id,
        }
        events.append(
            {
                "source": "DIAGNOSTIC_STORE",
                "source_id": f"investigation:{investigation.investigation_id}:created",
                "timestamp": _json_value(investigation.created_at),
                "signal_type": "INVESTIGATION_CREATED",
                "reason": "Diagnostic investigation registered.",
                "observation_snapshot": {},
                "signal_snapshot": {
                    "trigger": investigation.trigger,
                    "state": _json_value(investigation.state),
                    "evidence_ids": list(investigation.evidence_ids),
                    "diagnosis_id": investigation.diagnosis_id,
                },
                "correlation": correlation,
            }
        )

        observations = []
        for observation_id in investigation.observation_ids:
            observation = diagnostic_store.get_observation(
                investigation.investigation_id,
                observation_id,
            )
            if observation is None:
                raise ValueError(
                    f"diagnostic observation missing: {observation_id}"
                )
            if observation.investigation_id != investigation.investigation_id:
                raise ValueError("diagnostic observation investigation_id mismatch")
            if observation.component_id != component_id:
                raise ValueError("diagnostic observation component_id mismatch")
            observations.append(observation)

        observations.sort(
            key=lambda item: (
                _parse_timestamp(item.observed_at, "observation.observed_at"),
                item.observation_id,
            )
        )
        for observation in observations:
            events.append(
                {
                    "source": "DIAGNOSTIC_STORE",
                    "source_id": observation.observation_id,
                    "timestamp": _json_value(observation.observed_at),
                    "signal_type": "DIAGNOSTIC_OBSERVATION",
                    "reason": f"Diagnostic observation: {observation.subject}",
                    "observation_snapshot": {
                        "source": observation.source,
                        "subject": observation.subject,
                        "value": _json_value(observation.value),
                        "raw_evidence": _json_value(observation.raw_evidence),
                    },
                    "signal_snapshot": {
                        "diagnostic_action_id": observation.diagnostic_action_id,
                    },
                    "correlation": dict(
                        correlation,
                        observation_id=observation.observation_id,
                        diagnostic_action_id=observation.diagnostic_action_id,
                    ),
                }
            )

        actions = []
        for action_id in investigation.action_ids:
            action = diagnostic_store.get_action(
                investigation.investigation_id,
                action_id,
            )
            if action is None:
                raise ValueError(f"diagnostic action missing: {action_id}")
            if action.investigation_id != investigation.investigation_id:
                raise ValueError("diagnostic action investigation_id mismatch")
            if action.incident_id != incident_id:
                raise ValueError("diagnostic action incident_id mismatch")
            actions.append(action)

        def action_time(action: Any) -> datetime:
            value = (
                action.result.finished_at
                if action.result is not None
                else action.finished_at or action.started_at or investigation.updated_at
            )
            return _parse_timestamp(value, "diagnostic_action.timestamp")

        actions.sort(key=lambda item: (action_time(item), item.diagnostic_action_id))
        for action in actions:
            result = action.result
            signal = {
                "diagnostic_action_id": action.diagnostic_action_id,
                "classification": _json_value(action.classification),
                "command": action.command,
                "rationale": action.rationale,
                "expected_information": action.expected_information,
                "state": _json_value(action.state),
                "evidence_ids": list(action.evidence_ids),
            }
            timestamp = action_time(action).isoformat()
            signal_type = "DIAGNOSTIC_ACTION_STATE"
            reason = "Diagnostic action state recorded."
            if result is not None:
                signal.update(
                    {
                        "success": result.success,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exit_code": result.exit_code,
                        "started_at": _json_value(result.started_at),
                        "finished_at": _json_value(result.finished_at),
                        "result_observation": _json_value(result.observation),
                    }
                )
                signal_type = (
                    "DIAGNOSTIC_RESULT"
                    if result.success
                    else "DIAGNOSTIC_FAILURE"
                )
                reason = (
                    "Diagnostic action completed successfully."
                    if result.success
                    else "Diagnostic action failed; failure evidence preserved."
                )
            events.append(
                {
                    "source": "DIAGNOSTIC_STORE",
                    "source_id": f"diagnostic:{investigation.investigation_id}:{action.diagnostic_action_id}",
                    "timestamp": timestamp,
                    "signal_type": signal_type,
                    "reason": reason,
                    "observation_snapshot": {},
                    "signal_snapshot": signal,
                    "correlation": dict(
                        correlation,
                        diagnostic_action_id=action.diagnostic_action_id,
                    ),
                }
            )

        hypotheses = []
        for hypothesis_id in investigation.current_hypothesis_ids:
            hypothesis = diagnostic_store.get_hypothesis(
                investigation.investigation_id,
                hypothesis_id,
            )
            if hypothesis is None:
                raise ValueError(f"diagnostic hypothesis missing: {hypothesis_id}")
            if hypothesis.investigation_id != investigation.investigation_id:
                raise ValueError("diagnostic hypothesis investigation_id mismatch")
            hypotheses.append(hypothesis)

        hypotheses.sort(
            key=lambda item: (
                _parse_timestamp(item.created_at, "hypothesis.created_at"),
                item.hypothesis_id,
            )
        )
        for hypothesis in hypotheses:
            events.append(
                {
                    "source": "DIAGNOSTIC_STORE",
                    "source_id": hypothesis.hypothesis_id,
                    "timestamp": _json_value(hypothesis.created_at),
                    "signal_type": "DIAGNOSTIC_HYPOTHESIS",
                    "reason": "Diagnostic hypothesis recorded; not represented as fact.",
                    "observation_snapshot": {},
                    "signal_snapshot": {
                        "statement": hypothesis.statement,
                        "status": _json_value(hypothesis.status),
                        "supporting_evidence_ids": list(hypothesis.supporting_evidence_ids),
                        "contradicting_evidence_ids": list(
                            hypothesis.contradicting_evidence_ids
                        ),
                    },
                    "correlation": dict(
                        correlation,
                        hypothesis_id=hypothesis.hypothesis_id,
                    ),
                }
            )

        if investigation.state.value != "ACTIVE":
            if investigation.completed_at is None:
                raise ValueError("terminal investigation missing completed_at")
            events.append(
                {
                    "source": "DIAGNOSTIC_STORE",
                    "source_id": f"investigation:{investigation.investigation_id}:terminal",
                    "timestamp": _json_value(investigation.completed_at),
                    "signal_type": f"INVESTIGATION_{investigation.state.value}",
                    "reason": "Diagnostic investigation reached terminal state.",
                    "observation_snapshot": {},
                    "signal_snapshot": {
                        "state": investigation.state.value,
                        "diagnosis_id": investigation.diagnosis_id,
                        "evidence_ids": list(investigation.evidence_ids),
                    },
                    "correlation": correlation,
                }
            )

    return events


def _seal_timeline(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Deterministically order events and apply a SHA-256 hash chain."""
    normalized = [_json_value(event) for event in events]
    normalized.sort(
        key=lambda event: (
            _parse_timestamp(event["timestamp"]),
            str(event.get("source") or ""),
            str(event.get("source_id") or ""),
            str(event.get("signal_type") or ""),
        )
    )

    previous = ""
    sealed: list[dict[str, Any]] = []
    for sequence, event in enumerate(normalized, start=1):
        item = deepcopy(event)
        item["sequence"] = sequence
        item["category"] = _category(_signal_type(item.get("signal_type")))
        item["observed_state"] = _observed_state(item)
        item["previous_sha256"] = previous or None
        digest_input = {
            key: value
            for key, value in item.items()
            if key not in {"event_sha256"}
        }
        digest = hashlib.sha256(_canonical_bytes(digest_input)).hexdigest()
        item["event_sha256"] = digest
        sealed.append(item)
        previous = digest

    return sealed, previous or _EMPTY_TIMELINE_SHA256


def verify_timeline_integrity(timeline: list[Mapping[str, Any]]) -> bool:
    """Verify sequence continuity and the evidence hash chain without mutation."""
    previous = ""
    for expected_sequence, raw in enumerate(timeline, start=1):
        item = _json_value(raw)
        if item.get("sequence") != expected_sequence:
            return False
        if item.get("previous_sha256") != (previous or None):
            return False
        expected = item.get("event_sha256")
        digest_input = {
            key: value
            for key, value in item.items()
            if key != "event_sha256"
        }
        actual = hashlib.sha256(_canonical_bytes(digest_input)).hexdigest()
        if expected != actual:
            return False
        previous = actual
    return True


class EvidenceCompleteIncidentReportBuilder:
    """Build an evidence-complete IncidentReport from canonical read-only state."""

    def __init__(
        self,
        diagnostic_store: Any | None = None,
        base_builder: IncidentReportBuilder | None = None,
    ) -> None:
        self.diagnostic_store = diagnostic_store
        self.base_builder = base_builder or IncidentReportBuilder()

    def build(self, source: Any) -> IncidentReport:
        base = self.base_builder.build(source).to_dict()
        incident_id = base["incident_id"]
        component_id = base["component_id"]

        events = _base_incident_events(source, base)
        events.extend(
            _diagnostic_events(
                self.diagnostic_store,
                incident_id,
                component_id,
            )
        )
        timeline, timeline_sha256 = _seal_timeline(events)

        detection = [event for event in timeline if event["category"] == "detection"]
        diagnostic = [event for event in timeline if event["category"] == "diagnostic"]
        remediation = [event for event in timeline if _is_remediation_event(event)]
        verification = [event for event in timeline if _is_verification_event(event)]
        commander = [event for event in timeline if event["category"] == "commander"]
        decisions = [event for event in timeline if _is_decision_event(event)]

        commander_required = bool(base.get("commander_attention_required")) or any(
            _commander_required(event) for event in timeline
        )
        if str(base.get("final_outcome") or "").upper() == "ESCALATED":
            commander_required = True

        observed_states = [
            {
                "sequence": event["sequence"],
                "timestamp": event["timestamp"],
                "source_id": event["source_id"],
                "state": event["observed_state"],
            }
            for event in timeline
            if event.get("observed_state") not in (None, "")
        ]
        normalized_inputs = [
            {
                "sequence": event["sequence"],
                "timestamp": event["timestamp"],
                "source_id": event["source_id"],
                "inputs": _normalized_inputs(event),
            }
            for event in timeline
            if _normalized_inputs(event)
        ]

        remediation_status: dict[str, Any] = {
            "known": bool(remediation),
            "eligibility": None,
            "status": None,
            "evidence_sequences": [event["sequence"] for event in remediation],
        }
        if remediation:
            last = remediation[-1]
            signal = last.get("signal_snapshot") or {}
            decision = None
            if isinstance(signal, Mapping):
                decision = (
                    signal.get("remediation_policy_decision")
                    or signal.get("decision")
                )
            decision_text = str(decision or "").upper()
            if decision_text == "ALLOW":
                remediation_status["eligibility"] = "ELIGIBLE"
            elif decision_text == "DENY":
                remediation_status["eligibility"] = "DENIED"
            remediation_status["status"] = last["signal_type"]

        verification_result = None
        if verification:
            explicit = [
                event
                for event in verification
                if _signal_type(event.get("signal_type")) != "RECOVERY"
            ]
            last = explicit[-1] if explicit else verification[-1]
            verification_result = {
                "sequence": last["sequence"],
                "signal_type": last["signal_type"],
                "reason": last["reason"],
                "signal_snapshot": deepcopy(last["signal_snapshot"]),
            }

        remediation_requires_verification = any(
            event["signal_type"]
            not in {"REMEDIATION_DENIED", "REMEDIATION_REPLAYED"}
            for event in remediation
        ) or str(base.get("final_outcome") or "").upper() == "RECOVERED"

        checks = {
            "incident_id": bool(incident_id),
            "component_id": bool(component_id),
            "detection_start_time": bool(base.get("started_at")),
            "observed_state": bool(observed_states),
            "normalized_inputs": bool(normalized_inputs),
            "diagnostics_understanding": bool(diagnostic),
            "decisions_accounted_for": (not commander_required) or bool(decisions or commander),
            "commander_requirement_recorded": isinstance(commander_required, bool),
            "remediation_status_accounted_for": isinstance(remediation_status["known"], bool),
            "remediation_evidence_preserved": (not remediation) or bool(remediation_status["evidence_sequences"]),
            "verification_accounted_for": (not remediation_requires_verification) or bool(verification),
            "final_incident_status": _terminal_final_status_recorded(base),
            "chronological_timeline": bool(timeline),
            "timeline_integrity": verify_timeline_integrity(timeline),
        }
        missing = [name for name, passed in checks.items() if not passed]

        payload = deepcopy(base)
        payload.update(
            {
                "evidence_profile": _EVIDENCE_PROFILE,
                "evidence_count": len(timeline),
                "detection_and_understanding": [
                    event
                    for event in timeline
                    if event["category"] in {"detection", "diagnostic"}
                ],
                "diagnostic_actions": diagnostic,
                "remediation_actions": remediation,
                "verification_results": verification,
                "commander_decisions": commander,
                "timeline": timeline,
                "timeline_sha256": timeline_sha256,
                "observed_states": observed_states,
                "normalized_inputs": normalized_inputs,
                "diagnostics_and_understanding": diagnostic,
                "decisions": decisions,
                "commander_decision_requirement": {
                    "required": commander_required,
                    "status": "REQUIRED" if commander_required else "NOT_REQUIRED",
                    "evidence_sequences": [
                        event["sequence"]
                        for event in timeline
                        if event in commander or _commander_required(event)
                    ],
                },
                "remediation_eligibility_status": remediation_status,
                "verification_result": verification_result,
                "final_incident_status": base.get("final_status"),
                "evidence_completeness": {
                    "complete": not missing,
                    "checks": checks,
                    "missing": missing,
                },
            }
        )
        return IncidentReport(_freeze(payload))

    def build_from_manager(self, manager: Any, incident_id: str) -> IncidentReport:
        if not incident_id:
            raise ValueError("incident_id must not be empty")

        active = manager.get_incident_by_id(incident_id)
        if active is not None:
            return self.build(active)

        for snapshot in manager.get_history():
            if snapshot.get("incident_id") == incident_id:
                return self.build(snapshot)

        raise KeyError(f"Unknown incident_id: {incident_id}")
