# PostgreSQL backend profiles

The Neon, AWS, Google Cloud, Azure, and generic profiles migrate PostgreSQL capabilities only. A Lovable application that still calls Supabase Auth, Storage, Realtime, Edge Functions, or the Supabase Data API is not ready for these targets.

The inventory creates one blocker per missing capability. Resolve each blocker with an explicit adapter and contract tests, then rerun the inventory. Typical replacements include:

- an application-owned API instead of direct PostgREST calls from the browser;
- an OIDC/Auth provider plus an authorization model that preserves tenant isolation;
- object storage with signed URLs and equivalent access policy;
- a realtime transport and reconnect/authorization behavior;
- a functions or jobs runtime with idempotency, retry, and secret separation.

Supported guided database destinations:

- [Neon Postgres migration guides](https://neon.com/docs/import/migrate-intro)
- [AWS RDS PostgreSQL import](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Procedural.Importing.EC2.html)
- [Google Cloud SQL PostgreSQL import/export](https://cloud.google.com/sql/docs/postgres/import-export/import-export-sql)
- [Azure Database for PostgreSQL dump and restore](https://learn.microsoft.com/en-us/azure/postgresql/migrate/how-to-migrate-using-dump-and-restore)

Use `generic-postgres` for another PostgreSQL-compatible service and verify supported extensions, roles, networking, TLS, connection pooling, backups, PITR, maintenance, and data residency against that provider's current documentation.

Never retain an unencrypted database dump in the repository, agent workspace, logs, or evidence package.
