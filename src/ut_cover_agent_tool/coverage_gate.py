from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import ToolConfig


def evaluate_coverage_gate(
    config: ToolConfig,
    coverage: dict[str, Any] | None,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if config.coverage_threshold is None and config.changed_files_coverage_threshold is None:
        return {
            "enabled": False,
            "ok": True,
            "status": "not_configured",
            "next_action": "continue",
            "message": "Coverage goal is not configured.",
        }

    if not coverage:
        return _unknown(config, "Coverage report was not parsed.")

    overall_percent = _as_float(coverage.get("percent"))
    failed_reasons: list[str] = []
    failed_files: list[dict[str, Any]] = []
    unknown_reasons: list[str] = []

    if config.coverage_threshold is not None:
        if overall_percent is None:
            unknown_reasons.append("Overall coverage percent is missing.")
        elif overall_percent < config.coverage_threshold:
            failed_reasons.append(
                f"Overall coverage {overall_percent:.2f}% is below required {config.coverage_threshold:.2f}%."
            )

    changed_file_threshold = config.changed_files_coverage_threshold
    if changed_file_threshold is not None:
        changed_files = _changed_source_files(analysis)
        coverage_by_file = {_normalize(item.get("path", "")): item for item in coverage.get("files", [])}
        for changed in changed_files:
            matched = _find_coverage_for_changed_file(changed, coverage_by_file)
            if matched is None:
                unknown_reasons.append(f"Coverage report has no file entry for changed file: {changed}")
                continue
            percent = _as_float(matched.get("percent"))
            if percent is None:
                unknown_reasons.append(f"Coverage percent is missing for changed file: {changed}")
            elif percent < changed_file_threshold:
                failed_files.append(
                    {
                        "path": changed,
                        "percent": percent,
                        "required_percent": changed_file_threshold,
                        "missing_lines": matched.get("missing_lines", []),
                    }
                )

    if failed_reasons or failed_files:
        return {
            "enabled": True,
            "ok": not config.coverage_fail_below_threshold,
            "status": "failed",
            "overall_percent": overall_percent,
            "required_overall_percent": config.coverage_threshold,
            "changed_files_required_percent": changed_file_threshold,
            "failed_reasons": failed_reasons,
            "failed_files": failed_files,
            "unknown_reasons": unknown_reasons,
            "next_action": _failed_next_action(failed_files),
        }

    if unknown_reasons:
        unknown = _unknown(config, "; ".join(unknown_reasons))
        unknown.update(
            {
                "overall_percent": overall_percent,
                "required_overall_percent": config.coverage_threshold,
                "changed_files_required_percent": changed_file_threshold,
                "unknown_reasons": unknown_reasons,
            }
        )
        return unknown

    return {
        "enabled": True,
        "ok": True,
        "status": "passed",
        "overall_percent": overall_percent,
        "required_overall_percent": config.coverage_threshold,
        "changed_files_required_percent": changed_file_threshold,
        "failed_reasons": [],
        "failed_files": [],
        "unknown_reasons": [],
        "next_action": "continue",
    }


def _unknown(config: ToolConfig, reason: str) -> dict[str, Any]:
    fail = config.coverage_unknown_action == "fail"
    return {
        "enabled": True,
        "ok": not fail,
        "status": "unknown",
        "message": reason,
        "next_action": "report_unknown_coverage" if not fail else "stop",
    }


def _failed_next_action(failed_files: list[dict[str, Any]]) -> str:
    if failed_files:
        return "continue_fix_tests"
    return "report_threshold_failure"


def _changed_source_files(analysis: dict[str, Any] | None) -> list[str]:
    if not analysis:
        return []
    values: list[str] = []
    seen: set[str] = set()
    for commit in analysis.get("commits", []):
        for item in commit.get("changed_files", []):
            path = _normalize(item.get("path", ""))
            if not path or path in seen:
                continue
            if Path(path).suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}:
                seen.add(path)
                values.append(path)
    return values


def _find_coverage_for_changed_file(
    changed_file: str, coverage_by_file: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    changed = _normalize(changed_file)
    if changed in coverage_by_file:
        return coverage_by_file[changed]
    changed_name = Path(changed).name
    suffix_matches = [
        item
        for path, item in coverage_by_file.items()
        if path.endswith("/" + changed) or path.endswith("/" + changed_name)
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    return None


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip("/").lower()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
