# Environment Setup Guide

## Prerequisites
- Mac with Docker Desktop installed
- Google Cloud Platform account (free tier works)
- Kaggle account (for dataset download)
- Slack workspace

---

## 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/covid-vaccine-tweet-pipeline.git
cd covid-vaccine-tweet-pipeline
```

---

## 2. Dataset Setup

Download the dataset from Kaggle:
1. Go to https://www.kaggle.com/datasets/gpreda/all-covid19-vaccines-tweets
2. Download `vaccination_all_tweets.csv`
3. Place it in the `dags/` folder

Or use Kaggle CLI:
```bash
pip install kaggle
kaggle datasets download -d gpreda/all-covid19-vaccines-tweets
unzip all-covid19-vaccines-tweets.zip -d ./dags/
```

A 100-row sample is included in `dags/vaccination_sample.csv` for testing.

---

## 3. Google Cloud Platform Setup

### Create Project
1. Go to https://console.cloud.google.com
2. Create a new project named `twitter-trend-project`
3. Note your Project ID from the top bar

### Enable APIs
Go to APIs & Services → Library and enable:
- BigQuery API
- Cloud Storage API

### Create Service Account
1. Go to IAM & Admin → Service Accounts
2. Create a service account named `airflow-pipeline-sa`
3. Assign roles: `BigQuery Admin` and `Storage Admin`
4. Generate and download a JSON key file
5. Place it in the project root as `gcp-key.json`

### Create BigQuery Dataset
1. Go to BigQuery in GCP Console
2. Click Create Dataset
3. Name it `twitter_trends`
4. Region: `US`

### Create GCS Bucket
1. Go to Cloud Storage → Buckets → Create
2. Name it `covid-tweets-bucket` (must be globally unique)
3. Region: `us-central1`

---

## 4. Slack Setup
1. Create a Slack workspace at https://slack.com
2. Create a channel named `#twitter-trend-alerts`
3. Go to https://api.slack.com/apps
4. Create a new app → From scratch
5. Enable Incoming Webhooks
6. Add webhook to `#twitter-trend-alerts` channel
7. Copy the webhook URL

---

## 5. Environment Configuration

Copy the template and fill in your values:
```bash
cp .env.template .env
```

Edit `.env`:
```
AIRFLOW_UID=501
AIRFLOW_GID=0
GOOGLE_APPLICATION_CREDENTIALS=/opt/airflow/gcp-key.json
AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=false
AIRFLOW__CORE__LOAD_EXAMPLES=false
```

Update `dags/config.py`:
```python
PROJECT_ID    = "your-gcp-project-id"
BUCKET_NAME   = "your-bucket-name"
SLACK_WEBHOOK = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

---

## 6. Docker and Airflow Setup

### Install Docker Desktop
Download from https://docker.com and make sure it is running.

### Build and Start
```bash
docker compose build
docker compose up airflow-init
docker compose up -d
```

### Verify all containers are healthy
```bash
docker compose ps
```

You should see these containers all showing healthy:
- `airflow-apiserver`
- `airflow-scheduler`
- `airflow-dag-processor`
- `airflow-worker`
- `airflow-triggerer`
- `postgres`
- `redis`
- `elasticsearch`
- `kibana`

---

## 7. Airflow GCP Connection Setup
1. Open http://localhost:8080 (username: `airflow`, password: `airflow`)
2. Go to Admin → Connections → +
3. Fill in:
   - **Connection ID:** `google_cloud_default`
   - **Connection Type:** `Google Cloud`
   - **Keyfile Path:** `/opt/airflow/gcp-key.json`
4. Click Test to verify
5. Click Save

---

## 8. Running the Pipeline

### Option 1 — One command (recommended)
```bash
bash run_pipeline.sh
```

This starts all containers, triggers the DAG and opens all UIs automatically.

### Option 2 — Manual
```bash
cd ~/airflow/airflow
docker compose up -d
sleep 40
docker compose exec --user airflow airflow-scheduler airflow dags unpause covid_vaccine_tweet_pipeline
docker compose exec --user airflow airflow-scheduler airflow dags trigger covid_vaccine_tweet_pipeline
open http://localhost:8080
open http://localhost:5601
```

---

## 9. Access UIs

| Service | URL | Credentials |
|---|---|---|
| Airflow | http://localhost:8080 | airflow / airflow |
| Kibana | http://localhost:5601 | none required |
| Elasticsearch | http://localhost:9200 | none required |
| BigQuery | https://console.cloud.google.com/bigquery | GCP account |

---

## 10. Stopping Everything
```bash
cd ~/airflow/airflow
docker compose down
```

To stop and delete all data volumes:
```bash
docker compose down -v
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| DAG is paused after restart | Run `airflow dags unpause covid_vaccine_tweet_pipeline` |
| GCP credentials not found | Copy key file: `docker cp gcp-key.json airflow-airflow-worker-1:/opt/airflow/gcp-key.json` |
| Elasticsearch out of memory | Increase Docker Desktop memory to 6GB in Settings → Resources |
| upload_csv_to_gcs timeout | File is already in GCS — check bucket and re-trigger |
| Kibana can't connect | Wait 2 minutes after starting — Elasticsearch needs time to start |
