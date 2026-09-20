from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .models import Finding


@dataclass(frozen=True)
class MigrationRecipe:
    id: str
    title: str
    finding_messages: tuple[str, ...]
    confidence: str
    strategy: str
    preconditions: tuple[str, ...]
    transforms: tuple[str, ...]
    verification: tuple[str, ...]
    rollback_triggers: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


RECIPES: tuple[MigrationRecipe, ...] = (
    MigrationRecipe(
        id="python-imp-to-importlib",
        title="Replace deprecated imp usage with importlib",
        finding_messages=("Python imp module is removed in Python 3.12+",),
        confidence="high",
        strategy="mechanical-with-behavior-check",
        preconditions=(
            "The module loading behavior is covered by a test or reproducible command.",
            "The target Python runtime is 3.8+.",
        ),
        transforms=(
            "Replace import imp with importlib/importlib.util equivalents.",
            "For find_module/load_module/load_source usage, construct a ModuleSpec and load via module_from_spec + exec_module.",
            "Preserve file-path and module-name semantics; do not broaden search paths implicitly.",
        ),
        verification=(
            "Legacy imp pattern is absent from the target file.",
            "Baseline module-loading tests remain green.",
            "Run under the target Python version.",
        ),
        rollback_triggers=(
            "Loaded module identity/name changes unexpectedly.",
            "Import side effects or search-path behavior changes.",
            "Any baseline test regresses.",
        ),
        notes=("Prefer a narrow helper around importlib if the old imp flow appears in multiple places.",),
    ),
    MigrationRecipe(
        id="python-distutils-to-setuptools",
        title="Move distutils packaging/build logic to setuptools",
        finding_messages=("distutils is removed from modern Python",),
        confidence="high",
        strategy="mechanical-build-migration",
        preconditions=(
            "A reproducible build/install command exists.",
            "Package metadata and extension-module behavior are captured before the change.",
        ),
        transforms=(
            "Replace distutils.core imports with setuptools equivalents.",
            "Preserve Extension source/include/library arguments exactly unless a separate migration requires changes.",
            "Do not simultaneously convert setup.py to pyproject.toml in the same slice unless independently verified.",
        ),
        verification=(
            "Wheel or source distribution builds successfully.",
            "Package installs into a clean environment.",
            "Existing import/self-test commands remain green.",
        ),
        rollback_triggers=(
            "Built extension names or artifacts differ unexpectedly.",
            "Package metadata changes outside the intended migration.",
            "Clean-environment install fails.",
        ),
    ),
    MigrationRecipe(
        id="python-collections-abc",
        title="Move collection ABC imports to collections.abc",
        finding_messages=("Legacy collections ABC import pattern",),
        confidence="high",
        strategy="mechanical-import-migration",
        preconditions=("Target runtime is Python 3.3+.",),
        transforms=(
            "Replace collections.Mapping/MutableMapping/Sequence/MutableSequence with collections.abc equivalents.",
            "Replace from collections import ABCName with from collections.abc import ABCName.",
        ),
        verification=(
            "Legacy collections ABC pattern is absent.",
            "Relevant tests pass on the target Python runtime.",
        ),
        rollback_triggers=("Any import error or type/issubclass behavior regression appears.",),
    ),
    MigrationRecipe(
        id="node-sass-to-sass",
        title="Replace node-sass with Dart Sass",
        finding_messages=("node-sass is deprecated",),
        confidence="medium",
        strategy="dependency-and-output-comparison",
        preconditions=(
            "Existing CSS/Sass build command is known.",
            "Representative compiled CSS output can be captured.",
        ),
        transforms=(
            "Replace node-sass dependency with sass.",
            "Update build scripts only where CLI flags/API calls differ.",
            "Avoid simultaneous Sass syntax rewrites unless the compiler requires them.",
        ),
        verification=(
            "The stylesheet build succeeds.",
            "Compiled CSS is compared against the baseline and unexplained diffs are blocked.",
        ),
        rollback_triggers=(
            "Material compiled CSS differences are unexplained.",
            "Build time or memory regresses beyond an agreed threshold.",
        ),
    ),
    MigrationRecipe(
        id="npm-request-to-modern-http",
        title="Replace deprecated request HTTP client",
        finding_messages=("request npm package is deprecated",),
        confidence="medium",
        strategy="semantic-api-migration",
        preconditions=(
            "HTTP call behavior is covered for status codes, redirects, timeouts, and error paths.",
            "Target Node runtime is known.",
        ),
        transforms=(
            "Choose one maintained client compatible with the runtime (native fetch/undici/axios).",
            "Preserve timeout, redirect, auth, proxy, encoding, and error semantics explicitly.",
            "Migrate one call site or cohesive client wrapper per slice.",
        ),
        verification=(
            "Contract tests cover representative success/error responses.",
            "No request dependency remains for migrated call sites.",
            "Network behavior differences are documented.",
        ),
        rollback_triggers=(
            "Timeout/redirect/error semantics differ without approval.",
            "Authentication or proxy behavior regresses.",
        ),
    ),
    MigrationRecipe(
        id="reactdom-render-to-createroot",
        title="Migrate ReactDOM.render to createRoot",
        finding_messages=("Legacy React render API detected",),
        confidence="medium",
        strategy="framework-entrypoint-migration",
        preconditions=(
            "Application boot/render smoke test exists.",
            "Current React and react-dom versions are known.",
        ),
        transforms=(
            "Import createRoot from react-dom/client.",
            "Create the root once for the existing container and call root.render().",
            "Do not mix this slice with unrelated component rewrites.",
        ),
        verification=(
            "Application mounts successfully.",
            "Boot-time console errors are absent.",
            "Existing UI tests remain green.",
        ),
        rollback_triggers=(
            "Mount lifecycle changes break behavior.",
            "StrictMode-related side effects surface and are not separately addressed.",
        ),
    ),
    MigrationRecipe(
        id="javax-to-jakarta-assessment",
        title="Assess javax to Jakarta namespace migration",
        finding_messages=("Javax namespace detected",),
        confidence="advisory",
        strategy="ecosystem-assessment",
        preconditions=(
            "Framework/server target versions are known.",
            "Dependency tree is available.",
        ),
        transforms=(
            "Classify each javax usage as JDK-provided, Java EE/Jakarta, or third-party.",
            "Migrate only namespaces required by the chosen framework/server upgrade.",
            "Do not apply global text replacement.",
        ),
        verification=(
            "Project compiles against the target dependency set.",
            "Integration tests cover container/framework startup.",
        ),
        rollback_triggers=(
            "Mixed javax/jakarta dependency graph causes linkage or runtime errors.",
            "Migration would require an unplanned framework/server upgrade.",
        ),
    ),
)


def recipe_for_finding(finding: Finding) -> MigrationRecipe | None:
    for recipe in RECIPES:
        if finding.message in recipe.finding_messages:
            return recipe
    return None


def build_recipe_instances(findings: Iterable[Finding]) -> list[dict[str, object]]:
    instances: list[dict[str, object]] = []
    for finding in findings:
        recipe = recipe_for_finding(finding)
        if recipe is None:
            continue
        payload = recipe.to_dict()
        payload.update({
            "target": finding.path,
            "evidence": finding.evidence,
            "finding_message": finding.message,
        })
        instances.append(payload)
    return sorted(instances, key=lambda item: (str(item["id"]), str(item["target"])))
