# Deploy to Cloud Run

`make deploy PROJECT=<id>` runs `scripts/deploy.sh`: it refuses a dirty tree, uploads the folder,
builds the `Dockerfile` on Cloud Build, deploys service `hackathon-starter` in `europe-west1` with
the commit as a label, prints the URL and checks `/health`. One deploy owner per event runs it,
from `main`, after `main` is promoted.

State is one JSON object, `gs://<project>-state/store.json` (`DATA_PATH`, set by `deploy.sh`;
`STATE_BUCKET` names another bucket). It survives redeploys and restarts, and up to three instances
share it through compare-and-swap writes. The bucket keeps old versions of the object: list them with
`gcloud storage ls -a gs://<project>-state/store.json` and restore one with
`gcloud storage cp gs://<project>-state/store.json#<generation> gs://<project>-state/store.json`.

Effect tools are simulated in the cloud too, unless the service is given `EFFECTS=live`. On demo day,
deploy with `MIN_INSTANCES=1` so the first visitor never waits for a cold start; set it back to 0
afterwards (an idle instance is billed).

## One-time setup (per GCP project)

```bash
gcloud auth login
export PROJECT=<gcp-project-id>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com --project "$PROJECT"

# The two secrets the service reads. printf, not echo: no trailing newline in the value.
printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=- --project "$PROJECT"
printf '%s' '<admin password>' | gcloud secrets create admin-password --data-file=- --project "$PROJECT"

# Cloud Run runs as the default compute service account; let it read both secrets.
SA="$(gcloud projects describe "$PROJECT" --format 'value(projectNumber)')-compute@developer.gserviceaccount.com"
for s in anthropic-api-key admin-password; do
  gcloud secrets add-iam-policy-binding "$s" --project "$PROJECT" \
    --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor
done

# The store's bucket: private, versioned, writable by the service account.
gcloud storage buckets create "gs://$PROJECT-state" --project "$PROJECT" \
  --location europe-west1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update "gs://$PROJECT-state" --project "$PROJECT" --versioning
gcloud storage buckets add-iam-policy-binding "gs://$PROJECT-state" --project "$PROJECT" \
  --member "serviceAccount:$SA" --role roles/storage.objectUser
```

If the first deploy fails with a Cloud Build permission error, the same account also builds:

```bash
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member "serviceAccount:$SA" --role roles/run.builder
```

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
