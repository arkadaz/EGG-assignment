# Deploy, step by step

There are two places to run the project:

| Where | How |
|---|---|
| Your computer | Docker Compose, with one command |
| GCP | Terraform, run by GitHub Actions when you click Deploy |

## Locally: one command

```bash
docker compose up --build
```

Then open http://localhost:8000. Compose builds the three images and starts db, migrate, ingest
and search in that order. Locally there is no Terraform and no GitHub Actions.

Before the first run, you need `.env` and the model in `models/`. The
[README](README.md#run-locally) shows both.

## On GCP

This part sets up GCP and GitHub from nothing, so that GitHub Actions can deploy the project with
one click and remove it with another. Steps 1 to 8 run once per GCP project. After that, you only
use the two buttons in step 9.

There are two kinds of setup:

| What | Made by | Why |
|---|---|---|
| APIs, state bucket, model bucket with the model, image registry, deployer account, GitHub sign-in, LLM key, Google sign-in client | you, once: `gcloud` in steps 1 to 6, the Console in step 7 | Terraform needs some of them before it can run. Deploy pushes the images to the registry before Terraform starts. The model and the LLM key are data that only you upload. Google has no API for creating the sign-in client. Destroy keeps all of them. |
| Cloud SQL, Cloud Run, `database-url` secret, app accounts, and each deploy of new images | Terraform, from `infrastructure/`, run by GitHub Actions | These are what Deploy creates and Destroy removes. |

### What you need

- A GCP project with billing turned on
- The `gcloud` CLI, signed in as an owner of that project (`gcloud auth login`)
- This code in a GitHub repository
- An OpenRouter API key, if you want the real LLM

You do not need Terraform on your computer; GitHub Actions runs it. The commands below are for
bash (Git Bash on Windows).

### 1. Set the names once

```bash
PROJECT=egg-interview
REGION=asia-southeast1
REPO=arkadaz/EGG-assignment
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
DEPLOYER=egg-rag-deployer@$PROJECT.iam.gserviceaccount.com
gcloud config set project $PROJECT
```

Use your own project ID and `owner/repository`. The project number is a second ID that Google
gives every project; the GitHub sign-in in step 5 needs it.

### 2. Turn on the APIs

```bash
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com \
  storage.googleapis.com
```

Every GCP product is off until you turn it on for the project. `sts` and `iamcredentials` are the
ones that let GitHub sign in without a key.

### 3. Create the buckets and the image registry

```bash
gcloud storage buckets create gs://$PROJECT-tfstate --location=$REGION \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://$PROJECT-tfstate --versioning
```

Terraform keeps a state file: the list of everything it has created. Kept in a bucket, it gives
every Deploy and Destroy run the same state, and Terraform locks it so two runs cannot change it
at once. Versioning keeps the old copies in case one gets broken. The state holds the database
password, which is why public access is blocked.

If the bucket name is taken (bucket names are global), pick another and put it in
`infrastructure/main.tf` under `backend "gcs"`.

Then create a second bucket for the embedding model and upload the model to it once:

```bash
gcloud storage buckets create gs://$PROJECT-models --location=$REGION \
  --uniform-bucket-level-access --public-access-prevention

uvx --from huggingface_hub huggingface-cli download onnx-community/embeddinggemma-300m-ONNX \
  config.json special_tokens_map.json tokenizer.json tokenizer_config.json \
  onnx/model.onnx onnx/model.onnx_data \
  --revision 5090578d9565bb06545b4552f76e6bc2c93e4a66 --local-dir models/embeddinggemma-300m

gcloud storage cp -r models/embeddinggemma-300m gs://$PROJECT-models/
```

The model is 1.2 GB. Here is why it lives in a bucket rather than in the images:

- **In the images,** every build would download it again and every deploy would push it again.
- **In the bucket,** it is uploaded once. Cloud Run mounts the bucket read-only at `/models`, so
  ingest and search read the files from it directly, and nothing downloads the model on a
  build, a deploy or a start.
- **Outside Terraform,** the bucket is kept by Destroy, like the state bucket, so the model never
  has to be uploaded again.

If you use a different bucket name, put it in `infrastructure/variables.tf` as `models_bucket`.

Last, create the registry for the Docker images:

```bash
gcloud artifacts repositories create egg-rag --repository-format=docker --location=$REGION
```

Deploy builds the images and pushes them here first, then runs Terraform with their tag. The
registry has to exist before that first push, so it is one-time setup and Destroy keeps it.

### 4. Create the deployer account

```bash
gcloud iam service-accounts create egg-rag-deployer --display-name="GitHub Actions deployer"

for ROLE in roles/run.admin roles/cloudsql.admin roles/artifactregistry.writer \
  roles/secretmanager.admin roles/iam.serviceAccountAdmin roles/iam.serviceAccountUser \
  roles/resourcemanager.projectIamAdmin; do
  gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$DEPLOYER \
    --role=$ROLE --condition=None
done

gcloud storage buckets add-iam-policy-binding gs://$PROJECT-tfstate \
  --member=serviceAccount:$DEPLOYER --role=roles/storage.objectAdmin

gcloud storage buckets add-iam-policy-binding gs://$PROJECT-models \
  --member=serviceAccount:$DEPLOYER --role=roles/storage.admin
```

GitHub Actions runs as this account. It pushes the images, which needs
`artifactregistry.writer`. Then Terraform creates Cloud SQL, Cloud Run, secrets, accounts and their
permissions, so it needs one role for each of those. The last two commands are for the buckets:

- **State bucket:** the deployer can read and write the state file.
- **Models bucket:** the deployer can give the app accounts read access to the model.

### 5. Let GitHub sign in as the deployer

```bash
gcloud iam workload-identity-pools create github --location=global

gcloud iam workload-identity-pools providers create-oidc github \
  --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition="assertion.repository=='$REPO' && assertion.ref=='refs/heads/main'"

gcloud iam service-accounts add-iam-policy-binding $DEPLOYER \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"
```

This is Workload Identity Federation. It works in three steps:

1. Each workflow run gets a short-lived token from GitHub, signed by GitHub, that says "I am
   repository X, running from branch Y".
2. GCP checks the signature and the condition: only your repository, and only `main`.
3. If both pass, the run can act as the deployer for one hour.

No password or key is stored anywhere, so there is nothing to leak or rotate. This is why the
repository needs no secrets in its GitHub settings.

Do not delete this pool to start over. Google keeps a deleted pool for 30 days, and its name
cannot be used again during that time.

### 6. Store the LLM key

```bash
gcloud secrets create llm-api --replication-policy=automatic
gcloud secrets versions add llm-api --data-file=-
```

The second command waits for input: paste the OpenRouter key, press Enter, then Ctrl+D.

The deploy expects this key. To deploy without one, skip this step and delete these from
`infrastructure/`:

- the `LLM_API` env block in `cloud_run.tf`, and the `search_llm_api` line in that service's
  `depends_on`
- `search_llm_api` in `service_accounts.tf`
- the `llm_api` data source in `secrets.tf`

Search then uses the mock LLM and the agent is off. Any text in the secret counts as a key, so do
not store a placeholder.

### 7. Create the Google sign-in client

Every page and API call needs a Google login, and only emails in the `users` table can sign in.
The migrate job adds `allowed_email` (from `infrastructure/variables.tf`) to that table as the
first user. The login works in four steps:

1. The **Sign in with Google** button on `/login` gives the page a JWT, signed by Google, that
   says which account signed in.
2. The page sends that JWT to `/auth/google`.
3. The service checks Google's signature, that the JWT is for your client ID, that it has not
   expired, that the email is verified, and that the email is in the `users` table.
4. If all of that passes, the JWT becomes a cookie that every later request is checked against.

The button needs a client ID from your project. Google has no API or Terraform for this, so you
make it in the Console:

1. Open **Google Auth Platform** in the Console
   (`https://console.cloud.google.com/auth/overview?project=<your project>`) and click
   **Get started**.
2. Fill in the app details:
   - **App information:** the app name `EGG RAG`, and your email as the support email
   - **Audience:** **External**
   - **Contact information:** your email
3. Accept the policy and click **Create**.
4. Go to **Audience** → **Test users** → **Add users**, add every email that will sign in, and
   save. While the app is in Testing mode, only test users can sign in at all. That is a second
   lock on top of the `users` table.
5. Go to **Clients** → **Create client**:
   - **Application type:** Web application
   - **Name:** `egg-rag-search`
   - **Authorized JavaScript origins:** add these three
     - `https://egg-rag-search-<project number>.<region>.run.app`. Cloud Run gives the service
       this address, so you know it before the first deploy. Print it with
       `echo https://egg-rag-search-$PROJECT_NUMBER.$REGION.run.app`.
     - `http://localhost`
     - `http://localhost:8000`
   - **Redirect URIs:** leave them empty. The button hands the JWT straight to the page.
6. Click **Create**, then copy the **Client ID**. It ends in `.apps.googleusercontent.com`. You do
   not need the client secret.

Put the client ID in two places:

- **For GCP:** in `infrastructure/variables.tf`, as the default of `google_client_id`
- **For local runs:** in `.env`, as `GOOGLE_CLIENT_ID`

### 8. Point the code at your project

If you used a different project, region or repository, change these places, then commit and
push:

| File | What to change |
|---|---|
| `infrastructure/variables.tf` | `project_id`, `region`, `allowed_email` and `google_client_id` |
| `infrastructure/main.tf` | the state bucket name |
| `.github/workflows/deploy.yml` | `REGION`, `REGISTRY`, `WORKLOAD_IDENTITY_PROVIDER` (it contains the project number) and `SERVICE_ACCOUNT` |
| `.github/workflows/destroy.yml` | `WORKLOAD_IDENTITY_PROVIDER` and `SERVICE_ACCOUNT` |

Print the provider name to copy into the workflows:

```bash
echo projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github
```

### 9. Deploy and destroy with a click

**Deploy:** on GitHub, open the repository, then **Actions** → **Deploy** → **Run workflow** →
branch `main` → **Run workflow**. Two jobs run, one after the other:

| Job | What it does | Time |
|---|---|---|
| `images` | builds the migrate, ingest and search images at the same time and pushes them, tagged with the commit | about 3 minutes |
| `terraform` | `terraform apply -var image_tag=<commit>`, which deploys those images | about 5 minutes, plus 10 to 15 the first time, while it creates Cloud SQL |

`terraform apply` does everything in this order, and each step waits for the one before it:

1. Creates or updates the infrastructure.
2. Points the migrate job at the new image and runs it. Terraform waits until the run has
   finished.
3. Does the same for the ingest job.
4. Points the search service at the new image. Cloud Run moves the traffic once the new revision
   has started.

Terraform runs each job once per commit. Running Deploy again on the same commit changes nothing.

Then open `https://egg-rag-search-<project number>.<region>.run.app/docs`:

1. It sends you to the login page. Sign in with Google.
2. You land back on `/docs`, the API. Use "Try it out" there.
3. The first request after an idle period takes a few extra seconds while an instance starts.

To let someone else sign in, add their email to the `users` table and add them as a test user
(step 7). On GCP, open **Cloud SQL** → the `egg-rag-…` instance → **Cloud SQL Studio**, sign in
to the `rag` database as `rag` (the password is in the `database-url` secret), and run:

```sql
INSERT INTO users (email) VALUES ('friend@example.com');
```

It works on their next request, with no restart. `DELETE FROM users WHERE email = '...'` locks
them out the same way.

Every request is logged as one JSON line. Find them in **Cloud Run** → `egg-rag-search` →
**Logs**, and filter by `jsonPayload.user`, `jsonPayload.path` or `jsonPayload.status`.

Cloud Run also gives the service an older, random-looking address. Google sign-in refuses it,
because it is not in the client's JavaScript origins, so always use the one with the project
number.

To call the API from curl, copy the `google_id_token` cookie from the browser after you sign in:

```bash
curl -X POST <url>/ask -H "Content-Type: application/json" \
  -b "google_id_token=<the cookie value>" \
  -d '{"question": "Who created Kubernetes?"}'
```

**Destroy:** **Actions** → **Destroy** → **Run workflow**. It removes everything Terraform made:

- Cloud SQL and its data
- Cloud Run
- the `database-url` secret
- the app accounts

What stays is the setup from steps 2 to 7, including the registry with the images, which costs
almost nothing. The next Deploy builds
everything again with a new database name (a random suffix), because Google blocks a deleted
Cloud SQL name for about a week.

### When something fails

- **Look at the failed step on GitHub first.** It prints the `gcloud` or Terraform error.
- **A `Permission denied` error names the missing permission.** Grant the deployer the matching
  role from step 4.
- **If the migrate or ingest run fails,** `terraform apply` stops with an error, and search keeps
  its old image. Its logs are in Cloud Run → Jobs → the job → the failed execution → Logs.
  - migrate prints one line per migration file.
  - ingest prints how many documents and chunks were new or skipped.

  Fix the cause and push. The new commit gets a new tag, so the next Deploy runs both jobs again.
- **If the search service does not start,** look at its logs. The usual causes are a missing
  `llm-api` secret version, or a database without tables because migrate did not run.
