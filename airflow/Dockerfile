FROM apache/airflow:2.10.5-python3.12

# Both virtualenvs are created as root (the default user cannot write to /opt),
# then we switch back to the Airflow user for running the containers.
# /opt/dbt-venv : dbt with the Databricks adapter (same version as the local project)
# /opt/mf-venv  : the extractors and uploaders in src/ (same packages as pyproject.toml,
#                 without the notebook-only matplotlib and seaborn)
USER root
RUN python -m venv /opt/dbt-venv \
 && /opt/dbt-venv/bin/pip install --no-cache-dir dbt-databricks==1.13.0 \
 && python -m venv /opt/mf-venv \
 && /opt/mf-venv/bin/pip install --no-cache-dir \
      "boto3>=1.43.123" \
      "databricks-sdk>=0.117.0" \
      "numpy>=2.5.4" \
      "openpyxl>=3.1.5" \
      "pandas>=3.1.0" \
      "psycopg[binary]>=3.3.6" \
      "pyarrow>=26.0.0" \
      "python-dotenv>=1.2.4" \
      "requests>=2.34.2" \
      "xlrd>=2.0.2" \
      "yfinance>=1.7.0" \
      "databricks-sql-connector>=4.4.0" \
      "sqlalchemy>=2.0"
USER airflow
