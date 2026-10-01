from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Protocol

from .model_eval import _npm_usage_sites
from .scanner import scan_repository
from .verification import (
    _copy_repository,
    _finding_key,
    build_verification_contract,
    provision_verification_environment,
    run_verification_contract,
)


RESPONSE_SCHEMA_VERSION = 1
REQUEST_SCHEMA_VERSION = 1


class ModelProviderAdapter(Protocol):
    provider: str
    model: str

    def invoke(self, request: dict[str, object]) -> dict[str, object]:
        """Return unified_diff, rationale, and optional provider usage/cost metadata."""
        ...


def _decode_structured_content(content: object) -> dict[str, object]:
    if not isinstance(content, str):
        raise ValueError("Model response content must be a string")
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned non-JSON content: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Model JSON response must be an object")
    return payload

class OpenAICompatibleAdapter:
    def __init__(
        self,
        *,
        provider: str,
        endpoint: str,
        model: str,
        timeout_seconds: int = 600,
        max_tokens: int = 8192,
        bearer_token: str | None = None,
    ) -> None:
        provider = provider.strip()
        endpoint = endpoint.strip()
        model = model.strip()
        if not provider:
            raise ValueError("provider must be non-empty")
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("endpoint must be an http(s) URL")
        if not model:
            raise ValueError("model must be non-empty")
        if timeout_seconds < 1 or max_tokens < 1:
            raise ValueError("timeout_seconds and max_tokens must be >= 1")
        self.provider = provider
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.bearer_token = bearer_token.strip() if isinstance(bearer_token, str) and bearer_token.strip() else None

    @staticmethod
    def _decode_content(content: object) -> dict[str, object]:
        return _decode_structured_content(content)

    def invoke(self, request: dict[str, object]) -> dict[str, object]:
        messages = request.get("messages")
        if not isinstance(messages, list):
            raise ValueError("Model request messages must be a list")

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "modfactory-wave7h",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        http_request = urllib.request.Request(
            self.endpoint,
            data=raw,
            method="POST",
            headers=headers,
        )

        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[-4000:]
            raise ValueError(f"OpenAI-compatible endpoint HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"OpenAI-compatible endpoint failed: {exc.reason}") from exc

        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OpenAI-compatible endpoint returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("OpenAI-compatible response envelope must be an object")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("OpenAI-compatible response has no completion choice")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("OpenAI-compatible response choice has no message")
        parsed = self._decode_content(message.get("content"))
        unified_diff = parsed.get("unified_diff")
        rationale = parsed.get("rationale")
        if not isinstance(unified_diff, str) or not isinstance(rationale, str):
            raise ValueError("Structured content must contain unified_diff and rationale strings")

        usage_payload = payload.get("usage")
        usage: dict[str, object] = {}
        if isinstance(usage_payload, dict):
            usage = {
                "input_tokens": usage_payload.get("prompt_tokens"),
                "output_tokens": usage_payload.get("completion_tokens"),
            }

        return {
            "provider_request_id": payload.get("id"),
            "provider_model_returned": payload.get("model"),
            "unified_diff": unified_diff,
            "rationale": rationale,
            "usage": usage,
            "cost_usd": None,
            "provider_metadata": {
                "created": payload.get("created"),
                "system_fingerprint": payload.get("system_fingerprint"),
            },
        }


def run_model_request(
    request: dict[str, object],
    adapter: ModelProviderAdapter,
    *,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, object]:
    valid, errors = validate_request_integrity(request)
    if not valid:
        raise ValueError("Invalid model request: " + ", ".join(errors))
    if adapter.provider != request.get("provider"):
        raise ValueError("Adapter provider does not match request provider")
    if adapter.model != request.get("model"):
        raise ValueError("Adapter model does not match request model")

    started = timer()
    result = adapter.invoke(request)
    finished = timer()
    if not isinstance(result, dict):
        raise ValueError("Provider adapter result must be an object")

    unified_diff = result.get("unified_diff")
    rationale = result.get("rationale")
    if not isinstance(unified_diff, str):
        raise ValueError("Provider adapter must return unified_diff as a string")
    if not isinstance(rationale, str):
        raise ValueError("Provider adapter must return rationale as a string")

    usage = result.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    input_tokens, input_error = _metric_number(usage.get("input_tokens"), integer=True)
    output_tokens, output_error = _metric_number(usage.get("output_tokens"), integer=True)
    cost_usd, cost_error = _metric_number(result.get("cost_usd"), integer=False)
    metric_errors = [err for err in (input_error, output_error, cost_error) if err]
    if metric_errors:
        raise ValueError("Invalid provider metrics: " + ", ".join(metric_errors))

    latency_ms = max(0.0, (finished - started) * 1000.0)
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "benchmark_id": request["benchmark_id"],
        "task_id": request["task_id"],
        "provider": request["provider"],
        "model": request["model"],
        "provider_request_id": result.get("provider_request_id"),
        "provider_model_returned": result.get("provider_model_returned"),
        "unified_diff": unified_diff,
        "rationale": rationale,
        "metrics": {
            "latency_ms": round(latency_ms, 3),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
        },
        "metrics_source": {
            "latency_ms": "runner-wall-clock",
            "input_tokens": "provider" if input_tokens is not None else None,
            "output_tokens": "provider" if output_tokens is not None else None,
            "cost_usd": "provider" if cost_usd is not None else None,
        },
        "provider_metadata": result.get("provider_metadata"),
    }


UNSUPPORTED_DIFF_MARKERS = (
    "GIT binary patch",
    "Binary files ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "new file mode ",
    "deleted file mode ",
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_load(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def _task_from_plan(plan: dict[str, object], task_id: str) -> dict[str, object]:
    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("plan.tasks must be a list")
    for item in tasks:
        if isinstance(item, dict) and str(item.get("task_id")) == task_id:
            return item
    raise ValueError(f"Task {task_id!r} was not found in the evaluation plan")


def build_model_request(
    plan: dict[str, object],
    task_id: str,
    *,
    provider: str,
    model: str,
) -> dict[str, object]:
    provider = provider.strip()
    model = model.strip()
    if not provider:
        raise ValueError("provider must be non-empty")
    if not model:
        raise ValueError("model must be non-empty")

    task = _task_from_plan(plan, task_id)
    task_json = json.dumps(task, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    benchmark_id = _sha256_text(task_json)[:16]

    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "benchmark_id": benchmark_id,
        "task_id": task_id,
        "provider": provider,
        "model": model,
        "task_sha256": _sha256_text(task_json),
        "task": task,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are producing a review-only repository modernization patch. "
                    "Do not merge, deploy, or modify files outside the explicit allowlist. "
                    "Return ONLY one JSON object with exactly two string fields: "
                    "unified_diff and rationale. unified_diff must be a standard multi-file unified diff "
                    "covering every required usage site and no files outside the allowlist. "
                    "Do not wrap the JSON in markdown fences."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(task, ensure_ascii=False, indent=2),
            },
        ],
        "response_contract": {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "required": [
                "benchmark_id",
                "task_id",
                "provider",
                "model",
                "unified_diff",
                "rationale",
                "metrics",
            ],
            "metrics": {
                "latency_ms": "non-negative number or null",
                "input_tokens": "non-negative integer or null",
                "output_tokens": "non-negative integer or null",
                "cost_usd": "non-negative number or null",
            },
            "note": (
                "Metrics must come from the provider/runtime. Unknown metrics must be null; "
                "never estimate or synthesize them."
            ),
        },
        "execution_policy": {
            "invokes_provider": False,
            "executes_project_code": False,
            "applies_patch_to_original": False,
        },
    }


def write_model_response(response: dict[str, object], out_dir: str | Path) -> Path:
    out = Path(out_dir) / "model-bench"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "response.json"
    path.write_text(json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_model_request(request: dict[str, object], out_dir: str | Path) -> Path:
    out = Path(out_dir) / "model-bench"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "request.json"
    path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _metric_number(value: object, *, integer: bool = False) -> tuple[object | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "boolean-is-not-a-metric"
    if integer:
        if not isinstance(value, int) or value < 0:
            return None, "must-be-a-non-negative-integer-or-null"
        return value, None
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0:
        return None, "must-be-a-non-negative-number-or-null"
    return float(value), None


def validate_request_integrity(request: dict[str, object]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    task = request.get("task")
    if not isinstance(task, dict):
        return False, ["request-task-missing"]
    canonical = json.dumps(task, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = _sha256_text(canonical)
    if request.get("task_sha256") != digest:
        errors.append("request-task-sha256-mismatch")
    expected_benchmark = digest[:16]
    if request.get("benchmark_id") != expected_benchmark:
        errors.append("request-benchmark-id-mismatch")
    return not errors, errors


def validate_repository_baseline(
    repository: str | Path,
    request: dict[str, object],
) -> tuple[bool, list[dict[str, str]]]:
    root = Path(repository).resolve()
    task = request.get("task")
    if not isinstance(task, dict):
        return False, [{"path": ".", "reason": "request-task-missing"}]
    context_files = task.get("context_files", [])
    if not isinstance(context_files, list):
        return False, [{"path": ".", "reason": "context-files-invalid"}]

    mismatches: list[dict[str, str]] = []
    for item in context_files:
        if not isinstance(item, dict):
            continue
        rel = item.get("path")
        expected = item.get("sha256")
        if not isinstance(rel, str) or not isinstance(expected, str):
            mismatches.append({"path": str(rel or "."), "reason": "context-hash-missing"})
            continue
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            mismatches.append({"path": rel, "reason": "context-path-escapes-root"})
            continue
        if not candidate.is_file():
            mismatches.append({"path": rel, "reason": "context-file-missing"})
            continue
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append({"path": rel, "reason": "context-sha256-mismatch"})
    return not mismatches, mismatches


def validate_response_envelope(
    request: dict[str, object],
    response: dict[str, object],
) -> tuple[bool, list[str], dict[str, object]]:
    errors: list[str] = []
    if response.get("schema_version") != RESPONSE_SCHEMA_VERSION:
        errors.append("response-schema-version-mismatch")
    for key in ("benchmark_id", "task_id", "provider", "model"):
        if response.get(key) != request.get(key):
            errors.append(f"{key}-mismatch")

    diff = response.get("unified_diff")
    rationale = response.get("rationale")
    if not isinstance(diff, str) or not diff.strip():
        errors.append("unified_diff-missing")
    if not isinstance(rationale, str):
        errors.append("rationale-must-be-string")

    raw_metrics = response.get("metrics")
    if not isinstance(raw_metrics, dict):
        errors.append("metrics-must-be-object")
        raw_metrics = {}

    normalized: dict[str, object] = {}
    for key, integer in (
        ("latency_ms", False),
        ("input_tokens", True),
        ("output_tokens", True),
        ("cost_usd", False),
    ):
        value, error = _metric_number(raw_metrics.get(key), integer=integer)
        normalized[key] = value
        if error:
            errors.append(f"metrics.{key}-{error}")

    return not errors, errors, normalized


def _normalize_diff_path(raw: str) -> str | None:
    raw = raw.strip()
    if raw == "/dev/null":
        return None
    if raw.startswith('"') or raw.endswith('"'):
        return None
    if raw.startswith("a/") or raw.startswith("b/"):
        raw = raw[2:]
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts or not raw or "\x00" in raw:
        return None
    return path.as_posix()


def inspect_unified_diff(diff: str) -> dict[str, object]:
    errors: list[str] = []
    if any(marker in diff for marker in UNSUPPORTED_DIFF_MARKERS):
        errors.append("unsupported-diff-operation")

    old_paths: list[str] = []
    new_paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith("--- "):
            path = _normalize_diff_path(line[4:].split("\t", 1)[0])
            if path is None:
                errors.append("invalid-or-create-delete-old-path")
            else:
                old_paths.append(path)
        elif line.startswith("+++ "):
            path = _normalize_diff_path(line[4:].split("\t", 1)[0])
            if path is None:
                errors.append("invalid-or-create-delete-new-path")
            else:
                new_paths.append(path)

    if not old_paths or not new_paths:
        errors.append("unified-diff-file-headers-missing")
    if len(old_paths) != len(new_paths):
        errors.append("unbalanced-diff-file-headers")

    paired = min(len(old_paths), len(new_paths))
    for index in range(paired):
        if old_paths[index] != new_paths[index]:
            errors.append("rename-or-path-mismatch")

    changed = sorted(set(old_paths + new_paths))
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "changed_files": changed,
    }


def _git_compatible_diff(diff: str) -> str:
    lines = diff.splitlines(keepends=True)
    output: list[str] = []
    has_explicit_diff_header = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git "):
            has_explicit_diff_header = True
            output.append(line)
            index += 1
            continue

        if line.startswith("--- ") and index + 1 < len(lines) and lines[index + 1].startswith("+++ "):
            old_path = _normalize_diff_path(line[4:].split("\t", 1)[0])
            new_path = _normalize_diff_path(lines[index + 1][4:].split("\t", 1)[0])
            if (
                old_path is not None
                and new_path is not None
                and old_path == new_path
                and not has_explicit_diff_header
            ):
                output.append(f"diff --git a/{old_path} b/{new_path}\n")
            output.append(line)
            output.append(lines[index + 1])
            has_explicit_diff_header = False
            index += 2
            continue

        output.append(line)
        index += 1
    return "".join(output)


def _git_apply(root: Path, diff: str, *, check_only: bool) -> tuple[bool, str]:
    diff = _git_compatible_diff(diff)
    argv = ["git", "apply", "--no-index", "--recount", "--whitespace=nowarn"]
    if check_only:
        argv.append("--check")

    # Candidate copies deliberately exclude .git. Explicit --no-index plus a
    # sanitized environment prevents an unrelated parent checkout or inherited
    # GIT_DIR/GIT_WORK_TREE from redirecting application outside the candidate.
    env = os.environ.copy()
    for key in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_PREFIX",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        env.pop(key, None)
    env["GIT_CEILING_DIRECTORIES"] = str(root.resolve().parent)

    try:
        completed = subprocess.run(
            argv,
            cwd=str(root),
            input=diff,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    detail = ((completed.stdout or "") + (completed.stderr or ""))[-4000:]
    return completed.returncode == 0, detail


def _legacy_usage_remaining(root: Path, task: dict[str, object]) -> list[str]:
    recipe = task.get("recipe")
    if not isinstance(recipe, dict):
        return []
    recipe_id = str(recipe.get("id", ""))
    package = None
    if recipe_id == "npm-request-to-modern-http":
        package = "request"
    elif recipe_id == "node-sass-to-sass":
        package = "node-sass"
    if package is None:
        return []
    return [path.relative_to(root).as_posix() for path in _npm_usage_sites(root, package)]


TEST_ORACLE_DIR_NAMES = {
    "test", "tests", "__tests__", "spec", "specs",
    "__snapshots__", "snapshot", "snapshots", "golden", "goldens",
}
TEST_ORACLE_SUFFIXES = (
    ".test.js", ".test.jsx", ".test.ts", ".test.tsx",
    ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx",
    "_test.py", "_tests.py", "_test.go", "_test.rs",
)
TEST_EXECUTION_CONFIG_NAMES = {
    "pytest.ini", "tox.ini", "conftest.py", "Makefile",
}


def _looks_like_test_oracle_path(path: str) -> bool:
    candidate = Path(path)
    parts = {part.lower() for part in candidate.parts}
    name = candidate.name.lower()
    if parts & TEST_ORACLE_DIR_NAMES:
        return True
    if name.startswith("test_"):
        return True
    if (
        name.endswith(".snap")
        or ".approved." in name
        or name.endswith(".golden")
    ):
        return True
    return any(name.endswith(suffix) for suffix in TEST_ORACLE_SUFFIXES)


def _package_scripts(root: Path) -> dict[str, object] | None:
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    scripts = payload.get("scripts")
    return scripts if isinstance(scripts, dict) else {}


def _verification_oracle_violations(
    before_root: Path,
    after_root: Path,
    changed_files: set[str],
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for path in sorted(changed_files):
        if _looks_like_test_oracle_path(path):
            violations.append({"path": path, "reason": "test-oracle-file-modified"})
        elif Path(path).name in TEST_EXECUTION_CONFIG_NAMES:
            violations.append({"path": path, "reason": "test-execution-config-modified"})

    if "package.json" in changed_files:
        before_scripts = _package_scripts(before_root)
        after_scripts = _package_scripts(after_root)
        if before_scripts != after_scripts:
            violations.append({
                "path": "package.json",
                "reason": "package-test-script-contract-modified",
            })
    return violations


def _tree_file_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _tree_identity(root: Path) -> dict[str, object]:
    files = _tree_file_hashes(root)
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "tree_sha256": _sha256_text(canonical),
        "files": files,
    }


def _candidate_identity(
    before_root: Path,
    after_root: Path,
    declared_changed_files: set[str],
    *,
    patch_sha256: str,
) -> dict[str, object]:
    before = _tree_identity(before_root)
    after = _tree_identity(after_root)
    before_files = before["files"]
    after_files = after["files"]
    assert isinstance(before_files, dict)
    assert isinstance(after_files, dict)

    actual_changed = sorted(
        path
        for path in set(before_files) | set(after_files)
        if before_files.get(path) != after_files.get(path)
    )
    declared = sorted(declared_changed_files)
    changed_file_digests = []
    for path in sorted(set(declared) | set(actual_changed)):
        changed_file_digests.append({
            "path": path,
            "baseline_sha256": before_files.get(path),
            "candidate_sha256": after_files.get(path),
        })

    return {
        "version": 1,
        "patch_sha256": patch_sha256,
        "baseline_tree_sha256": before["tree_sha256"],
        "candidate_tree_sha256": after["tree_sha256"],
        "declared_changed_files": declared,
        "actual_changed_files": actual_changed,
        "changed_files_match": actual_changed == declared,
        "candidate_differs_from_baseline": before["tree_sha256"] != after["tree_sha256"],
        "no_op": not actual_changed,
        "changed_file_digests": changed_file_digests,
    }


def _verification_oracle_identity(root: Path) -> dict[str, object]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if _looks_like_test_oracle_path(rel) or path.name in TEST_EXECUTION_CONFIG_NAMES:
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    payload = {
        "files": files,
        "package_test_scripts": _package_scripts(root),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "sha256": _sha256_text(canonical),
        **payload,
    }


def _static_compare(
    before_root: Path,
    after_root: Path,
    task: dict[str, object],
    targets: dict[str, str],
) -> dict[str, object]:
    before = scan_repository(before_root, targets=targets)
    after = scan_repository(after_root, targets=targets)
    before_keys = {_finding_key(item) for item in before.findings}
    after_keys = {_finding_key(item) for item in after.findings}

    target = str(task.get("target", ""))
    title = str(task.get("title", ""))
    target_key = next(
        (key for key in before_keys if key[1] == target and key[2] == title),
        None,
    )
    new_findings = sorted(after_keys - before_keys)
    removed_findings = sorted(before_keys - after_keys)
    legacy_remaining = _legacy_usage_remaining(after_root, task)

    return {
        "target_finding_present_before": target_key is not None,
        "target_finding_removed_after": target_key is not None and target_key not in after_keys,
        "legacy_usage_remaining": legacy_remaining,
        "new_findings": [
            {"category": c, "path": p, "message": m}
            for c, p, m in new_findings
        ],
        "removed_findings": [
            {"category": c, "path": p, "message": m}
            for c, p, m in removed_findings
        ],
        "risk_before": before.risk_score,
        "risk_after": after.risk_score,
        "risk_non_increasing": after.risk_score <= before.risk_score,
        "source_file_count_stable": len(before.source_files) == len(after.source_files),
        "no_new_dependency_cycles": (
            len(after.architecture.get("cycles", []))
            <= len(before.architecture.get("cycles", []))
        ),
    }


def score_model_response(
    repository: str | Path,
    request: dict[str, object],
    response: dict[str, object],
    *,
    allow_project_code: bool = False,
    timeout_seconds: int = 120,
    provision_environments: bool = False,
) -> dict[str, object]:
    root = Path(repository).resolve()
    request_valid, request_errors = validate_request_integrity(request)
    valid_envelope, envelope_errors, metrics = validate_response_envelope(request, response)
    task_id = str(request.get("task_id", ""))
    task = request.get("task")
    if not isinstance(task, dict):
        task = {}
    allow_noop = task.get("allow_noop") is True

    base: dict[str, object] = {
        "schema_version": 1,
        "benchmark_id": request.get("benchmark_id"),
        "task_id": task_id,
        "provider": request.get("provider"),
        "model": request.get("model"),
        "provider_model_returned": response.get("provider_model_returned"),
        "provider_request_id": response.get("provider_request_id"),
        "metrics": metrics,
        "metrics_source": response.get("metrics_source"),

        "allow_project_code": allow_project_code,
        "original_repository_modified": False,
        "status": "FAIL",
        "reason": "response-envelope-invalid",
        "gates": {},
        "project_tests": {"executed": False, "before": [], "after": []},
        "project_checks": {"executed": False, "before": [], "after": []},
        "verification_contract": None,
        "candidate_identity": None,
        "verification_oracle_identity": None,
        "environment_evidence": {
            "requested": provision_environments,
            "before": None,
            "after": None,
        },
        "deployment_admissible": False,
        "intentional_noop_requested": allow_noop,
    }
    if not request_valid:
        return {
            **base,
            "reason": "request-integrity-invalid",
            "request_errors": request_errors,
        }
    if not valid_envelope:
        return {**base, "envelope_errors": envelope_errors}

    baseline_valid, baseline_mismatches = validate_repository_baseline(root, request)
    if not baseline_valid:
        return {
            **base,
            "reason": "repository-baseline-mismatch",
            "baseline_mismatches": baseline_mismatches,
        }

    diff = str(response.get("unified_diff", ""))
    diff_info = inspect_unified_diff(diff)
    allowed = {
        str(path) for path in task.get("allowed_changes", [])
        if isinstance(path, str) and path not in {"directly related tests"}
    }
    changed = set(diff_info.get("changed_files", []))
    scope_violations = sorted(changed - allowed)

    gates: dict[str, object] = {
        "response_envelope_valid": True,
        "diff_structure_valid": bool(diff_info["valid"]),
        "scope_compliant": not scope_violations and bool(changed),
        "changed_files": sorted(changed),
        "allowed_files": sorted(allowed),
        "scope_violations": scope_violations,
    }
    base["gates"] = gates

    if not diff_info["valid"]:
        return {
            **base,
            "reason": "unified-diff-invalid",
            "diff_errors": diff_info["errors"],
        }
    if scope_violations or not changed:
        return {**base, "reason": "allowed-scope-violation"}

    target_profile = task.get("target_profile")
    if not isinstance(target_profile, dict):
        target_profile = {}
    target_profile = {
        str(k): str(v) for k, v in target_profile.items()
        if isinstance(k, str) and isinstance(v, str)
    }

    with TemporaryDirectory(prefix="modfactory-model-before-") as before_td, TemporaryDirectory(prefix="modfactory-model-after-") as after_td:
        before_root = Path(before_td)
        after_root = Path(after_td)
        _copy_repository(root, before_root)
        _copy_repository(root, after_root)

        check_ok, check_detail = _git_apply(after_root, diff, check_only=True)
        gates["patch_applies_cleanly"] = check_ok
        if not check_ok:
            return {
                **base,
                "reason": "patch-does-not-apply-cleanly",
                "patch_detail": check_detail,
            }

        apply_ok, apply_detail = _git_apply(after_root, diff, check_only=False)
        if not apply_ok:
            return {
                **base,
                "reason": "patch-application-failed",
                "patch_detail": apply_detail,
            }

        candidate_identity = _candidate_identity(
            before_root,
            after_root,
            changed,
            patch_sha256=_sha256_text(diff),
        )
        base["candidate_identity"] = candidate_identity
        candidate_identity["intentional_noop"] = bool(
            candidate_identity["no_op"] and allow_noop
        )
        if candidate_identity["no_op"]:
            if not allow_noop:
                return {
                    **base,
                    "status": "BLOCKED",
                    "reason": "patch-produced-no-candidate-change",
                    "verification_level": "candidate-identity",
                }
            oracle_before = _verification_oracle_identity(before_root)
            oracle_after = _verification_oracle_identity(after_root)
            base["verification_oracle_identity"] = {
                "before_sha256": oracle_before["sha256"],
                "after_sha256": oracle_after["sha256"],
                "unchanged": oracle_before["sha256"] == oracle_after["sha256"],
            }
            gates["intentional_noop_confirmed"] = True
            return {
                **base,
                "status": "REVIEW",
                "reason": "intentional-noop-confirmed",
                "verification_level": "candidate-identity",
            }
        if not candidate_identity["changed_files_match"]:
            return {
                **base,
                "status": "BLOCKED",
                "reason": "candidate-identity-mismatch",
                "verification_level": "candidate-identity",
            }

        oracle_before = _verification_oracle_identity(before_root)
        oracle_after = _verification_oracle_identity(after_root)
        base["verification_oracle_identity"] = {
            "before_sha256": oracle_before["sha256"],
            "after_sha256": oracle_after["sha256"],
            "unchanged": oracle_before["sha256"] == oracle_after["sha256"],
        }

        static = _static_compare(before_root, after_root, task, target_profile)
        gates.update({
            "target_finding_removed": static["target_finding_removed_after"],
            "legacy_usage_removed": not static["legacy_usage_remaining"],
            "no_new_findings": not static["new_findings"],
            "risk_non_increasing": static["risk_non_increasing"],
            "source_file_count_stable": static["source_file_count_stable"],
            "no_new_dependency_cycles": static["no_new_dependency_cycles"],
        })
        static_pass = all(bool(gates[key]) for key in (
            "patch_applies_cleanly",
            "target_finding_removed",
            "legacy_usage_removed",
            "no_new_findings",
            "risk_non_increasing",
            "source_file_count_stable",
            "no_new_dependency_cycles",
        ))
        base["static_checks"] = static

        known_gate_names = [
            "response_envelope_valid",
            "diff_structure_valid",
            "scope_compliant",
            "patch_applies_cleanly",
            "target_finding_removed",
            "legacy_usage_removed",
            "no_new_findings",
            "risk_non_increasing",
            "source_file_count_stable",
            "no_new_dependency_cycles",
        ]
        passed = sum(1 for key in known_gate_names if gates.get(key) is True)
        base["static_quality"] = {
            "gates_passed": passed,
            "gates_known": len(known_gate_names),
            "ratio": round(passed / len(known_gate_names), 4),
        }

        if not static_pass:
            return {**base, "reason": "static-model-patch-regression"}

        if not allow_project_code:
            return {
                **base,
                "status": "REVIEW",
                "reason": "static-pass-project-tests-not-executed",
                "verification_level": "static",
            }

        before_snapshot = scan_repository(before_root, targets=target_profile)
        after_snapshot = scan_repository(after_root, targets=target_profile)
        before_contract = build_verification_contract(
            before_root,
            before_snapshot,
            isolated_dependencies=provision_environments,
        )
        after_contract = build_verification_contract(
            after_root,
            after_snapshot,
            isolated_dependencies=provision_environments,
        )
        base["verification_contract"] = before_contract

        def command_signature(contract: dict[str, object]) -> list[tuple[str, str, str, str]]:
            raw = contract.get("commands", [])
            if not isinstance(raw, list):
                return []
            return [
                (
                    str(item.get("kind", "")),
                    str(item.get("command", "")),
                    str(item.get("source", "")),
                    str(item.get("working_directory", ".")),
                )
                for item in raw
                if isinstance(item, dict)
            ]

        before_command_contract = command_signature(before_contract)
        after_command_contract = command_signature(after_contract)
        gates["verification_command_contract_unchanged"] = (
            before_command_contract == after_command_contract
        )

        oracle_violations = _verification_oracle_violations(
            before_root,
            after_root,
            changed,
        )
        oracle_identity = base.get("verification_oracle_identity")
        oracle_identity_unchanged = bool(
            isinstance(oracle_identity, dict)
            and oracle_identity.get("unchanged") is True
        )
        gates["verification_oracle_unchanged"] = (
            not oracle_violations
            and oracle_identity_unchanged
            and bool(gates["verification_command_contract_unchanged"])
        )
        if not gates["verification_oracle_unchanged"]:
            return {
                **base,
                "status": "BLOCKED",
                "reason": "verification-oracle-modified",
                "verification_level": "contract-before",
                "oracle_violations": oracle_violations,
                "verification_command_contract_before": before_command_contract,
                "verification_command_contract_after": after_command_contract,
            }

        before_env = None
        after_env = None
        if provision_environments:
            before_env, before_environment = provision_verification_environment(
                before_root,
                before_contract,
                timeout_seconds=timeout_seconds,
            )
            base["environment_evidence"]["before"] = before_environment
            if before_env is None:
                return {
                    **base,
                    "status": "BLOCKED",
                    "reason": "baseline-environment-provisioning-failed",
                    "verification_level": "environment-before",
                }

            after_env, after_environment = provision_verification_environment(
                after_root,
                before_contract,
                timeout_seconds=timeout_seconds,
            )
            base["environment_evidence"]["after"] = after_environment
            if after_env is None:
                return {
                    **base,
                    "status": "BLOCKED",
                    "reason": "target-environment-provisioning-failed",
                    "verification_level": "environment-after",
                }

        before_checks = run_verification_contract(
            before_root,
            before_contract,
            timeout_seconds=timeout_seconds,
            execution_env=before_env,
        )
        base["project_checks"] = {
            "executed": True,
            "before": before_checks,
            "after": [],
        }
        before_tests = [item for item in before_checks if item.get("kind") == "test"]
        base["project_tests"] = {
            "executed": True,
            "before": before_tests,
            "after": [],
        }
        gates["baseline_contract_pass"] = bool(before_checks) and all(
            item.get("status") == "PASS" for item in before_checks
        )

        if not before_tests:
            return {
                **base,
                "status": "BLOCKED",
                "reason": "no-test-command-in-verification-contract",
                "verification_level": "contract-before",
            }
        if not gates["baseline_contract_pass"]:
            return {
                **base,
                "status": "BLOCKED",
                "reason": "baseline-verification-contract-failed",
                "verification_level": "contract-before",
            }

        # Execute the exact baseline contract after the patch; never rediscover
        # a weaker command set from the patched repository.
        after_checks = run_verification_contract(
            after_root,
            before_contract,
            timeout_seconds=timeout_seconds,
            execution_env=after_env,
        )
        base["project_checks"]["after"] = after_checks
        after_tests = [item for item in after_checks if item.get("kind") == "test"]
        base["project_tests"]["after"] = after_tests
        gates["patched_contract_pass"] = (
            len(after_checks) == len(before_checks)
            and bool(after_checks)
            and all(item.get("status") == "PASS" for item in after_checks)
        )

        if not gates["patched_contract_pass"]:
            return {
                **base,
                "status": "FAIL",
                "reason": "regression-after-model-patch",
                "verification_level": "contract",
            }

        return {
            **base,
            "status": "PASS",
            "reason": (
                "verification-contract-pass-isolated-dependencies"
                if provision_environments
                else "verification-contract-pass-shared-host"
            ),
            "verification_level": (
                "contract-isolated-dependencies"
                if provision_environments
                else "contract-shared-host"
            ),
            "deployment_admissible": False,
        }


def write_model_score(score: dict[str, object], out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir) / "model-bench"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "score.json"
    md_path = out / "score.md"
    json_path.write_text(json.dumps(score, indent=2, ensure_ascii=False), encoding="utf-8")

    metrics = score.get("metrics", {})
    gates = score.get("gates", {})
    lines = [
        "# ModFactory Model Benchmark Score",
        "",
        f"Status: **{score.get('status')}**",
        f"Reason: {score.get('reason')}",
        f"Provider: {score.get('provider')}",
        f"Model: {score.get('model')}",
        f"Latency ms: {metrics.get('latency_ms') if isinstance(metrics, dict) else None}",
        f"Input tokens: {metrics.get('input_tokens') if isinstance(metrics, dict) else None}",
        f"Output tokens: {metrics.get('output_tokens') if isinstance(metrics, dict) else None}",
        f"Cost USD: {metrics.get('cost_usd') if isinstance(metrics, dict) else None}",
        "",
        "## Gates",
        "",
    ]
    if isinstance(gates, dict):
        for key in sorted(gates):
            lines.append(f"- {key}: {gates[key]}")
    candidate_identity = score.get("candidate_identity")
    oracle_identity = score.get("verification_oracle_identity")
    lines.extend(["", "## Candidate identity", ""])
    if isinstance(candidate_identity, dict):
        lines.extend([
            f"- Patch SHA-256: {candidate_identity.get('patch_sha256')}",
            f"- Baseline tree SHA-256: {candidate_identity.get('baseline_tree_sha256')}",
            f"- Candidate tree SHA-256: {candidate_identity.get('candidate_tree_sha256')}",
            f"- Declared changed files: {candidate_identity.get('declared_changed_files', [])}",
            f"- Actual changed files: {candidate_identity.get('actual_changed_files', [])}",
            f"- Changed files match: {candidate_identity.get('changed_files_match')}",
            f"- No-op: {candidate_identity.get('no_op')}",
            f"- Intentional no-op: {candidate_identity.get('intentional_noop', False)}",
        ])
    if isinstance(oracle_identity, dict):
        lines.extend([
            "",
            "## Verification oracle identity",
            "",
            f"- Before SHA-256: {oracle_identity.get('before_sha256')}",
            f"- After SHA-256: {oracle_identity.get('after_sha256')}",
            f"- Unchanged: {oracle_identity.get('unchanged')}",
        ])
    lines.extend([
        "",
        "Project code execution is opt-in. The original repository is never modified.",
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def load_request(path: str | Path) -> dict[str, object]:
    return _json_load(path)


def load_response(path: str | Path) -> dict[str, object]:
    return _json_load(path)
