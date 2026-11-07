import json
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from portfolio.db import initialize,connect
from portfolio.server import handler_for
from portfolio.openapi import build_spec

class RestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.path=str(Path(cls.temp.name)/'api.db');initialize(cls.path)
        cls.key='integration-test-key-not-a-real-secret'
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(cls.path,api_key=cls.key))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()

    def request(self,method='GET',path='/api/v1/notes',body=None,headers=None):
        supplied={'X-API-Key':self.key,**(headers or {})}
        if body is not None:
            supplied.setdefault('Content-Type','application/json')
            raw=body if isinstance(body,bytes) else json.dumps(body).encode()
        else:
            raw=None
        try:
            response=urlopen(Request(self.url+path,data=raw,headers=supplied,method=method),timeout=5)
        except HTTPError as error:
            response=error
        with response:
            text=response.read()
            return response.status,response.headers,json.loads(text) if text else None

    def create(self,title=None,headers=None):
        return self.request('POST',body={'title':title or str(uuid.uuid4()),'content':'Test content','status':'draft'},headers=headers)

    def test_nonstandard_json_is_a_parse_error(self):
        for body in [b'{"title":"a","title":"b"}', b'{"title":NaN}',
                     b'{"title":1e999}', b'{"title":' + b'['*1500+b'0'+b']'*1500+b'}']:
            with self.subTest(body=body[:50]):
                status, headers, problem = self.request('POST',body=body)
                self.assertEqual(status,400)
                self.assertEqual(problem['detail'],'Malformed JSON body')
                self.assertEqual(headers['Content-Type'],'application/problem+json')

    def test_head_matches_get_metadata_without_body(self):
        _,created,_=self.create()
        for path in ['/api/v1/notes?page_size=1',created['Location']]:
            get_status,get_headers,_=self.request(path=path)
            status,headers,body=self.request('HEAD',path)
            self.assertEqual(status,get_status)
            self.assertEqual(headers['Content-Length'],get_headers['Content-Length'])
            self.assertEqual(headers.get('ETag'),get_headers.get('ETag'))
            self.assertIsNone(body)
        status,headers,body=self.request('HEAD',headers={'X-API-Key':'wrong'})
        self.assertEqual(status,401)
        self.assertEqual(headers['Content-Type'],'application/problem+json')
        self.assertIsNone(body)

    def test_conditional_note_reads_support_weak_tags_lists_and_wildcards(self):
        _,created,_=self.create();path=created['Location'];tag=created['ETag']
        for method in ('GET','HEAD'):
            for value in (tag,'W/'+tag,'*','"unrelated,tag", W/'+tag,', , '+tag+','):
                with self.subTest(method=method,value=value):
                    status,headers,body=self.request(method,path,headers={'If-None-Match':value})
                    self.assertEqual(status,304)
                    self.assertEqual(headers['ETag'],tag)
                    self.assertNotIn('Content-Length',headers)
                    self.assertNotIn('Content-Type',headers)
                    self.assertIsNone(body)
                    self.assertEqual(headers['Cache-Control'],'no-store')
        for value in ('"other"','W/"other"','',', ,'):
            self.assertEqual(self.request(path=path,headers={'If-None-Match':value})[0],200)
        self.assertEqual(self.request(path=path,headers={'If-None-Match':tag,'X-API-Key':'wrong'})[0],401)
        _,updated,_=self.request('PATCH',path,{'title':'A new version'},{'If-Match':tag})
        status,headers,body=self.request(path=path,headers={'If-None-Match':tag})
        self.assertEqual((status,headers['ETag'],body['version']),(200,updated['ETag'],2))

    def test_conditional_reads_reject_malformed_or_unsupported_conditions(self):
        _,created,_=self.create();path=created['Location'];tag=created['ETag']
        for value in ('unquoted','w/'+tag,tag+tag,'*, '+tag,'"unterminated','"x" '*2,'"x",'*101,'x'*8193):
            with self.subTest(value=value[:80]):
                self.assertEqual(self.request(path=path,headers={'If-None-Match':value})[0],400)
        self.assertEqual(self.request(headers={'If-None-Match':'*'})[0],400)
        self.assertEqual(self.request('PATCH',path,{'title':'unchanged'},
                                     {'If-Match':tag,'If-None-Match':'*'})[0],400)
        self.assertEqual(self.request(path=path)[1]['ETag'],tag)
        self.assertEqual(self.request(path='/api/v1/notes/'+str(uuid.uuid4()),headers={'If-None-Match':'*'})[0],404)

    def test_no_content_responses_omit_representation_framing(self):
        _,created,_=self.create()
        for method,path,headers in [('OPTIONS','/api/v1/notes',{}),
                                    ('DELETE',created['Location'],{'If-Match':created['ETag']})]:
            status,returned,body=self.request(method,path,headers=headers)
            self.assertEqual(status,204)
            self.assertIsNone(body)
            self.assertNotIn('Content-Length',returned)
            self.assertNotIn('Content-Type',returned)

    def test_create_location_get_and_persistence(self):
        status,headers,note=self.create()
        self.assertEqual(status,201)
        self.assertEqual(headers['Location'],'/api/v1/notes/'+note['id'])
        self.assertEqual(self.request(path=headers['Location'])[2],note)
        db=connect(self.path)
        try:
            self.assertEqual(db.execute('SELECT title FROM api_notes WHERE id=?',(note['id'],)).fetchone()[0],note['title'])
        finally:
            db.close()

    def test_patch_put_delete_lifecycle(self):
        _,headers,note=self.create();path=headers['Location']
        status,updated,result=self.request('PATCH',path,{'status':'published'},{'If-Match':headers['ETag']})
        self.assertEqual((status,result['version'],result['status']),(200,2,'published'))
        status,replaced,result=self.request('PUT',path,{'title':'Replaced','content':'Replacement','status':'draft'},{'If-Match':updated['ETag']})
        self.assertEqual((status,result['version'],result['title']),(200,3,'Replaced'))
        status,_,body=self.request('DELETE',path,headers={'If-Match':replaced['ETag']})
        self.assertEqual((status,body),(204,None))
        self.assertEqual(self.request(path=path)[0],404)

    def test_missing_and_stale_etag(self):
        _,headers,_=self.create();path=headers['Location']
        self.assertEqual(self.request('PATCH',path,{'title':'x'})[0],428)
        self.assertEqual(self.request('PATCH',path,{'title':'x'},{'If-Match':'"wrong"'})[0],412)
        self.assertEqual(self.request('DELETE',path,headers={'If-Match':'*'})[0],412)

    def test_concurrent_updates_allow_only_one_writer(self):
        _,headers,_=self.create();barrier=threading.Barrier(2)
        def change(value):
            barrier.wait(timeout=5)
            return self.request('PATCH',headers['Location'],{'title':value},{'If-Match':headers['ETag']})[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(change,['first','second']))
        self.assertEqual(sorted(results),[200,412])

    def test_idempotent_replay_and_conflict(self):
        key=str(uuid.uuid4());_,first,note=self.create('Repeat',{'Idempotency-Key':key})
        status,second,replay=self.create('Repeat',{'Idempotency-Key':key})
        self.assertEqual((status,replay),(201,note))
        self.assertEqual(second['Idempotency-Replayed'],'true')
        self.assertEqual(self.create('Changed',{'Idempotency-Key':key})[0],409)

    def test_concurrent_idempotent_creates(self):
        key=str(uuid.uuid4());barrier=threading.Barrier(2)
        def create(_):
            barrier.wait(timeout=5)
            return self.create('Concurrent',{'Idempotency-Key':key})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(create,range(2)))
        self.assertEqual(results[0][2]['id'],results[1][2]['id'])
        self.assertEqual(sorted(r[1]['Idempotency-Replayed'] for r in results),['false','true'])

    def test_pagination_search_and_status_filter(self):
        marker=str(uuid.uuid4())
        for i in range(3):
            self.create(marker+str(i))
        status,_,page=self.request(path='/api/v1/notes?q='+marker+'&page_size=2&status=draft')
        self.assertEqual((status,len(page['items']),page['total']),(200,2,3))
        second=self.request(path=page['next'])[2]
        self.assertEqual(len(second['items']),1)
        self.assertFalse({n['id'] for n in page['items']} & {n['id'] for n in second['items']})

    def test_auth_problem_format_and_request_id(self):
        status,headers,body=self.request(headers={'X-API-Key':'wrong'})
        self.assertEqual(status,401)
        self.assertEqual(headers.get_content_type(),'application/problem+json')
        self.assertEqual(body['status'],401)
        self.assertEqual(body['type'],'about:blank')
        uuid.UUID(headers['X-Request-ID'])

    def test_unknown_route_and_method_allow(self):
        self.assertEqual(self.request(path='/api/v1/unknown')[0],404)
        status,headers,_=self.request('PUT',body={})
        self.assertEqual(status,405)
        self.assertIn('POST',headers['Allow'])
        self.assertEqual(self.request('OPTIONS')[0],204)

    def test_body_validation_and_duplicate_json_keys(self):
        for body,status in [(b'{',400),(b'{"title":"a","title":"b"}',400),([],422),({},422),({'title':'x','content':'y','status':'wrong'},422),({'title':'x','content':'y','status':'draft','extra':1},422)]:
            self.assertEqual(self.request('POST',body=body)[0],status)
        self.assertEqual(self.request('POST',body=b'{}',headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('POST',body=b' '*65537)[0],413)

    def test_invalid_queries(self):
        for query in ['page=0','page_size=101','status=no','page=1&page=2','extra=x']:
            self.assertEqual(self.request(path='/api/v1/notes?'+query)[0],400)

    def test_replay_retains_original_response_after_delete(self):
        key=str(uuid.uuid4());_,headers,note=self.create('Snapshot',{'Idempotency-Key':key})
        self.request('DELETE',headers['Location'],headers={'If-Match':headers['ETag']})
        self.assertEqual(self.create('Snapshot',{'Idempotency-Key':key})[2],note)
        self.assertEqual(self.request(path=headers['Location'])[0],404)

    def test_openapi_matches_generator_and_documented_paths(self):
        status,_,schema=self.request(path='/openapi.json')
        self.assertEqual(status,200)
        self.assertEqual(schema,build_spec())
        self.assertEqual(set(schema['paths']['/api/v1/notes/{id}']),{'parameters','get','head','put','patch','delete','options'})

    def test_explorer_assets(self):
        for path in ['/rest','/rest.js','/rest.css']:
            with urlopen(self.url+path) as response:
                self.assertEqual(response.status,200)

class DisabledRestTests(unittest.TestCase):
    def test_missing_server_key_disables_rest_api(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'test.db');initialize(path)
            server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(path,api_key=''))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(f'http://127.0.0.1:{server.server_port}/api/v1/notes')
                self.assertEqual(caught.exception.code,503)
                caught.exception.close()
            finally:
                server.shutdown();server.server_close();thread.join()
