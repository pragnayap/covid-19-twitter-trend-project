# Configuration file for the COVID-19 Vaccine Tweet Pipeline

PROJECT_ID    = "twitter-trend-project-491803"
DATASET_NAME  = "twitter_trends"
RAW_TABLE     = "vaccination_tweets"
HASHTAG_TABLE = "hashtag_counts"
BUCKET_NAME   = "covid-tweets-bucket"
LOCATION      = "US"

CSV_FILE_NAME   = "vaccination_all_tweets.csv"
LOCAL_FILE_PATH = f"/opt/airflow/dags/{CSV_FILE_NAME}"

SLACK_WEBHOOK = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Schema for raw tweets table - matches vaccination_all_tweets.csv columns exactly
RAW_SCHEMA = [
    {"name": "id",               "type": "STRING",    "mode": "NULLABLE"},
    {"name": "user_name",        "type": "STRING",    "mode": "NULLABLE"},
    {"name": "user_location",    "type": "STRING",    "mode": "NULLABLE"},
    {"name": "user_description", "type": "STRING",    "mode": "NULLABLE"},
    {"name": "user_created",     "type": "TIMESTAMP", "mode": "NULLABLE"},
    {"name": "user_followers",   "type": "INTEGER",   "mode": "NULLABLE"},
    {"name": "user_friends",     "type": "INTEGER",   "mode": "NULLABLE"},
    {"name": "user_favourites",  "type": "INTEGER",   "mode": "NULLABLE"},
    {"name": "user_verified",    "type": "BOOLEAN",   "mode": "NULLABLE"},
    {"name": "date",             "type": "TIMESTAMP", "mode": "NULLABLE"},
    {"name": "text",             "type": "STRING",    "mode": "NULLABLE"},
    {"name": "hashtags",         "type": "STRING",    "mode": "NULLABLE"},
    {"name": "source",           "type": "STRING",    "mode": "NULLABLE"},
    {"name": "retweets",         "type": "INTEGER",   "mode": "NULLABLE"},
    {"name": "favorites",        "type": "INTEGER",   "mode": "NULLABLE"},
    {"name": "is_retweet",       "type": "BOOLEAN",   "mode": "NULLABLE"},
]

# Schema for hashtag counts table
HASHTAG_SCHEMA = [
    {"name": "hashtag",   "type": "STRING",    "mode": "REQUIRED"},
    {"name": "count",     "type": "INTEGER",   "mode": "REQUIRED"},
    {"name": "timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"},
]
