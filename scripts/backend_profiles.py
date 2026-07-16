#!/usr/bin/env python3
"""Backend profile registry and compatibility evaluation."""

from __future__ import annotations

from copy import deepcopy


DEFAULT_BACKEND = "auto"

BACKEND_PROFILES: dict[str, dict] = {
    "none": {
        "label": "No backend",
        "kind": "none",
        "support_level": "direct",
        "capabilities": set(),
        "reference": "references/backend-profiles.md",
    },
    "existing-backend": {
        "label": "Existing external backend or API",
        "kind": "existing",
        "support_level": "guided",
        "capabilities": {"application-defined"},
        "reference": "references/backend-profiles.md",
    },
    "supabase-managed": {
        "label": "Managed Supabase",
        "kind": "backend-as-a-service",
        "support_level": "direct",
        "capabilities": {"postgres", "data-api", "auth", "storage", "realtime", "edge-functions", "rls"},
        "reference": "references/backend-supabase.md",
    },
    "supabase-self-hosted": {
        "label": "Self-hosted Supabase",
        "kind": "backend-as-a-service",
        "support_level": "guided",
        "capabilities": {"postgres", "data-api", "auth", "storage", "realtime", "edge-functions", "rls"},
        "reference": "references/backend-supabase.md",
    },
    "neon-postgres": {
        "label": "Neon Postgres",
        "kind": "managed-postgres",
        "support_level": "guided",
        "capabilities": {"postgres", "rls"},
        "reference": "references/backend-postgres.md",
    },
    "aws-rds-postgres": {
        "label": "AWS RDS or Aurora PostgreSQL",
        "kind": "managed-postgres",
        "support_level": "guided",
        "capabilities": {"postgres", "rls"},
        "reference": "references/backend-postgres.md",
    },
    "gcp-cloud-sql-postgres": {
        "label": "Google Cloud SQL for PostgreSQL",
        "kind": "managed-postgres",
        "support_level": "guided",
        "capabilities": {"postgres", "rls"},
        "reference": "references/backend-postgres.md",
    },
    "azure-postgres": {
        "label": "Azure Database for PostgreSQL",
        "kind": "managed-postgres",
        "support_level": "guided",
        "capabilities": {"postgres", "rls"},
        "reference": "references/backend-postgres.md",
    },
    "generic-postgres": {
        "label": "Generic PostgreSQL",
        "kind": "postgres",
        "support_level": "guided",
        "capabilities": {"postgres", "rls"},
        "reference": "references/backend-postgres.md",
    },
}


def backend_choices(include_auto: bool = True) -> tuple[str, ...]:
    profiles = tuple(BACKEND_PROFILES)
    return (DEFAULT_BACKEND, *profiles) if include_auto else profiles


def backend_metadata(backend: str) -> dict:
    profile = BACKEND_PROFILES[backend]
    return {
        "id": backend,
        "label": profile["label"],
        "kind": profile["kind"],
        "support_level": profile["support_level"],
        "capabilities": sorted(profile["capabilities"]),
        "reference": profile["reference"],
    }


def detect_backend_requirements(inventory: dict) -> set[str]:
    supabase = inventory.get("supabase", {})
    features = inventory.get("portability", {}).get("features", {})
    app = inventory.get("application", {})
    requirements: set[str] = set()
    if app.get("uses_base44_sdk") or features.get("base44_sdk"):
        requirements.update({"data-api", "auth", "edge-functions"})
    if supabase.get("configured") or supabase.get("migration_count", 0) > 0 or app.get("uses_supabase_client"):
        requirements.update({"postgres", "rls"})
    if app.get("uses_supabase_client") or features.get("supabase_data_api"):
        requirements.add("data-api")
    if features.get("supabase_auth"):
        requirements.add("auth")
    if features.get("storage"):
        requirements.add("storage")
    if features.get("supabase_realtime"):
        requirements.add("realtime")
    if supabase.get("edge_function_count", 0) > 0 or features.get("supabase_functions"):
        requirements.add("edge-functions")
    return requirements


def resolve_backend(requested: str, inventory: dict) -> str:
    if requested != DEFAULT_BACKEND:
        return requested
    app = inventory.get("application", {})
    features = inventory.get("portability", {}).get("features", {})
    if app.get("uses_base44_sdk") or features.get("base44_sdk"):
        return "existing-backend"
    return "supabase-managed" if detect_backend_requirements(inventory) else "none"


def _blocker(code: str, message: str) -> dict:
    return {"code": code, "severity": "blocking", "message": message}


def evaluate_backend(
    requested: str,
    inventory: dict,
    target_id: str | None,
    readiness_evidence: str | None,
) -> tuple[str, list[dict], list[dict], list[dict]]:
    """Return resolved profile, executable operations, manual steps, and blockers."""

    backend = resolve_backend(requested, inventory)
    profile = BACKEND_PROFILES[backend]
    requirements = detect_backend_requirements(inventory)
    operations: list[dict] = []
    manual_steps: list[dict] = []
    blockers: list[dict] = []

    if backend == "none":
        if requirements:
            blockers.append(
                _blocker(
                    "backend_required",
                    f"The application still requires backend capabilities: {', '.join(sorted(requirements))}.",
                )
            )
        return backend, operations, manual_steps, blockers

    if backend == "existing-backend":
        if not readiness_evidence:
            blockers.append(
                _blocker(
                    "existing_backend_evidence_required",
                    "Document the existing API contract, owner, environment, and acceptance evidence.",
                )
            )
        if inventory.get("application", {}).get("uses_base44_sdk") or inventory.get("portability", {}).get("features", {}).get("base44_sdk"):
            manual_steps.append(
                {
                    "step": "verify-base44-contract",
                    "kind": "reviewed-manual-operation",
                    "action": "Verify the Base44 app id, backend URL, allowed origins, authentication callbacks, entities and functions against the pinned repository without copying identities or rows.",
                    "requires_approval": False,
                }
            )
        return backend, operations, manual_steps, blockers

    if not target_id:
        blockers.append(_blocker("backend_target_required", "Provide a non-secret backend target identifier."))

    if inventory.get("application", {}).get("uses_base44_sdk") or inventory.get("portability", {}).get("features", {}).get("base44_sdk"):
        blockers.append(
            _blocker(
                "base44_adapter_required",
                "Replace the Base44 SDK data, auth and function calls with a reviewed target-backend adapter before switching away from the existing Base44 backend.",
            )
        )

    missing = requirements - profile["capabilities"]
    for capability in sorted(missing):
        blockers.append(
            _blocker(
                f"{capability.replace('-', '_')}_adapter_required",
                f"The selected backend does not provide {capability}; implement and verify a replacement adapter.",
            )
        )

    if backend == "supabase-managed" and target_id:
        operations.extend(
            [
                {
                    "step": "supabase-link",
                    "kind": "command",
                    "argv": ["npx", "supabase", "link", "--project-ref", target_id],
                    "mutates_external_state": True,
                    "requires_approval": True,
                },
                {
                    "step": "supabase-db-push",
                    "kind": "command",
                    "argv": ["npx", "supabase", "db", "push", "--include-all", "--yes"],
                    "mutates_external_state": True,
                    "requires_approval": True,
                },
            ]
        )
        if inventory.get("supabase", {}).get("edge_function_count", 0) > 0:
            operations.append(
                {
                    "step": "supabase-functions-deploy",
                    "kind": "command",
                    "argv": ["npx", "supabase", "functions", "deploy", "--project-ref", target_id],
                    "mutates_external_state": True,
                    "requires_approval": True,
                }
            )
    else:
        if not readiness_evidence:
            blockers.append(
                _blocker(
                    "backend_readiness_evidence_required",
                    "Guided backend profiles require evidence for provisioning, schema application, secrets, backups, and connectivity.",
                )
            )
        manual_steps.append(
            {
                "step": "prepare-backend",
                "kind": "reviewed-manual-operation",
                "action": "Provision the selected backend, apply the reviewed schema/data plan, configure secrets, and attach acceptance evidence.",
                "requires_approval": True,
            }
        )

    return backend, deepcopy(operations), deepcopy(manual_steps), blockers
