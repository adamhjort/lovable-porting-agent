#!/usr/bin/env python3
"""Turn a portability inventory into an approval-gated deployment plan."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from backend_profiles import (
    DEFAULT_BACKEND,
    backend_choices,
    backend_metadata,
    evaluate_backend,
)
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
        "--hosting",
        "--target",
        dest="hosting",
        choices=target_choices(),
        default=DEFAULT_TARGET,
    )
    parser.add_argument("--backend", choices=backend_choices(), default=DEFAULT_BACKEND)
    parser.add_argument(
        "--database-migration-mode",
        choices=("empty", "schema-only", "clone-test-data"),
        default="empty",
        help="Standard ports default to an empty target; source-data evidence is only required for a test-data clone.",
    )
    parser.add_argument(
        "--backend-target-id",
        "--target-project-ref",
        dest="backend_target_id",
        help="Non-secret target identifier; a Supabase project ref for supabase-managed",
    )
    parser.add_argument("--backend-readiness-evidence", help="Required for guided or existing backend profiles")
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


def env_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
    if not normalized or normalized[0].isdigit():
        normalized = f"STACKFERRY_{normalized or 'PRIVATE_VALUE'}"
    return normalized[:128]


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
    target_name = slugify(args.app_name)
    unresolved: list[dict] = []
    deployment_remediations: list[dict] = []

    for blocker in inventory["portability"]["blockers"]:
        if blocker["code"] == "source_data_state_unknown":
            continue
        remediation = blocker.get("deployment_remediation")
        if remediation:
            deployment_remediations.append(
                {
                    "type": remediation,
                    "source_code": blocker["code"],
                    "locations": blocker.get("locations", []),
                }
            )
            continue
        unresolved.append(blocker)

    moves_backend = args.backend not in {"none", "existing-backend"}
    clones_source_data = moves_backend and args.database_migration_mode == "clone-test-data"
    if clones_source_data:
        if args.source_data_classification == "unknown":
            unresolved.append(
                {"code": "source_data_classification_required", "severity": "blocking", "message": "Classify source data before apply."}
            )
        elif args.source_data_classification == "contains-real-data":
            unresolved.append(
                {
                    "code": "separate_database_clone_plan_required",
                    "severity": "blocking",
                    "message": "The deployment plan never copies real data; create and approve a separate database clone plan.",
                }
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
    generated_files, target_blockers = evaluate_target(args.hosting, inventory, target_name)
    unresolved.extend(target_blockers)

    resolved_backend, backend_operations, backend_manual_steps, backend_blockers = evaluate_backend(
        args.backend,
        inventory,
        args.backend_target_id,
        args.backend_readiness_evidence,
    )
    unresolved.extend(backend_blockers)

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

    operations.extend(backend_operations)
    manual_operations = list(backend_manual_steps)
    deploy_operation = deployment_operation(args.hosting, target_name)
    if deploy_operation["kind"] == "command":
        operations.append(deploy_operation)
    else:
        manual_operations.append(deploy_operation)

    secret_names = [
        item["name"]
        for item in inventory["configuration"]["env_keys"]
        if item["classification"] == "secret"
    ]
    secret_names.extend(
        env_name(location.get("key", "STACKFERRY_PRIVATE_VALUE"))
        for remediation in deployment_remediations
        if remediation["type"] == "externalize-private-literal"
        for location in remediation["locations"]
    )
    commit = repo.get("commit") or "uncommitted"
    confirmation = f"APPLY:{target_name}:{commit[:12]}"
    plan = {
        "schema_version": 1,
        "app_name": args.app_name,
        "target": args.hosting,
        "hosting": args.hosting,
        "target_details": target_metadata(args.hosting),
        "hosting_details": target_metadata(args.hosting),
        "backend": resolved_backend,
        "backend_details": backend_metadata(resolved_backend),
        "source": {
            "repository": repo.get("origin") or repo.get("path"),
            "commit": repo.get("commit"),
            "data_classification": args.source_data_classification,
            "auth_users": args.source_auth_users,
            "storage_objects": args.source_storage_objects,
            "classification_evidence": args.classification_evidence,
            "database_migration_mode": args.database_migration_mode,
            "disposition": (
                "keep-existing-no-data-copy"
                if not moves_backend
                else "guarded-test-data-clone"
                if clones_source_data
                else "reviewed-schema-only-no-production-data-copy"
                if args.database_migration_mode == "schema-only"
                else "recreate-empty-no-data-copy"
            ),
        },
        "target_config": {
            "backend_target_id": args.backend_target_id,
            "backend_readiness_evidence": args.backend_readiness_evidence,
            "supabase_project_ref": args.backend_target_id if resolved_backend == "supabase-managed" else None,
            "public_domain": args.public_domain,
            "deployment_name": target_name,
            "worker_or_app_name": target_name,
        },
        "required_secret_names": sorted(set(secret_names)),
        "generated_files": generated_files,
        "deployment_remediations": deployment_remediations,
        "unresolved_blockers": unresolved,
        "can_apply": not unresolved,
        "confirmation_token": confirmation,
        "operations": operations,
        "manual_operations": manual_operations,
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
