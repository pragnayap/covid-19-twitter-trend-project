# Helper functions for Slack notifications, logging and file validation

import json
import logging
import os
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def send_slack_notification(message, webhook_url):
    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message}
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Time (UTC):* {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            }
        ]
    }
    try:
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        response.raise_for_status()
        logger.info("Slack notification sent.")
    except requests.exceptions.Timeout:
        logger.error("Slack request timed out.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"Slack HTTP error: {e}")
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")


def validate_csv_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    if os.path.getsize(file_path) == 0:
        raise ValueError(f"File is empty: {file_path}")
    logger.info(f"File validated: {file_path}")
    return True


def push_hashtags_to_elasticsearch(project_id, dataset, table, es_host, es_index):
    # Queries BigQuery and pushes results into Elasticsearch
    # so Kibana can visualize live data directly from BigQuery
    from google.cloud import bigquery

    logger.info("Connecting to BigQuery...")
    client = bigquery.Client(project=project_id)

    results = client.query(
        f"SELECT hashtag, count FROM `{project_id}.{dataset}.{table}` ORDER BY count DESC LIMIT 50"
    ).result()

    # Delete old index and recreate with correct field mappings
    requests.delete(f"{es_host}/{es_index}")
    requests.put(
        f"{es_host}/{es_index}",
        json={
            "mappings": {
                "properties": {
                    "hashtag": {"type": "keyword"},
                    "count":   {"type": "integer"}
                }
            }
        },
        headers={"Content-Type": "application/json"}
    )

    success_count = 0
    for row in results:
        response = requests.post(
            f"{es_host}/{es_index}/_doc",
            json={"hashtag": row.hashtag, "count": row.count},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code in [200, 201]:
            success_count += 1

    logger.info(f"Pushed {success_count} hashtags to Elasticsearch index: {es_index}")
    return success_count
