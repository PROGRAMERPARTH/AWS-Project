import json
import logging
import os
from datetime import datetime

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
sns_client = boto3.client('sns')


def lambda_handler(event, context):
    """AWS Lambda handler triggered by S3 events to process Cloud Café orders."""
    try:
        # Extract bucket and key from the S3 event
        s3_event = event['Records'][0]['s3']
        bucket = s3_event['bucket']['name']
        key = s3_event['object']['key']

        logger.info(f"Processing file: s3://{bucket}/{key}")

        # Skip if key doesn't start with 'orders/' or doesn't end with '.json'
        if not key.startswith('orders/') or not key.endswith('.json'):
            logger.info(f"Skipping non-order file: {key}")
            return {
                'statusCode': 200,
                'body': 'Skipped: not an order file'
            }

        # Read order JSON from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        order_data = json.loads(response['Body'].read().decode('utf-8'))

        logger.info(f"Order data loaded: {json.dumps(order_data)}")

        order_id = order_data['order_id']
        customer_name = order_data['customer_name']
        subtotal = order_data['subtotal']

        # Calculate GST and final total
        gst_amount = round(subtotal * 0.18, 2)
        final_total = round(subtotal + gst_amount, 2)

        # Build order summary
        summary = {
            'order_id': order_id,
            'customer_name': customer_name,
            'subtotal': subtotal,
            'gst_rate': 18,
            'gst_amount': gst_amount,
            'final_total': final_total,
            'processed_at': datetime.utcnow().isoformat(),
            'order_status': 'PROCESSED'
        }

        logger.info(f"Order summary: {json.dumps(summary)}")

        # Write summary to S3
        summary_key = f"order-summaries/{order_id}-summary.json"
        s3_client.put_object(
            Bucket=bucket,
            Key=summary_key,
            Body=json.dumps(summary, indent=2),
            ContentType='application/json'
        )

        logger.info(f"Summary written to s3://{bucket}/{summary_key}")

        # Publish to SNS topic
        sns_topic_arn = os.environ['SNS_TOPIC_ARN']
        sns_message = (
            f"Order Processed Successfully!\n"
            f"---------------------------\n"
            f"Order ID: {order_id}\n"
            f"Customer: {customer_name}\n"
            f"Subtotal: ₹{subtotal}\n"
            f"GST (18%): ₹{gst_amount}\n"
            f"Total: ₹{final_total}\n"
        )

        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=f"Order Processed: {order_id}",
            Message=sns_message
        )

        logger.info(f"SNS notification sent for order: {order_id}")

        return {
            'statusCode': 200,
            'body': 'Order processed successfully'
        }

    except Exception as e:
        logger.error(f"Error processing order: {str(e)}", exc_info=True)
        raise
