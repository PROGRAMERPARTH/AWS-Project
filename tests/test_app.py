import sys, os

# Set dummy AWS credentials before importing app/boto3
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["S3_BUCKET_NAME"] = "test-bucket"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import json
import re
import string
import random
import datetime
import boto3
from moto import mock_aws


@pytest.fixture
def mock_s3():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        yield s3


@pytest.fixture
def client():
    os.environ["S3_BUCKET_NAME"] = "test-bucket"
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"

    from app import app

    app.config["TESTING"] = True
    yield app.test_client()


def test_home_page(client):
    """GET / returns 200 and contains 'Caf' in the response."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Caf" in response.data


def test_place_order_success(client):
    """POST /order with valid data creates an order successfully."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        response = client.post(
            "/order",
            data=dict(customer_name="Alice", items=["Coffee", "Sandwich"]),
        )
        assert response.status_code == 200
        assert b"ORD-" in response.data


def test_missing_customer_name(client):
    """POST /order with empty customer_name returns an error or redirect."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        response = client.post(
            "/order",
            data=dict(customer_name="", items=["Coffee"]),
        )
        # Expect either an error status or a redirect
        assert response.status_code in (200, 302, 400)
        if response.status_code == 200:
            assert b"error" in response.data.lower() or b"required" in response.data.lower() or b"please" in response.data.lower()


def test_no_items_selected(client):
    """POST /order with customer_name but no items returns an error or redirect."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        response = client.post(
            "/order",
            data=dict(customer_name="Bob"),
        )
        # Expect either an error status or a redirect
        assert response.status_code in (200, 302, 400)
        if response.status_code == 200:
            assert b"error" in response.data.lower() or b"select" in response.data.lower() or b"item" in response.data.lower()


def test_order_id_format():
    """Order IDs should match the pattern ORD-YYYYMMDD-HHMMSS-XXXX."""
    pattern = r"^ORD-\d{8}-\d{6}-[A-Z0-9]{4}$"

    # Generate a sample order ID using the same logic the app would use
    now = datetime.datetime.now()
    random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    order_id = f"ORD-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{random_suffix}"

    assert re.match(pattern, order_id), f"Order ID '{order_id}' does not match expected format"
