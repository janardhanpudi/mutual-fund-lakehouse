FROM apache/airflow:2.10.5-python3.12

# Create the dbt environment as root (the default user cannot write to /opt),
# then switch back to the Airflow user for running the containers.
USER root
RUN python -m venv /opt/dbt-venv \
 && /opt/dbt-venv/bin/pip install --no-cache-dir dbt-databricks==1.13.0
USER airflow
