#!/usr/bin/env python3
"""Print or execute a reviewed port plan. Execution is explicit and allowlisted."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_EXECUTABLES = {"npm", "npm.cmd", "npx", "npx.cmd", "pnpm", "pnpm.cmd"}
FORBIDDEN_TOKENS = {"delete", "destroy", "drop", "reset", "remove", "rm", "teardown"}
REDACTIONS = (
    (re.compile(r"sbp_[A-Za-z0-9_-]+"), "sbp_<redacted>"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"), "<jwt-redacted>"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "<aws-key-redacted>"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s]+"), r"\1<redacted>"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", help="Must exactly match plan confirmation_token")
    parser.add_argument("--evidence-out", help="Write redacted execution evidence JSON")
    return parser.parse_args()


def redact(value: str) -> str:
    for pattern, replacement in REDACTIONS:
        value = pattern.sub(replacement, value)
    return value


def validate_argv(argv: list[str]) -> None:
    if not argv or argv[0].lower() not in ALLOWED_EXECUTABLES:
        raise ValueError(f"Executable is not allowlisted: {argv[0] if argv else '<empty>'}")
    for token in argv[1:]:
        if token.lower() in FORBIDDEN_TOKENS:
            raise ValueError(f"Destructive token is forbidden: {token}")
        if "<" in token or ">" in token:
            raise ValueError(f"Placeholder token is unresolved: {token}")


def main() -> int:
    args = parse_args()
    plan_path = Path(args.plan).resolve()
    repo = Path(args.repo).resolve()
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read plan: {exc}", file=sys.stderr)
        return 1
    if not repo.is_dir():
        print(f"Repository not found: {repo}", file=sys.stderr)
        return 1

    for operation in plan.get("operations", []):
        argv = operation.get("argv") or []
        validate_argv(argv)
        marker = "EXTERNAL" if operation.get("mutates_external_state") else "LOCAL"
        print(f"[{marker}] {operation['step']}: {' '.join(argv)}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply and the exact confirmation token after review.")
        return 0
    if not plan.get("can_apply"):
        print("Plan cannot apply while blockers remain.", file=sys.stderr)
        return 2
    if args.confirm != plan.get("confirmation_token"):
        print("Confirmation token mismatch.", file=sys.stderr)
        return 2

    evidence = {
        "schema_version": 1,
        "plan": str(plan_path),
        "source_commit": plan.get("source", {}).get("commit"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "operations": [],
    }
    for operation in plan.get("operations", []):
        argv = operation["argv"]
        started = time.monotonic()
        result = subprocess.run(
            argv,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        duration = round(time.monotonic() - started, 3)
        stdout = redact(result.stdout)[-8000:]
        stderr = redact(result.stderr)[-8000:]
        if stdout:
            print(stdout, end="" if stdout.endswith("\n") else "\n")
        if stderr:
            print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
        evidence["operations"].append(
            {
                "step": operation["step"],
                "argv": argv,
                "returncode": result.returncode,
                "duration_seconds": duration,
                "stdout_tail": stdout,
                "stderr_tail": stderr,
            }
        )
        if result.returncode != 0:
            evidence["status"] = "failed"
            break
    else:
        evidence["status"] = "completed"
    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()

    if args.evidence_out:
        out = Path(args.evidence_out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote redacted evidence: {out}")
    return 0 if evidence.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
