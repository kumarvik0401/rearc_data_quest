"""
Lambda handler that runs Part 1 (BLS sync) and Part 2 (population fetch).
Triggered on a daily CloudWatch Events / EventBridge schedule.

Also handles the SQS trigger (from S3 → SQS notifications) to run Part 3 reports.
"""

import io
import json
import logging
import os

import boto3
import pandas as pd
import requests
from bs4 import BeautifulSoup
import hashlib
from part1_sync_bls_data import bls_sync #bls to S2 sync
from part2_fetch_population import population_fetch #population fetch to S3

log = logging.getLogger()
log.setLevel(logging.INFO)

S3_BUCKET       = os.environ.get("S3_BUCKET","kumarvik-data-quest-bucket")
BLS_PREFIX      = os.environ.get("BLS_PREFIX", "bls/pr/")
POPULATION_KEY  = os.environ.get("POPULATION_KEY", "population/us_population.json")
BLS_BASE_URL    = "https://download.bls.gov/pub/time.series/pr/"
POPULATION_URL  = (
    "https://honolulu-api.datausa.io/tesseract/data.jsonrecords"
    "?cube=acs_yg_total_population_1&drilldowns=Year%2CNation&locale=en&measures=Population"
)
HEADERS = {
    "User-Agent": (
        "DataQuestLambda/1.0 "
        f"(contact: {os.environ.get('CONTACT_EMAIL', 'kumarvik0401@gmail.com')})"
    )
}

s3 = boto3.client("s3")


# ---------------------------------------------------------------------------
# Part 3 – Reports (triggered from SQS → S3 event)
# ---------------------------------------------------------------------------

def _load_bls() -> pd.DataFrame:
    key = BLS_PREFIX + "pr.data.0.Current"
    obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()), sep="\t")
    df.rename(columns=lambda c: c.strip(), inplace=True)
    str_cols = df.select_dtypes("object").columns
    df[str_cols] = df[str_cols].apply(lambda c: c.str.strip())
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def _load_population() -> pd.DataFrame:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=POPULATION_KEY)
    data = json.loads(obj["Body"].read())
    df = pd.DataFrame(data["data"])
    df["Year"] = df["Year"].astype(int)
    return df


def run_reports() -> None:
    log.info("=== Part 3: Analytics reports ===")
    bls_df = _load_bls()
    pop_df = _load_population()

    # Q1 – mean / std population 2013-2018
    pop_filt = pop_df[pop_df["Year"].between(2013, 2018)]
    log.info(
        "Q1 | Population 2013-2018 → mean=%.0f  std=%.0f",
        pop_filt["Population"].mean(),
        pop_filt["Population"].std(),
    )

    # Q2 – best year per series_id
    quarterly = bls_df[bls_df["period"].str.match(r"^Q0[1-4]$")]
    yearly = quarterly.groupby(["series_id", "year"])["value"].sum().reset_index(name="value")
    best = yearly.loc[yearly.groupby("series_id")["value"].idxmax()].reset_index(drop=True)
    log.info("Q2 | Best-year report (first 5 rows):\n%s", best.head(5).to_string(index=False))

    # Q3 – PRS30006032 / Q01 + population
    target = bls_df[(bls_df["series_id"] == "PRS30006032") & (bls_df["period"] == "Q01")].copy()
    target["year"] = target["year"].astype(int)
    report = target.merge(pop_df[["Year", "Population"]], left_on="year", right_on="Year", how="left")
    log.info(
        "Q3 | PRS30006032 Q01 report:\n%s",
        report[["series_id", "year", "period", "value", "Population"]].to_string(index=False),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    # SQS trigger from S3 → run analytics only
    if "Records" in event and event["Records"][0].get("eventSource") == "aws:sqs":
        run_reports()
        return {"status": "reports_done"}

    # Scheduled trigger → run ingestion
    log.info("=== Starting daily ingestion (BLS sync + population fetch) ===")
    bls_sync(BLS_BASE_URL, S3_BUCKET, BLS_PREFIX, HEADERS).sync()  # call the sync method of bls_sync class
    population_fetch(POPULATION_URL, S3_BUCKET, POPULATION_KEY, HEADERS).run() # call the run method of population_fetch class
    log.info("=== Ingestion complete ===")
    return {"status": "ingestion_done"}


# lambda_handler({}, {})  # for local testing