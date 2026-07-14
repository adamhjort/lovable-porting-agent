# Database cloning

Database copying is a separate opt-in workflow. The normal deployment plan remains empty/schema-only and cannot silently copy existing rows.

## Modes

- `full-clone`: copy schema and rows from a pinned backup or restore point. Synthetic data requires accountable classification evidence. Personal data requires equivalent controls, security and residency review, a retention period, and explicit authorization.
- `sanitized-clone`: create the copy inside a quarantined target, apply an application-specific masking specification, validate it, and only then consider developer access. Until validation is signed off, the target must be treated exactly like the unsanitized source.

## Methods

- `supabase-managed-restore`: preferred for eligible Supabase-to-Supabase copies. Supabase Restore to a New Project creates a database-only copy containing schema, rows, roles, permissions, and Auth records. Storage object binaries, Edge Functions, Auth configuration/API keys, Realtime settings, and several project settings require separate work.
- `postgres-logical-restore`: use the current official source and target `pg_dump`/`pg_restore` procedure. Credentials must come from an approved secret channel; do not put passwords in plan JSON or retained command output.
- `provider-native-migration`: use an approved provider migration service with documented source connectivity, rollback, cutover, validation, and cost.

Generate a dry-run plan:

```text
python scripts/make_database_clone_plan.py \
  --out .porting/database-clone-plan.json \
  --app-name example-app \
  --mode full-clone \
  --method supabase-managed-restore \
  --source-database-kind supabase-postgres \
  --source-project-ref source-project-ref \
  --source-backup-id backup-or-restore-point \
  --target-backend supabase-managed \
  --target-environment pre-production \
  --target-organization approved-organization \
  --source-data-classification synthetic \
  --source-auth-users 12 \
  --source-storage-objects 0 \
  --classification-evidence TICKET-123 \
  --authorization-evidence APPROVAL-456 \
  --target-access-restricted \
  --egress-extensions-reviewed
```

The plan only becomes executable when its blockers are empty. It always starts with `release_allowed: false`; post-clone acceptance evidence is required before access is broadened.

Immediately disable or redirect copied `pg_net`, `pg_cron`, wrappers, webhooks, SMTP, queues, and third-party callbacks. Rotate target credentials and signing material. Never tear down or overwrite the source as part of cloning.

Current Supabase references: [Restore to a new project](https://supabase.com/docs/guides/platform/clone-project), [CLI backup and restore](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore), and [database backup limitations](https://supabase.com/docs/guides/platform/backups).
