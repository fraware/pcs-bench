"""Parse failure localization from verifier outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FailureLocalizationResult:
    """Aligned with pcs-core FailureLocalizationResult.v0 shape."""

    schema_version: str = "v0"
    case_id: str | None = None
    failure_code: str | None = None
    responsible_component: str | None = None
    responsible_repo: str | None = None
    repair_hint: str | None = None
    repair_hint_kind: str | None = None
    artifact_path: str | None = None
    repair_command: str | None = None
    counterexample: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "failure_code": self.failure_code,
            "responsible_component": self.responsible_component,
            "responsible_repo": self.responsible_repo,
            "repair_hint": self.repair_hint,
            "repair_hint_kind": self.repair_hint_kind,
            "artifact_path": self.artifact_path,
            "repair_command": self.repair_command,
            "counterexample": self.counterexample,
        }


def parse_verification_result(
    data: dict[str, Any],
    *,
    case_id: str | None = None,
) -> FailureLocalizationResult:
    repair = data.get("repair_hint")
    if isinstance(repair, dict):
        return FailureLocalizationResult(
            case_id=case_id,
            failure_code=data.get("failure_code") or data.get("code"),
            responsible_component=repair.get("responsible_component")
            or data.get("responsible_component"),
            repair_hint_kind=repair.get("repair_kind") or data.get("repair_hint_kind"),
            repair_hint=json.dumps(repair, sort_keys=True),
            artifact_path=repair.get("artifact_path"),
            repair_command=repair.get("action") or repair.get("repair_command"),
            counterexample=data.get("counterexample") or data.get("violations"),
        )
    return FailureLocalizationResult(
        case_id=case_id,
        failure_code=data.get("failure_code") or data.get("code"),
        responsible_component=data.get("responsible_component"),
        repair_hint_kind=data.get("repair_hint_kind"),
        repair_hint=str(repair) if repair else None,
        counterexample=data.get("counterexample") or data.get("violations"),
    )


def load_failure_localization(path: Path, case_id: str | None = None) -> FailureLocalizationResult | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return parse_verification_result(data, case_id=case_id)
