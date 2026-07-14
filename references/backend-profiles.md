# Backend profiles

Hosting and backend are independent choices. Select `--backend auto` to keep the current behavior: applications with detected Supabase dependencies use `supabase-managed`; frontend-only applications use `none`.

| Profile | Capability level | Support | Notes |
| --- | --- | --- | --- |
| `none` | No backend | Direct | Only valid when inventory finds no backend dependency. |
| `existing-backend` | Application-defined API | Guided | Requires an owner, API contract, environment, and acceptance evidence. |
| `supabase-managed` | Postgres, Data API, Auth, Storage, Realtime, Functions, RLS | Direct | Lowest-remediation target for most Lovable applications. |
| `supabase-self-hosted` | Similar application services | Guided | Requires an operations, security, backup, and upgrade plan. |
| `neon-postgres` | Postgres and RLS | Guided | Supabase Auth, Storage, Realtime, Functions, and Data API need replacement adapters. |
| `aws-rds-postgres` | Postgres and RLS | Guided | Supports RDS or Aurora PostgreSQL; application services are separate. |
| `gcp-cloud-sql-postgres` | Postgres and RLS | Guided | Application services are separate. |
| `azure-postgres` | Postgres and RLS | Guided | Application services are separate. |
| `generic-postgres` | Postgres and RLS | Guided | Covers other managed or self-operated PostgreSQL targets. |

`direct` means the bundled runner has an allowlisted apply path after all blockers are resolved. `guided` means the agent produces compatibility blockers and reviewed manual operations; it must not claim that provider provisioning or cutover happened automatically.

Do not select `none` to silence backend work. The inventory must no longer detect database, Data API, Auth, Storage, Realtime, or Edge Function dependencies.
