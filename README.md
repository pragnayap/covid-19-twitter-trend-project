# COVID-19 Vaccine Tweet Analysis Pipeline

A complete end-to-end data pipeline that ingests publicly available COVID-19 vaccine tweet data, extracts and counts hashtags, sends Slack notifications, and visualizes trends in Kibana.

## Project Overview

This project builds a data pipeline using Apache Airflow, Google BigQuery, Google Cloud Storage, Slack, and Kibana to analyze trending hashtags in COVID-19 vaccine related tweets.

## Tools Used

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
- **Key columns:** `id`, `user_name`, `date`, `text`, `hashtags`, `retweets`, `favorites`

## Pipeline Architecture

```
vaccination_all_tweets.csv
          ↓
    validate_csv_file        ← checks file exists and is non-empty
          ↓
    upload_csv_to_gcs        ← uploads to Google Cloud Storage
          ↓
    create_bq_dataset        ← creates BigQuery dataset if needed
          ↓
    create_raw_table         ← creates partitioned + clustered table
          ↓
    gcs_to_bigquery          ← incrementally loads data into BigQuery
          ↓
    create_hashtag_table     ← creates hashtag counts table
          ↓
    analyze_hashtags         ← extracts and counts hashtags from tweets
          ↓
[notify_success] / [notify_failure]  ← Slack notification
```

## Key Features

### Incremental Loading
Data is loaded using `WRITE_APPEND` so each pipeline run only adds new records rather than reloading everything. Tables are partitioned by date to make incremental queries efficient.

### Optimization
- Raw tweets table partitioned by `date` field
- Hashtag counts table partitioned by `timestamp`
- Both tables clustered for faster queries
- BigQuery queries use standard SQL with CTEs for readability

### Error Handling
- File validation before pipeline starts
- 3 retries with exponential backoff on task failure
- Slack failure notification when any task fails
- Try/catch blocks in all Python functions

### Code Modularization
- `config.py` — all configuration variables in one place
- `helpers.py` — reusable functions for Slack and validation
- `twitter_pipeline.py` — main DAG using modular imports

## Top Trending Hashtags Found

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

## Project Structure

```
airflow/
├── dags/
│   ├── config.py                   # configuration variables
│   ├── helpers.py                  # reusable helper functions
│   ├── twitter_pipeline.py         # main Airflow DAG
│   └── vaccination_all_tweets.csv  # source dataset
├── logs/
├── plugins/
├── config/
├── Dockerfile                      # custom image with providers
├── docker-compose.yaml
└── .env
```

## Results

- Successfully loaded ~130,000 tweets into BigQuery
- Extracted and counted hashtags from tweet text and hashtags column
- Built Kibana dashboard with 4 visualizations:
  - Bar chart of top 20 hashtags
  - Pie chart of hashtag distribution
  - Data table with counts and percentages
  - Word cloud of trending hashtags

## Dataset Setup

The full dataset is not included due to size (90MB).

### Option 1 — Download from Kaggle
1. Go to: https://www.kaggle.com/datasets/gpreda/all-covid19-vaccines-tweets
2. Download `vaccination_all_tweets.csv`
3. Place it in the `dags/` folder

### Option 2 — Use Kaggle CLI
```bash
pip install kaggle
kaggle datasets download -d gpreda/all-covid19-vaccines-tweets
unzip all-covid19-vaccines-tweets.zip -d ./dags/
```

### Sample Dataset
A 100-row sample is included in `dags/vaccination_sample.csv` for testing.
