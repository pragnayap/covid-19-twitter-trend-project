# Pipeline Technical Documentation

This document explains the technical design decisions, implementation details, and rubric-aligned features of the COVID-19 Vaccine Tweet Analysis Pipeline.

---

## 1. Pipeline Overview

The pipeline consists of 9 tasks organized in a linear dependency chain:

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
[notify_success] / [notify_failure]
```

---

## 2. Incremental Loading

The pipeline uses `WRITE_APPEND` instead of `WRITE_TRUNCATE` so each run only adds new records:

```python
load_to_bq = GCSToBigQueryOperator(
    write_disposition="WRITE_APPEND",  # incremental — append only
    ...
)
```

Tables are partitioned by date so BigQuery only scans relevant partitions:

```sql
CREATE TABLE IF NOT EXISTS `project.dataset.table`
PARTITION BY DATE(date)
CLUSTER BY user_name;
```

This means:
- Queries filtering by date scan less data
- Each pipeline run adds to existing data rather than replacing it
- Historical data is preserved across runs

---

## 3. Table Schema and Mappings

### Raw Tweets Table (`vaccination_tweets`)

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

### Hashtag Counts Table (`hashtag_counts`)

| Column | Type | Description |
|---|---|---|
| hashtag | STRING | Extracted hashtag text |
| count | INTEGER | Frequency count |
| timestamp | TIMESTAMP | When analysis was run |

---

## 4. Hashtag Extraction Logic

Hashtags are extracted from two sources and combined:

```sql
-- Source 1: hashtags column stores values like ['PfizerBioNTech', 'COVID19']
WITH from_hashtag_col AS (
    SELECT
        REGEXP_EXTRACT_ALL(
            LOWER(hashtags),
            r"'([a-z0-9_]+)'"
        ) AS tags
    FROM `project.dataset.vaccination_tweets`
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
    FROM `project.dataset.vaccination_tweets`
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
    tag             AS hashtag,
    COUNT(*)        AS count,
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

This reduces query cost and improves performance since BigQuery only scans relevant date partitions.

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
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}
```

Retries use exponential backoff — 2min, 4min, 8min — capped at 30 minutes.

### File Validation
Before any GCP operations, the pipeline validates the CSV file:
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
Both success and failure states send Slack notifications:
```python
notify_success = PythonOperator(
    trigger_rule="all_success",  # only runs if all tasks succeed
    ...
)

notify_failure = PythonOperator(
    trigger_rule="one_failed",   # runs if any task fails
    ...
)
```

### Logging
All helper functions use Python's logging module:
```python
logger = logging.getLogger(__name__)
logger.info("File validated successfully")
logger.error(f"Slack notification failed: {e}")
```

---

## 7. Code Reusability and Modularization

The code is split into 3 files:

### config.py
Central configuration file. All variables are defined once here and imported everywhere:
```python
PROJECT_ID    = "twitter-trend-project-491803"
DATASET_NAME  = "twitter_trends"
BUCKET_NAME   = "covid-tweets-bucket"
```

### helpers.py
Reusable utility functions:
- `send_slack_notification()` — sends formatted Slack messages
- `validate_csv_file()` — validates file before pipeline starts

### twitter_pipeline.py
Main DAG file that imports from config and helpers:
```python
from config import PROJECT_ID, DATASET_NAME, ...
from helpers import send_slack_notification, validate_csv_file
```

This separation means:
- Config changes only need to be made in one place
- Helper functions can be reused across multiple DAGs
- Main DAG file stays clean and readable

---

## 8. BigQuery to Kibana Bridge

Instead of manually exporting CSV files, we built a Python bridge function as a dedicated Airflow task that automatically pushes data from BigQuery into Elasticsearch after every pipeline run:

```python
def push_hashtags_to_elasticsearch(project_id, dataset, table, es_host, es_index):
    client = bigquery.Client(project=project_id)
    results = client.query(f"SELECT hashtag, count FROM `{project_id}.{dataset}.{table}` ORDER BY count DESC LIMIT 50").result()

    # Create index with correct field mappings
    requests.delete(f"{es_host}/{es_index}")
    requests.put(f"{es_host}/{es_index}", json={
        "mappings": {
            "properties": {
                "hashtag": {"type": "keyword"},
                "count":   {"type": "integer"}
            }
        }
    })

    # Push each row into Elasticsearch
    for row in results:
        requests.post(f"{es_host}/{es_index}/_doc", json={"hashtag": row.hashtag, "count": row.count})
```

This means Kibana always shows **live data** from BigQuery without any manual steps.

## 9. Kibana Dashboard

Data flows automatically from BigQuery into Kibana via the Elasticsearch bridge with 4 visualizations:

| Visualization | Type | Insight |
|---|---|---|
| Top Hashtags Bar Chart | Vertical Bar | Shows top 20 hashtags by frequency |
| Hashtag Distribution Pie | Donut Pie | Shows proportional share of each hashtag |
| Hashtag Counts Table | Data Table | Lists all hashtags with counts and percentages |
| Word Cloud | Tag Cloud | Visual representation of hashtag popularity |

### Top Findings
- `covaxin` was the most discussed vaccine with 2,933,300 mentions (26%)
- `moderna` came second with 2,203,300 mentions (19.5%)
- `covid19` had 927,600 mentions (8.2%)
- Total of **11,281,494** hashtag mentions analyzed
