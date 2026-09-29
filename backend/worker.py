import json
import os
from pathlib import Path
import tempfile
import time
import traceback
import boto3
from converters import convert
from telemetry import event_line, log_record, save_log, MAX_EVENTS

def handler(event, context):
    if 'Records' in event:
        for record in event['Records']:
            handler(json.loads(record['body']), context)
        return {'status': 'processed'}
    s3 = boto3.client('s3')
    bucket = os.environ['DATA_BUCKET']
    prefix = event['prefix']
    state = {'engine': event['engine'], 'status': 'running', 'created': event['created'],
             'events':event.get('events',[]), 'revision':0}
    last_save = 0
    def save():
        nonlocal last_save
        try:
            save_log(s3, os.environ['LOG_BUCKET'], prefix.split('/')[0], log_record(prefix.split('/')[-1],state))
            state.pop('logError', None)
        except Exception as error:
            # Recording must not cancel an otherwise valid PDF conversion.
            print('Saved log update unavailable:', type(error).__name__)
            state['logError'] = 'The saved log could not be updated. Conversion continues; select Log again after completion.'
        s3.put_object(Bucket=bucket, Key=prefix+'/status.json', Body=json.dumps(state), ContentType='application/json')
        last_save = time.monotonic()
    def emit(message):
        state['events'].append(event_line(message))
        state['revision'] += 1
        if len(state['events']) > MAX_EVENTS:
            state['events'].pop(0)
            state['droppedEvents'] = state.get('droppedEvents',0)+1
        if time.monotonic()-last_save >= 2: save()
    try:
        emit('Worker started. Downloading the uploaded PDF.')
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'source.pdf', Path(directory)/'result.html'
            s3.download_file(bucket, event['sourceKey'], str(source))
            emit('PDF downloaded. Validating document.')
            metrics = convert(source, output, event['engine'], emit)
            emit('Uploading converted HTML.')
            s3.upload_file(str(output), bucket, prefix+'/result.html', ExtraArgs={'ContentType':'text/html; charset=utf-8'})
            state.update(metrics, status='complete', completed=int(time.time()))
            emit('Conversion complete. HTML is ready to view and download.')
    except Exception as error:
        traceback.print_exc()
        message = str(error) if isinstance(error, (ValueError, RuntimeError, TimeoutError)) else f'PDF processing failed ({type(error).__name__}). The server log contains diagnostic details.'
        state.update(status='failed', error=message)
        emit('Conversion failed: '+message)
    save()
    return state
