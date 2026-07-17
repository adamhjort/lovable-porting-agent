#!/usr/bin/env python3
"""Self-contained tests for the safe inventory and dry-run plan path."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import apply_port_plan
import backend_profiles
import inventory_repo
import target_profiles


HERE = Path(__file__).resolve().parent


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def commit_fixture(root: Path) -> None:
    git(root, "init")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Fixture")
    git(root, "add", ".")
    git(root, "commit", "-m", "fixture")


def run_plan(root: Path, inventory: dict, target: str, name: str = "Fixture App", backend: str = "auto") -> dict:
    inventory_path = root / f".porting/inventory-{target}.json"
    write(inventory_path, json.dumps(inventory))
    plan_path = root / f".porting/plan-{target}.json"
    subprocess.run(
        [
            sys.executable,
            str(HERE / "make_port_plan.py"),
            str(inventory_path),
            "--out",
            str(plan_path),
            "--app-name",
            name,
            "--hosting",
            target,
            "--backend",
            backend,
            "--backend-target-id",
            "abcdefghijklmnopqrst",
            "--source-data-classification",
            "test-only",
            "--source-auth-users",
            "0",
            "--source-storage-objects",
            "0",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(plan_path.read_text(encoding="utf-8"))


def test_blocker_detection(root: Path) -> None:
    write(
        root / "package.json",
        json.dumps(
            {
                "name": "fixture-fullstack",
                "scripts": {"build": "vite build"},
                "dependencies": {"@tanstack/react-start": "1", "react": "19", "vite": "8"},
            }
        ),
    )
    write(root / "package-lock.json", "{}")
    write(
        root / "src/lib/public-host.server.ts",
        """import { createHmac } from 'node:crypto';
const host = 'https://project--fixture.lovable.app';
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
void Promise.resolve('background');
""",
    )
    write(
        root / "supabase/migrations/20260101000000_fixture.sql",
        """create extension if not exists pg_cron;
insert into private.app_settings values ('cron_secret', '0123456789abcdef0123456789abcdef');
select cron.schedule('fixture', '* * * * *', $$ select 1 $$);
""",
    )
    inventory = inventory_repo.scan_repository(root)
    codes = {item["code"] for item in inventory["portability"]["blockers"]}
    assert inventory["application"]["stack"] == "tanstack-start"
    assert "hardcoded_lovable_runtime_host" in codes
    assert "committed_secret_candidate" in codes
    assert "background_work_in_request" in {
        item["code"] for item in inventory["portability"]["warnings"]
    }
    serialized = json.dumps(inventory)
    assert "0123456789abcdef0123456789abcdef" not in serialized


def test_lockfile_package_names_are_not_secret_literals(root: Path) -> None:
    write(root / "package.json", json.dumps({"name": "fixture", "scripts": {"build": "vite build"}, "dependencies": {"react": "19", "vite": "8"}}))
    write(root / "package-lock.json", json.dumps({"packages": {"node_modules/js-tokens": {"version": "4.0.0"}}}))
    inventory = inventory_repo.scan_repository(root)
    assert inventory["portability"]["secret_candidates"] == []


def test_supabase_capabilities_are_detected(root: Path) -> None:
    write(root / "package.json", json.dumps({"name": "fixture", "scripts": {"build": "vite build"}, "dependencies": {"@supabase/supabase-js": "2", "react": "19", "vite": "8"}}))
    write(root / "src/api.ts", "supabase.auth.signInWithOAuth({ provider: 'github' }); supabase.from('projects').select('*'); supabase.functions.invoke('ping');")
    inventory = inventory_repo.scan_repository(root)
    assert {"supabase_auth", "supabase_data_api", "supabase_functions"} <= set(inventory["portability"]["features"])


def test_base44_backend_is_detected_and_safely_gated(root: Path) -> None:
    write(root / "package.json", json.dumps({"name": "base44-fixture", "scripts": {"build": "vite build"}, "dependencies": {"@base44/sdk": "1", "react": "19", "vite": "8"}}))
    write(root / "src/api.ts", "import { createClient } from '@base44/sdk'; const id = import.meta.env.VITE_BASE44_APP_ID;")
    inventory = inventory_repo.scan_repository(root)
    assert inventory["application"]["uses_base44_sdk"] is True
    assert "base44_sdk" in inventory["portability"]["features"]
    assert backend_profiles.resolve_backend("auto", inventory) == "existing-backend"
    backend, _, manual, blockers = backend_profiles.evaluate_backend("existing-backend", inventory, None, "PINNED-BASE44-1")
    assert backend == "existing-backend" and manual and not blockers
    _, _, _, blockers = backend_profiles.evaluate_backend("supabase-managed", inventory, "target-project-ref", None)
    assert "base44_adapter_required" in {item["code"] for item in blockers}


def test_railway_accepts_nitro_tanstack_without_dockerfile() -> None:
    inventory = minimal_target_inventory(runtime="fullstack", stack="tanstack-start")
    inventory["application"].update({"uses_nitro": True, "build_command": "vite build"})
    generated, blockers = target_profiles.evaluate_target("railway", inventory, "fixture")
    assert generated == []
    assert blockers == []


def test_clean_dry_run(root: Path) -> None:
    write(
        root / "package.json",
        json.dumps(
            {
                "name": "fixture-spa",
                "scripts": {"build": "vite build", "lint": "eslint .", "test": "vitest run"},
                "dependencies": {"react": "19", "vite": "8", "wrangler": "4"},
            }
        ),
    )
    write(root / "package-lock.json", "{}")
    write(root / "src/main.tsx", "const url = import.meta.env.VITE_SUPABASE_URL;\n")
    write(root / "supabase/config.toml", "project_id = 'fixture'\n")
    write(root / "supabase/migrations/20260101000000_fixture.sql", "create table public.fixture(id uuid primary key);\n")
    write(
        root / "wrangler.jsonc",
        '{"name":"fixture","compatibility_date":"2026-07-14","assets":{"directory":"./dist","not_found_handling":"single-page-application"}}\n',
    )
    commit_fixture(root)

    inventory = inventory_repo.scan_repository(root)
    inventory_path = root / ".porting/inventory.json"
    write(inventory_path, json.dumps(inventory))
    plan_path = root / ".porting/plan.json"
    plan_result = subprocess.run(
        [
            sys.executable,
            str(HERE / "make_port_plan.py"),
            str(inventory_path),
            "--out",
            str(plan_path),
            "--app-name",
            "Fixture SPA",
            "--target-project-ref",
            "abcdefghijklmnopqrst",
            "--source-data-classification",
            "test-only",
            "--source-auth-users",
            "0",
            "--source-storage-objects",
            "0",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Can apply: True" in plan_result.stdout
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["can_apply"] is True
    assert plan["source_teardown_included"] is False

    dry_run = subprocess.run(
        [
            sys.executable,
            str(HERE / "apply_port_plan.py"),
            str(plan_path),
            "--repo",
            str(root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Dry-run only" in dry_run.stdout

    provision = subprocess.run(
        [
            sys.executable,
            str(HERE / "provision_supabase.py"),
            "--name",
            "Fixture SPA",
            "--organization-slug",
            "fixture-org",
            "--out",
            str(root / ".porting/target.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Dry-run only. No project was created." in provision.stdout
    assert "SUPABASE_DB_PASSWORD" in provision.stdout
    assert not (root / ".porting/target.json").exists()


def test_target_registry() -> None:
    assert target_profiles.DEFAULT_TARGET == "cloudflare"
    assert set(target_profiles.target_choices()) == {
        "cloudflare",
        "vercel",
        "netlify",
        "aws-amplify",
        "docker",
        "github-pages",
        "azure-static-web-apps",
        "gcp-cloud-run",
        "aws-ecs-fargate",
        "railway",
        "render",
        "fly-io",
        "kubernetes",
        "digitalocean-app-platform",
    }
    skill_root = HERE.parent
    for target in target_profiles.target_choices():
        metadata = target_profiles.target_metadata(target)
        assert (skill_root / metadata["reference"]).is_file()
        operation = target_profiles.deployment_operation(target, "fixture-app")
        if operation["kind"] == "command":
            apply_port_plan.validate_argv(operation["argv"])
    try:
        apply_port_plan.validate_argv(["curl", "https://example.invalid"])
    except ValueError:
        pass
    else:
        raise AssertionError("Non-allowlisted executables must be rejected")


def minimal_target_inventory(runtime: str = "static-spa", stack: str = "vite-react") -> dict:
    return {
        "application": {
            "runtime": runtime,
            "stack": stack,
            "uses_cloudflare_vite_plugin": False,
            "uses_netlify_tanstack_plugin": False,
            "uses_nitro": False,
            "lovable_tanstack_config_version": None,
            "uses_supabase_client": False,
        },
        "configuration": {
            "config_files": {
                "wrangler.jsonc": False,
                "amplify.yml": False,
                "vercel.json": False,
                "netlify.toml": False,
                "Dockerfile": False,
                "nginx.conf": False,
                "staticwebapp.config.json": False,
                "swa-cli.config.json": False,
                "github-pages-workflow": False,
                "railway.json": False,
                "railway.toml": False,
                "render.yaml": False,
                "fly.toml": False,
                ".do/app.yaml": False,
                "k8s/deployment.yaml": False,
                "k8s/service.yaml": False,
            }
        },
    }


def test_target_evaluation() -> None:
    inventory = minimal_target_inventory()
    generated, blockers = target_profiles.evaluate_target("vercel", inventory, "fixture")
    assert {item["path"] for item in generated} == {"vercel.json"}
    assert {item["code"] for item in blockers} == {"vercel_config_required"}

    generated, blockers = target_profiles.evaluate_target("netlify", inventory, "fixture")
    assert {item["path"] for item in generated} == {"netlify.toml"}
    assert {item["code"] for item in blockers} == {"netlify_config_required"}

    generated, blockers = target_profiles.evaluate_target("docker", inventory, "fixture")
    assert {item["path"] for item in generated} == {"Dockerfile", "nginx.conf"}
    assert blockers == []

    fullstack = minimal_target_inventory(runtime="fullstack", stack="tanstack-start")
    fullstack["application"]["uses_nitro"] = True
    assert target_profiles.evaluate_target("vercel", fullstack, "fixture") == ([], [])

    fullstack["application"]["uses_nitro"] = False
    fullstack["application"]["lovable_tanstack_config_version"] = "^2.6.2"
    assert target_profiles.evaluate_target("vercel", fullstack, "fixture") == ([], [])
    fullstack["application"]["lovable_tanstack_config_version"] = "2.5.9"
    assert target_profiles.evaluate_target("vercel", fullstack, "fixture")[1][0]["code"] == "vercel_tanstack_adapter_required"

    fullstack["application"]["uses_netlify_tanstack_plugin"] = True
    fullstack["configuration"]["config_files"]["netlify.toml"] = True
    assert target_profiles.evaluate_target("netlify", fullstack, "fixture") == ([], [])

    fullstack["configuration"]["config_files"]["Dockerfile"] = True
    assert target_profiles.evaluate_target("docker", fullstack, "fixture") == ([], [])

    fullstack["configuration"]["config_files"]["Dockerfile"] = False
    generated, blockers = target_profiles.evaluate_target("docker", fullstack, "fixture")
    assert {item["path"] for item in generated} == {"Dockerfile"}
    assert blockers == []

    generated, blockers = target_profiles.evaluate_target("github-pages", inventory, "fixture")
    assert {item["path"] for item in generated} == {".github/workflows/deploy-pages.yml"}
    assert {item["code"] for item in blockers} == {"github_pages_workflow_required"}

    generated, blockers = target_profiles.evaluate_target("azure-static-web-apps", inventory, "fixture")
    assert {item["path"] for item in generated} == {"staticwebapp.config.json"}
    assert {item["code"] for item in blockers} == {"azure_static_config_required"}

    container_ready = minimal_target_inventory()
    container_ready["configuration"]["config_files"]["Dockerfile"] = True
    container_ready["configuration"]["config_files"]["nginx.conf"] = True
    generated, blockers = target_profiles.evaluate_target("render", container_ready, "fixture")
    assert {item["path"] for item in generated} == {"render.yaml"}
    assert blockers == []

    assert target_profiles.deployment_operation("gcp-cloud-run", "fixture")["kind"] == "reviewed-manual-operation"


def test_end_to_end_target_plans(root: Path) -> None:
    write(
        root / "package.json",
        json.dumps(
            {
                "name": "fixture-spa-targets",
                "scripts": {"build": "vite build"},
                "dependencies": {"react": "19", "vite": "8"},
            }
        ),
    )
    write(root / "package-lock.json", "{}")
    write(root / "src/main.tsx", "const url = import.meta.env.VITE_SUPABASE_URL;\n")
    write(root / "supabase/config.toml", "project_id = 'fixture'\n")
    write(root / "supabase/migrations/20260101000000_fixture.sql", "create table public.fixture(id uuid primary key);\n")
    write(root / "vercel.json", '{"rewrites":[{"source":"/(.*)","destination":"/index.html"}]}\n')
    write(root / "netlify.toml", '[build]\n  command = "npm run build"\n  publish = "dist"\n')
    write(root / "Dockerfile", "FROM scratch\n")
    write(root / "nginx.conf", "server { listen 8080; }\n")
    commit_fixture(root)
    inventory = inventory_repo.scan_repository(root)

    expected = {
        "vercel": ("vercel-deploy", True),
        "netlify": ("netlify-deploy", True),
        "aws-amplify": ("amplify-deploy", True),
        "docker": ("docker-build", False),
        "railway": ("railway-deploy", True),
    }
    for target, (step, external) in expected.items():
        plan = run_plan(root, inventory, target)
        assert plan["can_apply"] is True
        assert plan["target_details"]["id"] == target
        operation = plan["operations"][-1]
        assert operation["step"] == step
        assert operation["mutates_external_state"] is external

    guided = run_plan(root, inventory, "gcp-cloud-run")
    assert guided["can_apply"] is True
    assert guided["manual_operations"][-1]["step"] == "cloud-run-deploy"
    guided_path = root / ".porting/plan-gcp-cloud-run.json"
    dry_run = subprocess.run(
        [sys.executable, str(HERE / "apply_port_plan.py"), str(guided_path), "--repo", str(root)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "[MANUAL] cloud-run-deploy" in dry_run.stdout


def test_backend_registry() -> None:
    inventory = minimal_target_inventory()
    inventory["supabase"] = {"configured": False, "migration_count": 0, "edge_function_count": 0}
    inventory["portability"] = {"features": {}}
    assert backend_profiles.resolve_backend("auto", inventory) == "none"
    backend, operations, manual, blockers = backend_profiles.evaluate_backend("none", inventory, None, None)
    assert backend == "none" and not operations and not manual and not blockers

    inventory["supabase"]["configured"] = True
    inventory["supabase"]["migration_count"] = 1
    assert backend_profiles.resolve_backend("auto", inventory) == "supabase-managed"
    backend, operations, manual, blockers = backend_profiles.evaluate_backend(
        "auto", inventory, "abcdefghijklmnopqrst", None
    )
    assert backend == "supabase-managed"
    assert {item["step"] for item in operations} == {"supabase-link", "supabase-db-push"}
    assert not manual and not blockers

    backend, operations, manual, blockers = backend_profiles.evaluate_backend(
        "neon-postgres", inventory, "neon-target", "READY-1"
    )
    assert backend == "neon-postgres" and operations and not manual and not blockers

    backend, operations, manual, blockers = backend_profiles.evaluate_backend(
        "digitalocean-postgres", inventory, "digitalocean-postgres:db.example/app", "Verified encrypted target connection"
    )
    assert backend == "digitalocean-postgres" and operations and not manual and not blockers

    inventory["portability"]["features"]["supabase_auth"] = ["src/auth.ts"]
    _, _, _, blockers = backend_profiles.evaluate_backend(
        "neon-postgres", inventory, "neon-target", "READY-1"
    )
    assert "auth_adapter_required" in {item["code"] for item in blockers}


def run_clone_plan(root: Path, name: str, extra: list[str]) -> dict:
    out = root / f"{name}.json"
    command = [
        sys.executable,
        str(HERE / "make_database_clone_plan.py"),
        "--out",
        str(out),
        "--app-name",
        name,
        "--mode",
        "full-clone",
        "--source-project-ref",
        "sourcefixtureproject1",
        "--source-backup-id",
        "backup-2026-07-14",
        "--target-environment",
        "pre-production",
        "--target-organization",
        "fixture-org",
        "--source-data-classification",
        "synthetic",
        "--source-auth-users",
        "2",
        "--source-storage-objects",
        "3",
        "--classification-evidence",
        "CLASS-1",
        "--authorization-evidence",
        "APPROVAL-1",
        "--target-access-restricted",
        "--egress-extensions-reviewed",
        *extra,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(out.read_text(encoding="utf-8"))


def test_database_clone_plans(root: Path) -> None:
    managed = run_clone_plan(root, "managed-clone", [])
    assert managed["can_execute"] is True
    assert managed["release_allowed"] is False
    assert managed["target"]["backend"] == "supabase-managed"
    assert managed["scope"]["auth_records_included"] is True
    assert managed["scope"]["storage_object_binaries_included"] is False
    assert "storage_objects_not_copied" in {item["code"] for item in managed["warnings"]}
    assert "password" not in json.dumps(managed).lower()

    logical = run_clone_plan(
        root,
        "logical-clone",
        [
            "--method",
            "postgres-logical-restore",
            "--source-database-kind",
            "postgres",
            "--target-backend",
            "neon-postgres",
            "--target-backend-id",
            "neon-fixture",
            "--target-verified-empty",
        ],
    )
    assert logical["can_execute"] is True
    assert logical["target"]["backend_details"]["kind"] == "managed-postgres"

    sanitized = run_clone_plan(root, "sanitized-clone", ["--mode", "sanitized-clone"])
    assert sanitized["can_execute"] is False
    assert "sanitization_spec_required" in {item["code"] for item in sanitized["unresolved_blockers"]}

    special = run_clone_plan(
        root,
        "special-category-clone",
        ["--source-data-classification", "special-category-data"],
    )
    codes = {item["code"] for item in special["unresolved_blockers"]}
    assert {"security_review_required", "data_residency_review_required", "control_equivalence_required", "retention_required", "legal_basis_required"} <= codes


def main() -> int:
    test_target_registry()
    test_target_evaluation()
    test_backend_registry()
    test_railway_accepts_nitro_tanstack_without_dockerfile()
    with tempfile.TemporaryDirectory(prefix="port-lovable-blockers-") as tmp:
        test_blocker_detection(Path(tmp))
    with tempfile.TemporaryDirectory(prefix="port-lovable-lockfile-") as tmp:
        test_lockfile_package_names_are_not_secret_literals(Path(tmp))
    with tempfile.TemporaryDirectory(prefix="port-lovable-capabilities-") as tmp:
        test_supabase_capabilities_are_detected(Path(tmp))
    with tempfile.TemporaryDirectory(prefix="port-base44-capabilities-") as tmp:
        test_base44_backend_is_detected_and_safely_gated(Path(tmp))
    with tempfile.TemporaryDirectory(prefix="port-lovable-clean-") as tmp:
        test_clean_dry_run(Path(tmp))
    with tempfile.TemporaryDirectory(prefix="port-lovable-targets-") as tmp:
        test_end_to_end_target_plans(Path(tmp))
    with tempfile.TemporaryDirectory(prefix="port-lovable-clones-") as tmp:
        test_database_clone_plans(Path(tmp))
    print("All port-lovable-app tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
