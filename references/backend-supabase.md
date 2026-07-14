# Supabase backend profiles

## Managed Supabase

Use `supabase-managed` when the application depends on the Supabase client, PostgREST/Data API, Auth, Storage, Realtime, Edge Functions, or Supabase-specific database behavior. It is the only directly automated backend profile in the current toolkit.

The normal port plan provisions or targets an empty project and applies versioned migrations. Existing-data copies use the separate [database cloning workflow](database-cloning.md).

Current official references:

- [CLI backup and restore](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)
- [Restore to a new project](https://supabase.com/docs/guides/platform/clone-project)
- [Database backups](https://supabase.com/docs/guides/platform/backups)
- [Migrating Auth users](https://supabase.com/docs/guides/troubleshooting/migrating-auth-users-between-projects)

## Self-hosted Supabase

Use `supabase-self-hosted` only with explicit operational ownership. Supabase documents Docker as the recommended self-hosting path, but the operator becomes responsible for hardening, upgrades, availability, backups, disaster recovery, monitoring, and capacity.

Platform-only features such as managed backups, PITR, branching, and the platform management API are not included in the self-hosted stack. Read the current [self-hosting overview](https://supabase.com/docs/guides/self-hosting) and [Docker guide](https://supabase.com/docs/guides/self-hosting/docker) before selecting it.

Do not reuse source signing keys, database passwords, service credentials, SMTP credentials, or integration secrets in either target.
