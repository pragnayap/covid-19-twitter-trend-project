# COVID-19 Vaccine Tweet Analysis Pipeline

An end-to-end data pipeline that ingests publicly available COVID-19 vaccine tweet data, extracts and counts hashtags, sends Slack notifications, and visualizes trends in Kibana.

## Tools

| Tool | Purpose |
|---|---|
| Apache Airflow | Pipeline orchestration and scheduling |
| Google BigQuery | Data warehouse for storing and querying tweets |
| Google Cloud Storage | Staging area for raw CSV files |
| Slack | Real-time pipeline status notifications |
| Kibana + Elasticsearch | Data visualization and dashboards |
| Python | Data processing and pipeline logic |

## Dataset

- **Source:** Kaggle — All COVID-19 Vaccines Tweets (gpreda)
- **File:** `vaccination_all_tweets.csv`
- **Size:** ~90MB
- **Records:** ~130,000 tweets
- **Columns:** `id`, `user_name`, `date`, `text`, `hashtags`, `retweets`, `favorites` and more

A 100-row sample is included in `dags/vaccination_sample.csv` for testing.

To get the full dataset:
1. Go to https://www.kaggle.com/datasets/gpreda/all-covid19-vaccines-tweets
2. Download `vaccination_all_tweets.csv`
3. Place it in the `dags/` folder

## Pipeline Architecture

```
vaccination_all_tweets.csv
          ↓
    validate_csv_file        checks file exists and is non-empty
          ↓
    upload_csv_to_gcs        uploads to Google Cloud Storage
          ↓
    create_bq_dataset        creates BigQuery dataset if needed
          ↓
    create_raw_table         creates partitioned + clustered table
          ↓
    gcs_to_bigquery          loads data into BigQuery
          ↓
    create_hashtag_table     creates hashtag counts table
          ↓
    analyze_hashtags         extracts and counts hashtags from tweets
          ↓
    push_to_elasticsearch    pushes results to Elasticsearch (BigQuery-Kibana bridge)
          ↓
[notify_success] / [notify_failure]   Slack notification
```

## Project Structure

```
airflow/
├── dags/
│   ├── config.py                   # all configuration variables
│   ├── helpers.py                  # reusable helper functions
│   ├── twitter_pipeline.py         # main Airflow DAG
│   └── vaccination_sample.csv      # 100-row sample dataset
├── logs/
├── plugins/
├── config/
├── Dockerfile                      # custom image with providers pre-installed
├── docker-compose.yaml             # all services including Elasticsearch and Kibana
├── .env.template                   # environment variables template
├── .gitignore
├── run_pipeline.sh                 # one-command startup script
├── README.md
├── SETUP.md
├── PIPELINE.md
└── CHALLENGES.md
```

## Key Features

### Incremental Loading
Data is loaded using `WRITE_TRUNCATE` so each pipeline run replaces data with fresh counts. Tables are partitioned by date and clustered for faster queries.

### BigQuery to Kibana Bridge
Since no native BigQuery-Kibana connector exists, a custom Python bridge task (`push_to_elasticsearch`) queries BigQuery and pushes results directly into Elasticsearch after every run. Kibana always shows live data without any manual steps.

### Optimization
- Raw tweets table partitioned by `date` field
- Hashtag counts table partitioned by `timestamp`
- Both tables clustered for faster queries
- BigQuery queries use CTEs for readability and performance

### Error Handling
- File validation before pipeline starts
- 3 retries with exponential backoff on task failure
- 15 minute execution timeout per task
- Slack failure notification when any task fails

### Code Modularization
- `config.py` — all configuration variables in one place
- `helpers.py` — reusable functions for Slack, validation and Elasticsearch
- `twitter_pipeline.py` — main DAG importing from config and helpers

## Top Findings

| Hashtag | Count | Percentage |
|---|---|---|
| covaxin | 2,933,300 | 26.0% |
| moderna | 2,203,300 | 19.5% |
| covid19 | 927,600 | 8.2% |
| sputnikv | 696,024 | 6.2% |
| bbmp | 680,832 | 6.0% |
| vaccine | 638,160 | 5.7% |
| covidvaccine | 591,790 | 5.2% |

**Total hashtag mentions analyzed: 11,281,494**

## Kibana Dashboard

4 visualizations built on live BigQuery data:
- Bar chart — top 20 hashtags by frequency
- Pie chart — proportional hashtag distribution
- Data table — hashtag counts with percentages
- Word cloud — visual representation of popularity

## Quick Start

### Prerequisites
- Docker Desktop installed and running
- GCP service account key JSON file
- Slack webhook URL

### Setup
1. Clone this repository
2. Copy `.env.template` to `.env` and fill in your values
3. Place your GCP key file as `gcp-key.json` in the project root
4. Download the full dataset from Kaggle and place in `dags/` folder
5. Update `config.py` with your `PROJECT_ID`, `BUCKET_NAME` and `SLACK_WEBHOOK`

### Run
```bash
bash run_pipeline.sh
```

This starts all Docker containers, triggers the pipeline and opens Airflow, Kibana and Slack.

### Manual Trigger
```bash
cd ~/airflow/airflow
docker compose exec --user airflow airflow-scheduler airflow dags unpause covid_vaccine_tweet_pipeline
docker compose exec --user airflow airflow-scheduler airflow dags trigger covid_vaccine_tweet_pipeline
```

### Access UIs
| Service | URL |
|---|---|
| Airflow | http://localhost:8080 |
| Kibana | http://localhost:5601 |
| Elasticsearch | http://localhost:9200 |
