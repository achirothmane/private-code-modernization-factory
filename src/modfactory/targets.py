from __future__ import annotations

SUPPORTED_TARGETS = {"react-dom", "spring-boot", "python"}


def parse_target_args(values: list[str] | None) -> dict[str, str]:
    targets: dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            raise ValueError(f"Invalid target {raw!r}; expected key=value")
        key, value = (part.strip() for part in raw.split("=", 1))
        if not key or not value:
            raise ValueError(f"Invalid target {raw!r}; expected key=value")
        if key not in SUPPORTED_TARGETS:
            supported = ", ".join(sorted(SUPPORTED_TARGETS))
            raise ValueError(f"Unsupported target {key!r}; supported: {supported}")
        targets[key] = value
    return targets


def merge_targets(
    base: dict[str, str] | None,
    override: dict[str, object] | None,
) -> dict[str, str]:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if key not in SUPPORTED_TARGETS:
            continue
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged
