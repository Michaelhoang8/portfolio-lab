"""Exercise the Notes API with a temporary note: python -m portfolio.rest_client."""
import argparse
import json
import os
import uuid
from urllib.request import Request,urlopen
from urllib.error import HTTPError

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    args=parser.parse_args()
    key=os.environ.get('PORTFOLIO_API_KEY')
    if not key:
        parser.error('Set PORTFOLIO_API_KEY to the same key as the server')
    def request(method,path,body=None,headers=None):
        head={'X-API-Key':key,**(headers or {})}
        raw=None
        if body is not None:
            head['Content-Type']='application/json';raw=json.dumps(body).encode()
        try:
            response=urlopen(Request(args.base_url.rstrip('/')+path,data=raw,headers=head,method=method),timeout=10)
        except HTTPError as error:
            if error.code==304:
                response=error
            else:
                with error:
                    raise RuntimeError(f'{error.code}: {error.read().decode()}') from None
        with response:
            text=response.read()
            print(f'{method} {path}: {response.status}')
            return response.headers,json.loads(text) if text else None
    path=None
    try:
        payload={'title':'Temporary API client demo','content':'This note will be deleted when the demo finishes.','status':'draft'}
        idem={'Idempotency-Key':str(uuid.uuid4())}
        headers,note=request('POST','/api/v1/notes',payload,idem);path=headers['Location']
        _,replay=request('POST','/api/v1/notes',payload,idem)
        assert replay['id']==note['id']
        request('GET','/api/v1/notes?page_size=2')
        headers,_=request('GET',path)
        current_tag=headers['ETag']
        head,body=request('HEAD',path)
        assert body is None and head['ETag']==current_tag
        unchanged,body=request('GET',path,headers={'If-None-Match':current_tag})
        assert body is None and unchanged['ETag']==current_tag
        _,updated=request('PATCH',path,{'status':'published'},{'If-Match':current_tag})
        changed,body=request('GET',path,headers={'If-None-Match':current_tag})
        assert body==updated and changed['ETag']!=current_tag
        print('Create, replay, pagination, retrieval, HEAD, conditional reads, and update succeeded.')
    finally:
        if path:
            headers,_=request('GET',path)
            request('DELETE',path,headers={'If-Match':headers['ETag']})

if __name__=='__main__':
    main()
