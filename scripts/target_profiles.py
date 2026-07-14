#!/usr/bin/env python3
"""Deployment target registry and target-specific plan evaluation."""

from __future__ import annotations

import re
from copy import deepcopy


DEFAULT_TARGET = "cloudflare-supabase"

TARGET_PROFILES: dict[str, dict] = {
    "cloudflare-supabase": {
        "label": "Cloudflare Workers + managed Supabase",
        "hosting": "cloudflare-workers",
        "backend": "managed-supabase",
        "reference": "references/cloudflare-supabase.md",
        "deploy_step": "cloudflare-deploy",
        "deploy_argv": ["npx", "wrangler", "deploy"],
        "deploys_external_state": True,
    },
    "vercel-supabase": {
        "label": "Vercel + managed Supabase",
        "hosting": "vercel",
        "backend": "managed-supabase",
        "reference": "references/vercel-supabase.md",
        "deploy_step": "vercel-deploy",
        "deploy_argv": ["npx", "vercel", "deploy", "--prod", "--yes"],
        "deploys_external_state": True,
    },
    "netlify-supabase": {
        "label": "Netlify + managed Supabase",
        "hosting": "netlify",
        "backend": "managed-supabase",
        "reference": "references/netlify-supabase.md",
        "deploy_step": "netlify-deploy",
        "deploy_argv": ["npx", "netlify", "deploy", "--prod"],
        "deploys_external_state": True,
    },
    "aws-amplify-supabase": {
        "label": "AWS Amplify Hosting + managed Supabase",
        "hosting": "aws-amplify",
        "backend": "managed-supabase",
        "reference": "references/aws-amplify-supabase.md",
        "deploy_step": "amplify-deploy",
        "deploy_argv": ["npx", "amplify", "publish", "--yes"],
        "deploys_external_state": True,
    },
    "docker-supabase": {
        "label": "Portable OCI container + managed Supabase",
        "hosting": "oci-container",
        "backend": "managed-supabase",
        "reference": "references/docker-supabase.md",
        "deploy_step": "docker-build",
        "deploy_argv": ["docker", "build", "--tag", "{name}:porting", "."],
        "deploys_external_state": False,
    },
}


def target_choices() -> tuple[str, ...]:
    return tuple(TARGET_PROFILES)


def target_metadata(target: str) -> dict:
    if target not in TARGET_PROFILES:
        raise KeyError(f"Unknown target profile: {target}")
    profile = TARGET_PROFILES[target]
    return {
        "id": target,
        "label": profile["label"],
        "hosting": profile["hosting"],
        "backend": profile["backend"],
        "reference": profile["reference"],
    }


def deployment_operation(target: str, target_name: str) -> dict:
    profile = TARGET_PROFILES[target]
    argv = [part.replace("{name}", target_name) for part in profile["deploy_argv"]]
    return {
        "step": profile["deploy_step"],
        "kind": "command",
        "argv": argv,
        "mutates_external_state": profile["deploys_external_state"],
        "requires_approval": profile["deploys_external_state"],
    }


def _config_exists(inventory: dict, name: str) -> bool:
    return bool(inventory["configuration"]["config_files"].get(name))


def _version_at_least(raw: str | None, minimum: tuple[int, int, int]) -> bool:
    if not raw:
        return False
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
    return bool(match and tuple(int(part) for part in match.groups()) >= minimum)


def _generated(path: str, purpose: str, content: dict | str) -> dict:
    return {"path": path, "purpose": purpose, "content": deepcopy(content)}


def _blocker(code: str, message: str) -> dict:
    return {"code": code, "severity": "blocking", "message": message}


def evaluate_target(target: str, inventory: dict, target_name: str) -> tuple[list[dict], list[dict]]:
    """Return generated templates and blockers for one target profile."""

    app = inventory["application"]
    runtime = app["runtime"]
    generated: list[dict] = []
    blockers: list[dict] = []

    if target == "cloudflare-supabase":
        if runtime == "static-spa" and not _config_exists(inventory, "wrangler.jsonc"):
            generated.append(
                _generated(
                    "wrangler.jsonc",
                    "Cloudflare Workers static assets with SPA fallback",
                    {
                        "$schema": "node_modules/wrangler/config-schema.json",
                        "name": target_name,
                        "compatibility_date": "SET_TO_CURRENT_DATE",
                        "assets": {
                            "directory": "./dist",
                            "not_found_handling": "single-page-application",
                        },
                    },
                )
            )
            blockers.append(_blocker("wrangler_config_required", "Review and commit the generated wrangler.jsonc template."))
        elif app["stack"] == "tanstack-start":
            if not app.get("uses_cloudflare_vite_plugin") or not _config_exists(inventory, "wrangler.jsonc"):
                blockers.append(
                    _blocker(
                        "cloudflare_tanstack_adapter_required",
                        "Configure the current official TanStack Cloudflare adapter and commit wrangler.jsonc.",
                    )
                )
        elif runtime != "static-spa":
            blockers.append(_blocker("unsupported_runtime", f"Unsupported runtime for Cloudflare profile: {runtime}"))

    elif target == "vercel-supabase":
        if runtime == "static-spa" and not _config_exists(inventory, "vercel.json"):
            generated.append(
                _generated(
                    "vercel.json",
                    "Vercel SPA fallback for client-side routes",
                    {"rewrites": [{"source": "/(.*)", "destination": "/index.html"}]},
                )
            )
            blockers.append(_blocker("vercel_config_required", "Review and commit the generated vercel.json template."))
        elif app["stack"] == "tanstack-start":
            lovable_ready = _version_at_least(app.get("lovable_tanstack_config_version"), (2, 6, 2))
            if not app.get("uses_nitro") and not lovable_ready:
                blockers.append(
                    _blocker(
                        "vercel_tanstack_adapter_required",
                        "Configure the current Nitro Vite adapter or verify @lovable.dev/vite-tanstack-config is at least 2.6.2.",
                    )
                )
        elif runtime != "static-spa":
            blockers.append(_blocker("unsupported_runtime", f"Unsupported runtime for Vercel profile: {runtime}"))

    elif target == "netlify-supabase":
        if runtime == "static-spa" and not _config_exists(inventory, "netlify.toml"):
            generated.append(
                _generated(
                    "netlify.toml",
                    "Netlify Vite build plus SPA fallback",
                    """[build]\n  command = \"npm run build\"\n  publish = \"dist\"\n\n[[redirects]]\n  from = \"/*\"\n  to = \"/index.html\"\n  status = 200\n""",
                )
            )
            blockers.append(_blocker("netlify_config_required", "Review and commit the generated netlify.toml template."))
        elif app["stack"] == "tanstack-start":
            if not app.get("uses_netlify_tanstack_plugin") or not _config_exists(inventory, "netlify.toml"):
                blockers.append(
                    _blocker(
                        "netlify_tanstack_adapter_required",
                        "Configure @netlify/vite-plugin-tanstack-start and commit netlify.toml using the current official output directory.",
                    )
                )
        elif runtime != "static-spa":
            blockers.append(_blocker("unsupported_runtime", f"Unsupported runtime for Netlify profile: {runtime}"))

    elif target == "aws-amplify-supabase":
        if runtime != "static-spa" and not _config_exists(inventory, "amplify.yml"):
            blockers.append(
                _blocker(
                    "amplify_ssr_adapter_required",
                    "Full-stack TanStack requires a reviewed Amplify deployment-spec adapter or post-build bundle.",
                )
            )

    elif target == "docker-supabase":
        if runtime == "static-spa":
            if not _config_exists(inventory, "Dockerfile"):
                generated.append(
                    _generated(
                        "Dockerfile",
                        "Portable multi-stage image for a Vite SPA",
                        """FROM node:22-alpine AS build\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci\nCOPY . .\nRUN npm run build\n\nFROM nginx:alpine\nCOPY --from=build /app/dist /usr/share/nginx/html\nCOPY nginx.conf /etc/nginx/conf.d/default.conf\nEXPOSE 8080\n""",
                    )
                )
                blockers.append(_blocker("dockerfile_required", "Review, harden, pin, and commit the generated Dockerfile template."))
            if not _config_exists(inventory, "nginx.conf"):
                generated.append(
                    _generated(
                        "nginx.conf",
                        "Container SPA fallback and port configuration",
                        """server {\n  listen 8080;\n  server_name _;\n  root /usr/share/nginx/html;\n  index index.html;\n\n  location / {\n    try_files $uri $uri/ /index.html;\n  }\n}\n""",
                    )
                )
                blockers.append(_blocker("container_spa_config_required", "Review and commit the generated nginx.conf template."))
        elif app["stack"] == "tanstack-start":
            if not _config_exists(inventory, "Dockerfile"):
                blockers.append(
                    _blocker(
                        "docker_fullstack_adapter_required",
                        "Add a reviewed multi-stage Dockerfile for the app's current TanStack server output and runtime port.",
                    )
                )
        else:
            blockers.append(_blocker("unsupported_runtime", f"Unsupported runtime for Docker profile: {runtime}"))

    return generated, blockers
