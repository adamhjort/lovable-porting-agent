#!/usr/bin/env python3
"""Hosting target registry and target-specific plan evaluation."""

from __future__ import annotations

import re
from copy import deepcopy


DEFAULT_TARGET = "cloudflare"

TARGET_PROFILES: dict[str, dict] = {
    "cloudflare": {
        "label": "Cloudflare Workers",
        "runtime": "edge-and-static",
        "support_level": "direct",
        "reference": "references/hosting-edge-static.md",
        "deploy_step": "cloudflare-deploy",
        "deploy_argv": ["npx", "wrangler", "deploy"],
        "deploys_external_state": True,
    },
    "vercel": {
        "label": "Vercel",
        "runtime": "serverless-and-static",
        "support_level": "direct",
        "reference": "references/hosting-edge-static.md",
        "deploy_step": "vercel-deploy",
        "deploy_argv": ["npx", "vercel", "deploy", "--prod", "--yes"],
        "deploys_external_state": True,
    },
    "netlify": {
        "label": "Netlify",
        "runtime": "serverless-and-static",
        "support_level": "direct",
        "reference": "references/hosting-edge-static.md",
        "deploy_step": "netlify-deploy",
        "deploy_argv": ["npx", "netlify", "deploy", "--prod"],
        "deploys_external_state": True,
    },
    "aws-amplify": {
        "label": "AWS Amplify Hosting",
        "runtime": "managed-web-hosting",
        "support_level": "direct",
        "reference": "references/hosting-edge-static.md",
        "deploy_step": "amplify-deploy",
        "deploy_argv": ["npx", "amplify", "publish", "--yes"],
        "deploys_external_state": True,
    },
    "docker": {
        "label": "Portable Docker or OCI image",
        "runtime": "container",
        "support_level": "direct-local-build",
        "reference": "references/hosting-containers.md",
        "deploy_step": "docker-build",
        "deploy_argv": ["docker", "build", "--tag", "{name}:porting", "."],
        "deploys_external_state": False,
    },
    "github-pages": {
        "label": "GitHub Pages",
        "runtime": "static",
        "support_level": "guided",
        "reference": "references/hosting-edge-static.md",
        "deploy_step": "github-pages-deploy",
        "manual_action": "Enable GitHub Pages with GitHub Actions and approve the generated deployment workflow.",
    },
    "azure-static-web-apps": {
        "label": "Azure Static Web Apps",
        "runtime": "static",
        "support_level": "direct",
        "reference": "references/hosting-edge-static.md",
        "deploy_step": "azure-static-web-apps-deploy",
        "deploy_argv": ["npx", "swa", "deploy", "--env", "production"],
        "deploys_external_state": True,
    },
    "gcp-cloud-run": {
        "label": "Google Cloud Run",
        "runtime": "container",
        "support_level": "guided",
        "reference": "references/hosting-containers.md",
        "deploy_step": "cloud-run-deploy",
        "manual_action": "Deploy the reviewed image or source with gcloud run deploy in the approved project and region.",
    },
    "aws-ecs-fargate": {
        "label": "AWS ECS with Fargate",
        "runtime": "container",
        "support_level": "guided",
        "reference": "references/hosting-containers.md",
        "deploy_step": "ecs-fargate-deploy",
        "manual_action": "Push the reviewed image to ECR and update the approved ECS task definition and Fargate service.",
    },
    "railway": {
        "label": "Railway",
        "runtime": "container-or-buildpack",
        "support_level": "direct",
        "reference": "references/hosting-containers.md",
        "deploy_step": "railway-deploy",
        "deploy_argv": ["npx", "@railway/cli", "up", "--detach"],
        "deploys_external_state": True,
    },
    "render": {
        "label": "Render",
        "runtime": "container-or-static",
        "support_level": "guided",
        "reference": "references/hosting-containers.md",
        "deploy_step": "render-deploy",
        "manual_action": "Apply the reviewed render.yaml Blueprint in the approved Render workspace.",
    },
    "fly-io": {
        "label": "Fly.io",
        "runtime": "container",
        "support_level": "direct",
        "reference": "references/hosting-containers.md",
        "deploy_step": "fly-deploy",
        "deploy_argv": ["fly", "deploy"],
        "deploys_external_state": True,
    },
    "kubernetes": {
        "label": "Kubernetes",
        "runtime": "container-orchestrator",
        "support_level": "guided",
        "reference": "references/hosting-containers.md",
        "deploy_step": "kubernetes-deploy",
        "manual_action": "Apply reviewed manifests through the organization's GitOps or cluster deployment workflow.",
    },
    "digitalocean-app-platform": {
        "label": "DigitalOcean App Platform",
        "runtime": "container-or-static",
        "support_level": "guided",
        "reference": "references/hosting-containers.md",
        "deploy_step": "digitalocean-app-deploy",
        "manual_action": "Apply the reviewed App Spec in the approved DigitalOcean project.",
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
        "runtime": profile["runtime"],
        "support_level": profile["support_level"],
        "reference": profile["reference"],
    }


def deployment_operation(target: str, target_name: str) -> dict:
    profile = TARGET_PROFILES[target]
    if "deploy_argv" not in profile:
        return {
            "step": profile["deploy_step"],
            "kind": "reviewed-manual-operation",
            "action": profile["manual_action"],
            "mutates_external_state": True,
            "requires_approval": True,
        }
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


def _container_readiness(inventory: dict) -> tuple[list[dict], list[dict]]:
    app = inventory["application"]
    runtime = app["runtime"]
    generated: list[dict] = []
    blockers: list[dict] = []
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
        blockers.append(_blocker("unsupported_runtime", f"Unsupported container runtime: {runtime}"))
    return generated, blockers


def evaluate_target(target: str, inventory: dict, target_name: str) -> tuple[list[dict], list[dict]]:
    """Return generated templates and blockers for one hosting profile."""

    app = inventory["application"]
    runtime = app["runtime"]
    generated: list[dict] = []
    blockers: list[dict] = []

    if target == "cloudflare":
        if runtime == "static-spa" and not _config_exists(inventory, "wrangler.jsonc"):
            generated.append(
                _generated(
                    "wrangler.jsonc",
                    "Cloudflare Workers static assets with SPA fallback",
                    {
                        "$schema": "node_modules/wrangler/config-schema.json",
                        "name": target_name,
                        "compatibility_date": "SET_TO_CURRENT_DATE",
                        "assets": {"directory": "./dist", "not_found_handling": "single-page-application"},
                    },
                )
            )
            blockers.append(_blocker("wrangler_config_required", "Review and commit the generated wrangler.jsonc template."))
        elif app["stack"] == "tanstack-start":
            if not app.get("uses_cloudflare_vite_plugin") or not _config_exists(inventory, "wrangler.jsonc"):
                blockers.append(_blocker("cloudflare_tanstack_adapter_required", "Configure the current official TanStack Cloudflare adapter and commit wrangler.jsonc."))
        elif runtime != "static-spa":
            blockers.append(_blocker("unsupported_runtime", f"Unsupported runtime for Cloudflare: {runtime}"))

    elif target == "vercel":
        if runtime == "static-spa" and not _config_exists(inventory, "vercel.json"):
            generated.append(_generated("vercel.json", "Vercel SPA fallback", {"rewrites": [{"source": "/(.*)", "destination": "/index.html"}]}))
            blockers.append(_blocker("vercel_config_required", "Review and commit the generated vercel.json template."))
        elif app["stack"] == "tanstack-start":
            lovable_ready = _version_at_least(app.get("lovable_tanstack_config_version"), (2, 6, 2))
            if not app.get("uses_nitro") and not lovable_ready:
                blockers.append(_blocker("vercel_tanstack_adapter_required", "Configure the current Nitro Vite adapter or verify the current Lovable TanStack adapter."))
        elif runtime != "static-spa":
            blockers.append(_blocker("unsupported_runtime", f"Unsupported runtime for Vercel: {runtime}"))

    elif target == "netlify":
        if runtime == "static-spa" and not _config_exists(inventory, "netlify.toml"):
            generated.append(_generated("netlify.toml", "Netlify Vite build plus SPA fallback", """[build]\n  command = \"npm run build\"\n  publish = \"dist\"\n\n[[redirects]]\n  from = \"/*\"\n  to = \"/index.html\"\n  status = 200\n"""))
            blockers.append(_blocker("netlify_config_required", "Review and commit the generated netlify.toml template."))
        elif app["stack"] == "tanstack-start":
            if not app.get("uses_netlify_tanstack_plugin") or not _config_exists(inventory, "netlify.toml"):
                blockers.append(_blocker("netlify_tanstack_adapter_required", "Configure the current Netlify TanStack adapter and commit netlify.toml."))
        elif runtime != "static-spa":
            blockers.append(_blocker("unsupported_runtime", f"Unsupported runtime for Netlify: {runtime}"))

    elif target == "aws-amplify":
        if runtime != "static-spa" and not _config_exists(inventory, "amplify.yml"):
            blockers.append(_blocker("amplify_ssr_adapter_required", "Full-stack TanStack requires a reviewed Amplify deployment adapter."))

    elif target == "github-pages":
        if runtime != "static-spa":
            blockers.append(_blocker("github_pages_static_only", "GitHub Pages supports static output only."))
        elif not _config_exists(inventory, "github-pages-workflow"):
            generated.append(
                _generated(
                    ".github/workflows/deploy-pages.yml",
                    "GitHub Pages build and deployment workflow",
                    """name: Deploy Pages\non:\n  push:\n    branches: [main]\n  workflow_dispatch:\npermissions:\n  contents: read\n  pages: write\n  id-token: write\nconcurrency:\n  group: pages\n  cancel-in-progress: true\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v6\n      - uses: actions/setup-node@v6\n        with:\n          node-version: 22\n          cache: npm\n      - run: npm ci\n      - run: npm run build\n      - uses: actions/configure-pages@v5\n      - uses: actions/upload-pages-artifact@v4\n        with:\n          path: dist\n  deploy:\n    needs: build\n    runs-on: ubuntu-latest\n    environment:\n      name: github-pages\n      url: ${{ steps.deployment.outputs.page_url }}\n    steps:\n      - id: deployment\n        uses: actions/deploy-pages@v4\n""",
                )
            )
            blockers.append(_blocker("github_pages_workflow_required", "Review the generated Pages workflow and the Vite base path, then enable Pages."))

    elif target == "azure-static-web-apps":
        if runtime != "static-spa":
            blockers.append(_blocker("azure_static_web_apps_static_only", "This profile currently supports static SPA output only."))
        elif not _config_exists(inventory, "staticwebapp.config.json"):
            generated.append(_generated("staticwebapp.config.json", "Azure SPA navigation fallback", {"navigationFallback": {"rewrite": "/index.html"}}))
            blockers.append(_blocker("azure_static_config_required", "Review and commit staticwebapp.config.json and the SWA CLI configuration."))

    elif target in {"docker", "gcp-cloud-run", "aws-ecs-fargate", "railway", "render", "fly-io", "kubernetes", "digitalocean-app-platform"}:
        railway_nitro_ready = (
            target == "railway"
            and app.get("stack") == "tanstack-start"
            and app.get("uses_nitro")
            and bool(app.get("build_command"))
        )
        if not railway_nitro_ready:
            container_generated, container_blockers = _container_readiness(inventory)
            generated.extend(container_generated)
            blockers.extend(container_blockers)
        if target == "render" and not _config_exists(inventory, "render.yaml"):
            generated.append(_generated("render.yaml", "Render Blueprint", f"""services:\n  - type: web\n    name: {target_name}\n    runtime: docker\n    dockerfilePath: ./Dockerfile\n    autoDeployTrigger: off\n"""))
            blockers.append(_blocker("render_blueprint_required", "Review and commit render.yaml."))
        elif target == "fly-io" and not _config_exists(inventory, "fly.toml"):
            blockers.append(_blocker("fly_config_required", "Run fly launch --no-deploy, review fly.toml, and commit it before deployment."))
        elif target == "kubernetes" and not (_config_exists(inventory, "k8s/deployment.yaml") and _config_exists(inventory, "k8s/service.yaml")):
            blockers.append(_blocker("kubernetes_manifests_required", "Add reviewed Deployment, Service, ingress, health checks, resource limits, and an immutable image digest."))
        elif target == "digitalocean-app-platform" and not _config_exists(inventory, ".do/app.yaml"):
            generated.append(_generated(".do/app.yaml", "DigitalOcean App Platform specification", f"""name: {target_name}\nservices:\n  - name: web\n    dockerfile_path: Dockerfile\n    http_port: 8080\n    instance_count: 1\n"""))
            blockers.append(_blocker("digitalocean_app_spec_required", "Review and commit the App Platform specification."))

    return generated, blockers
