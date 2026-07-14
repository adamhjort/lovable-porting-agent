#!/usr/bin/env python3
"""Turn a portability inventory into an approval-gated deployment plan."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from target_profiles import (
    DEFAULT_TARGET,
    deployment_operation,
    evaluate_target,
    target_choices,
    target_metadata,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", help="Inventory JSON from inventory_repo.py")
    parser.add_argument("--out", required=True, help="Output plan JSON")
    parser.add_argument("--app-name", required=True)
    parser.add_argument(
        "--target",
        choices=target_choices(),
        default=DEFAULT_TARGET,
    )
    parser.add_argument("--target-project-ref", help="Existing empty Supabase target project ref")
    parser.add_argument("--public-domain", help="Expected public domain after deployment")
    parser.add_argument(
        "--source-data-classification",
        choices=("unknown", "test-only", "contains-real-data"),
        default="unknown",
    )
    parser.add_argument("--source-auth-users", type=int)
    parser.add_argument("--source-storage-objects", type=int)
    parser.add_argument(
        "--classification-evidence",
        help="Short evidence reference; required when source counts are non-zero",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return value[:63] or "lovable-app"


def main() -> int:
    args = parse_args()
    inventory_path = Path(args.inventory).resolve()
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read inventory: {exc}", file=sys.stderr)
        return 1
    if inventory.get("schema_version") != 1:
        print("Unsupported inventory schema version", file=sys.stderr)
        return 1

    repo = inventory["repository"]
    app = inventory["application"]
    supabase = inventory["supabase"]
    target_name = slugify(args.app_name)
    unresolved: list[dict] = []

    for blocker in inventory["portability"]["blockers"]:
        if blocker["code"] == "source_data_state_unknown":
            continue
        unresolved.append(blocker)

    if args.source_data_classification == "unknown":
        unresolved.append(
            {"code": "source_data_classification_required", "severity": "blocking", "message": "Classify source data before apply."}
        )
    elif args.source_data_classification == "contains-real-data":
        unresolved.append(
            {"code": "real_data_migration_out_of_scope", "severity": "blocking", "message": "This skill recreates empty pre-production environments only."}
        )

    if args.source_auth_users is None or args.source_storage_objects is None:
        unresolved.append(
            {"code": "remote_counts_required", "severity": "blocking", "message": "Provide read-only auth-user and storage-object counts."}
        )
    elif (args.source_auth_users > 0 or args.source_storage_objects > 0) and not args.classification_evidence:
        unresolved.append(
            {"code": "classification_evidence_required", "severity": "blocking", "message": "Non-zero source counts require an evidence reference."}
        )

    if not repo.get("commit"):
        unresolved.append({"code": "git_commit_required", "severity": "blocking", "message": "Pin a Git commit before apply."})
    if not args.target_project_ref:
        unresolved.append(
            {"code": "empty_supabase_target_required", "severity": "blocking", "message": "Provision an empty target project and pass its ref."}
        )

    generated_files, target_blockers = evaluate_target(args.target, inventory, target_name)
    unresolved.extend(target_blockers)

    operations: list[dict] = []

    def command(step: str, argv: list[str], external: bool = False) -> None:
        operations.append(
            {
                "step": step,
                "kind": "command",
                "argv": argv,
                "mutates_external_state": external,
                "requires_approval": external,
            }
        )

    command("install", ["npm", "ci"])
    if "lint" in app.get("scripts", []):
        command("lint", ["npm", "run", "lint"])
    if "test" in app.get("scripts", []):
        command("test", ["npm", "test"])
    command("build", ["npm", "run", "build"])

    if args.target_project_ref:
        command("supabase-link", ["npx", "supabase", "link", "--project-ref", args.target_project_ref], True)
        command("supabase-db-push", ["npx", "supabase", "db", "push", "--include-all", "--yes"], True)
        if supabase.get("edge_function_count", 0) > 0:
            command(
                "supabase-functions-deploy",
                ["npx", "supabase", "functions", "deploy", "--project-ref", args.target_project_ref],
                True,
            )

    operations.append(deployment_operation(args.target, target_name))

    secret_names = [
        item["name"]
        for item in inventory["configuration"]["env_keys"]
        if item["classification"] == "secret"
    ]
    commit = repo.get("commit") or "uncommitted"
    confirmation = f"APPLY:{target_name}:{commit[:12]}"
    plan = {
        "schema_version": 1,
        "app_name": args.app_name,
        "target": args.target,
        "target_details": target_metadata(args.target),
        "source": {
            "repository": repo.get("origin") or repo.get("path"),
            "commit": repo.get("commit"),
            "data_classification": args.source_data_classification,
            "auth_users": args.source_auth_users,
            "storage_objects": args.source_storage_objects,
            "classification_evidence": args.classification_evidence,
            "disposition": "recreate-empty-no-data-copy",
        },
        "target_config": {
            "supabase_project_ref": args.target_project_ref,
            "public_domain": args.public_domain,
            "deployment_name": target_name,
            "worker_or_app_name": target_name,
        },
        "required_secret_names": sorted(secret_names),
        "generated_files": generated_files,
        "unresolved_blockers": unresolved,
        "can_apply": not unresolved,
        "confirmation_token": confirmation,
        "operations": operations,
        "source_teardown_included": False,
    }
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote port plan: {out}")
    print(f"Can apply: {plan['can_apply']}")
    if unresolved:
        print("Unresolved blockers:")
        for blocker in unresolved:
            print(f"- {blocker['code']}: {blocker['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
