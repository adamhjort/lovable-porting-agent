---
name: port-lovable-app
description: Inventory, remediate, and port Lovable-generated applications to independently operated infrastructure. Use for Lovable export or migration, portability assessment, pre-production recreation, optional approval-gated database cloning, removal of Lovable runtime dependencies, or repeatable deployment planning. Select hosting and backend independently across edge, static, serverless, container, Supabase, self-hosted, and common PostgreSQL targets. Works with Agent Skills clients including Codex and Claude Code. Never copy data implicitly, expose secrets, or tear down the source environment.
---

# Port Lovable App

## Outcome

Recreate a Lovable application from a pinned Git commit on independently controlled infrastructure. Select hosting and backend separately. Default to an empty or schema-only backend; copy existing database rows only through the separate, explicit clone workflow.

This is a model-neutral [Agent Skill](https://agentskills.io/specification). Read [agent-compatibility.md](references/agent-compatibility.md) when installation, invocation, tool names, or approval behavior depends on the current client.

## Non-negotiable controls

- Start read-only and produce a dry-run inventory.
- Pin a clean Git commit before any external deployment.
- Output secret names only. Never output, migrate, or commit secret values.
- Use aggregate metadata for classification; do not inspect row contents, identities, documents, recordings, or file names.
- Keep the normal deployment plan empty/schema-only. It must never copy database rows.
- Use [database-cloning.md](references/database-cloning.md) only when the user explicitly requests a copy and supplies the required human evidence.
- Treat a sanitized clone as fully sensitive until masking validation is signed off.
- Run external mutations only from a reviewed plan whose blockers are empty and after client-native approval.
- Never delete, disconnect, pause, overwrite, or tear down the source in this workflow.

Read [safety-and-evidence.md](references/safety-and-evidence.md) before any external mutation.

## Workflow

### 1. Establish the source

Prefer the Git repository as the code source. If only a Lovable project is available, use an available read-only connector to obtain its current commit and file inventory, then locate the synced repository.

Record repository, commit SHA, Lovable project id when available, owner, environment purpose, stated data classification, requested hosting, requested backend, and whether an existing-data copy was explicitly requested.

### 2. Run the local inventory

```text
python scripts/inventory_repo.py <repo> --out <repo>/.porting/inventory.json
```

The script detects application runtime, Supabase and Lovable dependencies, backend capability requirements, migrations, Edge Functions, API routes, target configuration, environment-variable names, unsafe background work, outbound database features, and likely committed secrets. It never emits a detected secret value.

Fix blockers and rerun. Do not acknowledge away a dirty worktree, committed secret candidate, hardcoded Lovable callback, or missing backend adapter.

### 3. Classify data and choose a transfer mode

Use the aggregate queries and evidence rules in [safety-and-evidence.md](references/safety-and-evidence.md).

- `test-only`: use the normal empty/schema-only path unless the user explicitly wants the synthetic rows copied.
- `contains-real-data`: the normal plan must stop; continue only through a separately authorized `full-clone` or `sanitized-clone` plan.
- `unknown`: stop before any external mutation.

Do not infer synthetic content from “development”, “test”, “pre-production”, or a project name.

### 4. Select hosting and backend independently

Hosting profiles:

- edge/static/serverless: read [hosting-edge-static.md](references/hosting-edge-static.md);
- containers and orchestrators: read [hosting-containers.md](references/hosting-containers.md).

Backend profiles:

- all choices and support levels: read [backend-profiles.md](references/backend-profiles.md);
- managed or self-hosted Supabase: read [backend-supabase.md](references/backend-supabase.md);
- Neon, AWS, Google Cloud, Azure, or generic PostgreSQL: read [backend-postgres.md](references/backend-postgres.md).

Use `--backend auto` when no backend constraint is stated. It resolves to `supabase-managed` only when the inventory detects Supabase/backend requirements; otherwise it resolves to `none`.

Do not describe guided profiles as fully automated. A plain PostgreSQL target does not replace Supabase Auth, Storage, Realtime, Edge Functions, or Data API behavior. Implement and test those adapters first.

### 5. Prepare an empty backend when no data copy is requested

For managed Supabase, provisioning remains dry-run by default:

```text
python scripts/provision_supabase.py \
  --name <name> \
  --organization-slug <organization> \
  --out <repo>/.porting/backend-target.json
```

Review the request, inject `SUPABASE_ACCESS_TOKEN` and `SUPABASE_DB_PASSWORD` through the process environment without printing them, then rerun with `--apply` and the exact confirmation token. For another backend, follow the selected profile's guided provisioning and attach non-secret readiness evidence.

### 6. Create a database clone plan only when requested

Read [database-cloning.md](references/database-cloning.md), then run `scripts/make_database_clone_plan.py`. Choose:

- `full-clone` for an authorized complete copy from an immutable restore point;
- `sanitized-clone` for a quarantined copy followed by a reviewed masking and validation specification.

Prefer provider-managed clone/restore when it preserves controls and avoids plaintext dumps. Use logical PostgreSQL restore or a provider migration service when required. Never place connection passwords in plan JSON, command arguments shown to the user, logs, or evidence.

The clone plan starts with `release_allowed: false`. After cloning, disable copied outbound integrations, rotate target credentials, reconfigure services not included in the database copy, validate RLS/Auth/counts, and obtain acceptance evidence before broadening access.

### 7. Remove portability blockers

Use the current agent's smallest safe patch mechanism. Typical work includes:

- replace hardcoded Lovable hosts with validated environment configuration;
- replace Lovable AI/email gateways with provider adapters or explicit test stubs;
- rotate literal secrets and move target values to an approved secret store;
- replace Supabase-specific client behavior when a non-Supabase backend is selected;
- preserve RLS and tenant isolation or replace them with an equivalent authorization layer;
- replace fire-and-forget work with platform-native durable execution;
- configure the current official hosting adapter;
- add deterministic synthetic seed data without personal information.

Do not rewrite production-used migrations destructively. Preserve an audit note for any sanitized pre-production migration chain.

### 8. Generate the deployment plan

```text
python scripts/make_port_plan.py <repo>/.porting/inventory.json \
  --out <repo>/.porting/plan.json \
  --app-name <name> \
  --hosting <hosting-profile> \
  --backend <backend-profile-or-auto> \
  --backend-target-id <non-secret-target-id> \
  --source-data-classification test-only \
  --source-auth-users <count> \
  --source-storage-objects <count> \
  --classification-evidence <reference>
```

For `none`, omit the backend target id. For guided or existing backends, add `--backend-readiness-evidence`. Review and commit generated target templates, rerun inventory, and regenerate until `can_apply` is true.

### 9. Review then apply

```text
python scripts/apply_port_plan.py <repo>/.porting/plan.json --repo <repo>
```

The dry run prints allowlisted command operations. Guided operations remain explicit manual steps. Before `--apply`, confirm the commit is unchanged and clean, the environment owner and budget exist, secrets are injected without logging, data handling matches the approved mode, and the client granted approval for network and external mutations.

```text
python scripts/apply_port_plan.py <repo>/.porting/plan.json \
  --repo <repo> \
  --apply \
  --confirm <token> \
  --evidence-out <repo>/.porting/apply-evidence.json
```

### 10. Verify and hand off

Run application tests and body-free smoke checks:

```text
python scripts/smoke_test.py https://<target-host> \
  --check /=200 \
  --out <repo>/.porting/smoke-evidence.json
```

Add tests for login/token refresh, tenant isolation, RLS or replacement authorization denial, private objects, server routes, callbacks, retries, disabled outbound integrations, redirects, and OAuth callbacks.

Deliver target URL and owners, source commit, hosting/backend profiles, deployment id, inventory and evidence, unresolved warnings, disabled integrations, clone scope and release decision when applicable, budget/alerts, retention deadline, rollback route to the still-running source, and an explicit statement that source teardown was not performed.

Persist material architectural findings according to the current knowledge workspace rules.
