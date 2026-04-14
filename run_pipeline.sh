#!/bin/bash

echo "Starting COVID-19 Vaccine Tweet Pipeline..."

# Go to airflow folder
cd ~/airflow/airflow

# Start everything
docker compose up -d
echo "Waiting for containers to be healthy..."
sleep 40

# Unpause and trigger DAG
docker compose exec --user airflow airflow-scheduler airflow dags unpause covid_vaccine_tweet_pipeline
docker compose exec --user airflow airflow-scheduler airflow dags trigger covid_vaccine_tweet_pipeline

# Open all UIs
open http://localhost:8080
open http://localhost:5601
open "https://app.slack.com/client/T0APXBC619S/C0APTPLQZPU"
open "https://console.cloud.google.com/bigquery?project=twitter-trend-project-491803"

echo "Pipeline triggered! Watch Airflow UI at http://localhost:8080"
