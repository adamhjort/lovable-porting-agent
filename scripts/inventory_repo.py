#!/usr/bin/env python3
"""Create a secret-safe portability inventory for a Lovable/GitHub repository."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = 1
SKIP_DIRS = {
    ".amplify",
    ".git",
    ".idea",
    ".netlify",
    ".next",
    ".output",
    ".turbo",
    ".vercel",
    ".wrangler",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
}
TEXT_SUFFIXES = {
    ".cjs",
    ".css",
    ".env",
    ".html",
    ".js",
    ".json",
    ".jsonc",
    ".jsx",
    ".md",
    ".mjs",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
MAX_TEXT_BYTES = 2 * 1024 * 1024

ENV_PATTERNS = (
    re.compile(r"Deno\.env\.get\(\s*['\"`]([A-Z][A-Z0-9_]*)['\"`]\s*\)"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"process\.env\[\s*['\"`]([A-Z][A-Z0-9_]*)['\"`]\s*\]"),
    re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(
        r"(?:getServerEnv|requireServerEnv|readEnv|env)\(\s*['\"`]([A-Z][A-Z0-9_]*)['\"`]"
    ),
)
URL_PATTERN = re.compile(r"https?://[^\s'\"`<>]+")
NODE_IMPORT_PATTERN = re.compile(
    r"(?:from\s*|import\s*\()\s*['\"`](node:[^'\"`]+)['\"`]"
)
EXTENSION_PATTERN = re.compile(
    r"create\s+extension(?:\s+if\s+not\s+exists)?\s+(?:\"([^\"]+)\"|([a-zA-Z0-9_]+))",
    re.IGNORECASE,
)
SECRET_KEY_PATTERN = re.compile(
    r"(?:SECRET|PASSWORD|PRIVATE(?:_KEY)?|SERVICE_ROLE|API_KEY|ACCESS_TOKEN|TOKEN|PEPPER|CERT_PEM|KEY_PEM)",
    re.IGNORECASE,
)
SECRET_TUPLE_PATTERN = re.compile(
    r"['\"]([A-Za-z0-9_.-]*(?:secret|password|private_key|service_role|api_key|access_token|token|pepper)[A-Za-z0-9_.-]*)['\"]"
    r"\s*[,=:]\s*['\"]([^'\"]{16,})['\"]",
    re.IGNORECASE,
)
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
AWS_KEY_PATTERN = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b")
PLACEHOLDER_PATTERN = re.compile(
    r"(?:placeholder|change[-_ ]?me|example|your[-_ ]|<[^>]+>|\$\{|process\.env|Deno\.env)",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?", default=".", help="Repository root")
    parser.add_argument("--out", help="Write JSON inventory to this path")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 when blocking findings exist",
    )
    return parser.parse_args()


def run_git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def sanitize_remote(value: str | None) -> str | None:
    if not value:
        return value
    try:
        parts = urlsplit(value)
        if parts.scheme in {"http", "https"} and parts.hostname:
            host = parts.hostname
            if parts.port:
                host += f":{parts.port}"
            return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    except ValueError:
        pass
    return value


def is_text_candidate(path: Path) -> bool:
    name = path.name.lower()
    return (
        path.suffix.lower() in TEXT_SUFFIXES
        or name.startswith(".env")
        or name in {"dockerfile", "procfile"}
    )


def iter_text_files(repo: Path):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in files:
            path = Path(root) / filename
            if not is_text_candidate(path):
                continue
            try:
                if path.stat().st_size > MAX_TEXT_BYTES:
                    continue
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            yield path.relative_to(repo).as_posix(), raw


def load_package(repo: Path) -> dict:
    path = repo / "package.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def classify_env_key(key: str) -> str:
    if key.startswith("VITE_") or key in {
        "SUPABASE_ANON_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
    }:
        return "public_build_config"
    if SECRET_KEY_PATTERN.search(key):
        return "secret"
    return "server_config"


def line_number(raw: str, offset: int) -> int:
    return raw.count("\n", 0, offset) + 1


def add_unique(items: list[dict], seen: set[tuple], value: dict, key: tuple) -> None:
    if key not in seen:
        seen.add(key)
        items.append(value)


def scan_repository(repo: Path) -> dict:
    package = load_package(repo)
    dependencies = {
        **(package.get("dependencies") or {}),
        **(package.get("devDependencies") or {}),
    }
    scripts = package.get("scripts") or {}

    env_keys: set[str] = set()
    node_imports: set[str] = set()
    extensions: set[str] = set()
    paths: list[str] = []
    migration_paths: list[str] = []
    edge_functions: set[str] = set()
    server_routes: list[str] = []
    hardcoded_hosts: list[dict] = []
    host_seen: set[tuple] = set()
    secret_candidates: list[dict] = []
    secret_seen: set[tuple] = set()
    feature_locations: dict[str, set[str]] = {
        "lovable_ai_gateway": set(),
        "lovable_email": set(),
        "deno_mtls": set(),
        "cron": set(),
        "pg_net": set(),
        "pgmq": set(),
        "vault": set(),
        "storage": set(),
        "supabase_auth": set(),
        "supabase_realtime": set(),
        "supabase_functions": set(),
        "supabase_data_api": set(),
        "fire_and_forget": set(),
    }

    for rel, raw in iter_text_files(repo):
        paths.append(rel)
        lower_rel = rel.lower()
        if re.match(r"^supabase/migrations/.+\.sql$", lower_rel):
            migration_paths.append(rel)
        match = re.match(r"^supabase/functions/([^/]+)/index\.(?:ts|js)$", lower_rel)
        if match:
            edge_functions.add(match.group(1))
        if re.match(r"^src/routes/api.*\.(?:ts|tsx)$", lower_rel):
            server_routes.append(rel)

        for pattern in ENV_PATTERNS:
            env_keys.update(pattern.findall(raw))

        if Path(rel).name.lower().startswith(".env"):
            for number, line in enumerate(raw.splitlines(), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'\"")
                if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                    env_keys.add(key)
                if SECRET_KEY_PATTERN.search(key) and value and not PLACEHOLDER_PATTERN.search(value):
                    add_unique(
                        secret_candidates,
                        secret_seen,
                        {"file": rel, "line": number, "kind": "secret_value_in_env_file", "key": key},
                        (rel, number, "secret_value_in_env_file", key),
                    )

        for match in NODE_IMPORT_PATTERN.finditer(raw):
            node_imports.add(match.group(1))

        for match in EXTENSION_PATTERN.finditer(raw):
            extensions.add((match.group(1) or match.group(2)).lower())

        for match in URL_PATTERN.finditer(raw):
            candidate = match.group(0).rstrip(".,);]}")
            try:
                host = (urlsplit(candidate).hostname or "").lower()
            except ValueError:
                continue
            if not host:
                continue
            category = None
            if host.endswith("lovable.app") or host.endswith("lovableproject.com"):
                category = "lovable_runtime_host"
            elif host.endswith("lovable.dev"):
                category = "lovable_managed_service"
            if category:
                number = line_number(raw, match.start())
                add_unique(
                    hardcoded_hosts,
                    host_seen,
                    {"file": rel, "line": number, "host": host, "category": category},
                    (rel, number, host, category),
                )

        scan_literal_tuples = Path(rel).name.lower() not in {
            "package.json", "package-lock.json", "npm-shrinkwrap.json",
            "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
        }
        for match in SECRET_TUPLE_PATTERN.finditer(raw) if scan_literal_tuples else ():
            key, value = match.group(1), match.group(2)
            if PLACEHOLDER_PATTERN.search(value):
                continue
            number = line_number(raw, match.start())
            add_unique(
                secret_candidates,
                secret_seen,
                {"file": rel, "line": number, "kind": "literal_secret_candidate", "key": key},
                (rel, number, "literal_secret_candidate", key),
            )
        for kind, pattern in (
            ("private_key", PRIVATE_KEY_PATTERN),
            ("aws_access_key", AWS_KEY_PATTERN),
            ("jwt_literal", JWT_PATTERN),
        ):
            for match in pattern.finditer(raw):
                number = line_number(raw, match.start())
                add_unique(
                    secret_candidates,
                    secret_seen,
                    {"file": rel, "line": number, "kind": kind},
                    (rel, number, kind),
                )

        feature_patterns = {
            "lovable_ai_gateway": r"ai\.gateway\.lovable\.dev|LOVABLE_API_KEY",
            "lovable_email": r"@lovable\.dev/email-js|LOVABLE_SEND_URL",
            "deno_mtls": r"Deno\.createHttpClient|createHttpClient\(",
            "cron": r"\bcron\.(?:schedule|unschedule|job)\b|pg_cron",
            "pg_net": r"\bnet\.http_|pg_net",
            "pgmq": r"\bpgmq\b",
            "vault": r"\bvault\.|supabase_vault",
            "storage": r"storage\.buckets|\.storage\.from\(",
            "supabase_auth": r"\bauth\.(?:users|identities|sessions)\b|\.auth\.(?:signIn|signUp|signOut|getSession|getUser|onAuthStateChange)",
            "supabase_realtime": r"\.channel\(|postgres_changes|\brealtime\.",
            "supabase_functions": r"\.functions\.invoke\(",
            "supabase_data_api": r"\.from\(['\"]|\.rpc\(['\"]",
            "fire_and_forget": r"\bvoid\s+(?:Promise\.|[A-Za-z_$][\w$]*\()",
        }
        for feature, pattern in feature_patterns.items():
            if re.search(pattern, raw, re.IGNORECASE):
                feature_locations[feature].add(rel)

    if "@tanstack/react-start" in dependencies:
        stack = "tanstack-start"
        runtime = "fullstack"
    elif "vite" in dependencies and "react" in dependencies:
        stack = "vite-react"
        runtime = "fullstack" if server_routes or any(".server." in p for p in paths) else "static-spa"
    elif package:
        stack = "node-unknown"
        runtime = "unknown"
    else:
        stack = "unknown"
        runtime = "unknown"

    lockfiles = [name for name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb") if (repo / name).exists()]
    config_files = {
        name: (repo / name).exists()
        for name in (
            "wrangler.jsonc",
            "wrangler.toml",
            "amplify.yml",
            "vercel.json",
            "netlify.toml",
            "Dockerfile",
            "nginx.conf",
            "staticwebapp.config.json",
            "swa-cli.config.json",
            "railway.json",
            "railway.toml",
            "render.yaml",
            "fly.toml",
            ".do/app.yaml",
            "k8s/deployment.yaml",
            "k8s/service.yaml",
            "supabase/config.toml",
        )
    }
    config_files["github-pages-workflow"] = any(
        (repo / ".github" / "workflows").glob("*pages*.y*ml")
    )

    commit = run_git(repo, "rev-parse", "HEAD")
    dirty_raw = run_git(repo, "status", "--porcelain")
    dirty_lines = dirty_raw.splitlines() if dirty_raw else []
    origin = sanitize_remote(run_git(repo, "remote", "get-url", "origin"))

    blockers: list[dict] = [
        {
            "code": "source_data_state_unknown",
            "severity": "blocking",
            "message": "Remote auth-user and storage-object counts must be classified before apply.",
        }
    ]
    if secret_candidates:
        blockers.append(
            {
                "code": "committed_secret_candidate",
                "severity": "critical",
                "message": "Potential committed secret literals must be removed and rotated.",
                "locations": secret_candidates,
            }
        )
    runtime_hosts = [item for item in hardcoded_hosts if item["category"] == "lovable_runtime_host"]
    if runtime_hosts:
        blockers.append(
            {
                "code": "hardcoded_lovable_runtime_host",
                "severity": "blocking",
                "message": "Runtime callbacks or links still point at a Lovable-hosted app.",
                "locations": runtime_hosts,
            }
        )
    if dirty_lines:
        blockers.append(
            {
                "code": "dirty_worktree",
                "severity": "blocking",
                "message": f"Git worktree contains {len(dirty_lines)} uncommitted path(s); apply must use a clean pinned commit.",
            }
        )

    warnings: list[dict] = []
    if not lockfiles:
        warnings.append({"code": "missing_lockfile", "message": "No supported package lockfile found."})
    if feature_locations["lovable_ai_gateway"]:
        warnings.append(
            {
                "code": "lovable_ai_dependency",
                "message": "AI runtime depends on Lovable-managed credentials or gateway.",
                "files": sorted(feature_locations["lovable_ai_gateway"]),
            }
        )
    if feature_locations["lovable_email"]:
        warnings.append(
            {
                "code": "lovable_email_dependency",
                "message": "Email runtime depends on a Lovable-managed service.",
                "files": sorted(feature_locations["lovable_email"]),
            }
        )
    if feature_locations["fire_and_forget"]:
        warnings.append(
            {
                "code": "background_work_in_request",
                "message": "Fire-and-forget work requires waitUntil, a queue, or a durable workflow in serverless runtimes.",
                "files": sorted(feature_locations["fire_and_forget"]),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": {
            "path": str(repo),
            "origin": origin,
            "commit": commit,
            "dirty": bool(dirty_lines),
            "dirty_path_count": len(dirty_lines),
        },
        "application": {
            "package_name": package.get("name"),
            "stack": stack,
            "runtime": runtime,
            "build_command": scripts.get("build"),
            "scripts": sorted(scripts),
            "lockfiles": lockfiles,
            "uses_lovable_tanstack_config": "@lovable.dev/vite-tanstack-config" in dependencies,
            "lovable_tanstack_config_version": dependencies.get("@lovable.dev/vite-tanstack-config"),
            "uses_cloudflare_vite_plugin": "@cloudflare/vite-plugin" in dependencies,
            "uses_netlify_tanstack_plugin": "@netlify/vite-plugin-tanstack-start" in dependencies,
            "uses_nitro": "nitro" in dependencies or "nitropack" in dependencies,
            "uses_wrangler": "wrangler" in dependencies,
            "uses_supabase_client": "@supabase/supabase-js" in dependencies,
        },
        "supabase": {
            "configured": config_files["supabase/config.toml"],
            "migration_count": len(migration_paths),
            "migrations": sorted(migration_paths),
            "edge_function_count": len(edge_functions),
            "edge_functions": sorted(edge_functions),
            "extensions": sorted(extensions),
        },
        "server": {
            "api_route_count": len(server_routes),
            "api_routes": sorted(server_routes),
            "node_imports": sorted(node_imports),
        },
        "configuration": {
            "env_keys": [
                {"name": key, "classification": classify_env_key(key)} for key in sorted(env_keys)
            ],
            "config_files": config_files,
        },
        "portability": {
            "hardcoded_lovable_hosts": hardcoded_hosts,
            "secret_candidates": secret_candidates,
            "features": {key: sorted(value) for key, value in feature_locations.items() if value},
            "blockers": blockers,
            "warnings": warnings,
        },
        "scan": {"text_file_count": len(paths)},
    }


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"Repository not found: {repo}", file=sys.stderr)
        return 1
    inventory = scan_repository(repo)
    payload = json.dumps(inventory, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = repo / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"Wrote secret-safe inventory: {out}")
    else:
        print(payload, end="")
    blocking = [x for x in inventory["portability"]["blockers"] if x["severity"] in {"blocking", "critical"}]
    if args.strict and blocking:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
