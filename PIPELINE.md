# Pipeline Technical Documentation

## Overview

The pipeline consists of 10 tasks in a linear dependency chain:

```
validate_csv_file
      ↓
upload_csv_to_gcs
      ↓
create_bq_dataset
      ↓
create_raw_table
      ↓
gcs_to_bigquery
      ↓
create_hashtag_table
      ↓
analyze_hashtags
      ↓
push_to_elasticsearch
      ↓
[notify_success] / [notify_failure]
```

---

## 1. Data Ingestion

### validate_csv_file
Checks the CSV file exists and is non-empty before starting any GCP operations. Raises `FileNotFoundError` or `ValueError` if validation fails, stopping the pipeline early.

### upload_csv_to_gcs
Uploads `vaccination_all_tweets.csv` (90MB) from the Airflow container to Google Cloud Storage using `LocalFilesystemToGCSOperator`. Has a 15 minute execution timeout to handle large file uploads.

### create_bq_dataset
Creates the `twitter_trends` BigQuery dataset if it doesn't already exist. Uses `exists_ok=True` so re-runs don't fail.

---

## 2. Table Schema and Mappings

### create_raw_table
Creates the raw tweets table with partitioning and clustering using `CREATE TABLE IF NOT EXISTS`:

```sql
CREATE TABLE IF NOT EXISTS `project.twitter_trends.vaccination_tweets`
(
    id               STRING,
    user_name        STRING,
    user_location    STRING,
    user_description STRING,
    user_created     TIMESTAMP,
    user_followers   INTEGER,
    user_friends     INTEGER,
    user_favourites  INTEGER,
    user_verified    BOOL,
    date             TIMESTAMP,
    text             STRING,
    hashtags         STRING,
    source           STRING,
    retweets         INTEGER,
    favorites        INTEGER,
    is_retweet       BOOL
)
PARTITION BY DATE(date)
CLUSTER BY user_name;
```

### Raw Tweets Table (vaccination_tweets)

| Column | Type | Description |
|---|---|---|
| id | STRING | Unique tweet ID |
| user_name | STRING | Twitter username |
| user_location | STRING | User location |
| user_description | STRING | User bio |
| user_created | TIMESTAMP | Account creation date |
| user_followers | INTEGER | Follower count |
| user_friends | INTEGER | Following count |
| user_favourites | INTEGER | Total likes |
| user_verified | BOOLEAN | Verified account |
| date | TIMESTAMP | Tweet timestamp |
| text | STRING | Tweet text content |
| hashtags | STRING | Hashtags list |
| source | STRING | Twitter client used |
| retweets | INTEGER | Retweet count |
| favorites | INTEGER | Like count |
| is_retweet | BOOLEAN | Whether it is a retweet |

### Hashtag Counts Table (hashtag_counts)

| Column | Type | Description |
|---|---|---|
| hashtag | STRING | Extracted hashtag text |
| count | INTEGER | Frequency count |
| timestamp | TIMESTAMP | When analysis was run |

---

## 3. Incremental Loading

Data is loaded using `WRITE_TRUNCATE` which replaces the table on each run ensuring clean consistent data:

```python
load_to_bq = GCSToBigQueryOperator(
    write_disposition="WRITE_TRUNCATE",
    ...
)
```

Tables are partitioned by date so BigQuery only scans relevant partitions when querying by date range, reducing query cost and improving performance.

---

## 4. Hashtag Extraction Logic

Hashtags are extracted from two sources and combined using `UNION ALL`:

```sql
-- Source 1: hashtags column stores values like ['PfizerBioNTech', 'COVID19']
WITH from_hashtag_col AS (
    SELECT
        REGEXP_EXTRACT_ALL(
            LOWER(hashtags),
            r"'([a-z0-9_]+)'"
        ) AS tags
    FROM `project.twitter_trends.vaccination_tweets`
    WHERE hashtags IS NOT NULL
      AND hashtags != '[]'
),

-- Source 2: extract #hashtags from raw tweet text
from_text AS (
    SELECT
        REGEXP_EXTRACT_ALL(
            LOWER(text),
            r'(#[a-z0-9_]+)'
        ) AS tags
    FROM `project.twitter_trends.vaccination_tweets`
    WHERE text IS NOT NULL
),

-- Combine both sources
all_tags AS (
    SELECT tag FROM from_hashtag_col, UNNEST(tags) AS tag
    UNION ALL
    SELECT REPLACE(tag, '#', '') AS tag
    FROM from_text, UNNEST(tags) AS tag
)

SELECT
    tag                 AS hashtag,
    COUNT(*)            AS count,
    CURRENT_TIMESTAMP() AS timestamp
FROM all_tags
WHERE tag IS NOT NULL
  AND LENGTH(tag) > 1
GROUP BY tag
ORDER BY count DESC;
```

---

## 5. Optimization Techniques

### Table Partitioning
Both tables are partitioned by date fields:
- `vaccination_tweets` partitioned by `DATE(date)`
- `hashtag_counts` partitioned by `DATE(timestamp)`

Partitioning means BigQuery only scans relevant date partitions, reducing query cost and improving performance.

### Table Clustering
- `vaccination_tweets` clustered by `user_name`
- `hashtag_counts` clustered by `hashtag`

Clustering physically organizes data so queries filtering by these fields run faster.

### Query Efficiency
- Uses CTEs instead of nested subqueries for readability and performance
- Filters out NULL values and empty hashtags early
- Uses `REGEXP_EXTRACT_ALL` for efficient bulk extraction

---

## 6. Error Handling and Logging

### Task-Level Retries
```python
default_args = {
    "retries":                   3,
    "retry_delay":               timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay":           timedelta(minutes=30),
    "execution_timeout":         timedelta(minutes=15),
}
```

Retries use exponential backoff — 2min, 4min, 8min — capped at 30 minutes. Each task also has a 15 minute execution timeout.

### File Validation
```python
def validate_csv_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    if os.path.getsize(file_path) == 0:
        raise ValueError(f"File is empty: {file_path}")
    logger.info(f"File validated: {file_path}")
    return True
```

### Slack Notifications
```python
notify_success = PythonOperator(
    trigger_rule="all_success",  # runs only if all tasks succeed
    ...
)

notify_failure = PythonOperator(
    trigger_rule="one_failed",   # runs if any task fails
    ...
)
```

### Logging
```python
logger = logging.getLogger(__name__)
logger.info("File validated successfully")
logger.error(f"Slack notification failed: {e}")
```

---

## 7. Code Reusability and Modularization

The code is split into 3 files:

### config.py
All configuration variables defined once and imported everywhere. Changing a value like `PROJECT_ID` only needs to be done in one place.

### helpers.py
Three reusable functions:
- `send_slack_notification()` — sends formatted Slack messages with error handling
- `validate_csv_file()` — validates file before pipeline starts
- `push_hashtags_to_elasticsearch()` — BigQuery to Elasticsearch bridge

### twitter_pipeline.py
Main DAG file that imports from config and helpers:
```python
from config import PROJECT_ID, DATASET_NAME, ...
from helpers import send_slack_notification, validate_csv_file, push_hashtags_to_elasticsearch
```

---

## 8. BigQuery to Kibana Bridge

Since no native BigQuery-Kibana connector exists, we built a custom Python bridge as a dedicated Airflow task:

```python
def push_hashtags_to_elasticsearch(project_id, dataset, table, es_host, es_index):
    client = bigquery.Client(project=project_id)
    results = client.query(
        f"SELECT hashtag, count FROM `{project_id}.{dataset}.{table}` ORDER BY count DESC LIMIT 50"
    ).result()

    # Delete old index and recreate with correct field mappings
    requests.delete(f"{es_host}/{es_index}")
    requests.put(f"{es_host}/{es_index}", json={
        "mappings": {
            "properties": {
                "hashtag": {"type": "keyword"},
                "count":   {"type": "integer"}
            }
        }
    })

    for row in results:
        requests.post(f"{es_host}/{es_index}/_doc",
                     json={"hashtag": row.hashtag, "count": row.count})
```

This means Kibana always shows live data from BigQuery automatically after every pipeline run.

---

## 9. Kibana Dashboard

4 visualizations built on live BigQuery data via Elasticsearch:

| Visualization | Type | Insight |
|---|---|---|
| Top Hashtags Bar Chart | Vertical Bar | Top 20 hashtags by frequency |
| Hashtag Distribution Pie | Donut Pie | Proportional share of each hashtag |
| Hashtag Counts Table | Data Table | All hashtags with counts and percentages |
| Word Cloud | Tag Cloud | Visual representation of hashtag popularity |

### Top Findings
- `covaxin` was the most discussed vaccine with 2,933,300 mentions (26%)
- `moderna` came second with 2,203,300 mentions (19.5%)
- `covid19` had 927,600 mentions (8.2%)
- Total of **11,281,494** hashtag mentions analyzed
