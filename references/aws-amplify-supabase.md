# AWS Amplify Hosting + managed Supabase

## Use this profile

Use only when AWS placement is explicitly selected. This profile keeps Supabase and changes hosting; it does not translate Supabase into Cognito, S3, DynamoDB/RDS, Lambda, or AppSync.

Check current primary documentation:

- Amplify Hosting overview: <https://docs.aws.amazon.com/amplify/latest/userguide/welcome.html>
- SSR deployment specification: <https://docs.aws.amazon.com/amplify/latest/userguide/ssr-deployment-specification.html>
- Any-framework SSR adapters: <https://docs.aws.amazon.com/amplify/latest/userguide/server-side-rendering-amplify.html>
- Pull-request previews: <https://docs.aws.amazon.com/amplify/latest/userguide/pr-previews.html>

## Account boundary

Deploy pre-production apps in a dedicated sandbox/SDLC AWS account, not an existing production account by default. Require:

- owner and purpose tags;
- monthly budget and alerts;
- GitHub OIDC or approved short-lived credentials;
- least-privilege deployment and SSR compute roles;
- CloudWatch log retention;
- separate production promotion.

## Vite React SPA

Amplify can build `npm run build` and serve `dist`. Configure an SPA rewrite to `index.html`, Node 22, build-time `VITE_*` values, preview access control, and custom-domain redirects.

## TanStack Start

Amplify requires a framework adapter or post-build step that emits `.amplify-hosting/`:

- `static/` for public assets;
- `compute/default/` with a self-contained Node server;
- `deploy-manifest.json`;
- a Node entry point listening on port 3000.

Do not improvise the bundle during deployment. Add the adapter to the repository, build it in CI, and test the exact artifact locally. Observe Amplify compute limits and writable `/tmp` behavior.

## AWS-native replatforming boundary

Replacing Supabase is a separate architecture program because it changes:

- authentication and session semantics;
- Postgres functions, triggers, extensions, and RLS;
- storage policies and signed URLs;
- Realtime behavior;
- Edge Functions and service-role access;
- branch/preview lifecycle.

Require a separate decision, contract tests, data model, security review, and migration plan. Do not hide it inside a hosting port.
