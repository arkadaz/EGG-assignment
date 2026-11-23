# Deploy to GCP, step by step

This guide sets up GCP and GitHub from nothing, so that GitHub Actions can deploy the project with
one click and remove it with another. Steps 1 to 8 run once per GCP project. After that, you only
use the two buttons in step 9.

There are two kinds of setup:

| What | Made by | Why |
|---|---|---|
| APIs, state bucket, deployer account, GitHub sign-in, LLM key, Google sign-in client | you, once: `gcloud` in steps 1 to 6, the Console in step 7 | Terraform needs them before it can run, the LLM key is something only you have, and Google has no API for creating the sign-in client. |
| Cloud SQL, Cloud Run, images, `database-url` secret, app accounts | Terraform, from `infrastructure/` | These are what Deploy creates and Destroy removes. |

## What you need

- A GCP project with billing turned on
- The `gcloud` CLI, signed in as an owner of that project (`gcloud auth login`)
- This code in a GitHub repository
- An OpenRouter API key, if you want the real LLM

You do not need Terraform on your computer; GitHub Actions runs it. The commands below are for
bash (Git Bash on Windows).

## 1. Set the names once

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

## 2. Turn on the APIs

```bash
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com \
  storage.googleapis.com
```

Every GCP product is off until you turn it on for the project. `sts` and `iamcredentials` are the
ones that let GitHub sign in without a key.

## 3. Create the bucket for the Terraform state

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

## 4. Create the deployer account

```bash
gcloud iam service-accounts create egg-rag-deployer --display-name="GitHub Actions deployer"

for ROLE in roles/run.admin roles/cloudsql.admin roles/artifactregistry.admin \
  roles/secretmanager.admin roles/iam.serviceAccountAdmin roles/iam.serviceAccountUser \
  roles/resourcemanager.projectIamAdmin; do
  gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$DEPLOYER \
    --role=$ROLE --condition=None
done

gcloud storage buckets add-iam-policy-binding gs://$PROJECT-tfstate \
  --member=serviceAccount:$DEPLOYER --role=roles/storage.objectAdmin
```

GitHub Actions runs as this account. Terraform creates Cloud SQL, Cloud Run, images, secrets,
accounts and their permissions, so it needs one role for each of those. The last command lets it
read and write the state file.

## 5. Let GitHub sign in as the deployer

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

## 6. Store the LLM key

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

## 7. Create the Google sign-in client

Every page and API call needs a Google login, and only `allowed_email` can sign in. The login
works in four steps:

1. The **Sign in with Google** button on `/login` gives the page a JWT, signed by Google, that
   says which account signed in.
2. The page sends that JWT to `/auth/google`.
3. The service checks Google's signature, that the JWT is for your client ID, that it has not
   expired, and that the email is `allowed_email` and verified.
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
4. Go to **Audience** → **Test users** → **Add users**, add the email that will sign in, and save.
   While the app is in Testing mode, only test users can sign in at all. That is a second lock on
   top of `allowed_email`.
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

## 8. Point the code at your project

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

## 9. Deploy and destroy with a click

**Deploy:** on GitHub, open the repository, then **Actions** → **Deploy** → **Run workflow** →
branch `main` → **Run workflow**. Four jobs run, one after the other:

| Job | What it does | Time |
|---|---|---|
| `infrastructure` | `terraform apply`. The first run creates Cloud SQL, which is the slow part. | about 10 to 15 minutes the first time, under a minute after that |
| `migrate` | builds and pushes the migrate image, then runs the job | 1 to 2 minutes |
| `ingest` | builds and pushes the ingest image, then runs the job | several minutes (the image holds the 1.2 GB model) |
| `search` | builds and pushes the search image, then moves the service to it | several minutes |

Then open `https://egg-rag-search-<project number>.<region>.run.app/`:

1. It sends you to the login page. Sign in with Google.
2. You land in the ADK web UI. `/docs` is the API.
3. The first request after an idle period takes a few extra seconds while an instance starts.

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
- the images
- the `database-url` secret
- the app accounts

What stays is the setup from steps 2 to 7, which costs almost nothing. The next Deploy builds
everything again with a new database name (a random suffix), because Google blocks a deleted
Cloud SQL name for about a week.

## When something fails

- **Look at the failed step on GitHub first.** It prints the `gcloud` or Terraform error.
- **A `Permission denied` error names the missing permission.** Grant the deployer the matching
  role from step 4.
- **A failed job shows its logs:** Cloud Run → Jobs → the job → the failed execution → Logs.
  - migrate prints one line per migration file.
  - ingest prints how many documents and chunks were new or skipped.
- **If the search service does not start,** look at its logs. The usual causes are a missing
  `llm-api` secret version, or a database without tables because migrate did not run.
- **To see what Terraform would change without changing anything,** run this in
  `infrastructure/` with owner access:

  ```bash
  GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token) terraform init
  GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token) terraform plan
  ```
