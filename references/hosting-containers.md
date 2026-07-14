# Container hosting

The container profiles use a reviewed Dockerfile or OCI image as the portability boundary. A generated Dockerfile is a starting template, not a production-hardening claim.

| Profile | Apply path |
| --- | --- |
| `docker` | Direct local image build; no registry push |
| `gcp-cloud-run` | Guided Cloud Run deployment |
| `aws-ecs-fargate` | Guided ECR, task-definition, and service update |
| `railway` | Direct Railway CLI deployment |
| `render` | Guided `render.yaml` Blueprint |
| `fly-io` | Direct after reviewed `fly.toml` |
| `kubernetes` | Guided organization-owned GitOps or cluster workflow |
| `digitalocean-app-platform` | Guided App Spec deployment |

Official platform references:

- [Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Google Cloud Run source deployment](https://cloud.google.com/run/docs/deploying-source-code)
- [Amazon ECS container images](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/create-container-image.html)
- [Railway CLI deployment](https://docs.railway.com/cli/up)
- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Fly.io deployment](https://fly.io/docs/launch/deploy/)
- [Kubernetes workload management](https://kubernetes.io/docs/concepts/workloads/controllers/)
- [DigitalOcean App Platform](https://docs.digitalocean.com/products/app-platform/details/features/)

Before external deployment, pin base images and the deployed image digest, run as non-root when supported, define health checks and graceful shutdown, set CPU/memory limits, keep secrets outside the image, restrict egress, and configure logs, alerts, scaling, rollback, and regional placement.
