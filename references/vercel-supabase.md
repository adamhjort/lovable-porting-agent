# Vercel + managed Supabase

## Use this profile

Use for Vite SPAs or TanStack Start applications when Vercel previews, Git integration, or the existing Nitro/Lovable adapter make it the lowest-change target. Keep Postgres, Auth, Storage, RLS, Realtime, and Edge Functions in managed Supabase.

Check current primary documentation before editing configuration:

- Vercel TanStack Start: <https://vercel.com/docs/frameworks/full-stack/tanstack-start>
- Vercel CLI deploy: <https://vercel.com/docs/cli/deploy>
- Vercel environments: <https://vercel.com/docs/deployments/environments>
- Supabase branching: <https://supabase.com/docs/guides/deployment/branching>

## Isolated pre-production project

Use a separate Vercel project and an empty Supabase project. Configure preview and production variables for this pre-production system without reusing production credentials. Connect a dedicated branch or repository when Git-based deploys are used.

The plan uses `vercel deploy --prod` only to promote within the isolated pre-production Vercel project. Do not link it to a real production domain.

## Vite React SPA

Build to `dist`. Add a `vercel.json` rewrite from `/(.*)` to `/index.html` so client-side routes do not return a platform 404. Validate direct navigation to representative nested routes.

## TanStack Start

Use the current Nitro Vite integration. Current Vercel documentation also supports zero-configuration Lovable projects using `@lovable.dev/vite-tanstack-config` version `2.6.2` or later. Treat an older or unparseable version as a blocker and verify the exact build locally before deployment.

## Provider boundary

Do not replace Supabase with Vercel-native data, auth, storage, or AI services as part of this profile. Provider substitution requires separate contracts, security review, and migration planning.
