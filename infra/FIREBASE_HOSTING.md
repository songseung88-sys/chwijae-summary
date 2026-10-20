# Firebase Hosting → existing Cloud Run

The dashboard remains deployed to Cloud Run in the original Google Cloud project:
- Project: `chwijae-summary`
- Service: `chwijae-api` in `asia-northeast3`
- Existing backend URL: `https://chwijae-api-ejmdmrnztq-du.a.run.app/`
- Firebase Hosting address after initial setup: `https://chwijae-summary.web.app/`

`firebase.json` forwards all dynamic routes (including `/api/**`, `/admin`, `/about`, `/static/**`, and article metadata) to that existing service. No articles or settings are migrated. We intentionally omit `pinTag` so that new Cloud Run revisions continue to serve through Hosting without redeploying Hosting.

`.github/workflows/deploy-firebase-hosting.yml` deploys the Hosting configuration through the existing keyless GitHub Actions Google Cloud identity. The initial run attempts to register Firebase with this existing Google Cloud project and create its default Hosting site, but Google Cloud permissions or acceptance of Firebase Terms might require a one-time project-owner step. It must **not** make a separate Google Cloud project.

After purchasing `based-on-our-reporting.com`, connect it to this Firebase Hosting site in Firebase Console > Hosting > Add custom domain, then apply the exact DNS records Firebase supplies at the registrar. Do not change DNS before ownership verification. Once verified and HTTPS is ready, update the canonical URL, `og:url`, OG image URL and share rendering to point to the custom domain. Do not change these to an unowned domain.

The original Cloud Run address remains operational during setup and migration. The existing article collection jobs, Firestore data, admin passwords and APIs remain unchanged.
