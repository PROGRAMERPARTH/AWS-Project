"""Cloud Café Order Processor - Flask Application."""

import json
import logging
import os
import random
import string
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
from flask import Flask, flash, jsonify, render_template, request

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

# In local dev without credentials, disable IMDS probing to avoid 10s timeout
if os.environ.get('FLASK_ENV') != 'production' and not (
    os.environ.get('AWS_ACCESS_KEY_ID') or os.environ.get('AWS_PROFILE')
):
    os.environ.setdefault('AWS_EC2_METADATA_DISABLED', 'true')

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
MENU_ITEMS = {
    'Coffee': 4.50,
    'Sandwich': 8.00,
    'Cake': 6.00,
    'Juice': 3.50,
    'Muffin': 3.00,
}

# ---------------------------------------------------------------------------
# AWS / S3
# ---------------------------------------------------------------------------
AWS_REGION = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', '')

s3_config = Config(
    connect_timeout=2,
    read_timeout=2,
    retries={'max_attempts': 1}
)
s3_client = boto3.client('s3', region_name=AWS_REGION, config=s3_config)


def _generate_order_id() -> str:
    """Return an order ID in the format ORD-YYYYMMDD-HHMMSS-XXXX."""
    now = datetime.now(timezone.utc)
    random_suffix = ''.join(
        random.choices(string.ascii_uppercase + string.digits, k=4)
    )
    return f"ORD-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{random_suffix}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/', methods=['GET'])
def index():
    """Render the order form."""
    return render_template('index.html', menu_items=MENU_ITEMS)


@app.route('/stats', methods=['GET'])
def stats():
    """Return JSON statistics for all saved orders."""
    order_count = 0
    total_amount = 0.0

    # 1. Read orders from S3 if configured
    if S3_BUCKET_NAME:
        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix='orders/'):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if key.endswith('.json'):
                        resp = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
                        data = json.loads(resp['Body'].read().decode('utf-8'))
                        order_count += 1
                        total_amount += float(data.get('subtotal', 0.0))
        except Exception as exc:  # noqa: BLE001
            logger.warning('Could not read stats from S3 (%s), checking local folder.', exc)

    # 2. Fallback / local orders check if S3 returned nothing
    if order_count == 0:
        local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.local_orders', 'orders')
        if os.path.exists(local_dir):
            for filename in os.listdir(local_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(local_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            order_count += 1
                            total_amount += float(data.get('subtotal', 0.0))
                    except Exception:  # noqa: BLE001
                        pass

    return jsonify({
        'order_count': order_count,
        'total_amount': round(total_amount, 2),
        'version': 'v2',
    })


@app.route('/order', methods=['POST'])
def place_order():
    """Validate the order, upload it to S3 and show the success page."""

    # --- Validate customer name -------------------------------------------
    customer_name = (request.form.get('customer_name') or '').strip()
    if not customer_name:
        flash('Please enter your name.', 'error')
        return render_template('index.html', menu_items=MENU_ITEMS)

    # --- Validate selected items ------------------------------------------
    selected_item_names = request.form.getlist('items')
    if not selected_item_names:
        flash('Please select at least one item.', 'error')
        return render_template('index.html', menu_items=MENU_ITEMS)

    # Build the list of selected items with prices
    selected_items = []
    for name in selected_item_names:
        if name in MENU_ITEMS:
            selected_items.append({'name': name, 'price': MENU_ITEMS[name]})

    if not selected_items:
        flash('Invalid items selected. Please try again.', 'error')
        return render_template('index.html', menu_items=MENU_ITEMS)

    # --- Build the order --------------------------------------------------
    subtotal = sum(item['price'] for item in selected_items)
    order_id = _generate_order_id()

    order = {
        'order_id': order_id,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'customer_name': customer_name,
        'selected_items': selected_items,
        'subtotal': float(subtotal),
        'status': 'NEW',
    }

    # --- Upload to S3 -----------------------------------------------------
    s3_key = f"orders/{order_id}.json"
    uploaded_to_s3 = False

    if S3_BUCKET_NAME:
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=json.dumps(order, indent=2),
                ContentType='application/json',
            )
            uploaded_to_s3 = True
            logger.info('Order %s uploaded to s3://%s/%s', order_id, S3_BUCKET_NAME, s3_key)
        except NoCredentialsError:
            logger.warning(
                'No AWS credentials found. Saving order %s locally in dev mode.', order_id
            )
        except (ClientError, EndpointConnectionError) as exc:
            logger.warning(
                'S3 upload unavailable (%s). Saving order %s locally in dev mode.', exc, order_id
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception('Unexpected error during S3 upload for %s: %s', order_id, exc)

    # Fallback to local storage when running in local development without AWS credentials
    if not uploaded_to_s3:
        local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.local_orders', 'orders')
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, f"{order_id}.json")
        with open(local_path, 'w', encoding='utf-8') as f:
            json.dump(order, f, indent=2)
        logger.info('Order %s saved locally at %s', order_id, local_path)

    # --- Render success page ----------------------------------------------
    return render_template(
        'success.html',
        order_id=order_id,
        customer_name=customer_name,
        items=selected_items,
        subtotal=subtotal,
        uploaded_to_s3=uploaded_to_s3,
    )


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
