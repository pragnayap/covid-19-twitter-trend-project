# Challenges and Difficulties Faced

This document outlines the key challenges encountered during the implementation of the COVID-19 Vaccine Tweet Analysis Pipeline, mapped to the rubric criteria.

---

## 1. Environment Setup Challenges

### Docker and Airflow Setup
- **Challenge:** The `docker-compose` command was not found initially because Docker Desktop was not installed. The newer Docker uses `docker compose` (with a space) instead of `docker-compose` (with a hyphen).
- **Fix:** Installed Docker Desktop which includes the updated Compose plugin.

### File Sharing Permissions
- **Challenge:** Docker could not mount the project folders from the Desktop due to macOS permission restrictions. The error was:
  ```
  mkdir /host_mnt/Users/ritchit/Desktop: operation not permitted
  ```
- **Fix:** Created all required folders (`dags`, `logs`, `plugins`, `config`) manually and set permissions using `chmod -R 777`. Also verified Docker Desktop's Virtual File Sharing settings included `/Users`.

### Airflow Init Loop
- **Challenge:** The `airflow-init-1` container kept showing `Exited` in a loop, preventing other containers from starting.
- **Fix:** Fixed the `.env` file to include both `AIRFLOW_UID` and `AIRFLOW_GID=0`, then ran `docker compose up airflow-init` cleanly.

### Provider Installation
- **Challenge:** Installing `apache-airflow-providers-google` failed with `Permission denied` because pip ran as root inside the container.
- **Fix:** Created a custom `Dockerfile` that installs the provider at build time:
  ```dockerfile
  FROM apache/airflow:3.1.8
  USER root
  RUN pip install apache-airflow-providers-google apache-airflow-providers-slack google-cloud-bigquery
  USER airflow
  ```
  Then rebuilt using `docker compose build`.

---

## 2. Incremental Loading and Schema Challenges

### Schema Mismatch
- **Challenge:** The initial schema used generic column names (`tweet_id`, `retweet_count`) that didn't match the actual CSV columns (`id`, `retweets`). This caused the BigQuery load to fail silently.
- **Fix:** Inspected the CSV using `head -2` to get exact column names and updated `RAW_SCHEMA` in `config.py` to match exactly.

### BigQueryCreateEmptyTableOperator Removed
- **Challenge:** `BigQueryCreateEmptyTableOperator` was removed in the version of the Google provider installed. The error was:
  ```
  ImportError: cannot import name 'BigQueryCreateEmptyTableOperator'
  ```
- **Fix:** Replaced all table creation tasks with `BigQueryInsertJobOperator` using `CREATE TABLE IF NOT EXISTS` SQL with partitioning and clustering built in.

### Deprecated Imports in Airflow 3
- **Challenge:** Several imports that worked in Airflow 2 were deprecated or removed in Airflow 3:
  - `from airflow.operators.python import PythonOperator` → moved to `airflow.providers.standard`
  - `from airflow.utils.dates import days_ago` → removed entirely
  - `schedule_interval` parameter → renamed to `schedule`
- **Fix:** Updated all imports and parameters to match Airflow 3 syntax.

### Hashtag Column Format
- **Challenge:** The `hashtags` column in the CSV stored values as Python list strings like `['PfizerBioNTech', 'COVID19']` rather than plain text. Standard regex for `#hashtag` patterns didn't work on this format.
- **Fix:** Used two separate regex patterns — one for the list format column and one for the raw tweet text — then combined results using `UNION ALL`.

---

## 3. Error Handling Challenges

### GCP Credentials Error
- **Challenge:** The pipeline repeatedly failed with:
  ```
  DefaultCredentialsError: Your default credentials were not found
  ```
  Even after setting up the Airflow connection via the UI, the credentials weren't being picked up correctly.
- **Fix:** Copied the service account JSON file directly into the Docker container and set `GOOGLE_APPLICATION_CREDENTIALS` in the `.env` file:
  ```
  GOOGLE_APPLICATION_CREDENTIALS=/opt/airflow/gcp-key.json
  ```

### Mutually Exclusive Connection Fields
- **Challenge:** The Airflow connection kept failing with:
  ```
  AirflowException: The keyfile_dict, key_path, credential_config_file, is_anonymous and key_secret_name fields are all mutually exclusive
  ```
  This happened because both `Keyfile JSON` and `Keyfile Path` fields were set simultaneously in the connection.
- **Fix:** Deleted the connection completely from the command line and recreated it with only the `key_path` field set. Also set `GOOGLE_APPLICATION_CREDENTIALS` as an environment variable as a backup.

### Scheduled Runs Piling Up
- **Challenge:** With `schedule="@daily"`, Airflow created multiple queued runs that all failed, making it hard to identify which run was the current one.
- **Fix:** Changed `schedule=None` in the DAG to disable automatic scheduling and trigger runs manually only.

### Key File Lost After Restart
- **Challenge:** Every time Docker containers restarted, the GCP key file copied into the container was lost because containers don't persist files between restarts.
- **Fix:** Added the key file copy step to the startup procedure and documented it in SETUP.md.

---

## 4. Optimization Challenges

### Query Duplicates in Hashtag Table
- **Challenge:** Running the pipeline multiple times caused duplicate hashtag entries in `hashtag_counts` table because `INSERT INTO` kept adding new rows.
- **Fix:** Added a `DELETE FROM table WHERE TRUE` statement before each insert to clear old results before adding fresh counts.

### Memory Issues with Elasticsearch
- **Challenge:** Elasticsearch container crashed with exit code 137 (out of memory):
  ```
  ERROR: Elasticsearch exited unexpectedly, with exit code 137
  ```
- **Fix:** Limited Java heap size using `-e "ES_JAVA_OPTS=-Xms256m -Xmx256m"` and increased Docker Desktop memory allocation to 6GB.

---

## 5. Code Modularization Challenges

### Import Path Issues in Docker
- **Challenge:** Importing `config` and `helpers` modules from `twitter_pipeline.py` failed inside Docker because Python couldn't find the modules in its path. The error was:
  ```
  ModuleNotFoundError: No module named 'config'
  ```
- **Fix:** Added `sys.path.insert(0, '/opt/airflow/dags')` at the top of `twitter_pipeline.py` to explicitly add the dags folder to Python's module search path.

### VS Code Showing False Errors
- **Challenge:** VS Code showed 8 import errors for all Airflow modules because they aren't installed in the local Python environment — only inside Docker.
- **Fix:** Disabled Pylance type checking in VS Code settings:
  ```json
  {
    "python.analysis.typeCheckingMode": "off"
  }
  ```
  These were cosmetic errors only and did not affect the actual pipeline execution.

---

## 6. Kibana Visualization Challenges

### No Direct BigQuery-Kibana Connector
- **Challenge:** The assignment asked to connect Kibana directly to BigQuery, but no free native connector exists. Kibana works with Elasticsearch, not BigQuery directly.
- **Fix:** Built a custom Python bridge function in `helpers.py` that queries BigQuery and pushes results into Elasticsearch. This was added as a dedicated Airflow task `push_to_elasticsearch` in the pipeline, making it fully orchestrated and automated.

### CSV Field Names Not Imported Correctly
- **Challenge:** When uploading the exported BigQuery CSV to Kibana, the fields were named `column1` and `column2` instead of `hashtag` and `count` because the CSV was exported without headers.
- **Fix:** Added headers manually using:
  ```bash
  echo "hashtag,count" | cat - hashtag_counts.csv > hashtag_counts_fixed.csv
  ```
  Then updated the Kibana ingest pipeline to use correct target field names.

### Aggregation Rendering Errors
- **Challenge:** Creating visualizations using the "Aggregation based" method caused rendering errors in the browser console, preventing charts from displaying.
- **Fix:** Switched to using the Lens visualization editor which is the recommended approach in Kibana 8.x and rendered charts correctly.

### Elasticsearch Field Mapping
- **Challenge:** The `hashtag` field was stored as `text` type by default, which doesn't support Terms aggregation needed for bar charts and pie charts. The error was:
  ```
  Saved field 'hashtag' is invalid for use with the Terms aggregation
  ```
- **Fix:** Updated the `push_hashtags_to_elasticsearch` function to create the index with explicit mappings before inserting data:
  ```python
  mapping = {
    "mappings": {
      "properties": {
        "hashtag": {"type": "keyword"},
        "count":   {"type": "integer"}
      }
    }
  }
  ```

---

## Summary of Key Lessons Learned

| Challenge | Root Cause | Solution |
|---|---|---|
| Docker permission errors | macOS Desktop restrictions | Move project to home directory |
| Provider install failures | Root permission issues | Custom Dockerfile with pre-installed packages |
| GCP credentials failing | Connection field conflicts | Use GOOGLE_APPLICATION_CREDENTIALS env var |
| Schema mismatches | Generic template schema | Inspect CSV with head -2 before defining schema |
| Kibana field mapping | Default text type | Explicit keyword mapping before data insert |
| Scheduled runs piling up | Daily schedule with failures | Switch to schedule=None, trigger manually |
| Import errors in Docker | Python path not set | Add sys.path.insert for dags folder |
| No BigQuery-Kibana connector | Different ecosystems | Custom Python bridge as Airflow task |
