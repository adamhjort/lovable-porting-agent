# Netlify + managed Supabase

## Use this profile

Use for Vite SPAs or TanStack Start applications when the repository already uses Netlify, needs Netlify deploy previews, or benefits from the official TanStack Start adapter. Keep Postgres, Auth, Storage, RLS, Realtime, and Edge Functions in managed Supabase.

Check current primary documentation before editing configuration:

- Netlify TanStack Start: <https://docs.netlify.com/build/frameworks/framework-setup-guides/tanstack-start/>
- Netlify CLI: <https://docs.netlify.com/api-and-cli-guides/cli-guides/get-started-with-cli/>
- Netlify SPA redirects: <https://docs.netlify.com/resources/troubleshooting/page-not-found-error-guide/>
- Supabase branching: <https://supabase.com/docs/guides/deployment/branching>

## Isolated pre-production project

Use a separate Netlify project and an empty Supabase project. Configure variables in the appropriate deploy context and keep real production credentials and domains out of the project.

The plan uses `netlify deploy --prod` only for the primary URL of the isolated pre-production project.

## Vite React SPA

Build to `dist`. Configure `netlify.toml` with the build command and publish directory. Add a rewrite from `/*` to `/index.html` with status `200`, then test direct navigation to nested client routes.

## TanStack Start

Use `@netlify/vite-plugin-tanstack-start` with the current official output directory in `netlify.toml`. Netlify's documented configuration varies for older TanStack Start versions; detect the installed version and follow the matching current documentation instead of copying a stale adapter.

## Provider boundary

Do not replace Supabase with Netlify-native data, auth, storage, or AI services inside this hosting profile. Treat that as a separate replatforming decision.
