# Safety and evidence

## Source metadata gate

Use read-only aggregate queries. Do not select row contents, file names, identities, emails, transcripts, documents, or care data.

```sql
select count(*)::bigint as auth_user_count from auth.users;
```

```sql
select bucket_id, count(*)::bigint as object_count
from storage.objects
group by bucket_id
order by bucket_id;
```

Optional schema evidence:

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
order by tablename;
```

```sql
select count(*)::bigint as policy_count
from pg_policies
where schemaname = 'public';
```

## Classification rule

`test-only` requires an accountable human reference. Examples:

- named product owner attestation with date;
- test-environment ticket;
- documented synthetic seed source.

If auth or storage counts are non-zero, record the counts and the attestation reference in the port plan. Never infer synthetic content from a project name or environment label.

The normal deployment plan is always empty/schema-only. When the user explicitly requests an existing-data copy, stop that plan and use [database-cloning.md](database-cloning.md). A clone requires a separate authorization reference and immutable restore point.

Personal data additionally requires security, data-residency, control-equivalence, access-restriction, and retention evidence. Special-category data also requires a documented legal-basis reference. A sanitized target remains regulated and quarantined until the masking validation is signed off.

## Secret rule

- Inventory names only.
- Treat committed secret candidates as compromised.
- Rotate them before deployment.
- Store target values in Supabase secrets, Cloudflare secrets, AWS Secrets Manager, or the approved organizational equivalent.
- Never place secret values in Git, plan JSON, evidence JSON, command arguments shown to the user, or tool output.
- Public Supabase publishable/anon keys are configuration; service-role keys are secrets.

## Mutation rule

The deployment plan may create an empty target, apply schema, configure a target, and deploy code when the user requested a port/deployment. It may not copy rows, delete, or modify the source.

A separate clone plan may copy a pinned database restore point after its blockers are empty and the external copy operation receives explicit approval. It may not copy Storage object binaries implicitly, reuse source secrets, broaden target access before acceptance, or delete the source. Destructive target recovery also requires a new explicit approval.

## Evidence package

Retain:

- source repository and commit;
- inventory and blocker resolution;
- source auth/storage counts and classification reference;
- target project/worker identifiers without credentials;
- migration and function deployment results;
- build, test, and smoke results;
- runtime warnings and intentionally disabled integrations;
- cost budget and alert owner;
- rollback URL.

For database clones, also retain the immutable restore point, data classification, authorization, target control evidence, aggregate validation results, disabled outbound integrations, release decision, retention owner, and cleanup deadline. Never retain row contents or an unencrypted dump in the evidence package.

Store evidence under `.porting/` or the workspace output area. Ensure `.porting/` evidence containing environment identifiers follows repository policy before committing it.

## Separate teardown

Only consider teardown after acceptance testing and a retention window. Re-run the aggregate gate, confirm ownership, export any required audit evidence, and ask separately for deletion approval. Do not add teardown commands to the port plan.
