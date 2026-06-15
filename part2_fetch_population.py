"""
Part 2: Fetch US population data from the DataUSA API and save as JSON to S3.
"""

import json
import os
import logging
import boto3
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

class population_fetch:

    def __init__(self, API_URL=None, S3_BUCKET=None, S3_KEY=None, HEADERS=None):
        self.API_URL = API_URL or (
            "https://honolulu-api.datausa.io/tesseract/data.jsonrecords"
            "?cube=acs_yg_total_population_1"
            "&drilldowns=Year%2CNation"
            "&locale=en"
            "&measures=Population"
        )


        self.S3_BUCKET = S3_BUCKET or os.environ.get("S3_BUCKET", "kumarvik-data-quest-bucket")
        self.S3_KEY = S3_KEY or os.environ.get("S3_POPULATION_KEY", "population/us_population.json")


    def fetch_population(self) -> dict:
        """Fetch data from the DataUSA API and return the parsed JSON."""
        log.info("Fetching population data from DataUSA API…")
        resp = requests.get(self.API_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        log.info("Fetched %d records.", len(data.get("data", [])))
        return data


    def save_to_s3(self, data: dict, bucket: str = None, key: str = None) -> None:
        """Serialize data as JSON and write it to S3."""
        s3 = boto3.client("s3")
        body = json.dumps(data, indent=2).encode("utf-8")
        s3.put_object(Bucket=bucket or self.S3_BUCKET, Key=key or self.S3_KEY, Body=body, ContentType="application/json")
        log.info("Saved to s3://%s/%s", bucket or self.S3_BUCKET, key or self.S3_KEY)


    def run(self) -> dict:
        bucket = self.S3_BUCKET
        key = self.S3_KEY
        data = self.fetch_population()
        self.save_to_s3(data, bucket, key)
        return data


if __name__ == "__main__":
    fetcher = population_fetch()
    fetcher.run()