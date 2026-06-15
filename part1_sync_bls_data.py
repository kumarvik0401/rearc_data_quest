"""
Part 1: Sync BLS time-series data from https://download.bls.gov/pub/time.series/pr/
to an AWS S3 bucket, keeping files in sync (add/update/delete).
"""

import os
import hashlib
import logging
import boto3
import requests
from bs4 import BeautifulSoup
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

class bls_sync:

    def __init__(self, BLS_BASE_URL=None, S3_BUCKET=None, S3_PREFIX=None, HEADERS=None):
            

        self.BLS_BASE_URL = BLS_BASE_URL or "https://download.bls.gov/pub/time.series/pr/"
        self.S3_BUCKET = S3_BUCKET or os.environ.get("S3_BUCKET", "kumarvik-data-quest-bucket")
        self.S3_PREFIX = S3_PREFIX or os.environ.get("S3_PREFIX", "bls/pr/")

        # BLS requires a User-Agent with contact info to avoid 403 errors.
        self.HEADERS = HEADERS or {
            "User-Agent": (
                "DataQuestSyncBot/1.0 "
                "(contact: kumarvik0401@gmail.com; "
                "purpose: academic/non-commercial sync of BLS public data)"
            )
        }


    def list_bls_files(self) -> dict[str, str]:
        """Scrape the BLS directory listing and return {filename: url}."""
        resp = requests.get(self.BLS_BASE_URL, headers=self.HEADERS, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        files: dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            # Skip parent-directory links and directory links
            if a.get_text() == "[To Parent Directory]" or href.startswith("?") or href=="/": #href.startswith("/") or href.endswith("/"):
                continue
            files[a.get_text()] = self.BLS_BASE_URL + a.get_text() # href
            # print("href: ", href)
            # print("a: ", a.get_text())
            
        
        log.info("Found %d files on BLS server.", len(files))
        return files


    def md5_of_bytes(self, data: bytes) -> str:
        return hashlib.md5(data).hexdigest()


    def list_s3_files(self, s3, bucket: str, prefix: str) -> dict[str, str]:
        """Return {s3_key: etag_without_quotes} for all objects under prefix."""
        paginator = s3.get_paginator("list_objects_v2")
        result: dict[str, str] = {}
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                etag = obj["ETag"].strip('"')
                result[obj["Key"]] = etag
        log.info("Found %d objects in s3://%s/%s", len(result), bucket, prefix)
        return result


    def download_file(self, url: str) -> bytes:
        resp = requests.get(url, headers=self.HEADERS, timeout=60)
        resp.raise_for_status()
        return resp.content


    def upload_to_s3(self, s3, bucket: str, key: str, data: bytes) -> None:
        s3.put_object(Bucket=bucket, Key=key, Body=data)
        log.info("Uploaded s3://%s/%s", bucket, key)


    def delete_from_s3(self, s3, bucket: str, key: str) -> None:
        s3.delete_object(Bucket=bucket, Key=key)
        log.info("Deleted s3://%s/%s", bucket, key)


    def sync(self) -> None:
        bucket = self.S3_BUCKET
        prefix = self.S3_PREFIX
        s3 = boto3.client("s3")

        bls_files = self.list_bls_files()           # {filename: url}
        s3_objects = self.list_s3_files(s3, bucket, prefix)  # {s3_key: etag}
        #print("S3 objects: ", s3_objects)

        uploaded = deleted = skipped = 0

        # --- Upload new or changed files ---
        for filename, url in bls_files.items():
            s3_key = prefix + filename
            data = self.download_file(url)
            local_md5 = self.md5_of_bytes(data)

            existing_etag = s3_objects.get(s3_key)
            if existing_etag and existing_etag == local_md5:
                log.debug("Skipping unchanged file: %s", filename)
                skipped += 1
                continue

            self.upload_to_s3(s3, bucket, s3_key, data)
            uploaded += 1

        # --- Delete files removed from BLS ---
        bls_keys = {prefix + f for f in bls_files}
        for s3_key in list(s3_objects):
            if s3_key not in bls_keys:
                self.delete_from_s3(s3, bucket, s3_key)
                deleted += 1

        log.info(
            "Sync complete — uploaded: %d, deleted: %d, skipped (unchanged): %d",
            uploaded, deleted, skipped,
        )


if __name__ == "__main__":
    bls_sync_instance = bls_sync()
    bls_sync_instance.sync()
    # bls_file=list_bls_files()
    # print("bls_files: ", bls_file)
    # download_file(bls_file["/pub/time.series/pr/pr.data.0.Current"])
    # list_s3_files()
