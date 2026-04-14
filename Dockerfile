FROM apache/airflow:3.1.8
RUN pip install apache-airflow-providers-google apache-airflow-providers-slack
