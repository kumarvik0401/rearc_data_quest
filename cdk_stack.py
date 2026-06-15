"""
Part 4: AWS CDK Stack – Data Pipeline
Provisions: S3 bucket, daily Lambda (Part 1+2), SQS queue, S3→SQS notification,
            analytics Lambda (Part 3) triggered by SQS.
"""

from aws_cdk import (
    Duration,
    Stack,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_sqs as sqs,
    aws_lambda_event_sources as event_sources,
    RemovalPolicy,
)
from constructs import Construct


class RearcQuestStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # S3 Bucket                                                            #
        # ------------------------------------------------------------------ #
        bucket = s3.Bucket(
            self,
            "kumarvik-data-quest-bucket",
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ------------------------------------------------------------------ #
        # SQS Queue (receives S3 event when population JSON is written)       #
        # ------------------------------------------------------------------ #
        dlq = sqs.Queue(
            self,
            "AnalyticsDLQ",
            retention_period=Duration.days(14),
        )

        queue = sqs.Queue(
            self,
            "PopulationQueue",
            visibility_timeout=Duration.minutes(15),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=dlq),
        )

        # ------------------------------------------------------------------ #
        # Lambda layer / shared env vars                                       #
        # ------------------------------------------------------------------ #
        common_env = {
            "S3_BUCKET":        "kumarvik-data-quest-bucket",
            "BLS_PREFIX":       "bls/pr/",
            "POPULATION_KEY":   "population/us_population.json",
            "CONTACT_EMAIL":    "kumarvik0401@gmail.com", 
        }

        lambda_code = lambda_.Code.from_asset(
            "../lambda",
            bundling={
                "image": lambda_.Runtime.PYTHON_3_12.bundling_image,
                "command": [
                    "bash", "-c",
                    "pip install -r requirements.txt -t /asset-output && cp -r . /asset-output",
                ],
            },
        )

        # ------------------------------------------------------------------ #
        # Ingestion Lambda (Part 1 + Part 2) – runs daily                     #
        # ------------------------------------------------------------------ #
        ingestion_fn = lambda_.Function(
            self,
            "IngestionFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_code,
            timeout=Duration.minutes(15),
            memory_size=512,
            environment=common_env,
        )

        bucket.grant_read_write(ingestion_fn)

        # Daily schedule (midnight UTC)
        events.Rule(
            self,
            "DailySchedule",
            schedule=events.Schedule.cron(minute="0", hour="0"),
            targets=[targets.LambdaFunction(ingestion_fn)],
        )

        # ------------------------------------------------------------------ #
        # S3 → SQS notification when population JSON is put                   #
        # ------------------------------------------------------------------ #
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.SqsDestination(queue),
            s3.NotificationKeyFilter(prefix="population/", suffix=".json"),
        )

        # ------------------------------------------------------------------ #
        # Analytics Lambda (Part 3) – triggered by SQS                        #
        # ------------------------------------------------------------------ #
        analytics_fn = lambda_.Function(
            self,
            "AnalyticsFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_code,
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment=common_env,
        )

        bucket.grant_read(analytics_fn)

        analytics_fn.add_event_source(
            event_sources.SqsEventSource(queue, batch_size=1)
        )

        # ------------------------------------------------------------------ #
        # Output bucket name for reference                                     #
        # ------------------------------------------------------------------ #
        from aws_cdk import CfnOutput
        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "QueueUrl",   value=queue.queue_url)
