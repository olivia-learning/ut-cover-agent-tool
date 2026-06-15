from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(data: dict[str, Any], path: str | Path) -> Path:
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def build_report_payload(
    analysis: dict[str, Any] | None,
    coverage: dict[str, Any] | None,
    touched_tests: list[str] | None = None,
) -> dict[str, Any]:
    commits = analysis.get("commits", []) if analysis else []
    coverage_summary = coverage.get("coverage", {}) if coverage else {}
    test_result = coverage.get("test_result", {}) if coverage else {}
    coverage_gate = coverage.get("coverage_gate", {}) if coverage else {}
    return {
        "commits": commits,
        "test_result": test_result,
        "coverage": coverage_summary,
        "coverage_gate": coverage_gate,
        "touched_tests": touched_tests or [],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# UT Coverage Report",
        "",
        "## Test Result",
        "",
    ]
    test_result = payload.get("test_result") or {}
    if test_result:
        status = "PASS" if test_result.get("ok") else "FAIL"
        lines.extend(
            [
                f"- Status: {status}",
                f"- Command: `{test_result.get('command', '')}`",
                f"- Exit code: {test_result.get('exit_code', '')}",
                f"- Duration: {test_result.get('duration_ms', '')} ms",
                "",
            ]
        )
    else:
        lines.extend(["- Status: not run", ""])

    coverage = payload.get("coverage") or {}
    lines.extend(["## Coverage", ""])
    if coverage:
        percent = coverage.get("percent")
        percent_text = f"{percent:.2f}%" if isinstance(percent, (int, float)) else "unknown"
        lines.extend(
            [
                f"- Format: {coverage.get('format', 'unknown')}",
                f"- Report: `{coverage.get('report_path', '')}`",
                f"- Line coverage: {percent_text}",
                f"- Covered lines: {coverage.get('covered_lines')}",
                f"- Total lines: {coverage.get('total_lines')}",
                "",
            ]
        )
    else:
        lines.extend(["- Coverage report not available", ""])

    gate = payload.get("coverage_gate") or {}
    lines.extend(["## Coverage Gate", ""])
    if gate:
        lines.extend(
            [
                f"- Status: {gate.get('status', 'unknown')}",
                f"- OK: {gate.get('ok')}",
                f"- Next action: `{gate.get('next_action', '')}`",
            ]
        )
        if gate.get("required_overall_percent") is not None:
            lines.append(f"- Required overall: {gate.get('required_overall_percent')}%")
        if gate.get("changed_files_required_percent") is not None:
            lines.append(f"- Required changed files: {gate.get('changed_files_required_percent')}%")
        failed_files = gate.get("failed_files") or []
        if failed_files:
            lines.append("- Failed files:")
            for item in failed_files:
                lines.append(
                    f"  - `{item.get('path')}` {item.get('percent')}% < {item.get('required_percent')}%"
                )
        lines.append("")
    else:
        lines.extend(["- Not configured or not evaluated", ""])

    lines.extend(["## Commits", ""])
    for commit in payload.get("commits", []):
        changed_files = commit.get("changed_files", [])
        lines.append(f"### `{commit.get('commit', '')[:12]}` {commit.get('subject', '')}")
        lines.append("")
        lines.append(f"- Author: {commit.get('author_name', '')} <{commit.get('author_email', '')}>")
        lines.append(f"- Date: {commit.get('author_date', '')}")
        lines.append(f"- Changed files: {len(changed_files)}")
        for item in changed_files:
            previous = f" (from `{item.get('previous_path')}`)" if item.get("previous_path") else ""
            lines.append(f"  - `{item.get('status')}` `{item.get('path')}`{previous}")
        lines.append("")

    lines.extend(["## Touched Tests", ""])
    touched_tests = payload.get("touched_tests", [])
    if touched_tests:
        lines.extend(f"- `{path}`" for path in touched_tests)
    else:
        lines.append("- Not provided")
    lines.append("")

    missing_files = [
        item
        for item in (coverage.get("files") or [])
        if item.get("missing_lines")
    ]
    lines.extend(["## Missing Lines", ""])
    if missing_files:
        for item in missing_files:
            preview = ", ".join(str(line) for line in item.get("missing_lines", [])[:40])
            suffix = " ..." if len(item.get("missing_lines", [])) > 40 else ""
            lines.append(f"- `{item.get('path')}`: {preview}{suffix}")
    else:
        lines.append("- No missing line details found")
    lines.append("")
    return "\n".join(lines)


def write_markdown(markdown: str, path: str | Path) -> Path:
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    return output
