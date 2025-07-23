import config

_table = None


def get_table():
    """Return cached DynamoDB table for runner state."""
    global _table
    if _table is None:
        if not config.RUNNER_TABLE:
            raise RuntimeError("RUNNER_TABLE environment variable not set")
        _table = config.dynamodb.Table(config.RUNNER_TABLE)
    return _table


def get_item(key):
    return get_table().get_item(Key=key).get("Item")


def put_item(item):
    get_table().put_item(Item=item)


def update_item(key, **kwargs):
    get_table().update_item(Key=key, **kwargs)


def delete_item(key):
    get_table().delete_item(Key=key)
