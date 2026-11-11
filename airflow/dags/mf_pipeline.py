"""Daily mutual fund pipeline: Databricks bronze load, then dbt build.

Steps:
  1. start the bronze_ingest job in Databricks (Auto Loader: landing files -> bronze tables)
  2. wait until that job has finished, and fail if it did not succeed
  3. run dbt build (silver -> gold, with tests)
"""

import os
import time
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

DBT_PROJECT = "/opt/airflow/dbt_mf"
DBT_BIN = "/opt/dbt-venv/bin/dbt"
POLL_SECONDS = 30
TIMEOUT_SECONDS = 60 * 60


def _databricks_url(path: str) -> str:
    # DATABRICKS_HOST is stored without "https://" in .env
    return f"https://{os.environ['DATABRICKS_HOST']}{path}"


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['DATABRICKS_TOKEN']}"}


def start_bronze_job(ti) -> None:
    resp = requests.post(
        _databricks_url("/api/2.1/jobs/run-now"),
        headers=_headers(),
        json={"job_id": int(os.environ["DATABRICKS_BRONZE_JOB_ID"])},
        timeout=60,
    )
    resp.raise_for_status()
    run_id = resp.json()["run_id"]
    ti.xcom_push(key="run_id", value=run_id)


def wait_for_bronze_job(ti) -> None:
    run_id = ti.xcom_pull(task_ids="start_bronze_job", key="run_id")
    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        resp = requests.get(
            _databricks_url("/api/2.1/jobs/runs/get"),
            headers=_headers(),
            params={"run_id": run_id},
            timeout=60,
        )
        resp.raise_for_status()
        state = resp.json()["state"]
        if state["life_cycle_state"] in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            if state.get("result_state") == "SUCCESS":
                return
            raise RuntimeError(f"bronze_ingest run {run_id} ended: {state}")
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"bronze_ingest run {run_id} did not finish in an hour")


with DAG(
    dag_id="mf_pipeline",
    description="Databricks bronze load, then dbt build",
    start_date=datetime(2026, 1, 1),
    schedule="0 17 * * *",  # 17:00 UTC = 22:30 IST every day (Airflow uses UTC)
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=10)},
    tags=["mf-lakehouse"],
) as dag:
    start = PythonOperator(task_id="start_bronze_job", python_callable=start_bronze_job)
    wait = PythonOperator(task_id="wait_for_bronze_job", python_callable=wait_for_bronze_job)
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{DBT_BIN} build --project-dir {DBT_PROJECT} --profiles-dir {DBT_PROJECT}",
    )

    start >> wait >> dbt_build
