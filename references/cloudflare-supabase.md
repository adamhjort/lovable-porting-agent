# Cloudflare Workers + managed Supabase

## Use this profile

Use for the smallest architectural change from Lovable Cloud. Keep Postgres, Auth, Storage, RLS, Realtime, and Edge Functions in managed Supabase; run the app on Cloudflare Workers.

Check current primary documentation before editing configuration:

- Cloudflare static assets: <https://developers.cloudflare.com/workers/static-assets/>
- Cloudflare Node compatibility: <https://developers.cloudflare.com/workers/runtime-apis/nodejs/>
- TanStack Start hosting: <https://tanstack.com/start/latest/docs/framework/react/guide/hosting>
- Supabase CLI: <https://supabase.com/docs/reference/cli/supabase-projects-create>
- Supabase branching: <https://supabase.com/docs/guides/deployment/branching>

## Empty Supabase target

Use an isolated organization/project with an owner and budget. Prefer an interactive password prompt or an approved secret-injection mechanism; never print a database password.

The bundled `provision_supabase.py` uses the official Management API, reads its PAT and database password from `SUPABASE_ACCESS_TOKEN` and `SUPABASE_DB_PASSWORD`, and defaults to dry-run. Verify the current Management API contract before `--apply` because provider schemas can change.

Current CLI flow:

```text
supabase projects create <name> --org-id <org> --region <region> --size micro
supabase link --project-ref <ref>
supabase config push --project-ref <ref>
supabase db push --include-all --yes
supabase functions deploy --project-ref <ref>
```

Use only the commands applicable to the repository. Configure secrets separately. Validate that migrations create required extensions, buckets, policies, cron jobs, and queues without source-specific URLs or secrets.

For pull requests, use data-less Supabase preview branches. Do not pass `--with-data` for this workflow.

## Vite React SPA

Use Workers Static Assets with SPA fallback:

```json
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "app-name",
  "compatibility_date": "CURRENT_DATE",
  "assets": {
    "directory": "./dist",
    "not_found_handling": "single-page-application"
  }
}
```

Build with Node 22 unless the repository proves another supported version. Inject `VITE_*` variables at build time.

## TanStack Start

Do not assume a Lovable build wrapper is portable merely because it mentions Cloudflare. Move to the current official TanStack setup:

- `@cloudflare/vite-plugin` in `vite.config.ts`;
- `tanstackStart()` and the React Vite plugin;
- `wrangler.jsonc` with `main: "@tanstack/react-start/server-entry"`;
- current compatibility date;
- `nodejs_compat` when Node APIs or dependencies require it;
- `deploy` script that builds and runs `wrangler deploy`.

Build-test all Node imports. Cloudflare supports many Node APIs under `nodejs_compat`, but some modules remain partial or shimmed.

## Durable work

Do not rely on untracked promises after returning an HTTP response. Use:

- `ctx.waitUntil` for short, best-effort completion tied to the request;
- Queues for delivery, retry, and backpressure;
- Workflows for multi-step durable orchestration;
- Supabase cron/pgmq only when ownership and observability are explicit.

Telephony, document signing, email delivery, and AI jobs require idempotency keys, bounded retries, dead-letter handling, and traceable status.

## Provider exits

Replace direct Lovable gateway calls with a narrow provider interface. Keep prompts, schemas, model choice, cost logging, and safety decisions outside the provider client. Replace Lovable email helpers with the approved provider and preserve suppression, unsubscribe, retry, and audit behavior.
