from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Finding:
    category: str
    severity: str
    path: str
    message: str
    evidence: str
    remediation: str
    score: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepoSnapshot:
    root: str
    files: int
    lines: int
    languages: dict[str, int] = field(default_factory=dict)
    manifests: list[str] = field(default_factory=list)
    ci_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    history: dict[str, Any] = field(default_factory=dict)

    @property
    def risk_score(self) -> int:
        raw = sum(f.score for f in self.findings)
        return min(100, raw)

    @property
    def risk_band(self) -> str:
        score = self.risk_score
        if score >= 70:
            return "critical"
        if score >= 45:
            return "high"
        if score >= 20:
            return "medium"
        return "low"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk_score"] = self.risk_score
        payload["risk_band"] = self.risk_band
        return payload
