"""Small API Gateway handler. Authentication is enforced by the Cognito JWT authorizer."""
import json
import os
import re
import time
import uuid
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ENGINES = ['pdf2htmlEX', 'docling', 'opendataloader']
UUID = re.compile(r'^[a-f0-9]{32}$')

def response(code, data):
    return {'statusCode': code, 'headers': {'content-type':'application/json', 'cache-control':'no-store'}, 'body':json.dumps(data)}

def handler(event, context):
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
        owner = claims.get('sub')
        if not owner:
            return response(401, {'error':'Sign in to continue.'})
        region = os.environ.get('AWS_REGION', 'ap-south-1')
        s3 = boto3.client('s3', region_name=region, endpoint_url=f'https://s3.{region}.amazonaws.com',
                          config=Config(signature_version='s3v4', s3={'addressing_style':'virtual'}))
        bucket = os.environ['DATA_BUCKET']
        body = json.loads(event.get('body') or '{}')
        route = event['routeKey']
        if route == 'POST /uploads':
            size = body.get('size', 0)
            if not isinstance(size, int) or not 0 < size <= 20*1024*1024:
                return response(400, {'error':'Choose a PDF of at most 20 MB.'})
            ident = uuid.uuid4().hex
            key = f'{owner}/uploads/{ident}.pdf'
            upload = s3.generate_presigned_post(bucket, key,
                Fields={'Content-Type':'application/pdf'},
                Conditions=[['content-length-range', 1, 20*1024*1024], {'Content-Type':'application/pdf'}], ExpiresIn=900)
            return response(200, {'id':ident, 'upload':upload})
        if route == 'POST /jobs':
            upload, engine = body.get('uploadId',''), body.get('engine','')
            if not UUID.fullmatch(upload) or engine not in ENGINES:
                return response(400, {'error':'Invalid upload or converter.'})
            source_key = f'{owner}/uploads/{upload}.pdf'
            info = s3.head_object(Bucket=bucket, Key=source_key)
            if info['ContentLength'] > 20*1024*1024:
                return response(400, {'error':'PDF exceeds the file size limit.'})
            ident = uuid.uuid4().hex
            prefix = f'{owner}/jobs/{ident}'
            created = int(time.time())
            state = {'status':'queued','engine':engine,'created':created}
            s3.put_object(Bucket=bucket, Key=prefix+'/status.json', Body=json.dumps(state), ContentType='application/json')
            boto3.client('sqs').send_message(QueueUrl=os.environ['QUEUE_URL'],
                MessageBody=json.dumps({'prefix':prefix,'sourceKey':source_key,'engine':engine,'created':created}))
            return response(202, {'id':ident, **state})
        if route == 'GET /jobs/{id}':
            ident = event['pathParameters'].get('id','')
            if not UUID.fullmatch(ident):
                return response(400, {'error':'Invalid job.'})
            prefix = f'{owner}/jobs/{ident}'
            state = json.loads(s3.get_object(Bucket=bucket, Key=prefix+'/status.json')['Body'].read())
            if state['status'] in ('queued','running') and time.time()-state['created'] > 960:
                state.update(status='failed', error='The job timed out. Please try fewer pages.')
            if state['status'] == 'complete':
                state['url'] = s3.generate_presigned_url('get_object', Params={'Bucket':bucket,'Key':prefix+'/result.html'}, ExpiresIn=900)
            return response(200, state)
        return response(404, {'error':'Not found.'})
    except (ValueError, TypeError):
        return response(400, {'error':'Invalid request.'})
    except ClientError as error:
        code = error.response['Error']['Code']
        if code in ('NoSuchKey','404','NotFound'):
            return response(404, {'error':'File not found or expired. Upload it again.'})
        print('AWS request failed:', code)
        return response(503, {'error':'Service temporarily unavailable. Please retry.'})
