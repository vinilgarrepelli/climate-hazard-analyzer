# Deploy Climate Lens manually on Vercel

Current public app: https://climate-lens-vinil.vercel.app
Source: https://github.com/vinilgarrepelli/climate-hazard-analyzer

## Deploy from GitHub

1. Sign in to https://vercel.com with your account.
2. Click **Add New → Project**, connect GitHub if necessary, and import **vinilgarrepelli/climate-hazard-analyzer**. If it is missing, grant the Vercel GitHub app access to this repository.
3. Use these settings before clicking Deploy:

| Setting | Value |
|---|---|
| Production branch | `main` |
| Framework preset | **FastAPI** |
| Root directory | Repository root; leave the field empty |
| Build command | `python scripts/build_frontend.py` |
| Output directory | Leave the preset default; do not override with `public` |
| Install command | Leave the preset default |
| Node.js version | `24.x` |

4. Under **Environment Variables**, add **`STORAGE_BACKEND` = `tinydb-seeded`**, with Production selected. Add Preview too if you want working preview deployments. The included real historical dataset works without Atlas credentials. Do not set the frontend preview variables for this deployment.
5. Click **Deploy**. Wait for **Ready**, then open the assigned `.vercel.app` production URL.
6. In **Project Settings → Deployment Protection → Vercel Authentication**, choose **Only Preview Deployments** and save. Production should be public. Open the production URL in an incognito window to confirm reviewers do not need your account.

The repository configures the Python entrypoint `backend.main:app`. Its build script runs `npm ci` and builds React into `public/`, which Vercel serves alongside the FastAPI function. You do not need separate frontend and backend projects.

## If you are updating the existing project

Open **climate-lens-vinil** in Vercel. Under **Settings → Environment Variables**, confirm `STORAGE_BACKEND=tinydb-seeded` is present for Production. Go to **Deployments**, select the latest production deployment, and click **Redeploy** after changing variables. If the project is connected to GitHub, pushing an updated `main` triggers a new build. If it is not connected, link the repository under **Settings → Git** first.

## Verify before submission

1. Open `/api/health` on your deployment. Expect `status: ok` and `database: tinydb-seeded`.
2. Open the dashboard. Hyderabad 1990–2025 should load without a login: about 61 events, 465 heatwave days, and a 39.3°C threshold for the bundled October 2026 data.
3. Choose **London, United Kingdom**, click **Run analysis**, and confirm the heading and results change.
4. Change the years to **2010–2025**, click **Run analysis**, and confirm the year range changes while the location's fixed threshold stays the same.
5. Open **Annual data**, export CSV, and open `/api/docs`.
6. Submit your GitHub repository URL and the public production URL. Follow [the interview demonstration guide](DEMO_GUIDE.md).

## Optional MongoDB Atlas upgrade

The included demo has an honest limitation: versioned historical documents survive restarts, but newly computed query caches are bounded worker memory. For durable shared writes:

1. In Atlas, create a database user with read/write access only to the project's database and configure network access suitable for the hosting environment.
2. Add the Atlas connection string as an **encrypted** Vercel `MONGODB_URI` variable. Add `MONGODB_DATABASE=climate_lens`.
3. Redeploy, then check `/api/health` reports `database: mongodb`.

A configured URI takes priority over `STORAGE_BACKEND`. Keep credentials in Vercel settings, never in React code or GitHub. Do not claim this upgrade is active until the health check succeeds.

## Common issues

| Symptom | Fix |
|---|---|
| Vercel asks reviewers to log in | Use the production alias and set Vercel Authentication to Only Preview Deployments |
| Health returns 503 | Confirm Production has `STORAGE_BACKEND=tinydb-seeded`, then redeploy; if using MongoDB, check its user/network configuration |
| Frontend loads but `/api/analyze` is missing | Select FastAPI and the repository root; keep the configured Python entrypoint |
| City selection changes but results stay the same | Click Run analysis; the app labels results as stale until a new analysis completes |
| An unbundled city returns an upstream error | Retry later or demonstrate Hyderabad/London; no synthetic data replaces unavailable weather |
| Settings changed but the app has not | Redeploy so the new environment settings reach the function |
