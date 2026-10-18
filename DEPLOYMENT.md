# Deploying LearnLens on Google Cloud Run

LearnLens ships as **one container**: the FastAPI backend serves the API and the `frontend/` folder, so there is
one service, one URL and no CORS to configure. It keeps no database and no state, so it scales to zero when idle.

Expect about 15 minutes the first time. Firebase Hosting in front is optional (last section).

## Before you start

**Cloud Run needs a billing account, even to stay free.** Google's free allowance is applied to a billing account, and
Cloud Run will not deploy without one. See "Staying inside the free tier" below for how a demo costs about nothing.

- A Google Cloud project linked to a billing account (Cloud Run and Cloud Build need it, even within the free tier). A card is required to create one. If signup offers the $300 free trial, take it.
- The [gcloud CLI](https://cloud.google.com/sdk/docs/install). Check with `gcloud --version`.
- A Gemini API key from https://aistudio.google.com/apikey.
- Your terminal open in the repo root, the folder that contains `Dockerfile`, `backend/` and `frontend/`.

## 1. Set your variables

Replace the values, then keep this terminal open for the remaining steps.

```bash
export PROJECT_ID="your-project-id"
export REGION="us-central1"          # Iowa. Google works out the free allowance at this region's prices, so it goes furthest here.
export SERVICE="learnlens"
```

## 2. Sign in and pick the project

```bash
gcloud auth login
gcloud config set project "$PROJECT_ID"
```

## 3. Turn on the services

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com
```

## 4. Store the Gemini key in Secret Manager

The key never goes in the image, the repo or a command-line flag that shows up in logs.

```bash
# bash: type or paste the key (it is not shown), then press Enter.
# zsh (the macOS default): use   read -rs "?Gemini API key: " GEMINI_KEY; echo   instead.
read -rsp "Gemini API key: " GEMINI_KEY; echo

# printf avoids adding a trailing newline, which would make the key invalid.
printf '%s' "$GEMINI_KEY" | gcloud secrets create gemini-api-key --data-file=-
unset GEMINI_KEY

# Let the service read it. Cloud Run runs as the Compute Engine default account unless you set --service-account.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## 5. Deploy

```bash
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest" \
  --set-env-vars "GEMINI_MODEL=gemini-2.5-flash" \
  --memory 512Mi \
  --timeout 300 \
  --max-instances 3
```

What this does: uploads the folder (minus what `.gcloudignore` excludes), has Cloud Build build the `Dockerfile`,
stores the image in Artifact Registry, and starts the service. If gcloud asks to create an Artifact Registry
repository, answer `Y`. The first build takes a few minutes. At the end it prints the **Service URL**.

Flags worth knowing:

| Flag | Why |
|---|---|
| `--allow-unauthenticated` | Makes the site public. Needed for a demo link anyone can open. See "Cost and abuse" below. |
| `--max-instances 3` | Caps how many copies can run, which caps how fast the Gemini quota can be used up. |
| `--set-secrets` | Mounts the secret as the `GEMINI_API_KEY` environment variable the app already reads. |
| `--memory 512Mi` | Plenty for this app. |
| `--timeout 300` | Lets one request run for five minutes. Analyzing takes up to about a minute, but YouTube links that need Gemini to listen to the video can take several minutes. The app stops waiting on Gemini at 240 seconds and the browser at 270, so Cloud Run never cuts off a request the page is still waiting for. |

## 6. Check it works

```bash
URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
curl -s "$URL/api/health"
```

You should see `{"status":"ok","mode":"gemini","model":"gemini-2.5-flash"}`.

- `"mode":"mock"` means the key did not reach the app. Go to Troubleshooting.
- Open `$URL` in a browser, click **Load sample transcript**, then **Analyze transcript**. The status dot at the top
  right should say Gemini, and there should be no "offline demo" banner.
- Try a YouTube link in the link box, with a **public** video. The page says whether the text came from captions or from Gemini listening to the video. The Gemini route is the one that works from Cloud Run, so test it here at least once (a quick check: `curl -s -X POST "$URL/api/youtube" -H 'Content-Type: application/json' -d '{"url":"https://www.youtube.com/watch?v=VIDEO_ID"}'`).
- Click through every tab: Overview, Tutor, Concept map, Ask the video, Quiz. Take one quiz, then open the Tutor tab.

## Running the same container on your machine first (optional)

```bash
docker build -t learnlens .
docker run --rm -p 8080:8080 -e GEMINI_API_KEY="your-key" learnlens
# open http://localhost:8080
```

Leave out `-e GEMINI_API_KEY=...` to try offline demo mode.

## Day-to-day

| Task | Command |
|---|---|
| Ship a code change | Run the step 5 command again. Each deploy is a new revision. |
| Read logs | `gcloud run services logs read "$SERVICE" --region "$REGION" --limit 50` |
| List revisions | `gcloud run revisions list --service "$SERVICE" --region "$REGION"` |
| Roll back | `gcloud run services update-traffic "$SERVICE" --region "$REGION" --to-revisions REVISION_NAME=100` |
| Rotate the Gemini key | Read the new key into `NEW_KEY` as in step 4, run `printf '%s' "$NEW_KEY" \| gcloud secrets versions add gemini-api-key --data-file=-`, then redeploy so every instance starts with it |
| Take it down | `gcloud run services delete "$SERVICE" --region "$REGION"` and `gcloud secrets delete gemini-api-key` |

## Staying inside the free tier

Free allowance each month, shared across all projects on one billing account (Google's pricing pages):

| Product | Free each month |
|---|---|
| Cloud Run (request-based billing) | 2 million requests, 180,000 vCPU-seconds (about 50 hours of one busy CPU), 360,000 GiB-seconds, 1 GiB outbound data within North America |
| Cloud Build | 2,500 build-minutes |
| Secret Manager | 6 active secret versions (this app uses 1) |
| Artifact Registry | 0.5 GiB of storage, then about $0.10 per GiB-month |

This app scales to zero and is billed only while it handles a request, so a hackathon demo normally stays inside this.
To keep it that way:

1. Use `us-central1`, as in step 1. The allowance is worked out at that region's prices.
2. Do not add `--min-instances`. Idle instances are only billed when you set a minimum.
3. Keep `--max-instances 3` (or lower).
4. Create a budget with alerts (Billing → Budgets & alerts), for example for $1. **Budgets only email you. They do not stop spending.**
5. Deploy only a handful of times. Each deploy stores an image in Artifact Registry. After your last deploy, delete the old
   images (Console → Artifact Registry → `cloud-run-source-deploy`) to stay under 0.5 GiB.
6. When the event is over, delete the service and the secret (see "Day-to-day"), or unlink billing from the project.

What is not covered: Gemini usage is billed through your API key, not through this allowance, and anything beyond the
free amounts is charged at standard rates. On a free-trial account, overage comes out of the $300 credit.

## Cost and abuse: read this before sharing the link

The most expensive call is a YouTube link that needs Gemini to listen to the video: about 100 tokens per second of video, so an hour is roughly 360,000 tokens. The app allows two such transcriptions at a time per instance (`YOUTUBE_MAX_TRANSCRIPTIONS`), and `--max-instances` caps the rest.

`--allow-unauthenticated` means **anyone with the URL can call the API, and every call can spend your Gemini quota.**
LearnLens has no login and no rate limiting yet. For a hackathon demo that is usually acceptable if you:

1. Keep `--max-instances` low (as above).
2. Set a budget alert: Cloud Console → Billing → Budgets & alerts.
3. Check the quota and spend limits on the Gemini API key in Google AI Studio.
4. Delete the service when the event is over.

For a private demo, deploy with `--no-allow-unauthenticated` instead and open it yourself through a local proxy:
`gcloud run services proxy "$SERVICE" --region "$REGION"`, then visit http://localhost:8080.

Scale-to-zero means the first request after a quiet period waits a few seconds for a cold start. If that matters
during your presentation, add `--min-instances 1` to the deploy command. It costs money while idle, so remove it
afterwards.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `health` says `"mode":"mock"` | The secret is not mounted. Run `gcloud run services describe "$SERVICE" --region "$REGION"` and look for `GEMINI_API_KEY` under environment variables. Repeat step 4's IAM command, then redeploy. |
| Deploy fails with a permission error | Your account needs permission to deploy, build and use the service account. The project Owner role has all of it. Otherwise ask for Cloud Run Admin, Cloud Build Editor and Service Account User. |
| Deploy succeeds, URL returns 403 | Your organization blocks public services (a "domain restricted sharing" policy). Use the proxy method above, or ask an admin to allow it. |
| Analyze returns "Gemini request failed" | Quota exhausted, wrong key, or a model name your key cannot use. Check `gcloud run services logs read`, and try a different `GEMINI_MODEL` value with `gcloud run services update "$SERVICE" --region "$REGION" --set-env-vars GEMINI_MODEL=...`. |
| Page loads but shows "Backend not reachable" | You opened the frontend from somewhere other than the service URL. Use the URL from step 6. |
| YouTube link says "Gemini could not read this video" | The video must be public (not private or unlisted) and not too long. Check `gcloud run services logs read` for the underlying Gemini error (quota, model access). Pasting the transcript always works. |
| YouTube link is slow | Captions are blocked from Cloud Run, so Gemini is listening to the video. Expect a minute or two for a long video. Set `YOUTUBE_METHOD=gemini` to skip the caption attempt that will fail anyway. |
| Build cannot find `backend/requirements.txt` | You ran the command from the wrong folder. Run it from the repo root. |

## Optional: Firebase Hosting in front

Use this for a custom domain and CDN-served static files. It needs the project on Firebase's pay-as-you-go (Blaze) plan, because Firebase Hosting can only reach Cloud Run once a billing account is attached. Firebase's free Spark plan alone cannot do this. The app works fine without it, and the Cloud Run URL stays
the simplest option.

```bash
npm install -g firebase-tools
firebase login
firebase init hosting     # public directory: frontend | single-page app: No | do not overwrite index.html
```

Put this in `firebase.json`:

```json
{
  "hosting": {
    "public": "frontend",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
    "rewrites": [
      { "source": "/api/**", "run": { "serviceId": "learnlens", "region": "us-central1" } }
    ]
  }
}
```

Then `firebase deploy --only hosting`. The Firebase project must be the same Google Cloud project as the Cloud Run
service, and the `region` above must match `$REGION`. Requests to `/api/**` are forwarded to Cloud Run on the same
domain, so `frontend/config.js` needs no change.

**Check the timeout before relying on this.** Firebase Hosting applies its own, shorter request timeout to rewrites
to Cloud Run. I could not confirm the current value while writing this (I remember 60 seconds), so check the
[Firebase Hosting and Cloud Run documentation](https://firebase.google.com/docs/hosting/cloud-run). Analyzing a long
transcript can take about a minute, and a YouTube link that needs Gemini to listen to the video can take several, so
these may fail through Hosting while working on the direct Cloud Run URL.
