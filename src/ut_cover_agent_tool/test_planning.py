from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ToolConfig


HIGH_CONFIDENCE = 70
MEDIUM_CONFIDENCE = 45
BLOCKED_NON_UNIT_DISPLAY = 20

SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
}

TEST_SUFFIXES = SOURCE_SUFFIXES
ASSERTION_PATTERNS = [
    r"\bassert\b",
    r"\bself\.assert[A-Z_]",
    r"\bexpect\s*\(",
    r"\bshould\b",
    r"\bEXPECT_[A-Z_]+\s*\(",
    r"\bASSERT_[A-Z_]+\s*\(",
    r"\bREQUIRE\s*\(",
    r"\bCHECK\s*\(",
]


@dataclass(frozen=True)
class TestCandidate:
    path: str
    is_unit: bool
    confidence: int
    reasons: list[str]
    classification: str
    mimic_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "is_unit": self.is_unit,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "classification": self.classification,
            "mimic_summary": self.mimic_summary,
        }


def build_test_plan(repo: str | Path, config: ToolConfig, analysis: dict[str, Any]) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    changed_sources = _changed_source_files(config, analysis)
    test_files = _find_test_files(repo_path, config)
    entries: list[dict[str, Any]] = []

    for source in changed_sources:
        candidates = [
            _score_candidate(repo_path, config, source, test_path)
            for test_path in test_files
        ]
        candidates.sort(key=lambda item: item.confidence, reverse=True)
        unit_candidates = [item for item in candidates if item.is_unit]
        high_confidence = [item for item in unit_candidates if item.confidence >= HIGH_CONFIDENCE][:3]
        nearest_non_unit = [item for item in candidates if not item.is_unit and item.confidence >= BLOCKED_NON_UNIT_DISPLAY][:3]
        action = (
            "use_high_confidence_neighbors"
            if high_confidence
            else "stop_for_user_or_minimal_template"
        )
        entries.append(
            {
                "source_file": source,
                "action": action,
                "status": "ready" if high_confidence else "low_confidence",
                "recommended_neighbors": [item.to_dict() for item in high_confidence],
                "other_unit_candidates": [item.to_dict() for item in unit_candidates[:5]],
                "blocked_non_unit_candidates": [item.to_dict() for item in nearest_non_unit],
                "guidance": _guidance_for_source(source, high_confidence),
            }
        )

    return {
        "policy": {
            "high_confidence_threshold": HIGH_CONFIDENCE,
            "max_mimic_files": 3,
            "global_style_summary_allowed": False,
            "dt_or_integration_mimic_allowed": False,
        },
        "source_count": len(changed_sources),
        "entries": entries,
    }


def render_test_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# UT Test Plan",
        "",
        "Policy: use only high-confidence unit-test neighbors; do not mimic DT/integration tests.",
        "",
    ]
    for entry in plan.get("entries", []):
        lines.append(f"## `{entry.get('source_file')}`")
        lines.append("")
        lines.append(f"- Status: {entry.get('status')}")
        lines.append(f"- Action: {entry.get('action')}")
        lines.append(f"- Guidance: {entry.get('guidance')}")
        lines.append("")
        lines.append("### Recommended UT Neighbors")
        recommended = entry.get("recommended_neighbors") or []
        if recommended:
            for candidate in recommended:
                reasons = "; ".join(candidate.get("reasons", []))
                lines.append(
                    f"- `{candidate.get('path')}` confidence={candidate.get('confidence')} reasons={reasons}"
                )
        else:
            lines.append("- None. Stop and ask, or use a minimal unit-test template with explicit disclosure.")
        lines.append("")
        blocked = entry.get("blocked_non_unit_candidates") or []
        if blocked:
            lines.append("### Blocked Non-UT Candidates")
            for candidate in blocked:
                reasons = "; ".join(candidate.get("reasons", []))
                lines.append(
                    f"- `{candidate.get('path')}` classification={candidate.get('classification')} reasons={reasons}"
                )
            lines.append("")
    return "\n".join(lines)


def review_touched_tests(
    repo: str | Path,
    config: ToolConfig,
    touched_tests: list[str],
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    allowed_neighbors = _allowed_neighbor_paths(plan or {})
    results: list[dict[str, Any]] = []
    ok = True

    for raw_path in touched_tests:
        rel = _normalize_path(raw_path)
        path = repo_path / rel
        classification, class_reasons = classify_test_path(config, rel)
        has_assertion = path.exists() and _has_assertion(path)
        is_allowed_neighbor = rel in allowed_neighbors
        warnings: list[str] = []

        if classification != "unit":
            ok = False
            warnings.append("Touched test is classified as non-unit; do not mimic or add DT/integration tests.")
        if not has_assertion:
            ok = False
            warnings.append("No explicit assertion pattern found.")
        if allowed_neighbors and not is_allowed_neighbor:
            warnings.append("Touched test was not one of the high-confidence neighbor files.")

        results.append(
            {
                "path": rel,
                "ok": not warnings,
                "classification": classification,
                "classification_reasons": class_reasons,
                "has_assertion": has_assertion,
                "is_allowed_neighbor": is_allowed_neighbor,
                "warnings": warnings,
            }
        )

    return {
        "ok": ok,
        "reviewed_count": len(results),
        "results": results,
    }


def classify_test_path(config: ToolConfig, path: str) -> tuple[str, list[str]]:
    normalized = _normalize_path(path)
    lower = normalized.lower()
    reasons: list[str] = []

    if _matches_any(normalized, config.unit_test_include):
        reasons.append("matched unit_test_include")
        return "unit", reasons
    if _matches_any(normalized, config.unit_test_exclude):
        reasons.append("matched unit_test_exclude")
        return "non_unit", reasons
    if _matches_any(normalized, config.dt_test_patterns) or any(
        token in lower.split("/") for token in _dt_tokens()
    ):
        reasons.append("matched DT/integration pattern")
        return "non_unit", reasons

    if _looks_like_unit_test_path(normalized):
        reasons.append("looks like unit test path")
        return "unit", reasons

    reasons.append("test file but no explicit unit marker")
    return "unknown", reasons


def _changed_source_files(config: ToolConfig, analysis: dict[str, Any]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for commit in analysis.get("commits", []):
        for item in commit.get("changed_files", []):
            path = _normalize_path(item.get("path", ""))
            if not path or path in seen:
                continue
            if _is_test_like_path(path, config):
                continue
            if Path(path).suffix.lower() not in SOURCE_SUFFIXES:
                continue
            seen.add(path)
            values.append(path)
    return values


def _find_test_files(repo: Path, config: ToolConfig) -> list[str]:
    roots = config.preferred_test_roots or config.test_dirs or ["tests"]
    files: list[str] = []
    seen: set[str] = set()
    for root in roots:
        root_path = repo / root
        if not root_path.exists():
            continue
        for path in root_path.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEST_SUFFIXES:
                continue
            rel = _normalize_path(path.relative_to(repo).as_posix())
            if rel in seen or _matches_any(rel, config.exclude):
                continue
            if _is_test_like_name(rel):
                seen.add(rel)
                files.append(rel)
    return files


def _score_candidate(repo: Path, config: ToolConfig, source: str, test_path: str) -> TestCandidate:
    source_parts = Path(source).with_suffix("").parts
    test_parts = Path(test_path).with_suffix("").parts
    source_stem = Path(source).stem.lower()
    test_stem = Path(test_path).stem.lower()
    confidence = 0
    reasons: list[str] = []

    classification, class_reasons = classify_test_path(config, test_path)
    is_unit = classification == "unit"
    if not is_unit:
        confidence -= 30

    if source_stem and source_stem in test_stem:
        confidence += 55
        reasons.append("test filename contains source stem")
    if test_stem and test_stem.replace("test_", "").replace("_test", "") == source_stem:
        confidence += 20
        reasons.append("test filename is an exact source-stem variant")

    shared = _shared_path_parts(source_parts, test_parts)
    if shared:
        add = min(shared * 8, 24)
        confidence += add
        reasons.append(f"shares {shared} path/module parts")

    if _same_language(source, test_path):
        confidence += 8
        reasons.append("same implementation/test language family")

    if _under_any_root(test_path, config.preferred_test_roots):
        confidence += 10
        reasons.append("under preferred_test_roots")

    reasons.extend(class_reasons)
    confidence = max(0, min(100, confidence))
    return TestCandidate(
        path=test_path,
        is_unit=is_unit,
        confidence=confidence,
        reasons=reasons,
        classification=classification,
        mimic_summary=_mimic_summary(repo / test_path),
    )


def _mimic_summary(path: Path) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    interesting = [
        line.strip()
        for line in lines[:120]
        if line.strip().startswith(("import ", "from ", "#include", "describe(", "it(", "test(", "class ", "def ", "TEST", "TEST_F"))
    ]
    return "\n".join(interesting[:20])


def _guidance_for_source(source: str, high_confidence: list[TestCandidate]) -> str:
    if high_confidence:
        paths = ", ".join(item.path for item in high_confidence)
        return f"Write or update UT by mimicking only these high-confidence files: {paths}."
    return (
        "No high-confidence unit-test neighbor found. Stop for user confirmation, "
        "or create a minimal UT template and explicitly state there was no safe style source."
    )


def _allowed_neighbor_paths(plan: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for entry in plan.get("entries", []):
        for item in entry.get("recommended_neighbors", []):
            paths.add(_normalize_path(item.get("path", "")))
    return paths


def _has_assertion(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    return any(re.search(pattern, text) for pattern in ASSERTION_PATTERNS)


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized = _normalize_path(path)
    return any(fnmatch.fnmatch(normalized, _normalize_path(pattern).lower()) for pattern in patterns)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/").lower()


def _is_test_like_name(path: str) -> bool:
    name = Path(path).name.lower()
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
        or name.endswith("_test.cpp")
        or name.endswith("_test.cc")
        or name.endswith("_test.cxx")
        or name.endswith("test.cpp")
        or name.endswith("test.cc")
    )


def _is_test_like_path(path: str, config: ToolConfig) -> bool:
    normalized = _normalize_path(path)
    return _under_any_root(normalized, config.test_dirs) or _is_test_like_name(normalized)


def _looks_like_unit_test_path(path: str) -> bool:
    lower = _normalize_path(path)
    if any(part in {"unit", "unittest", "unit_test", "unit-tests", "unit_tests"} for part in lower.split("/")):
        return True
    return _is_test_like_name(lower)


def _under_any_root(path: str, roots: list[str]) -> bool:
    normalized = _normalize_path(path)
    return any(normalized == _normalize_path(root) or normalized.startswith(_normalize_path(root) + "/") for root in roots)


def _shared_path_parts(source_parts: tuple[str, ...], test_parts: tuple[str, ...]) -> int:
    source = {part.lower() for part in source_parts if part.lower() not in {"src", "source", "include"}}
    test = {part.lower() for part in test_parts if part.lower() not in {"tests", "test", "__tests__"}}
    return len(source & test)


def _same_language(source: str, test_path: str) -> bool:
    source_suffix = Path(source).suffix.lower()
    test_suffix = Path(test_path).suffix.lower()
    python = {".py"}
    js = {".js", ".jsx", ".ts", ".tsx"}
    cpp = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
    return any(source_suffix in group and test_suffix in group for group in [python, js, cpp])


def _dt_tokens() -> set[str]:
    return {
        "integration",
        "e2e",
        "system",
        "dt",
        "device",
        "driver",
        "hardware",
        "scenario",
        "acceptance",
    }
