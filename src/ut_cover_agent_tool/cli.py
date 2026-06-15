from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .commands import run_shell
from .config import DEFAULT_CONFIG_NAME, load_config
from .config_writer import append_config_list_values, update_config_values
from .coverage import parse_coverage_report
from .coverage_gate import evaluate_coverage_gate
from .errors import ToolUnavailableError, UtCoverError
from .git_tools import analyze_commits, ensure_git_available, ensure_git_repo, parse_commit_inputs
from .presets import CONFIG_PRESETS, detect_preset, render_config
from .remote import (
    ai_ssh_mcp_available,
    create_remote_backend,
    diagnose_remote_failure,
    fetch_remote_artifacts,
    remote_workspace_for,
    run_remote_commands,
    sync_workspace,
)
from .reports import build_report_payload, read_json, render_markdown, write_json, write_markdown
from .test_planning import build_test_plan, render_test_plan_markdown, review_touched_tests
from .upgrade import (
    build_upgrade_status,
    upgrade_ai_ssh_mcp_from_zip,
    upgrade_from_zip,
    write_upgrade_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ToolUnavailableError, UtCoverError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ut-cover", description="Commit-driven UT coverage helper.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check git, config, and project commands.")
    add_common(doctor)
    doctor.set_defaults(func=cmd_doctor)

    init_config = subparsers.add_parser("init-config", help="Create a beginner-friendly .ut-cover.yaml.")
    init_config.add_argument("--repo", default=".", help="Target repository path.")
    init_config.add_argument(
        "--preset",
        default="auto",
        choices=["auto", *sorted(CONFIG_PRESETS)],
        help="Config preset to write. Defaults to auto-detection.",
    )
    init_config.add_argument("--force", action="store_true", help="Overwrite an existing .ut-cover.yaml.")
    init_config.add_argument("--test-command", help="Override the preset test command.")
    init_config.add_argument("--coverage-command", help="Override the preset coverage command.")
    init_config.add_argument("--coverage-report", help="Override the preset coverage report path.")
    init_config.set_defaults(func=cmd_init_config)

    coverage_goal = subparsers.add_parser("set-coverage-goal", help="Write user-approved coverage goals to config.")
    coverage_goal.add_argument("--repo", default=".", help="Target repository path.")
    coverage_goal.add_argument("--overall", type=float, required=True, help="Required overall line coverage percent.")
    coverage_goal.add_argument("--changed-files", type=float, required=True, help="Required changed-files line coverage percent.")
    coverage_goal.add_argument("--unknown-action", choices=["warn", "fail"], default="warn", help="What to do when coverage cannot be evaluated.")
    coverage_goal.set_defaults(func=cmd_set_coverage_goal)

    autonomous = subparsers.add_parser("set-autonomous-mode", help="Enable or disable autonomous/rest mode.")
    autonomous.add_argument("--repo", default=".", help="Target repository path.")
    autonomous.add_argument("--enable", required=True, choices=["true", "false"], help="true enables autonomous mode; false restores interactive mode.")
    autonomous.set_defaults(func=cmd_set_autonomous_mode)

    autonomous_status = subparsers.add_parser("autonomous-status", help="Show autonomous/rest mode status.")
    autonomous_status.add_argument("--repo", default=".", help="Target repository path.")
    autonomous_status.add_argument("--config", default=None, help=f"Config path. Defaults to repo/{DEFAULT_CONFIG_NAME}.")
    autonomous_status.set_defaults(func=cmd_autonomous_status)

    recovery = subparsers.add_parser("set-recovery-instructions", help="Store user-approved remote recovery commands.")
    recovery.add_argument("--repo", default=".", help="Target repository path.")
    recovery.add_argument("--command", action="append", required=True, help="Recovery command. May be repeated.")
    recovery.add_argument("--replace", action="store_true", help="Replace existing recovery commands.")
    recovery.set_defaults(func=cmd_set_recovery_instructions)

    upgrade_status = subparsers.add_parser("upgrade-status", help="Check installed versions and ZIP upgrade inputs.")
    upgrade_status.add_argument("--install-dir", help="Current ut-cover-agent-tool install dir.")
    upgrade_status.add_argument("--ut-zip", help="New ut-cover-agent-tool.zip path.")
    upgrade_status.add_argument("--ssh-zip", help="New ai-ssh-mcp-tool.zip path.")
    upgrade_status.add_argument("--zip-dir", help="Directory containing staged ZIP files.")
    upgrade_status.add_argument("--repo", help="Optional target repo used to read interaction_mode.")
    upgrade_status.set_defaults(func=cmd_upgrade_status)

    upgrade = subparsers.add_parser("upgrade", help="Upgrade ut-cover and optionally ai_ssh_mcp from staged ZIP files.")
    upgrade.add_argument("--install-dir", required=True, help="Current ut-cover-agent-tool install dir.")
    upgrade.add_argument("--ut-zip", required=True, help="New ut-cover-agent-tool.zip path.")
    upgrade.add_argument("--ssh-zip", help="New ai-ssh-mcp-tool.zip path. Defaults to same directory as ut zip.")
    upgrade.add_argument("--ssh-install-dir", help="Current ai_ssh_mcp install dir if it cannot be inferred.")
    upgrade.add_argument("--upgrade-ssh", action="store_true", help="Confirm SSH MCP upgrade in interactive mode.")
    upgrade.add_argument("--repo", help="Optional target repo used to read interaction_mode.")
    upgrade.add_argument("--skip-pip-install", action="store_true", help=argparse.SUPPRESS)
    upgrade.set_defaults(func=cmd_upgrade)

    analyze = subparsers.add_parser("analyze-commits", help="Analyze commit diffs.")
    add_common(analyze)
    analyze.add_argument("--commit", "--commits", dest="commits", action="append", help="Commit id(s), comma or whitespace separated.")
    analyze.add_argument("--commit-file", help="File containing commit ids.")
    analyze.add_argument("--output", default=".ut-cover/analysis.json", help="Analysis JSON output path.")
    analyze.set_defaults(func=cmd_analyze_commits)

    coverage = subparsers.add_parser("run-coverage", help="Run configured coverage command and parse coverage report.")
    add_common(coverage)
    coverage.add_argument("--output", default=".ut-cover/coverage.json", help="Coverage result JSON output path.")
    coverage.add_argument("--timeout", type=int, default=None, help="Command timeout in seconds.")
    coverage.set_defaults(func=cmd_run_coverage)

    remote_doctor = subparsers.add_parser("remote-doctor", help="Check remote execution configuration.")
    add_common(remote_doctor)
    remote_doctor.set_defaults(func=cmd_remote_doctor)

    remote_sync = subparsers.add_parser("remote-sync", help="Sync local workspace to remote Linux executor.")
    add_common(remote_sync)
    remote_sync.add_argument("--run-id", help="Run id. Defaults to timestamp.")
    remote_sync.add_argument("--output", default=".ut-cover/remote-sync.json", help="Remote sync JSON output.")
    remote_sync.set_defaults(func=cmd_remote_sync)

    remote_run = subparsers.add_parser("remote-run", help="Run remote build and DT commands.")
    add_common(remote_run)
    remote_run.add_argument("--remote-workspace", help="Remote workspace path. Defaults to latest sync output.")
    remote_run.add_argument("--timeout", type=int, default=None, help="Remote command timeout in seconds.")
    remote_run.add_argument("--output", default=".ut-cover/remote-run.json", help="Remote run JSON output.")
    remote_run.set_defaults(func=cmd_remote_run)

    remote_fetch = subparsers.add_parser("remote-fetch", help="Fetch remote logs and reports.")
    add_common(remote_fetch)
    remote_fetch.add_argument("--remote-workspace", help="Remote workspace path. Defaults to latest sync/run output.")
    remote_fetch.add_argument("--output", default=".ut-cover/remote-fetch.json", help="Remote fetch JSON output.")
    remote_fetch.set_defaults(func=cmd_remote_fetch)

    remote_diagnose = subparsers.add_parser("remote-diagnose", help="Diagnose remote build or DT failure.")
    add_common(remote_diagnose)
    remote_diagnose.add_argument("--remote-run", default=".ut-cover/remote-run.json", help="Remote run JSON path.")
    remote_diagnose.add_argument("--log", action="append", default=[], help="Local log file to include. May be repeated.")
    remote_diagnose.add_argument("--output", default=".ut-cover/remote-diagnosis.json", help="Remote diagnosis JSON output.")
    remote_diagnose.set_defaults(func=cmd_remote_diagnose)

    plan_tests = subparsers.add_parser("plan-tests", help="Find local UT neighbors and produce a safe test plan.")
    add_common(plan_tests)
    plan_tests.add_argument("--analysis", default=".ut-cover/analysis.json", help="Analysis JSON path.")
    plan_tests.add_argument("--output", default=".ut-cover/test-plan.json", help="Test plan JSON output path.")
    plan_tests.add_argument("--markdown-output", default=".ut-cover/test-plan.md", help="Test plan Markdown output path.")
    plan_tests.set_defaults(func=cmd_plan_tests)

    inspect_tests = subparsers.add_parser("inspect-tests", help="Inspect local test neighbors without global style summary.")
    add_common(inspect_tests)
    inspect_tests.add_argument("--analysis", default=".ut-cover/analysis.json", help="Analysis JSON path.")
    inspect_tests.add_argument("--output", default=".ut-cover/test-neighbors.json", help="Neighbor JSON output path.")
    inspect_tests.add_argument("--markdown-output", default=".ut-cover/test-neighbors.md", help="Neighbor Markdown output path.")
    inspect_tests.set_defaults(func=cmd_plan_tests)

    review_tests = subparsers.add_parser("review-tests", help="Review touched tests for DT mimic and missing assertions.")
    add_common(review_tests)
    review_tests.add_argument("--plan", default=".ut-cover/test-plan.json", help="Test plan JSON path.")
    review_tests.add_argument("--output", default=".ut-cover/test-review.json", help="Review JSON output path.")
    review_tests.add_argument("--touched-test", action="append", default=[], help="Changed test file. May be repeated.")
    review_tests.add_argument("--touched-test-file", help="File containing changed test paths.")
    review_tests.set_defaults(func=cmd_review_tests)

    report = subparsers.add_parser("report", help="Build Markdown and JSON summary reports.")
    report.add_argument("--analysis", default=".ut-cover/analysis.json", help="Analysis JSON path.")
    report.add_argument("--coverage", default=".ut-cover/coverage.json", help="Coverage JSON path.")
    report.add_argument("--output", default=".ut-cover/reports/ut-coverage-report.md", help="Markdown output path.")
    report.add_argument("--json-output", default=".ut-cover/reports/ut-coverage-report.json", help="JSON output path.")
    report.add_argument("--touched-test", action="append", default=[], help="Test file changed by the AI agent. May be repeated.")
    report.add_argument("--touched-test-file", help="File containing changed test paths.")
    report.set_defaults(func=cmd_report)
    return parser


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".", help="Target repository path.")
    parser.add_argument("--config", default=None, help=f"Config path. Defaults to repo/{DEFAULT_CONFIG_NAME}.")


def cmd_doctor(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    checks: list[dict[str, Any]] = []

    try:
        git_path = ensure_git_available()
        checks.append({"name": "git", "ok": True, "message": f"git is available: {git_path}"})
    except ToolUnavailableError as exc:
        checks.append({"name": "git", "ok": False, "message": str(exc)})

    try:
        ensure_git_repo(repo)
        checks.append({"name": "repo", "ok": True, "message": f"{repo} is a git repository"})
    except Exception as exc:
        checks.append({"name": "repo", "ok": False, "message": str(exc)})

    checks.append(
        {
            "name": "config",
            "ok": bool(config.config_path),
            "message": config.config_path or f"No config found; defaults are in use. Create {DEFAULT_CONFIG_NAME}.",
            "config": config.to_dict(),
        }
    )

    test_command_ok = bool(config.test_command or config.coverage_command)
    checks.append(
        {
            "name": "commands",
            "ok": test_command_ok,
            "message": "test_command or coverage_command is configured"
            if test_command_ok
            else "Configure test_command and/or coverage_command before running coverage.",
        }
    )

    coverage_path = (repo / config.coverage_report).resolve()
    checks.append(
        {
            "name": "coverage_report",
            "ok": coverage_path.exists(),
            "message": str(coverage_path) if coverage_path.exists() else f"Coverage report not found yet: {coverage_path}",
        }
    )

    ok = all(item["ok"] for item in checks if item["name"] in {"git", "repo", "commands"})
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_init_config(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    repo.mkdir(parents=True, exist_ok=True)
    output = repo / DEFAULT_CONFIG_NAME
    if output.exists() and not args.force:
        raise UtCoverError(f"Config already exists: {output}. Use --force to overwrite it.")

    preset = detect_preset(repo) if args.preset == "auto" else args.preset
    text = render_config(
        preset,
        test_command=args.test_command,
        coverage_command=args.coverage_command,
        coverage_report=args.coverage_report,
    )
    output.write_text(text, encoding="utf-8")
    print(f"Wrote config: {output}")
    print(f"Preset: {preset}")
    print("Next: run `ut-cover doctor --repo <TARGET_REPO>` to check it.")
    return 0


def cmd_set_coverage_goal(args: argparse.Namespace) -> int:
    _validate_percent(args.overall, "overall")
    _validate_percent(args.changed_files, "changed-files")
    output = update_config_values(
        args.repo,
        {
            "coverage_threshold": args.overall,
            "changed_files_coverage_threshold": args.changed_files,
            "coverage_fail_below_threshold": True,
            "coverage_unknown_action": args.unknown_action,
        },
    )
    print(f"Wrote coverage goal: {output}")
    print(f"Overall: {args.overall:.2f}%")
    print(f"Changed files: {args.changed_files:.2f}%")
    print(f"Unknown action: {args.unknown_action}")
    return 0


def cmd_set_autonomous_mode(args: argparse.Namespace) -> int:
    mode = "autonomous" if args.enable == "true" else "interactive"
    output = update_config_values(args.repo, {"interaction_mode": mode})
    print(json.dumps({"ok": True, "config": str(output), "interaction_mode": mode}, ensure_ascii=False, indent=2))
    return 0


def cmd_autonomous_status(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    payload = {
        "ok": True,
        "repo": str(repo),
        "interaction_mode": config.interaction_mode,
        "autonomous_enabled": config.interaction_mode == "autonomous",
        "autonomous_recovery_commands": config.autonomous_recovery_commands,
        "autonomous_max_iterations": config.autonomous_max_iterations,
        "autonomous_low_confidence_action": config.autonomous_low_confidence_action,
        "autonomous_missing_coverage_goal": config.autonomous_missing_coverage_goal,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_set_recovery_instructions(args: argparse.Namespace) -> int:
    output = append_config_list_values(
        args.repo,
        "autonomous_recovery_commands",
        list(args.command or []),
        replace=args.replace,
    )
    config = load_config(args.repo)
    print(
        json.dumps(
            {
                "ok": True,
                "config": str(output),
                "autonomous_recovery_commands": config.autonomous_recovery_commands,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_analyze_commits(args: argparse.Namespace) -> int:
    commits = parse_commit_inputs(args.commits, args.commit_file)
    if not commits:
        raise UtCoverError("No commits provided. Use --commit or --commit-file.")
    repo = Path(args.repo).resolve()
    analysis = analyze_commits(repo, commits)
    payload = {
        "repo": str(repo),
        "commits": [item.to_dict() for item in analysis],
    }
    output = _resolve_output(repo, args.output)
    write_json(payload, output)
    print(f"Wrote analysis: {output}")
    return 0


def cmd_run_coverage(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    config = _ensure_autonomous_coverage_goal(repo, config)
    if config.execution_mode == "remote":
        return cmd_run_remote_coverage(args, repo, config)

    command = config.coverage_command or config.test_command
    if not command:
        raise UtCoverError("No coverage_command or test_command configured.")
    result = run_shell(command, repo, timeout=args.timeout)
    coverage_path = (repo / config.coverage_report).resolve()
    coverage_summary = parse_coverage_report(coverage_path) if coverage_path.exists() else None
    analysis = _read_optional_json(_resolve_output(repo, ".ut-cover/analysis.json"))
    coverage_dict = coverage_summary.to_dict() if coverage_summary else None
    coverage_gate = evaluate_coverage_gate(config, coverage_dict, analysis)
    payload = {
        "repo": str(repo),
        "config": config.to_dict(),
        "test_result": result.to_dict(),
        "coverage": coverage_dict,
        "coverage_gate": coverage_gate,
    }
    output = _resolve_output(repo, args.output)
    write_json(payload, output)
    print(f"Wrote coverage result: {output}")
    if not result.ok:
        return result.exit_code
    return 0 if coverage_gate.get("ok", True) else 1


def cmd_run_remote_coverage(args: argparse.Namespace, repo: Path, config) -> int:
    backend = create_remote_backend(config)
    try:
        sync = sync_workspace(repo, config, backend)
        write_json(sync, _resolve_output(repo, ".ut-cover/remote-sync.json"))
        remote_run = run_remote_commands(config, backend, sync["remote_workspace"], timeout=args.timeout)
        write_json(remote_run, _resolve_output(repo, ".ut-cover/remote-run.json"))
        fetched = fetch_remote_artifacts(repo, config, backend, sync["remote_workspace"])
        write_json(fetched, _resolve_output(repo, ".ut-cover/remote-fetch.json"))
    finally:
        backend.close()

    coverage_path = _find_fetched_coverage(repo, config)
    coverage_summary = parse_coverage_report(coverage_path) if coverage_path else None
    analysis = _read_optional_json(_resolve_output(repo, ".ut-cover/analysis.json"))
    coverage_dict = coverage_summary.to_dict() if coverage_summary else None
    coverage_gate = evaluate_coverage_gate(config, coverage_dict, analysis)
    payload = {
        "repo": str(repo),
        "config": config.to_dict(),
        "test_result": remote_run.get("dt_result") or remote_run.get("build_result"),
        "remote_sync": sync,
        "remote_run": remote_run,
        "remote_fetch": fetched,
        "coverage": coverage_dict,
        "coverage_gate": coverage_gate,
    }
    output = _resolve_output(repo, args.output)
    write_json(payload, output)
    print(f"Wrote coverage result: {output}")
    if not remote_run["ok"]:
        diagnosis = diagnose_remote_failure(remote_run, config=config)
        payload["remote_diagnosis"] = diagnosis
        write_json(payload, output)
        write_json(diagnosis, _resolve_output(repo, ".ut-cover/remote-diagnosis.json"))
        return 1
    return 0 if coverage_gate.get("ok", True) else 1


def cmd_remote_doctor(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    backend_available = ai_ssh_mcp_available() if config.remote_backend == "ai_ssh_mcp" else False
    checks = [
        {"name": "execution_mode", "ok": config.execution_mode == "remote", "message": config.execution_mode},
        {"name": "remote_backend", "ok": config.remote_backend == "ai_ssh_mcp", "message": config.remote_backend},
        {
            "name": "ai_ssh_mcp",
            "ok": backend_available,
            "message": "ai_ssh_mcp importable"
            if backend_available
            else "ai_ssh_mcp is not importable. Install or keep it beside Create_tool/src.",
        },
        {"name": "remote_workspace_root", "ok": bool(config.remote_workspace_root), "message": config.remote_workspace_root},
        {
            "name": "remote_commands",
            "ok": bool(config.remote_build_command or config.remote_dt_command),
            "message": "remote_build_command or remote_dt_command is configured"
            if (config.remote_build_command or config.remote_dt_command)
            else "Configure remote_build_command and/or remote_dt_command.",
        },
    ]
    ok = all(item["ok"] for item in checks)
    print(json.dumps({"ok": ok, "checks": checks, "next_action": "continue" if ok else "stop"}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_remote_sync(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    backend = create_remote_backend(config)
    try:
        result = sync_workspace(repo, config, backend, run_id=args.run_id)
    finally:
        backend.close()
    output = write_json(result, _resolve_output(repo, args.output))
    print(f"Wrote remote sync: {output}")
    return 0


def cmd_remote_run(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    remote_workspace = args.remote_workspace or _latest_remote_workspace(repo, config)
    backend = create_remote_backend(config)
    try:
        result = run_remote_commands(config, backend, remote_workspace, timeout=args.timeout)
    finally:
        backend.close()
    output = write_json(result, _resolve_output(repo, args.output))
    print(f"Wrote remote run: {output}")
    return 0 if result["ok"] else 1


def cmd_remote_fetch(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    remote_workspace = args.remote_workspace or _latest_remote_workspace(repo, config)
    backend = create_remote_backend(config)
    try:
        result = fetch_remote_artifacts(repo, config, backend, remote_workspace)
    finally:
        backend.close()
    output = write_json(result, _resolve_output(repo, args.output))
    print(f"Wrote remote fetch: {output}")
    return 0 if result["ok"] else 1


def cmd_remote_diagnose(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    remote_run = read_json(_resolve_output(repo, args.remote_run))
    log_text = "\n".join(
        Path(path).read_text(encoding="utf-8", errors="replace")
        for path in args.log
        if Path(path).exists()
    )
    result = diagnose_remote_failure(remote_run, fetched_text=log_text, config=config)
    output = write_json(result, _resolve_output(repo, args.output))
    print(f"Wrote remote diagnosis: {output}")
    return 0 if result["ok"] else 1


def cmd_upgrade_status(args: argparse.Namespace) -> int:
    interaction_mode = _interaction_mode_from_repo(args.repo)
    payload = build_upgrade_status(
        install_dir=args.install_dir,
        ut_zip=args.ut_zip,
        ssh_zip=args.ssh_zip,
        zip_dir=args.zip_dir,
        interaction_mode=interaction_mode,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def cmd_upgrade(args: argparse.Namespace) -> int:
    interaction_mode = _interaction_mode_from_repo(args.repo)
    ssh_zip = Path(args.ssh_zip).resolve() if args.ssh_zip else Path(args.ut_zip).resolve().parent / "ai-ssh-mcp-tool.zip"
    status = build_upgrade_status(
        install_dir=args.install_dir,
        ut_zip=args.ut_zip,
        ssh_zip=ssh_zip,
        interaction_mode=interaction_mode,
    )
    report = {
        "ok": True,
        "action": "upgrade",
        "interaction_mode": interaction_mode,
        "status_before": status,
        "ut_upgrade": None,
        "ssh_upgrade": None,
        "next_action": "continue",
    }
    report["ut_upgrade"] = upgrade_from_zip(
        args.install_dir,
        args.ut_zip,
        run_pip_install=not args.skip_pip_install,
    )
    report["ok"] = bool(report["ut_upgrade"].get("ok"))
    if not report["ok"]:
        report["next_action"] = "inspect_ut_upgrade_error"
    should_upgrade_ssh = args.upgrade_ssh or (
        interaction_mode == "autonomous"
        and status.get("next_action") == "auto_upgrade_ai_ssh_mcp"
        and ssh_zip.exists()
    )
    if should_upgrade_ssh:
        report["ssh_upgrade"] = upgrade_ai_ssh_mcp_from_zip(
            ssh_zip,
            ssh_install_dir=args.ssh_install_dir,
            reference_install_dir=args.install_dir,
            run_pip_install=not args.skip_pip_install,
        )
        report["ok"] = bool(report["ok"] and report["ssh_upgrade"].get("ok"))
    elif status.get("next_action") in {"upgrade_ai_ssh_mcp_with_confirmation", "auto_upgrade_ai_ssh_mcp"}:
        report["ok"] = False
        report["next_action"] = (
            "provide_ai_ssh_mcp_zip"
            if not ssh_zip.exists()
            else "rerun_with_upgrade_ssh"
        )
    write_upgrade_report(args.install_dir, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


def cmd_plan_tests(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    analysis_path = _resolve_output(repo, args.analysis)
    if not analysis_path.exists():
        raise UtCoverError(f"Analysis not found: {analysis_path}. Run analyze-commits first.")
    analysis = read_json(analysis_path)
    plan = build_test_plan(repo, config, analysis)
    json_output = write_json(plan, _resolve_output(repo, args.output))
    markdown_output = write_markdown(render_test_plan_markdown(plan), _resolve_output(repo, args.markdown_output))
    print(f"Wrote test plan JSON: {json_output}")
    print(f"Wrote test plan Markdown: {markdown_output}")
    return 0


def cmd_review_tests(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    touched_tests = list(args.touched_test or [])
    if args.touched_test_file:
        touched_tests.extend(
            line.strip()
            for line in Path(args.touched_test_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if not touched_tests:
        raise UtCoverError("No touched tests provided. Use --touched-test or --touched-test-file.")
    plan_path = _resolve_output(repo, args.plan)
    plan = read_json(plan_path) if plan_path.exists() else None
    review = review_touched_tests(repo, config, touched_tests, plan)
    output = write_json(review, _resolve_output(repo, args.output))
    print(f"Wrote test review: {output}")
    return 0 if review["ok"] else 1


def cmd_report(args: argparse.Namespace) -> int:
    analysis_path = Path(args.analysis).resolve()
    coverage_path = Path(args.coverage).resolve()
    analysis = read_json(analysis_path) if analysis_path.exists() else None
    coverage = read_json(coverage_path) if coverage_path.exists() else None
    touched_tests = list(args.touched_test or [])
    if args.touched_test_file:
        touched_tests.extend(
            line.strip()
            for line in Path(args.touched_test_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    payload = build_report_payload(analysis, coverage, touched_tests)
    json_output = write_json(payload, args.json_output)
    markdown_output = write_markdown(render_markdown(payload), args.output)
    print(f"Wrote JSON report: {json_output}")
    print(f"Wrote Markdown report: {markdown_output}")
    return 0


def _resolve_output(repo: Path, output: str) -> Path:
    path = Path(output)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def _validate_percent(value: float, field: str) -> None:
    if value < 0 or value > 100:
        raise UtCoverError(f"{field} must be between 0 and 100")


def _ensure_autonomous_coverage_goal(repo: Path, config):
    if config.interaction_mode != "autonomous":
        return config
    if config.autonomous_missing_coverage_goal != "use_defaults":
        return config
    if config.coverage_threshold is not None and config.changed_files_coverage_threshold is not None:
        return config
    update_config_values(
        repo,
        {
            "coverage_threshold": config.coverage_threshold if config.coverage_threshold is not None else 80,
            "changed_files_coverage_threshold": config.changed_files_coverage_threshold
            if config.changed_files_coverage_threshold is not None
            else 85,
            "coverage_unknown_action": config.coverage_unknown_action or "warn",
            "coverage_fail_below_threshold": config.coverage_fail_below_threshold,
        },
    )
    return load_config(repo)


def _interaction_mode_from_repo(repo: str | None) -> str:
    if not repo:
        return "interactive"
    try:
        return load_config(repo).interaction_mode
    except Exception:
        return "interactive"


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    return read_json(path) if path.exists() else None


def _latest_remote_workspace(repo: Path, config) -> str:
    sync_path = _resolve_output(repo, ".ut-cover/remote-sync.json")
    if sync_path.exists():
        data = read_json(sync_path)
        if data.get("remote_workspace"):
            return data["remote_workspace"]
    return remote_workspace_for(repo, config, "latest")


def _find_fetched_coverage(repo: Path, config) -> Path | None:
    remote_root = repo / ".ut-cover" / "remote"
    candidates = [
        remote_root / config.coverage_report.replace("/", "_"),
        remote_root / Path(config.coverage_report).name,
    ]
    candidates.extend(remote_root.glob("*.xml"))
    candidates.extend(remote_root.glob("*.json"))
    for candidate in candidates:
        if candidate.exists() and candidate.name not in {"remote-run.json", "remote-fetch.json"}:
            return candidate
    return None
