# Edge, serverless, and static hosting

Backend selection is independent from every hosting profile.

| Profile | Supported shape | Apply path |
| --- | --- | --- |
| `cloudflare` | Static SPA or reviewed TanStack adapter | Direct via Wrangler |
| `vercel` | Static SPA or reviewed TanStack/Nitro adapter | Direct via Vercel CLI |
| `netlify` | Static SPA or reviewed TanStack adapter | Direct via Netlify CLI |
| `aws-amplify` | Static SPA; full-stack requires reviewed adapter | Direct via Amplify CLI |
| `github-pages` | Static output only | Guided GitHub Actions workflow |
| `azure-static-web-apps` | Static SPA in the current profile | Direct via SWA CLI |

Official platform references:

- [Cloudflare Workers static assets](https://developers.cloudflare.com/workers/static-assets/)
- [Vercel TanStack Start](https://vercel.com/docs/frameworks/full-stack/tanstack-start)
- [Netlify TanStack Start](https://docs.netlify.com/build/frameworks/framework-setup-guides/tanstack-start/)
- [AWS Amplify Hosting](https://docs.aws.amazon.com/amplify/latest/userguide/welcome.html)
- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [Azure Static Web Apps framework deployment](https://learn.microsoft.com/en-us/azure/static-web-apps/deploy-web-framework)

Review generated SPA fallbacks, preview behavior, custom domains, OAuth callbacks, environment-variable scope, build-time secrets, and regional/compliance constraints before apply.
