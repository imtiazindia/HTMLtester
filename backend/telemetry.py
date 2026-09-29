"""Bounded live telemetry and an atomic, private archive of three log files."""
import json
import re
from datetime import datetime, timezone
from botocore.exceptions import ClientError

MAX_EVENTS = 500

def event_line(message):
    return {'time': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
            'message': re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', str(message))[:1000]}

def log_record(ident, state):
    lines = [f"HTMLtester | {state['engine']} | {ident}", f"Status: {state['status']}"]
    if state.get('droppedEvents'):
        lines.append(f"Earlier output omitted: {state['droppedEvents']} events (bounded log).")
    lines += [f"{item['time']}  {item['message']}" for item in state.get('events', [])]
    if state.get('error'): lines.append('ERROR: '+state['error'])
    return {'id':ident, 'created':state['created'], 'engine':state['engine'],
            'status':state['status'], 'revision':state.get('revision',0),
            'filename':f"{state['engine']}-{ident}.log", 'text':'\n'.join(lines)+'\n'}

def read_archive(s3, bucket, owner):
    try:
        result = s3.get_object(Bucket=bucket, Key=owner+'/logs.json')
        return json.loads(result['Body'].read()), result['ETag']
    except ClientError as error:
        if error.response['Error']['Code'] in ('NoSuchKey','404','NotFound'): return [], None
        raise

def save_log(s3, bucket, owner, record, create=False):
    # Conditional writes prevent two workers/tabs from losing updates or exceeding
    # retention. Evicted entries cannot be recreated by a still-running worker.
    for _ in range(8):
        records, etag = read_archive(s3, bucket, owner)
        existing = next((item for item in records if item['id']==record['id']), None)
        if not existing and not create: return False
        if existing and existing['revision'] > record['revision']: return True
        records = [item for item in records if item['id']!=record['id']] + [record]
        records = sorted(records, key=lambda item:(item['created'],item['id']), reverse=True)[:3]
        try:
            s3.put_object(Bucket=bucket, Key=owner+'/logs.json', Body=json.dumps(records),
                          ContentType='application/json', **({'IfMatch':etag} if etag else {'IfNoneMatch':'*'}))
            return any(item['id']==record['id'] for item in records)
        except ClientError as error:
            if error.response['Error']['Code'] not in ('PreconditionFailed','ConditionalRequestConflict','412','409'): raise
    raise RuntimeError('Log archive is busy. Please retry.')
