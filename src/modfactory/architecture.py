from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

PY_EXTENSIONS = {".py"}
JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

_JS_IMPORT_RE = re.compile(
    r"(?:from\s+[\"'](?P<from>\.{1,2}/[^\"']+)[\"']|"
    r"require\(\s*[\"'](?P<require>\.{1,2}/[^\"']+)[\"']\s*\)|"
    r"import\(\s*[\"'](?P<dynamic>\.{1,2}/[^\"']+)[\"']\s*\))"
)


def _python_module_for_path(path: str) -> str:
    p = Path(path)
    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if parts and parts[0] in {"src", "lib"}:
        parts = parts[1:]
    return ".".join(parts)


def _python_module_index(source_files: Iterable[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for rel in source_files:
        if Path(rel).suffix != ".py":
            continue
        module = _python_module_for_path(rel)
        if module:
            index[module] = rel
    return index


def _resolve_python_import(
    importer: str,
    module: str | None,
    level: int,
    index: dict[str, str],
) -> str | None:
    importer_module = _python_module_for_path(importer)
    package_parts = importer_module.split(".")[:-1]

    if level:
        keep = max(0, len(package_parts) - (level - 1))
        base = package_parts[:keep]
        target_parts = base + (module.split(".") if module else [])
        candidate = ".".join(p for p in target_parts if p)
    else:
        candidate = module or ""

    if not candidate:
        return None
    if candidate in index:
        return index[candidate]

    parts = candidate.split(".")
    while len(parts) > 1:
        parts.pop()
        shorter = ".".join(parts)
        if shorter in index:
            return index[shorter]
    return None


def _python_edges(root: Path, source_files: Iterable[str]) -> set[tuple[str, str]]:
    source_files = list(source_files)
    index = _python_module_index(source_files)
    edges: set[tuple[str, str]] = set()
    for rel in source_files:
        if Path(rel).suffix not in PY_EXTENSIONS:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _resolve_python_import(rel, alias.name, 0, index)
                    if target and target != rel:
                        edges.add((rel, target))
            elif isinstance(node, ast.ImportFrom):
                resolved_any = False
                for alias in node.names:
                    combined = f"{node.module}.{alias.name}" if node.module else alias.name
                    target = _resolve_python_import(rel, combined, node.level, index)
                    if target and target != rel:
                        edges.add((rel, target))
                        resolved_any = True
                if not resolved_any:
                    target = _resolve_python_import(rel, node.module, node.level, index)
                    if target and target != rel:
                        edges.add((rel, target))
    return edges


def _resolve_js_target(root: Path, importer: str, raw: str) -> str | None:
    base = (root / importer).parent
    target = (base / raw).resolve()
    candidates = [target]
    if target.suffix == "":
        candidates.extend(target.with_suffix(ext) for ext in JS_EXTENSIONS)
        candidates.extend(target / f"index{ext}" for ext in JS_EXTENSIONS)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
    return None


def _js_edges(root: Path, source_files: Iterable[str]) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for rel in source_files:
        if Path(rel).suffix not in JS_EXTENSIONS:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in _JS_IMPORT_RE.finditer(text):
            raw = match.group("from") or match.group("require") or match.group("dynamic")
            target = _resolve_js_target(root, rel, raw)
            if target and target != rel:
                edges.add((rel, target))
    return edges


def _strongly_connected_components(nodes: list[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for src, dst in edges:
        adjacency[src].append(dst)

    index = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for nxt in adjacency.get(node, []):
            if nxt not in indices:
                visit(nxt)
                lowlink[node] = min(lowlink[node], lowlink[nxt])
            elif nxt in on_stack:
                lowlink[node] = min(lowlink[node], indices[nxt])

        if lowlink[node] == indices[node]:
            component: list[str] = []
            while stack:
                popped = stack.pop()
                on_stack.remove(popped)
                component.append(popped)
                if popped == node:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for node in nodes:
        if node not in indices:
            visit(node)
    return sorted(components, key=lambda c: (-len(c), c))


def analyze_architecture(root: str | Path, source_files: Iterable[str]) -> dict[str, object]:
    root = Path(root).resolve()
    nodes = sorted(set(source_files))
    edges = _python_edges(root, nodes) | _js_edges(root, nodes)

    fan_in: Counter[str] = Counter()
    fan_out: Counter[str] = Counter()
    for src, dst in edges:
        fan_out[src] += 1
        fan_in[dst] += 1

    cycles = _strongly_connected_components(nodes, edges)
    hubs = [
        {
            "path": node,
            "fan_in": fan_in[node],
            "fan_out": fan_out[node],
            "degree": fan_in[node] + fan_out[node],
        }
        for node in nodes
        if fan_in[node] >= 3 or fan_out[node] >= 4
    ]
    hubs.sort(key=lambda item: (-int(item["degree"]), str(item["path"])))

    boundaries: list[dict[str, object]] = []
    for item in hubs[:20]:
        boundaries.append({
            "type": "dependency-hub",
            "path": item["path"],
            "reason": f"fan-in={item['fan_in']}, fan-out={item['fan_out']}",
            "verification": "Require targeted tests and isolate changes to this boundary.",
        })
    for component in cycles[:20]:
        boundaries.append({
            "type": "dependency-cycle",
            "paths": component,
            "reason": f"{len(component)} source files form a dependency cycle",
            "verification": "Break or explicitly preserve the cycle before broad upgrades.",
        })

    return {
        "nodes": nodes,
        "edges": [{"from": src, "to": dst} for src, dst in sorted(edges)],
        "edge_count": len(edges),
        "cycles": cycles,
        "hubs": hubs[:20],
        "upgrade_boundaries": boundaries,
    }
