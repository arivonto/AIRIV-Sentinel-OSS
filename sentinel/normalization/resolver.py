from typing import Dict, List, Optional


class IdentityResolver:
    """
    Explicit configuration-driven identity resolver.

    Identity is resolved only from configured window_name/pane_title
    metadata. No command-based inference is performed.
    """

    def __init__(
        self,
        mapping_rules: Optional[Dict[str, str]] = None,
    ):
        self.mapping_rules = mapping_rules or {}

    def resolve_identity(self, observation: Dict) -> str:
        window_name = (
            observation.get("window_name") or ""
        ).strip().lower()

        pane_title = (
            observation.get("pane_title") or ""
        ).strip().lower()

        for key, agent_id in self.mapping_rules.items():
            normalized_key = key.strip().lower()

            if not normalized_key:
                continue

            if (
                window_name == normalized_key
                or pane_title == normalized_key
            ):
                return agent_id

        return "UNKNOWN"


class ActivityDetector:
    """
    Observable activity classification only.

    No policy decision such as STUCK, WAITING, FAILED,
    or COMPLETED is made here.
    """

    @staticmethod
    def classify_activity(observation: Dict) -> str:
        if observation.get("pane_dead") is True:
            return "PANE_DEAD"

        if observation.get("capture_ok") is False:
            return "CAPTURE_FAILED"

        if observation.get("first_observation") is True:
            return "INITIALIZED"

        if (
            observation.get("previous_command") is not None
            and observation.get("current_command")
            != observation.get("previous_command")
        ):
            return "PROCESS_CHANGED"

        if observation.get("output_changed") is True:
            return "OUTPUT_CHANGED"

        return "OUTPUT_SILENT"


def normalize_observations(
    raw_observations: List[Dict],
    resolver: IdentityResolver,
) -> List[Dict]:
    normalized: List[Dict] = []

    for observation in raw_observations:
        enriched = dict(observation)

        enriched["agent_identity"] = (
            resolver.resolve_identity(enriched)
        )

        enriched["activity_state"] = (
            ActivityDetector.classify_activity(enriched)
        )

        normalized.append(enriched)

    return normalized
