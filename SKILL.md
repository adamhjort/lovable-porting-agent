---
name: port-lovable-app
description: Inventory, remediate, and port Lovable-generated GitHub applications to independently operated pre-production hosting with an empty managed Supabase backend. Use for Lovable export or migration, external deployment, portability reviews, Supabase schema and function recreation, removal of Lovable runtime dependencies, or repeatable porting pipelines. Supports Vite React SPAs and TanStack Start across Cloudflare Workers, Vercel, Netlify, AWS Amplify, and portable Docker or OCI targets. Works with Agent Skills clients including Codex and Claude Code. Never use this workflow to copy real user data or tear down the source environment.
---

# Port Lovable App

## Outcome

Recreate a Lovable app from a pinned Git commit on independently controlled infrastructure. Preserve code, schema, RLS, functions, and synthetic seed data. Do not copy users, table contents, storage objects, passwords, or secret values.

Follow the open Agent Skills format. Read [agent-compatibility.md](references/agent-compatibility.md) when installation, invocation, tool names, or approval behavior depends on the current agent client.

## Non-negotiable controls

- Start read-only and produce a dry-run inventory.
- Pin a clean Git commit before any external deployment.
- Output secret names only. Never output, migrate, or commit secret values.
- Query only aggregate source metadata for the data gate. Never inspect care records, applications, recordings, documents, or other row contents.
- Require explicit `test-only` classification. Non-zero auth or storage counts require a human evidence reference.
- Create a new empty backend. Never point a port at an existing production project.
- Run external mutations only from a reviewed plan with `can_apply: true`.
- Never delete, disconnect, pause, or overwrite the Lovable source in this workflow. Teardown is a separate user-approved task.

Read [safety-and-evidence.md](references/safety-and-evidence.md) before any external mutation.

## Workflow

### 1. Establish the source

Prefer the GitHub repository as the deployment source. If only a Lovable project is available, use an available read-only Lovable connector to obtain its current commit and file inventory, then locate or request the synced repository.

Record the repository, commit SHA, Lovable project id when available, app owner, environment purpose, stated data classification, and target profile. Do not modify the Lovable project while inventorying it.

### 2. Run the local inventory

Run:

```text
python scripts/inventory_repo.py <repo> --out <repo>/.porting/inventory.json
```

The script detects stack, runtime, migrations, Edge Functions, API routes, environment-variable names, Node imports, Lovable runtime hosts, managed Lovable services, migration extensions, fire-and-forget work, and likely committed secrets. It never emits a detected secret value.

Review every blocker. Fix code or configuration and rerun the inventory; do not acknowledge away committed secrets, hardcoded Lovable callback hosts, or a dirty worktree.

### 3. Complete the remote data gate

When a Lovable/Supabase read tool is available, run only the aggregate queries in [safety-and-evidence.md](references/safety-and-evidence.md). Otherwise ask the environment owner for the same counts.

Classify the source as one of:

- `test-only`: continue with empty recreation;
- `contains-real-data`: stop; this skill is not a data-migration workflow;
- `unknown`: stop before apply.

Do not treat “pre-production” as evidence that all data is synthetic.

### 4. Select and prepare the target

Choose the profile with the smallest verified remediation surface:

- `cloudflare-supabase`: read [cloudflare-supabase.md](references/cloudflare-supabase.md); prefer for static SPAs or an existing Cloudflare adapter.
- `vercel-supabase`: read [vercel-supabase.md](references/vercel-supabase.md); prefer for an existing Nitro/Vercel adapter or Vercel preview workflow.
- `netlify-supabase`: read [netlify-supabase.md](references/netlify-supabase.md); prefer for an existing Netlify adapter or Netlify preview workflow.
- `aws-amplify-supabase`: read [aws-amplify-supabase.md](references/aws-amplify-supabase.md); use for an explicit AWS placement requirement.
- `docker-supabase`: read [docker-supabase.md](references/docker-supabase.md); use when a portable OCI artifact is the primary requirement.

If no adapter exists, default to Cloudflare for a static SPA. For TanStack Start, compare the current official Cloudflare, Vercel, and Netlify adapters and choose the one requiring the least code change unless the user states a platform constraint. Keep Supabase unless the user separately authorizes backend replatforming.

The supported profiles and deploy operations live in `scripts/target_profiles.py`. Add future targets there and in a directly linked reference file without weakening the shared safety gate.

Create the target in an isolated pre-production account/organization with a budget and owner. Keep one Supabase project per app. Use data-less preview branches for pull requests when needed.

Provisioning is dry-run by default:

```text
python scripts/provision_supabase.py \
  --name <name> \
  --organization-slug <organization> \
  --out <repo>/.porting/supabase-target.json
```

Review the request, place `SUPABASE_ACCESS_TOKEN` and `SUPABASE_DB_PASSWORD` in the process environment without printing them, then rerun with `--apply` and the exact confirmation token. The script writes only the new project ref and other non-secret metadata. If the current Supabase API differs from the bundled reference, stop and update the script against current official documentation.

### 5. Remove portability blockers

Use the current agent's smallest safe patch or file-editing mechanism. Typical remediations are:

- replace hardcoded `*.lovable.app` callback hosts with validated environment configuration;
- replace Lovable AI and email gateways with provider adapters or explicit disabled/test stubs;
- rotate any literal secret found in migrations and move its value to a target secret store;
- replace `project_id` and callback URLs with target configuration;
- convert background work to `waitUntil`, a queue, or a durable workflow;
- make the build use the current official target adapter;
- retain RLS and service-role separation;
- add deterministic synthetic seed data without personal information.

Do not rewrite historical migrations destructively after they have been used in production. For these pre-production ports, sanitize the target migration chain on a new branch and preserve an audit note explaining the change.

### 6. Generate the port plan

Run with read-only source counts and an existing empty target project ref:

```text
python scripts/make_port_plan.py <repo>/.porting/inventory.json \
  --out <repo>/.porting/plan.json \
  --app-name <name> \
  --target <supported-profile> \
  --target-project-ref <empty-project-ref> \
  --source-data-classification test-only \
  --source-auth-users <count> \
  --source-storage-objects <count> \
  --classification-evidence <reference>
```

On PowerShell, place each argument on one line or use the PowerShell continuation character. Do not put secret values in the command.

If the plan returns generated file templates, review and commit them, rerun inventory, and regenerate the plan. Continue only when `can_apply` is `true`.

### 7. Review then apply

Print the exact operation list without executing it:

```text
python scripts/apply_port_plan.py <repo>/.porting/plan.json --repo <repo>
```

Before `--apply`, confirm the commit is still current and clean, the target is empty and pre-production, secrets are configured without logging values, billing guardrails exist, and the current agent client has granted approval for network access and external mutations.

Apply with the exact confirmation token from the plan and write redacted evidence:

```text
python scripts/apply_port_plan.py <repo>/.porting/plan.json \
  --repo <repo> \
  --apply \
  --confirm <token> \
  --evidence-out <repo>/.porting/apply-evidence.json
```

The runner allowlists package and target commands and rejects destructive tokens. The Docker profile builds a local image only. No profile provisions or deletes the source project.

### 8. Verify

Run the application-specific test suite plus body-free HTTP checks:

```text
python scripts/smoke_test.py https://<target-host> \
  --check /=200 \
  --check /api/public/v1/healthz=200 \
  --out <repo>/.porting/smoke-evidence.json
```

Use only routes that exist. Add separate tests for login and token refresh, tenant isolation, representative RLS denial, private storage signed URLs, server routes, callback signatures, idempotency, the AI test stub/provider, cron/queue retry behavior, redirects, and OAuth callbacks.

### 9. Hand off

Deliver:

- target URL and environment owner;
- source commit and target deployment id;
- inventory, plan, apply evidence, and smoke evidence;
- unresolved warnings and disabled integrations;
- monthly budget/alert configuration;
- rollback route to the still-running Lovable source;
- an explicit statement that source teardown was not performed.

When operating inside a durable knowledge workspace, persist material architectural findings according to that workspace's rules. Record a formal decision only after the user accepts the target architecture.
