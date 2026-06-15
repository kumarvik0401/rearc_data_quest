# Rearc Data Quest – Solution
[text](https://github.com/rearc-data/quest)

Made use of Claude code free version (Sonnet 4.6 model) to get overall structure of the code.
Used prompts like: 
    * List S3 bucket using Python and add/delete file(s) to and from S3 bucket.
    * For Part4 - Used entire questions and asked Claude to provide a solution to automate execution using lambda function 
Refined the code as per the requirement.
While getting any error during execution, used ChatGpt to resolve error.
Have faced errors, getting connected to S3 bucket and listing files (It was first time dealing with S3 bucket). ChatGPT helped and got aws configure in my local machine (with aws cli installtion).



## Structure

```
rearc-quest/
├── part1_sync_bls_data.py      # Syncs BLS data to S3 (add/update/delete)
├── part2_fetch_population.py   # Fetches DataUSA population API → S3 JSON
├── part3_analysis.ipynb        # Pandas analytics (3 questions)
├── lambda - handler.py         # Combined Lambda (ingestion + analytics)
└── part4
    ├── app.py                # CDK app entrypoint
    └── cdk_stack.py          # Full pipeline stack
```

---

## Part 1 – BLS Sync

**Key design decisions:**
- Scrapes the BLS directory listing dynamically — no hard-coded filenames.
- Computes MD5 of each downloaded file and compares against the S3 ETag to skip unchanged files.
- Deletes S3 objects whose source files no longer exist on the BLS server.
- Includes a `User-Agent` header with contact info, which is required by BLS policy to avoid 403 errors.

---

## Part 2 – Population API

Saves the full API response as `population/us_population.json` in the S3 bucket.

---

## Part 3 – Analytics

Open `part3/analysis.ipynb` in Jupyter. Update `S3_BUCKET` in the first cell then run all cells.

### Q1 – Mean & Std of US Population (2013–2018)
Filters the population dataframe to years 2013–2018 inclusive and computes mean and standard deviation.

### Q2 – Best Year per series_id
Groups BLS quarterly records (Q01–Q04) by `series_id` and `year`, sums `value`, then picks the year with the highest sum for each series.

### Q3 – PRS30006032 / Q01 joined with Population
Filters BLS data to `series_id = PRS30006032` and `period = Q01`, then left-joins with the population dataframe on `year`.

---

## Part 4 – CDK Pipeline


### What gets created
| Resource | Purpose |
|---|---|
| S3 Bucket (versioned) | Stores BLS files + population JSON |
| Ingestion Lambda | Runs Part 1 + Part 2 daily at midnight UTC |
| EventBridge Rule | Daily cron trigger for Ingestion Lambda |
| SQS Queue + DLQ | Receives S3 notification when population JSON is written |
| Analytics Lambda | Triggered by SQS; logs Part 3 reports to CloudWatch |

---

## Notes
- The BLS `User-Agent` header is critical — without it 403 errors may occur.
- `pr.data.0.Current` is tab-separated and has leading/trailing whitespace in string columns — the analytics code trims these before filtering/joining.
- The CDK stack bundles the Lambda code with Docker; ensure Docker is running locally when deploying.
