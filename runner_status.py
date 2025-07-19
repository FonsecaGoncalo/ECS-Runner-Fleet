import os
import sys
import datetime
import boto3

TABLE_NAME = os.environ.get('RUNNER_TABLE')
REGION = os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION') or 'us-east-1'

if not TABLE_NAME:
    print('RUNNER_TABLE environment variable required', file=sys.stderr)
    sys.exit(1)

db = boto3.resource('dynamodb', region_name=REGION)
table = db.Table(TABLE_NAME)

runner_id = os.environ.get('RUNNER_ID') or os.uname().nodename


def update_status(status):
    table.put_item(Item={
        'runner_id': runner_id,
        'status': status,
        'timestamp': int(datetime.datetime.utcnow().timestamp())
    })

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: runner_status.py <status>', file=sys.stderr)
        sys.exit(1)
    update_status(sys.argv[1])
