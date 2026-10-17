# Deploy to Cloud Run

`make deploy PROJECT=<id>` runs `scripts/deploy.sh`: it refuses a dirty tree, uploads the folder,
builds the `Dockerfile` on Cloud Build, deploys service `hackathon-starter` in `europe-west1` with
the commit as a label, prints the URL and checks `/health`, then runs the tests marked `live`
against that URL (every GET below 500, a request without the token refused). One deploy owner per event runs it,
from `main`, after `main` is promoted.

State is one JSON object, `gs://<project>-state/store.json` (`DATA_PATH`, set by `deploy.sh`;
`STATE_BUCKET` names another bucket). It survives redeploys and restarts, and up to three instances
share it through compare-and-swap writes. The bucket keeps old versions of the object: list them with
`gcloud storage ls -a gs://<project>-state/store.json` and restore one with
`gcloud storage cp gs://<project>-state/store.json#<generation> gs://<project>-state/store.json`.

Effect tools are simulated in the cloud too, unless the service is given `EFFECTS=live`. On demo day,
deploy with `MIN_INSTANCES=1` so the first visitor never waits for a cold start; set it back to 0
afterwards (an idle instance is billed).

Every setting the service reads is listed in `.env.example` at its local default, and
`tests/test_env_example.py` fails when that list and `starter/runtime/config.py` drift apart. A new
setting that cloud needs goes in `deploy.sh` (`--set-env-vars`, or a secret) in the same change.
Real email and calls need `EFFECTS=live` plus the `RESEND_API_KEY`/`EMAIL_FROM` or `ELEVENLABS_*`
settings on the service (keys as secrets); without them a live send fails with 503, sending nothing.

## One-time setup (per GCP project)

```bash
gcloud auth login
PROJECT=<gcp-project-id> ANTHROPIC_API_KEY=<key> ADMIN_PASSWORD=<password> make bootstrap
```

`scripts/bootstrap.sh` enables the APIs, creates the Artifact Registry repository, the state bucket
(private, versioned), the secrets, and a `deployer` service account that `deploy.sh` impersonates
for every gcloud call; it grants the Cloud Run service account the bucket, the secrets and Cloud
Build. Each step describes first and creates only what is missing, so rerunning it is safe and
creates nothing. A secret's value is read only when the secret is created.

Whoever runs `deploy.sh` must be allowed to impersonate the deployer: you by default, or
`DEPLOY_AS=<service-account-email>` (the hub VM's account, when `hub live` deploys). Rerun with each
account that deploys. A grant that fails right after the deployer is created is IAM catching up;
rerun.

Rotate a secret with `gcloud secrets versions add <name> --data-file=-`, then redeploy.

## Which commit is live

```bash
gcloud run services describe hackathon-starter --region europe-west1 --project "$PROJECT" \
  --format 'value(metadata.labels.commit,status.latestReadyRevisionName)'
gcloud run revisions list --service hackathon-starter --region europe-west1 --project "$PROJECT" \
  --format 'table(metadata.name,metadata.labels.commit,status.conditions[0].status)'
```

## Rollback

```bash
gcloud run services update-traffic hackathon-starter --region europe-west1 --project "$PROJECT" \
  --to-revisions <previous-revision-name>=100
```

The next `make deploy` sends all traffic to the new revision again.
