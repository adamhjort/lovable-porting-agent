#!/usr/bin/env python3
"""Create an approval-gated plan for copying an existing PostgreSQL database."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from backend_profiles import BACKEND_PROFILES, backend_choices, backend_metadata


MODES = ("full-clone", "sanitized-clone")
METHODS = ("supabase-managed-restore", "postgres-logical-restore", "provider-native-migration")
CLASSIFICATIONS = ("unknown", "synthetic", "personal-data", "special-category-data")
SOURCE_KINDS = ("supabase-postgres", "postgres")
NON_PRODUCTION_ENVIRONMENTS = {"development", "test", "staging", "pre-production"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Write the clone plan JSON")
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--method", choices=METHODS, default="supabase-managed-restore")
    parser.add_argument("--source-database-kind", choices=SOURCE_KINDS, default="supabase-postgres")
    parser.add_argument(
        "--source-database-id",
        "--source-project-ref",
        dest="source_database_id",
        required=True,
        help="Non-secret source database or project identifier",
    )
    parser.add_argument("--source-backup-id", help="Backup id or immutable restore-point reference")
    parser.add_argument(
        "--target-backend",
        choices=tuple(x for x in backend_choices(include_auto=False) if x not in {"none", "existing-backend"}),
        default="supabase-managed",
    )
    parser.add_argument("--target-backend-id", help="Required unless managed restore creates the target")
    parser.add_argument("--target-environment", required=True)
    parser.add_argument("--target-organization", required=True)
    parser.add_argument("--source-data-classification", choices=CLASSIFICATIONS, default="unknown")
    parser.add_argument("--source-auth-users", type=int)
    parser.add_argument("--source-storage-objects", type=int)
    parser.add_argument("--classification-evidence")
    parser.add_argument("--authorization-evidence")
    parser.add_argument("--security-review-evidence")
    parser.add_argument("--legal-basis-evidence")
    parser.add_argument("--data-residency-evidence")
    parser.add_argument("--control-equivalence-evidence")
    parser.add_argument("--sanitization-spec")
    parser.add_argument("--migration-readiness-evidence")
    parser.add_argument("--retention-days", type=int)
    parser.add_argument("--target-access-restricted", action="store_true")
    parser.add_argument("--egress-extensions-reviewed", action="store_true")
    parser.add_argument("--target-verified-empty", action="store_true")
    parser.add_argument("--include-auth-users", action="store_true")
    return parser.parse_args()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return value[:48] or "lovable-app"


def blocker(code: str, message: str) -> dict:
    return {"code": code, "severity": "blocking", "message": message}


def warning(code: str, message: str) -> dict:
    return {"code": code, "severity": "warning", "message": message}


def manual_operation(step: str, action: str, approval: bool = False) -> dict:
    return {
        "step": step,
        "kind": "reviewed-manual-operation",
        "action": action,
        "mutates_external_state": approval,
        "requires_approval": approval,
    }


def build_plan(args: argparse.Namespace) -> dict:
    blockers: list[dict] = []
    warnings: list[dict] = []
    classification = args.source_data_classification
    target_environment = args.target_environment.strip().lower()

    if classification == "unknown":
        blockers.append(blocker("data_classification_required", "Classify the source before any database copy."))
    if args.source_auth_users is None or args.source_storage_objects is None:
        blockers.append(blocker("aggregate_counts_required", "Provide read-only Auth user and Storage object counts."))
    elif args.source_auth_users < 0 or args.source_storage_objects < 0:
        blockers.append(blocker("invalid_aggregate_counts", "Aggregate counts cannot be negative."))
    if not args.classification_evidence:
        blockers.append(blocker("classification_evidence_required", "Provide an accountable classification evidence reference."))
    if not args.authorization_evidence:
        blockers.append(blocker("copy_authorization_required", "Provide explicit authorization evidence for copying the database."))
    if not args.source_backup_id:
        blockers.append(blocker("immutable_restore_point_required", "Pin an immutable backup id or restore-point reference."))
    if not args.target_access_restricted:
        blockers.append(blocker("restricted_target_required", "Restrict target access before the clone is created."))
    if not args.egress_extensions_reviewed:
        blockers.append(
            blocker(
                "egress_extension_review_required",
                "Review pg_net, pg_cron, wrappers, webhooks, and other outbound integrations before cloning.",
            )
        )

    if classification in {"personal-data", "special-category-data"}:
        if not args.security_review_evidence:
            blockers.append(blocker("security_review_required", "Personal-data copies require a security review reference."))
        if not args.data_residency_evidence:
            blockers.append(blocker("data_residency_review_required", "Verify source and target data residency."))
        if not args.control_equivalence_evidence:
            blockers.append(
                blocker(
                    "control_equivalence_required",
                    "Show that target access, logging, encryption, backups, and incident controls are equivalent.",
                )
            )
        if args.retention_days is None or args.retention_days <= 0:
            blockers.append(blocker("retention_required", "Set a positive retention period and cleanup deadline."))
        if target_environment in NON_PRODUCTION_ENVIRONMENTS and args.mode == "full-clone":
            warnings.append(
                warning(
                    "real_data_in_non_production",
                    "A full personal-data clone into non-production expands the regulated data footprint; prefer sanitized-clone.",
                )
            )
    if classification == "special-category-data" and not args.legal_basis_evidence:
        blockers.append(blocker("legal_basis_required", "Special-category data requires a documented legal-basis reference."))

    if args.mode == "sanitized-clone" and not args.sanitization_spec:
        blockers.append(
            blocker(
                "sanitization_spec_required",
                "Provide a reviewed, application-specific masking and validation specification.",
            )
        )

    target_profile = BACKEND_PROFILES[args.target_backend]
    if "postgres" not in target_profile["capabilities"]:
        blockers.append(blocker("postgres_target_required", "Database clone targets must provide PostgreSQL."))

    if args.method == "supabase-managed-restore":
        if args.source_database_kind != "supabase-postgres" or args.target_backend != "supabase-managed":
            blockers.append(
                blocker(
                    "managed_restore_profile_mismatch",
                    "Supabase managed restore requires a Supabase source and the supabase-managed target backend.",
                )
            )
        if args.target_backend_id:
            blockers.append(
                blocker(
                    "managed_restore_creates_target",
                    "Managed Restore to a New Project creates the target; do not supply an existing target id.",
                )
            )
        auth_records_included = True
    else:
        if not args.target_backend_id:
            blockers.append(blocker("database_target_required", "The selected migration method requires a target backend id."))
        if not args.target_verified_empty:
            blockers.append(blocker("empty_target_evidence_required", "Verify that the migration target is empty."))
        if args.method == "provider-native-migration" and not args.migration_readiness_evidence:
            blockers.append(
                blocker(
                    "provider_migration_evidence_required",
                    "Document the provider-native migration service, source connectivity, rollback, and validation plan.",
                )
            )
        if (args.source_auth_users or 0) > 0 and not args.include_auth_users:
            warnings.append(
                warning(
                    "auth_users_excluded",
                    "The selected plan excludes Auth users; create synthetic users or add a separately reviewed Auth migration.",
                )
            )
        auth_records_included = bool(args.include_auth_users)

    if (args.source_storage_objects or 0) > 0:
        warnings.append(
            warning(
                "storage_objects_not_copied",
                "Database cloning does not copy Storage object binaries; inventory and authorize them separately.",
            )
        )

    operations = [
        manual_operation(
            "pre-clone-quarantine",
            "Confirm restricted target membership, network controls, audit logging, budget, retention owner, and blocked outbound integrations.",
        ),
    ]
    if args.method == "supabase-managed-restore":
        operations.append(
            manual_operation(
                "clone-database",
                "Use Supabase Restore to a New Project from the pinned backup or restore point in the approved organization.",
                approval=True,
            )
        )
    elif args.method == "postgres-logical-restore":
        operations.append(
            manual_operation(
                "logical-export-restore",
                "Follow the current official source and target PostgreSQL dump/restore procedure using an approved secret channel and no unencrypted retained dump.",
                approval=True,
            )
        )
    else:
        operations.append(
            manual_operation(
                "provider-native-migration",
                "Run the reviewed provider-native database migration service from the pinned restore point into the isolated target.",
                approval=True,
            )
        )
    operations.extend(
        [
            manual_operation(
                "disable-source-egress-copies",
                "Immediately disable cloned cron jobs, webhooks, pg_net, wrappers, SMTP, queues, and third-party callbacks.",
                approval=True,
            ),
            manual_operation(
                "rotate-target-credentials",
                "Issue target-specific API keys, signing material, database credentials, and integration secrets; do not reuse source secrets.",
                approval=True,
            ),
            manual_operation(
                "reconfigure-services",
                "Recreate reviewed Auth, Realtime, Storage, Edge Function, extension, and network settings that the database clone does not transfer.",
                approval=True,
            ),
        ]
    )
    if args.mode == "sanitized-clone":
        operations.extend(
            [
                manual_operation(
                    "apply-sanitization",
                    "Run the reviewed masking specification while the target remains quarantined.",
                    approval=True,
                ),
                manual_operation(
                    "validate-sanitization",
                    "Run aggregate and policy-safe validation queries and obtain human sign-off before granting developer access.",
                ),
            ]
        )
    operations.append(
        manual_operation(
            "acceptance-gate",
            "Verify schema, row counts, RLS denial, Auth behavior, disabled egress, missing Storage objects, audit evidence, and cleanup deadline.",
        )
    )

    app_slug = slugify(args.app_name)
    backup_fragment = re.sub(r"[^A-Za-z0-9]+", "", args.source_backup_id or "unpinned")[:12]
    confirmation = f"CLONE:{app_slug}:{args.source_database_id}:{backup_fragment}"
    return {
        "schema_version": 1,
        "plan_type": "database-clone",
        "app_name": args.app_name,
        "mode": args.mode,
        "method": args.method,
        "source": {
            "database_kind": args.source_database_kind,
            "database_id": args.source_database_id,
            "project_ref": args.source_database_id if args.source_database_kind == "supabase-postgres" else None,
            "backup_or_restore_point": args.source_backup_id,
            "data_classification": classification,
            "auth_users": args.source_auth_users,
            "storage_objects": args.source_storage_objects,
            "classification_evidence": args.classification_evidence,
        },
        "target": {
            "backend": args.target_backend,
            "backend_details": backend_metadata(args.target_backend),
            "organization": args.target_organization,
            "environment": target_environment,
            "backend_id": args.target_backend_id,
            "access_restricted": args.target_access_restricted,
        },
        "governance": {
            "authorization_evidence": args.authorization_evidence,
            "security_review_evidence": args.security_review_evidence,
            "legal_basis_evidence": args.legal_basis_evidence,
            "data_residency_evidence": args.data_residency_evidence,
            "control_equivalence_evidence": args.control_equivalence_evidence,
            "retention_days": args.retention_days,
            "sanitization_spec": args.sanitization_spec,
            "migration_readiness_evidence": args.migration_readiness_evidence,
        },
        "scope": {
            "database_schema_and_rows": True,
            "auth_records_included": auth_records_included,
            "storage_object_binaries_included": False,
            "source_secrets_included": False,
            "source_teardown_included": False,
        },
        "warnings": warnings,
        "unresolved_blockers": blockers,
        "can_execute": not blockers,
        "release_allowed": False,
        "confirmation_token": confirmation,
        "operations": operations,
    }


def main() -> int:
    args = parse_args()
    plan = build_plan(args)
    out = Path(args.out).resolve()
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Cannot write clone plan: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote database clone plan: {out}")
    print(f"Can execute: {plan['can_execute']}")
    print("Release allowed: False (requires post-clone acceptance evidence)")
    if plan["unresolved_blockers"]:
        print("Unresolved blockers:")
        for item in plan["unresolved_blockers"]:
            print(f"- {item['code']}: {item['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
