from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileCoverage:
    path: str
    percent: float | None
    covered_lines: int | None
    total_lines: int | None
    missing_lines: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "percent": self.percent,
            "covered_lines": self.covered_lines,
            "total_lines": self.total_lines,
            "missing_lines": self.missing_lines,
        }


@dataclass(frozen=True)
class CoverageSummary:
    report_path: str
    format: str
    percent: float | None
    covered_lines: int | None
    total_lines: int | None
    files: list[FileCoverage]
    raw_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_path": self.report_path,
            "format": self.format,
            "percent": self.percent,
            "covered_lines": self.covered_lines,
            "total_lines": self.total_lines,
            "files": [item.to_dict() for item in self.files],
            "raw_summary": self.raw_summary,
        }


def parse_coverage_report(path: str | Path) -> CoverageSummary:
    report_path = Path(path).resolve()
    if not report_path.exists():
        raise FileNotFoundError(f"Coverage report not found: {report_path}")
    suffix = report_path.suffix.lower()
    if suffix == ".json":
        return parse_coverage_json(report_path)
    if suffix == ".xml":
        return parse_cobertura_xml(report_path)
    return CoverageSummary(
        report_path=str(report_path),
        format="text",
        percent=None,
        covered_lines=None,
        total_lines=None,
        files=[],
        raw_summary={"preview": report_path.read_text(encoding="utf-8", errors="replace")[:4000]},
    )


def parse_coverage_json(path: str | Path) -> CoverageSummary:
    report_path = Path(path).resolve()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    totals = data.get("totals", {}) if isinstance(data, dict) else {}
    files_data = data.get("files", {}) if isinstance(data, dict) else {}
    files: list[FileCoverage] = []
    for filename, details in files_data.items():
        summary = details.get("summary", {}) if isinstance(details, dict) else {}
        missing_lines = details.get("missing_lines", []) if isinstance(details, dict) else []
        files.append(
            FileCoverage(
                path=str(filename),
                percent=_as_float(summary.get("percent_covered")),
                covered_lines=_as_int(summary.get("covered_lines")),
                total_lines=_total_lines(summary),
                missing_lines=[int(item) for item in missing_lines],
            )
        )
    covered = _as_int(totals.get("covered_lines"))
    total = _total_lines(totals)
    return CoverageSummary(
        report_path=str(report_path),
        format="coverage-json",
        percent=_as_float(totals.get("percent_covered")),
        covered_lines=covered,
        total_lines=total,
        files=files,
        raw_summary=totals,
    )


def parse_cobertura_xml(path: str | Path) -> CoverageSummary:
    report_path = Path(path).resolve()
    root = ET.parse(report_path).getroot()
    line_rate = _as_float(root.attrib.get("line-rate"))
    lines_valid = _as_int(root.attrib.get("lines-valid"))
    lines_covered = _as_int(root.attrib.get("lines-covered"))
    files: list[FileCoverage] = []

    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename", "")
        line_nodes = class_node.findall(".//line")
        missing = [
            int(line.attrib["number"])
            for line in line_nodes
            if line.attrib.get("hits") == "0" and line.attrib.get("number", "").isdigit()
        ]
        total = len(line_nodes)
        covered = total - len(missing)
        percent = (covered / total * 100.0) if total else None
        files.append(
            FileCoverage(
                path=filename,
                percent=percent,
                covered_lines=covered,
                total_lines=total,
                missing_lines=missing,
            )
        )

    return CoverageSummary(
        report_path=str(report_path),
        format="cobertura-xml",
        percent=(line_rate * 100.0) if line_rate is not None else None,
        covered_lines=lines_covered,
        total_lines=lines_valid,
        files=files,
        raw_summary=dict(root.attrib),
    )


def _total_lines(summary: dict[str, Any]) -> int | None:
    covered = _as_int(summary.get("covered_lines"))
    missing = _as_int(summary.get("missing_lines"))
    excluded = _as_int(summary.get("excluded_lines")) or 0
    num_statements = _as_int(summary.get("num_statements"))
    if num_statements is not None:
        return num_statements
    if covered is None and missing is None:
        return None
    return (covered or 0) + (missing or 0) + excluded


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
