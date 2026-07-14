#!/usr/bin/env python3
"""Self-contained tests for the safe inventory and dry-run plan path."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import apply_port_plan
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


def run_plan(root: Path, inventory: dict, target: str, name: str = "Fixture App") -> dict:
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
            "--target",
            target,
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
    assert target_profiles.DEFAULT_TARGET == "cloudflare-supabase"
    assert set(target_profiles.target_choices()) == {
        "cloudflare-supabase",
        "vercel-supabase",
        "netlify-supabase",
        "aws-amplify-supabase",
        "docker-supabase",
    }
    skill_root = HERE.parent
    for target in target_profiles.target_choices():
        metadata = target_profiles.target_metadata(target)
        assert (skill_root / metadata["reference"]).is_file()
        operation = target_profiles.deployment_operation(target, "fixture-app")
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
        },
        "configuration": {
            "config_files": {
                "wrangler.jsonc": False,
                "amplify.yml": False,
                "vercel.json": False,
                "netlify.toml": False,
                "Dockerfile": False,
                "nginx.conf": False,
            }
        },
    }


def test_target_evaluation() -> None:
    inventory = minimal_target_inventory()
    generated, blockers = target_profiles.evaluate_target("vercel-supabase", inventory, "fixture")
    assert {item["path"] for item in generated} == {"vercel.json"}
    assert {item["code"] for item in blockers} == {"vercel_config_required"}

    generated, blockers = target_profiles.evaluate_target("netlify-supabase", inventory, "fixture")
    assert {item["path"] for item in generated} == {"netlify.toml"}
    assert {item["code"] for item in blockers} == {"netlify_config_required"}

    generated, blockers = target_profiles.evaluate_target("docker-supabase", inventory, "fixture")
    assert {item["path"] for item in generated} == {"Dockerfile", "nginx.conf"}
    assert {item["code"] for item in blockers} == {"dockerfile_required", "container_spa_config_required"}

    fullstack = minimal_target_inventory(runtime="fullstack", stack="tanstack-start")
    fullstack["application"]["uses_nitro"] = True
    assert target_profiles.evaluate_target("vercel-supabase", fullstack, "fixture") == ([], [])

    fullstack["application"]["uses_nitro"] = False
    fullstack["application"]["lovable_tanstack_config_version"] = "^2.6.2"
    assert target_profiles.evaluate_target("vercel-supabase", fullstack, "fixture") == ([], [])
    fullstack["application"]["lovable_tanstack_config_version"] = "2.5.9"
    assert target_profiles.evaluate_target("vercel-supabase", fullstack, "fixture")[1][0]["code"] == "vercel_tanstack_adapter_required"

    fullstack["application"]["uses_netlify_tanstack_plugin"] = True
    fullstack["configuration"]["config_files"]["netlify.toml"] = True
    assert target_profiles.evaluate_target("netlify-supabase", fullstack, "fixture") == ([], [])

    fullstack["configuration"]["config_files"]["Dockerfile"] = True
    assert target_profiles.evaluate_target("docker-supabase", fullstack, "fixture") == ([], [])


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
        "vercel-supabase": ("vercel-deploy", True),
        "netlify-supabase": ("netlify-deploy", True),
        "aws-amplify-supabase": ("amplify-deploy", True),
        "docker-supabase": ("docker-build", False),
    }
    for target, (step, external) in expected.items():
        plan = run_plan(root, inventory, target)
        assert plan["can_apply"] is True
        assert plan["target_details"]["id"] == target
        operation = plan["operations"][-1]
        assert operation["step"] == step
        assert operation["mutates_external_state"] is external


def main() -> int:
    test_target_registry()
    test_target_evaluation()
    with tempfile.TemporaryDirectory(prefix="port-lovable-blockers-") as tmp:
        test_blocker_detection(Path(tmp))
    with tempfile.TemporaryDirectory(prefix="port-lovable-clean-") as tmp:
        test_clean_dry_run(Path(tmp))
    with tempfile.TemporaryDirectory(prefix="port-lovable-targets-") as tmp:
        test_end_to_end_target_plans(Path(tmp))
    print("All port-lovable-app tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
