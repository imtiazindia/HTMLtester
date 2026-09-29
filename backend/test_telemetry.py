import io
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch
import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).parent))
import api
from converters import stream_process
from telemetry import read_archive, save_log, log_record
import worker

class Store:
    def __init__(self): self.objects = {}; self.version = 0; self.conflict = None
    def get_object(self, Bucket, Key):
        if (Bucket,Key) not in self.objects: raise ClientError({'Error':{'Code':'NoSuchKey'}},'GetObject')
        body, etag = self.objects[Bucket,Key]
        return {'Body':io.BytesIO(body), 'ETag':etag}
    def put_object(self, Bucket, Key, Body, **kwargs):
        if self.conflict:
            callback, self.conflict = self.conflict, None
            callback()
        existing = self.objects.get((Bucket,Key))
        if (kwargs.get('IfNoneMatch')=='*' and existing) or ('IfMatch' in kwargs and (not existing or existing[1]!=kwargs['IfMatch'])):
            raise ClientError({'Error':{'Code':'PreconditionFailed'}},'PutObject')
        self.version += 1
        self.objects[Bucket,Key] = (Body.encode() if isinstance(Body,str) else Body, str(self.version))

def record(ident, created=1, revision=1):
    return log_record(ident, {'engine':'docling','status':'running','created':created,'revision':revision,
                              'events':[{'time':'now','message':f'Event {revision}'}]})

def test_retention_and_late_worker_cannot_resurrect_evicted_log():
    store = Store()
    for n in range(4): save_log(store,'logs','owner',record(str(n),n),create=True)
    assert [item['id'] for item in read_archive(store,'logs','owner')[0]] == ['3','2','1']
    assert not save_log(store,'logs','owner',record('0',0,5))
    assert len(read_archive(store,'logs','owner')[0]) == 3
    assert read_archive(store,'logs','other-user')[0] == []

def test_conditional_write_retries_preserve_concurrent_save():
    store = Store()
    save_log(store,'logs','owner',record('first'),create=True)
    store.conflict = lambda: save_log(store,'logs','owner',record('concurrent',2),create=True)
    save_log(store,'logs','owner',record('last',3),create=True)
    assert {item['id'] for item in read_archive(store,'logs','owner')[0]} == {'first','concurrent','last'}

def test_older_snapshot_does_not_replace_newer_events():
    store = Store()
    save_log(store,'logs','owner',record('one',revision=9),create=True)
    save_log(store,'logs','owner',record('one',revision=2),create=True)
    assert read_archive(store,'logs','owner')[0][0]['revision']==9

def test_streams_output_before_exit_and_captures_stderr():
    events = []
    started = time.monotonic()
    code = stream_process([sys.executable,'-u','-c',"import time,sys; print('first',flush=True); time.sleep(.6); print('last',file=sys.stderr)"],lambda line:events.append((time.monotonic(),line)))
    ended = time.monotonic()
    assert code == 0
    assert [line for _,line in events] == ['first','last']
    assert events[0][0]-started < ended-started-.3

def test_stream_timeout_kills_child():
    with pytest.raises(TimeoutError):
        stream_process([sys.executable,'-c','import time; time.sleep(10)'],lambda line:None,timeout=.1)

def test_log_read_scoped_to_user_and_rejects_traversal(monkeypatch):
    monkeypatch.setenv('DATA_BUCKET','data'); monkeypatch.setenv('LOG_BUCKET','logs')
    store = Store()
    save_log(store,'logs','victim',record('a'*32),create=True)
    event = {'requestContext':{'authorizer':{'jwt':{'claims':{'sub':'reader'}}}},'routeKey':'GET /logs/{id}','pathParameters':{'id':'a'*32}}
    with patch('api.boto3.client',return_value=store):
        assert api.handler(event,None)['statusCode']==404
        event['pathParameters']['id']='../victim'
        assert api.handler(event,None)['statusCode']==400

def test_save_catches_worker_finish_between_initial_read_and_archive_write(monkeypatch):
    monkeypatch.setenv('DATA_BUCKET','data'); monkeypatch.setenv('LOG_BUCKET','logs')
    store = Store(); ident='b'*32
    state={'engine':'docling','status':'running','created':1,'revision':1,'events':[]}
    store.put_object(Bucket='data',Key=f'owner/jobs/{ident}/status.json',Body=json.dumps(state))
    def finish():
        state.update(status='complete',revision=2)
        store.put_object(Bucket='data',Key=f'owner/jobs/{ident}/status.json',Body=json.dumps(state))
    store.conflict = finish
    event={'requestContext':{'authorizer':{'jwt':{'claims':{'sub':'owner'}}}},'routeKey':'POST /jobs/{id}/log','pathParameters':{'id':ident},'body':'{}'}
    with patch('api.boto3.client',return_value=store): assert api.handler(event,None)['statusCode']==200
    assert read_archive(store,'logs','owner')[0][0]['status']=='complete'

def test_archive_outage_does_not_cancel_conversion(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setenv('DATA_BUCKET','data'); monkeypatch.setenv('LOG_BUCKET','logs')
    storage = MagicMock()
    with patch('worker.boto3.client',return_value=storage), patch('worker.save_log',side_effect=RuntimeError('archive offline')), patch('worker.convert',return_value={'pages':1,'seconds':1,'bytes':10}):
        result=worker.handler({'prefix':'owner/jobs/'+'c'*32,'sourceKey':'source','engine':'docling','created':1},None)
    assert result['status']=='complete'
    assert result['logError']
    storage.upload_file.assert_called_once()
