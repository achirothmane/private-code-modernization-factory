from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .verification import run_verification_contract


MAX_BEHAVIOR_COMMANDS = 32


def load_behavior_contract(
    path: str | Path,
    *,
    repository_root: str | Path,
) -> tuple[dict[str, object], dict[str, object]]:
    """Load and freeze an explicit behavior contract outside the repository.

    The file itself is external evidence: a patch under review must not be able
    to rewrite the behavior probes that judge it.
    """
    root = Path(repository_root).resolve()
    contract_path = Path(path).resolve()

    try:
        contract_path.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("behavior-contract-must-be-external-to-repository")

    try:
        raw = contract_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"behavior-contract-read-failed: {exc}") from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"behavior-contract-invalid-json: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("behavior-contract-root-must-be-object")
    if payload.get("schema_version") != 1:
        raise ValueError("behavior-contract-schema-version-unsupported")

    raw_commands = payload.get("commands")
    if not isinstance(raw_commands, list) or not raw_commands:
        raise ValueError("behavior-contract-commands-missing")
    if len(raw_commands) > MAX_BEHAVIOR_COMMANDS:
        raise ValueError("behavior-contract-too-many-commands")

    commands: list[dict[str, object]] = []
    ids: list[str] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_commands):
        if not isinstance(item, dict):
            raise ValueError(f"behavior-contract-command-{index}-invalid")

        case_id = str(item.get("id", "")).strip()
        command = str(item.get("command", "")).strip()
        working_directory = str(item.get("working_directory", ".")).strip() or "."

        if not case_id:
            raise ValueError(f"behavior-contract-command-{index}-id-missing")
        if case_id in seen_ids:
            raise ValueError(f"behavior-contract-command-id-duplicate: {case_id}")
        if not command:
            raise ValueError(f"behavior-contract-command-{case_id}-command-missing")

        seen_ids.add(case_id)
        ids.append(case_id)
        commands.append({
            "kind": "behavior",
            "command": command,
            "source": f"external-behavior-contract:{case_id}",
            "confidence": "explicit",
            "working_directory": working_directory,
        })

    frozen_payload: dict[str, object] = {
        "schema_version": 1,
        "commands": commands,
    }
    canonical = json.dumps(
        frozen_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    contract_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    file_sha256 = hashlib.sha256(raw).hexdigest()

    contract = {
        **frozen_payload,
        "contract_sha256": contract_sha256,
    }
    evidence = {
        "path": str(contract_path),
        "sha256": file_sha256,
        "size_bytes": len(raw),
        "contract_sha256": contract_sha256,
        "case_ids": ids,
        "external_to_repository": True,
    }
    return contract, evidence


def run_behavior_contract(
    root: str | Path,
    contract: dict[str, object],
    *,
    timeout_seconds: int,
) -> list[dict[str, object]]:
    return run_verification_contract(
        root,
        contract,
        timeout_seconds=timeout_seconds,
        execution_env=None,
    )
