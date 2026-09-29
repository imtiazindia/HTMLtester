import json
import os
from pathlib import Path
import tempfile
import time
import boto3
from converters import convert

def handler(event, context):
    if 'Records' in event:
        for record in event['Records']:
            handler(json.loads(record['body']), context)
        return {'status': 'processed'}
    s3 = boto3.client('s3')
    bucket = os.environ['DATA_BUCKET']
    prefix = event['prefix']
    state = {'engine': event['engine'], 'status': 'running', 'created': event['created']}
    def save():
        s3.put_object(Bucket=bucket, Key=prefix+'/status.json', Body=json.dumps(state), ContentType='application/json')
    save()
    try:
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'source.pdf', Path(directory)/'result.html'
            s3.download_file(bucket, event['sourceKey'], str(source))
            metrics = convert(source, output, event['engine'])
            s3.upload_file(str(output), bucket, prefix+'/result.html', ExtraArgs={'ContentType':'text/html; charset=utf-8'})
            state.update(metrics, status='complete', completed=int(time.time()))
    except Exception as error:
        print(type(error).__name__, str(error)[:1000])
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else 'Conversion failed or exceeded its time limit. Try a smaller document or another engine.'
        state.update(status='failed', error=message)
    save()
    return state
