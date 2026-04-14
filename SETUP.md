# Environment Setup Guide

This document covers the setup of all tools required for the COVID-19 Vaccine Tweet Analysis Pipeline.

## Prerequisites

- Mac with Docker Desktop installed
- Google Cloud Platform account (free tier works)
- Kaggle account (for dataset download)
- Slack workspace

---

## 1. Docker and Airflow Setup

### Install Docker Desktop
Download and install Docker Desktop from https://docker.com. Make sure it is running before proceeding.

### Start Airflow
```bash
mkdir airflow && cd airflow
curl -LfO 'https://airflow.apache.org/docs/apache-airflow/stable/docker-compose.yaml'
mkdir -p ./dags ./logs ./plugins ./config
echo "AIRFLOW_UID=$(id -u)" > .env
echo "AIRFLOW_GID=0" >> .env
docker compose up airflow-init
docker compose up -d
```

Open Airflow at http://localhost:8080 (username: airflow, password: airflow)

### Install Google Provider
Add this line to your `.env` file:
```
_PIP_ADDITIONAL_REQUIREMENTS=apache-airflow-providers-google
```

Or build a custom Docker image using the provided Dockerfile:
```bash
docker compose build
docker compose up -d
```

---

## 2. Google Cloud Platform Setup

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

## 3. Airflow GCP Connection Setup

1. Open Airflow UI at http://localhost:8080
2. Go to Admin → Connections → +
3. Fill in:
   - Connection ID: `google_cloud_default`
   - Connection Type: `Google Cloud`
   - Keyfile Path: `/opt/airflow/gcp-key.json`
4. Copy the JSON key into the container:
```bash
docker cp ~/Downloads/your-key-file.json airflow-airflow-worker-1:/opt/airflow/gcp-key.json
docker cp ~/Downloads/your-key-file.json airflow-airflow-scheduler-1:/opt/airflow/gcp-key.json
```
5. Click Test to verify the connection
6. Click Save

---

## 4. Slack Setup

1. Create a Slack workspace at https://slack.com
2. Create a channel named `#twitter-trend-alerts`
3. Go to https://api.slack.com/apps
4. Create a new app → From scratch
5. Enable Incoming Webhooks
6. Add webhook to `#twitter-trend-alerts` channel
7. Copy the webhook URL and paste it into `config.py` as `SLACK_WEBHOOK`

---

## 5. Dataset Setup

Download the dataset from Kaggle:
```bash
pip install kaggle
kaggle datasets download -d gpreda/all-covid19-vaccines-tweets
unzip all-covid19-vaccines-tweets.zip -d ./dags/
```

Or download manually from:
https://www.kaggle.com/datasets/gpreda/all-covid19-vaccines-tweets

Place `vaccination_all_tweets.csv` in the `./dags/` folder.

---

## 6. Kibana Setup

```bash
docker run -d --name elasticsearch \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  -e "ES_JAVA_OPTS=-Xms256m -Xmx256m" \
  elasticsearch:8.11.0

sleep 40

docker run -d --name kibana \
  -p 5601:5601 \
  -e "ELASTICSEARCH_HOSTS=http://elasticsearch:9200" \
  -e "xpack.security.enabled=false" \
  --link elasticsearch:elasticsearch \
  kibana:8.11.0
```

Open Kibana at http://localhost:5601

---

## 7. Update Configuration

Open `dags/config.py` and update:
```python
PROJECT_ID    = "your-gcp-project-id"
BUCKET_NAME   = "your-bucket-name"
SLACK_WEBHOOK = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

---

## 8. Running the Pipeline

1. Place all DAG files in `./dags/` folder
2. Open Airflow UI at http://localhost:8080
3. Find `covid_vaccine_tweet_pipeline`
4. Enable the DAG using the toggle
5. Click Trigger DAG
6. Watch tasks turn green one by one
7. Check Slack for success notification
