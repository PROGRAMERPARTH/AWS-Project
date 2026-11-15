import sys, os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lambda"),
)

import pytest
import json
import boto3
from moto import mock_aws

from lambda_function import lambda_handler


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_s3_event(bucket, key):
    """Return a dict mimicking an S3 event notification."""
    return {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {
                        "name": bucket,
                        "arn": f"arn:aws:s3:::{bucket}",
                    },
                    "object": {
                        "key": key,
                    },
                },
            }
        ]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@mock_aws
def test_lambda_processes_order():
    """Lambda reads an order from S3, calculates 18% GST, writes a summary, and publishes to SNS."""
    # --- Setup S3 ---
    s3 = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3.create_bucket(Bucket=bucket)

    order_id = "ORD-20261115-210000-AB12"
    order_key = f"orders/{order_id}.json"
    order_data = {
        "order_id": order_id,
        "customer_name": "Alice",
        "subtotal": 12.50,
        "selected_items": ["Coffee", "Sandwich"],
        "status": "NEW",
    }
    s3.put_object(Bucket=bucket, Key=order_key, Body=json.dumps(order_data))

    # --- Setup SNS ---
    sns = boto3.client("sns", region_name="us-east-1")
    topic = sns.create_topic(Name="order-notifications")
    topic_arn = topic["TopicArn"]

    # --- Environment ---
    os.environ["S3_BUCKET_NAME"] = bucket
    os.environ["SNS_TOPIC_ARN"] = topic_arn
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"

    # --- Invoke Lambda ---
    event = make_s3_event(bucket, order_key)
    result = lambda_handler(event, None)

    # --- Verify summary written to S3 ---
    summary_key = f"order-summaries/{order_id}-summary.json"
    summary_obj = s3.get_object(Bucket=bucket, Key=summary_key)
    summary = json.loads(summary_obj["Body"].read().decode("utf-8"))

    assert summary["gst_rate"] == 18
    assert summary["gst_amount"] == 2.25
    assert summary["final_total"] == 14.75
    assert summary["order_status"] == "PROCESSED"


@mock_aws
def test_gst_calculation():
    """Verify GST math: subtotal 20.0 -> gst 3.6 -> total 23.6."""
    # --- Setup S3 ---
    s3 = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3.create_bucket(Bucket=bucket)

    order_id = "ORD-20261115-213000-CD34"
    order_key = f"orders/{order_id}.json"
    order_data = {
        "order_id": order_id,
        "customer_name": "Bob",
        "subtotal": 20.0,
        "selected_items": ["Burger", "Juice"],
        "status": "NEW",
    }
    s3.put_object(Bucket=bucket, Key=order_key, Body=json.dumps(order_data))

    # --- Setup SNS ---
    sns = boto3.client("sns", region_name="us-east-1")
    topic = sns.create_topic(Name="order-notifications")
    topic_arn = topic["TopicArn"]

    # --- Environment ---
    os.environ["S3_BUCKET_NAME"] = bucket
    os.environ["SNS_TOPIC_ARN"] = topic_arn
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"

    # --- Invoke Lambda ---
    event = make_s3_event(bucket, order_key)
    lambda_handler(event, None)

    # --- Verify GST math ---
    summary_key = f"order-summaries/{order_id}-summary.json"
    summary_obj = s3.get_object(Bucket=bucket, Key=summary_key)
    summary = json.loads(summary_obj["Body"].read().decode("utf-8"))

    assert summary["gst_rate"] == 18
    assert summary["gst_amount"] == 3.6
    assert summary["final_total"] == 23.6


@mock_aws
def test_skip_non_order_files():
    """Lambda should gracefully handle (skip) events for non-order files."""
    # --- Setup S3 ---
    s3 = boto3.client("s3", region_name="us-east-1")
    bucket = "test-bucket"
    s3.create_bucket(Bucket=bucket)

    s3.put_object(Bucket=bucket, Key="other/file.json", Body=json.dumps({"data": "irrelevant"}))

    # --- Setup SNS (in case lambda tries to use it) ---
    sns = boto3.client("sns", region_name="us-east-1")
    topic = sns.create_topic(Name="order-notifications")
    topic_arn = topic["TopicArn"]

    # --- Environment ---
    os.environ["S3_BUCKET_NAME"] = bucket
    os.environ["SNS_TOPIC_ARN"] = topic_arn
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"

    # --- Invoke Lambda with a non-order key ---
    event = make_s3_event(bucket, "other/file.json")
    # Should return without raising an exception
    result = lambda_handler(event, None)

    # Verify no summary was written for this non-order file
    response = s3.list_objects_v2(Bucket=bucket, Prefix="order-summaries/")
    assert response.get("KeyCount", 0) == 0
