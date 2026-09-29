import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).parent))
import api
from converters import validate_pdf

def pdf(path, pages=1, password=None):
    writer = PdfWriter()
    for _ in range(pages): writer.add_blank_page(width=612, height=792)
    if password: writer.encrypt(password)
    writer.write(path)
    return path

def test_rejects_fake_pdf(tmp_path):
    path=tmp_path/'fake.pdf'; path.write_text('<html>Not a PDF</html>')
    with pytest.raises(ValueError, match='not a PDF'): validate_pdf(path)

def test_accepts_null_encryption_entry(tmp_path):
    path = pdf(tmp_path/'null-encryption.pdf')
    data = path.read_bytes()
    # Only the trailer changes, so all cross-reference offsets remain valid.
    before, trailer = data.rsplit(b'trailer', 1)
    path.write_bytes(before + b'trailer' + trailer.replace(b'/Root', b'/Encrypt null\n/Root', 1))
    assert validate_pdf(path) == 1


def test_rejects_encrypted_and_too_many_pages(tmp_path):
    with pytest.raises(ValueError, match='Password-protected'): validate_pdf(pdf(tmp_path/'locked.pdf',password='private'))
    with pytest.raises(ValueError, match='1–500'): validate_pdf(pdf(tmp_path/'large.pdf',pages=501))
    assert validate_pdf(pdf(tmp_path/'valid.pdf',pages=500)) == 500

def event(route, body=None, owner='owner-one', ident='a'*32):
    return {'requestContext':{'authorizer':{'jwt':{'claims':{'sub':owner} if owner else {}}}},'routeKey':route,'body':json.dumps(body or {}),'pathParameters':{'id':ident}}

def test_auth_is_required_before_any_aws_call():
    with patch('api.boto3.client') as client:
        assert api.handler(event('POST /uploads',owner=None),None)['statusCode']==401
        client.assert_not_called()

def test_output_is_always_scoped_to_authenticated_user(monkeypatch):
    monkeypatch.setenv('DATA_BUCKET','private-bucket')
    s3=MagicMock()
    s3.get_object.return_value={'Body':MagicMock(read=lambda: b'{"status":"failed","error":"test"}')}
    with patch('api.boto3.client',return_value=s3):
        result=api.handler(event('GET /jobs/{id}',{'owner':'victim'}),None)
    assert result['statusCode']==200
    s3.get_object.assert_called_once_with(Bucket='private-bucket',Key='owner-one/jobs/'+'a'*32+'/status.json')

@pytest.mark.parametrize('size',[0,-1,20*1024*1024+1,'1000'])
def test_upload_limits(monkeypatch,size):
    monkeypatch.setenv('DATA_BUCKET','private-bucket')
    with patch('api.boto3.client') as client:
        assert api.handler(event('POST /uploads',{'size':size}),None)['statusCode']==400
        client.return_value.generate_presigned_post.assert_not_called()

def test_job_rejects_path_traversal(monkeypatch):
    monkeypatch.setenv('DATA_BUCKET','private-bucket')
    with patch('api.boto3.client') as client:
        assert api.handler(event('POST /jobs',{'uploadId':'../../victim','engine':'docling'}),None)['statusCode']==400
        client.return_value.head_object.assert_not_called()
