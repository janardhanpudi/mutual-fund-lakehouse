# Databricks notebook source
# Bronze ingestion: Auto Loader loads new (or overwritten) Parquet files from the Volume into Delta tables.

from pyspark.sql import functions as F

CATALOG = "mf_lakehouse"
LANDING = f"/Volumes/{CATALOG}/bronze/raw_landing"
STATE = f"/Volumes/{CATALOG}/bronze/autoloader_state"
SOURCES = ["nav", "index_prices", "aum", "ter", "scheme_master_cdc"]


def ingest(source: str) -> int:
    table = f"{CATALOG}.bronze.{source}"
    (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"{STATE}/{source}/schema")
        .option("cloudFiles.partitionColumns", "")      # folder names are already columns in the files
        .option("cloudFiles.allowOverwrites", "true")   # re-load files our extractors overwrite
        .load(f"{LANDING}/{source}/")
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_file_modified_at", F.col("_metadata.file_modification_time"))
        .withColumn("_bronze_loaded_at", F.current_timestamp())
        .writeStream
        .option("checkpointLocation", f"{STATE}/{source}/checkpoint")
        .trigger(availableNow=True)
        .toTable(table)
        .awaitTermination()
    )
    return spark.table(table).count()


for source in SOURCES:
    print(f"{source:<14} {ingest(source):>8} rows in bronze")