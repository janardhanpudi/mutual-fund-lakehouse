"""Daily mutual fund pipeline.

  1. extract NAV, index prices and TER from the sources into data/landing
  2. upload the landing files to S3 (archive) and to the Databricks Volume
  3. start the bronze_ingest Databricks job, and wait until it finishes
  4. check that the bronze data is fresh
  5. dbt build (silver -> gold, with tests)
"""

import os
import time
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

MF_PYTHON = "/opt/mf-venv/bin/python"      # the extractors and uploaders (src/)
DBT_BIN = "/opt/dbt-venv/bin/dbt"          # dbt with the Databricks adapter
DBT_PROJECT = "/opt/airflow/dbt_mf"
POLL_SECONDS = 30
TIMEOUT_SECONDS = 60 * 60


def _module(name: str) -> str:
    """Run one module from src/ (PYTHONPATH is set in docker-compose.yml)."""
    return f"{MF_PYTHON} -m {name}"


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
    ti.xcom_push(key="run_id", value=resp.json()["run_id"])


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
    description="Extract, upload, load to Databricks, check freshness, dbt build",
    start_date=datetime(2026, 1, 1),
    schedule="0 17 * * *",  # 17:00 UTC = 22:30 IST every day (Airflow uses UTC)
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=10)},
    tags=["mf-lakehouse"],
) as dag:
    extract_nav = BashOperator(
        task_id="extract_nav", bash_command=_module("mf_lakehouse.extract.nav")
    )
    extract_index = BashOperator(
        task_id="extract_index_prices", bash_command=_module("mf_lakehouse.extract.index_prices")
    )
    extract_ter = BashOperator(
        task_id="extract_ter", bash_command=_module("mf_lakehouse.extract.ter")
    )
    upload_s3 = BashOperator(
        task_id="upload_s3", bash_command=_module("mf_lakehouse.common.s3")
    )
    upload_volume = BashOperator(
        task_id="upload_volume", bash_command=_module("mf_lakehouse.common.volume")
    )
    start = PythonOperator(task_id="start_bronze_job", python_callable=start_bronze_job)
    wait = PythonOperator(task_id="wait_for_bronze_job", python_callable=wait_for_bronze_job)
    freshness = BashOperator(
        task_id="dbt_source_freshness",
        bash_command=f"{DBT_BIN} source freshness --target prod --project-dir {DBT_PROJECT} --profiles-dir {DBT_PROJECT}",
    )
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{DBT_BIN} build --target prod --project-dir {DBT_PROJECT} --profiles-dir {DBT_PROJECT}",
    )

    extract_nav >> extract_index >> extract_ter >> upload_s3 >> upload_volume
    upload_volume >> start >> wait >> freshness >> dbt_build
