"""Cloud Café Order Processor - Flask Application."""

import json
import logging
import os
import random
import string
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from flask import Flask, flash, render_template, request

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

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
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', '')

s3_client = boto3.client('s3', region_name=AWS_REGION)


def _generate_order_id() -> str:
    """Return an order ID in the format ORD-YYYYMMDD-HHMMSS-XXXX."""
    now = datetime.utcnow()
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
        'created_at': datetime.utcnow().isoformat(),
        'customer_name': customer_name,
        'selected_items': selected_items,
        'subtotal': float(subtotal),
        'status': 'NEW',
    }

    # --- Upload to S3 -----------------------------------------------------
    if not S3_BUCKET_NAME:
        logger.error('S3_BUCKET_NAME environment variable is not set.')
        flash('Server configuration error. Please contact the administrator.', 'error')
        return render_template('index.html', menu_items=MENU_ITEMS)

    s3_key = f"orders/{order_id}.json"
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=json.dumps(order, indent=2),
            ContentType='application/json',
        )
        logger.info('Order %s uploaded to s3://%s/%s', order_id, S3_BUCKET_NAME, s3_key)
    except ClientError as exc:
        logger.exception('Failed to upload order %s to S3: %s', order_id, exc)
        flash('Failed to upload your order. Please try again later.', 'error')
        return render_template('index.html', menu_items=MENU_ITEMS)
    except Exception as exc:  # noqa: BLE001
        logger.exception('Unexpected error uploading order %s: %s', order_id, exc)
        flash('An unexpected error occurred. Please try again later.', 'error')
        return render_template('index.html', menu_items=MENU_ITEMS)

    # --- Render success page ----------------------------------------------
    return render_template(
        'success.html',
        order_id=order_id,
        customer_name=customer_name,
        items=selected_items,
        subtotal=subtotal,
    )


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
