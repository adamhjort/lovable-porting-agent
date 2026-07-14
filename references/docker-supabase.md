# Portable OCI container + managed Supabase

## Use this profile

Use when portability matters more than a provider-specific serverless adapter. The output is a reviewed OCI image that can later run on Cloud Run, ECS/Fargate, Azure Container Apps, Fly.io, Render, Railway, Kubernetes, or another container platform.

Check current primary documentation before editing the image:

- Docker multi-stage builds: <https://docs.docker.com/build/building/multi-stage/>
- Docker build best practices: <https://docs.docker.com/build/building/best-practices/>

Also check the selected runtime provider's current container contract before deployment.

## Safety boundary

The bundled plan builds a local image only. It does not push to a registry or deploy to a platform. Registry push, platform creation, domain binding, and traffic promotion require a separate reviewed target operation.

Keep Supabase managed and empty for this pre-production workflow. Inject runtime configuration through the platform secret store; do not bake `.env` files or credentials into image layers.

## Vite React SPA

Use a multi-stage build: compile with Node, copy only `dist` into a small static runtime, and configure SPA fallback. Review and pin base images, run as a non-root user when the selected image supports it, expose the platform port, and add a health check where appropriate.

## TanStack Start

Do not generate a generic Dockerfile without confirming the current server build output. Create a multi-stage image that copies only the production server artifact and dependencies, listens on the platform-provided port, handles termination signals, writes only to permitted temporary storage, and runs without embedded secrets.

## Promotion

Tag the image with the source commit and retain its digest in the evidence package. Deploy that immutable digest to the selected provider and keep the Lovable source active as the rollback route until acceptance testing is complete.
