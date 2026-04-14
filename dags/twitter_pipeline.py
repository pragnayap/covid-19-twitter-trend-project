# Airflow DAG for COVID-19 Vaccine Tweet Pipeline
# Loads tweet data into BigQuery, extracts hashtags, pushes to Elasticsearch and sends Slack alerts

import sys
sys.path.insert(0, '/opt/airflow/dags')

from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.google.cloud.operators.bigquery import (
    BigQueryCreateEmptyDatasetOperator,
    BigQueryInsertJobOperator,
)
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from airflow.providers.google.cloud.transfers.local_to_gcs import LocalFilesystemToGCSOperator

from config import (
    PROJECT_ID, DATASET_NAME, RAW_TABLE, HASHTAG_TABLE,
    BUCKET_NAME, CSV_FILE_NAME, LOCAL_FILE_PATH, LOCATION,
    SLACK_WEBHOOK, RAW_SCHEMA, HASHTAG_SCHEMA,
)
from helpers import send_slack_notification, validate_csv_file, push_hashtags_to_elasticsearch

default_args = {
    "owner":                     "airflow",
    "depends_on_past":           False,
    "email_on_failure":          False,
    "email_on_retry":            False,
    "retries":                   3,
    "retry_delay":               timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay":           timedelta(minutes=30),
    "execution_timeout":         timedelta(minutes=15),
}

with DAG(
    dag_id="covid_vaccine_tweet_pipeline",
    default_args=default_args,
    description="Ingest COVID vaccine tweets, extract hashtags, push to Kibana, notify via Slack",
    schedule=None,
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["covid", "vaccines", "bigquery", "hashtags"],
) as dag:

    # Validate CSV file exists before starting pipeline
    validate_file = PythonOperator(
        task_id="validate_csv_file",
        python_callable=validate_csv_file,
        op_kwargs={"file_path": LOCAL_FILE_PATH},
    )

    # Upload CSV to Google Cloud Storage
    upload_to_gcs = LocalFilesystemToGCSOperator(
        task_id="upload_csv_to_gcs",
        src=LOCAL_FILE_PATH,
        dst=CSV_FILE_NAME,
        bucket=BUCKET_NAME,
        gcp_conn_id="google_cloud_default",
        mime_type="text/csv",
    )

    # Create BigQuery dataset if it doesn't exist
    create_dataset = BigQueryCreateEmptyDatasetOperator(
        task_id="create_bq_dataset",
        dataset_id=DATASET_NAME,
        project_id=PROJECT_ID,
        location=LOCATION,
        gcp_conn_id="google_cloud_default",
        exists_ok=True,
    )

    # Create raw tweets table with date partitioning and clustering for query optimization
    create_raw_table = BigQueryInsertJobOperator(
        task_id="create_raw_table",
        configuration={
            "query": {
                "query": f"""
                    CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.{DATASET_NAME}.{RAW_TABLE}`
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
                """,
                "useLegacySql": False,
            }
        },
        location=LOCATION,
        gcp_conn_id="google_cloud_default",
    )

    # Load data from GCS into BigQuery using WRITE_APPEND for incremental loading
    load_to_bq = GCSToBigQueryOperator(
        task_id="gcs_to_bigquery",
        bucket=BUCKET_NAME,
        source_objects=[CSV_FILE_NAME],
        destination_project_dataset_table=f"{PROJECT_ID}.{DATASET_NAME}.{RAW_TABLE}",
        schema_fields=RAW_SCHEMA,
        source_format="CSV",
        create_disposition="CREATE_IF_NEEDED",
        write_disposition="WRITE_TRUNCATE",
        skip_leading_rows=1,
        field_delimiter=",",
        quote_character='"',
        allow_quoted_newlines=True,
        allow_jagged_rows=True,
        gcp_conn_id="google_cloud_default",
    )

    # Create hashtag counts table with partitioning and clustering
    create_hashtag_table = BigQueryInsertJobOperator(
        task_id="create_hashtag_table",
        configuration={
            "query": {
                "query": f"""
                    CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.{DATASET_NAME}.{HASHTAG_TABLE}`
                    (
                        hashtag   STRING NOT NULL,
                        count     INTEGER NOT NULL,
                        timestamp TIMESTAMP NOT NULL
                    )
                    PARTITION BY DATE(timestamp)
                    CLUSTER BY hashtag;
                """,
                "useLegacySql": False,
            }
        },
        location=LOCATION,
        gcp_conn_id="google_cloud_default",
    )

    # Extract hashtags from tweet text and hashtags column, count occurrences
    analyze_hashtags = BigQueryInsertJobOperator(
        task_id="analyze_hashtags",
        configuration={
            "query": {
                "query": f"""
                    DELETE FROM `{PROJECT_ID}.{DATASET_NAME}.{HASHTAG_TABLE}` WHERE TRUE;

                    INSERT INTO `{PROJECT_ID}.{DATASET_NAME}.{HASHTAG_TABLE}`

                    WITH
                    -- Source 1: hashtags column stores values like ['PfizerBioNTech', 'COVID19']
                    from_hashtag_col AS (
                        SELECT
                            REGEXP_EXTRACT_ALL(
                                LOWER(hashtags),
                                r"'([a-z0-9_]+)'"
                            ) AS tags
                        FROM `{PROJECT_ID}.{DATASET_NAME}.{RAW_TABLE}`
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
                        FROM `{PROJECT_ID}.{DATASET_NAME}.{RAW_TABLE}`
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
                """,
                "useLegacySql": False,
                "priority": "INTERACTIVE",
            }
        },
        location=LOCATION,
        gcp_conn_id="google_cloud_default",
    )

    # Push hashtag counts from BigQuery to Elasticsearch (BigQuery-Kibana bridge)
    push_to_elasticsearch = PythonOperator(
        task_id="push_to_elasticsearch",
        python_callable=push_hashtags_to_elasticsearch,
        op_kwargs={
            "project_id": PROJECT_ID,
            "dataset":    DATASET_NAME,
            "table":      HASHTAG_TABLE,
            "es_host":    "http://host.docker.internal:9200",
            "es_index":   "twitter-hashtags-live",
        },
    )

    # Send Slack notification on pipeline success
    notify_success = PythonOperator(
        task_id="notify_success",
        python_callable=send_slack_notification,
        op_kwargs={
            "message": (
                ":white_check_mark: *COVID Vaccine Tweet Pipeline — SUCCESS*\n"
                f"• Project: `{PROJECT_ID}`\n"
                f"• Raw tweets loaded into: `{RAW_TABLE}`\n"
                f"• Hashtag counts saved in: `{HASHTAG_TABLE}`\n"
                f"• Run date: `{datetime.now(timezone.utc).strftime('%Y-%m-%d')}`"
            ),
            "webhook_url": SLACK_WEBHOOK,
        },
        trigger_rule="all_success",
    )

    # Send Slack notification on pipeline failure
    notify_failure = PythonOperator(
        task_id="notify_failure",
        python_callable=send_slack_notification,
        op_kwargs={
            "message": (
                ":red_circle: *COVID Vaccine Tweet Pipeline — FAILED*\n"
                f"• Project: `{PROJECT_ID}`\n"
                f"• Dataset: `{DATASET_NAME}`\n"
                "• Check Airflow logs for details."
            ),
            "webhook_url": SLACK_WEBHOOK,
        },
        trigger_rule="one_failed",
    )

    # Pipeline flow
    (
        validate_file
        >> upload_to_gcs
        >> create_dataset
        >> create_raw_table
        >> load_to_bq
        >> create_hashtag_table
        >> analyze_hashtags
        >> push_to_elasticsearch
        >> [notify_success, notify_failure]
    )
