from http.client import HTTPConnection
import json
import csv
import io
import tempfile
import threading
import socket
import http.client
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from portfolio.db import initialize, connect
from portfolio import services as s
from portfolio.server import handler_for
from portfolio.validation import ValidationError, ConflictError

class DomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'test.db')
        initialize(self.path)
        self.db = connect(self.path)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def product(self):
        return s.product_create(self.db, {'name':'Keyboard','sku':'KEY-01','reorder_point':2})['id']

    def test_ticket_lifecycle_audit_and_idempotent_status(self):
        item = s.ticket_create(self.db, {'title':'Fix login','description':'Handle expired session','priority':'high'})['id']
        for status in ['active', 'done', 'done']:
            s.ticket_move(self.db, item, {'status':status})
        state = s.snapshot(self.db)
        self.assertEqual(state['tickets'][0]['status'], 'done')
        self.assertEqual(len(state['events']), 3)

    def test_issue_edit_preserves_omitted_fields_and_audits_once(self):
        ticket=s.ticket_create(self.db,{'title':'Original','description':'Context','priority':'medium',
                                      'assignee':'Ada','due_date':'2026-12-01'})['id']
        first=s.ticket_details(self.db,ticket,{'title':'Revised','expected_version':1})
        self.assertEqual(first['version'],2)
        self.assertEqual((first['assignee'],first['due_date'],first['description']),('Ada','2026-12-01','Context'))
        replay=s.ticket_details(self.db,ticket,{'title':'Revised','expected_version':1})
        self.assertEqual(first,replay)
        self.assertEqual(len(s.snapshot(self.db)['events']),2)
        with self.assertRaises(ValidationError):
            s.ticket_details(self.db,ticket,{'description':'','priority':'high','expected_version':2})
        self.assertEqual(s.snapshot(self.db)['tickets'][0]['priority'],'medium')

    def test_stale_issue_edits_cannot_overwrite_newer_details_or_status(self):
        ticket=s.ticket_create(self.db,{'title':'Original','description':'Context','priority':'medium'})['id']
        s.ticket_move(self.db,ticket,{'status':'active'})
        with self.assertRaises(ConflictError):
            s.ticket_details(self.db,ticket,{'title':'Stale','expected_version':1})
        latest=s.ticket_details(self.db,ticket,{'title':'Current','expected_version':2})
        self.assertEqual(latest['version'],3)
        with self.assertRaises(ConflictError):
            s.ticket_details(self.db,ticket,{'assignee':'Lost update','expected_version':2})
        with self.assertRaises(ValidationError):
            s.ticket_details(self.db,ticket,{'expected_version':True})
        current=s.snapshot(self.db)['tickets'][0]
        self.assertEqual((current['title'],current['assignee'],current['status']),('Current','','active'))

    def test_product_metadata_edit_is_versioned_without_changing_stock(self):
        product=self.product()
        s.movement_create(self.db,{'product_id':product,'delta':7,'note':'Opening stock'})
        updated=s.product_details(self.db,product,{'name':'Renamed keyboard','reorder_point':9,'expected_version':1})
        self.assertEqual(updated['version'],2)
        replay=s.product_details(self.db,product,{'name':'Renamed keyboard','reorder_point':9,'expected_version':1})
        self.assertEqual(replay['version'],2)
        row=s.snapshot(self.db)['products'][0]
        self.assertEqual((row['sku'],row['stock'],row['name'],row['reorder_point']),('KEY-01',7,'Renamed keyboard',9))
        self.assertEqual(self.db.execute('SELECT count(*) FROM movements').fetchone()[0],1)

    def test_product_edit_validation_and_stale_versions_preserve_saved_values(self):
        product=self.product()
        s.product_details(self.db,product,{'reorder_point':10,'expected_version':1})
        with self.assertRaises(ConflictError):
            s.product_details(self.db,product,{'name':'Stale rename','expected_version':1})
        for fields in ({'name':''},{'reorder_point':-1},{'sku':'REPLACED'},{'expected_version':True}):
            with self.subTest(fields=fields),self.assertRaises(ValidationError):
                s.product_details(self.db,product,{'expected_version':2,**fields})
        row=s.snapshot(self.db)['products'][0]
        self.assertEqual((row['name'],row['reorder_point'],row['version']),('Keyboard',10,2))

    def test_concurrent_product_edit_has_one_winner(self):
        product=self.product();barrier=threading.Barrier(2)
        def edit(name):
            db=connect(self.path)
            try:
                barrier.wait(timeout=5)
                try:return s.product_details(db,product,{'name':name,'expected_version':1})['version']
                except ConflictError:return 'conflict'
            finally:db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(edit,['First label','Second label']))
        self.assertCountEqual(results,[2,'conflict'])

    def test_stock_rejects_overdraw_without_writing_ledger(self):
        pid = self.product()
        s.movement_create(self.db, {'product_id':pid,'delta':5,'note':'Receive'})
        with self.assertRaises(ValidationError):
            s.movement_create(self.db, {'product_id':pid,'delta':-6,'note':'Ship'})
        self.assertEqual(s.snapshot(self.db)['products'][0]['stock'],5)
        self.assertEqual(len(s.snapshot(self.db)['movements']),1)

    def test_concurrent_withdrawals_cannot_oversell(self):
        pid = self.product()
        s.movement_create(self.db, {'product_id':pid,'delta':10,'note':'Receive'})
        barrier = threading.Barrier(2)
        def withdraw():
            db = connect(self.path)
            try:
                barrier.wait(timeout=5)
                s.movement_create(db, {'product_id':pid,'delta':-7,'note':'Concurrent ship'})
                return True
            except ValidationError:
                return False
            finally:
                db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: withdraw(), range(2)))
        self.assertEqual(sorted(results), [False,True])
        self.assertEqual(s.snapshot(self.db)['products'][0]['stock'],3)

    def test_stock_retry_replays_original_result_after_other_movements(self):
        pid = self.product()
        request = {'product_id':pid,'delta':5,'note':'Receipt','request_key':'receipt-1'}
        first = s.movement_create(self.db,request)
        s.movement_create(self.db,{'product_id':pid,'delta':-2,'note':'Later shipment'})
        other = connect(self.path)
        try:
            replay = s.movement_create(other,request)
            self.assertEqual(replay, {**first,'replayed':True})
            with self.assertRaises(ConflictError):
                s.movement_create(other,{**request,'delta':6})
        finally:
            other.close()
        self.assertEqual(s.snapshot(self.db)['products'][0]['stock'],3)
        self.assertEqual(len(s.snapshot(self.db)['movements']),2)

    def test_concurrent_duplicate_receipts_write_once(self):
        pid = self.product()
        barrier = threading.Barrier(2)
        def receive(_):
            db = connect(self.path)
            try:
                barrier.wait(timeout=5)
                return s.movement_create(db,{'product_id':pid,'delta':7,'note':'Retry','request_key':'same-receipt'})
            finally:
                db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(receive,range(2)))
        self.assertEqual(sorted(r['replayed'] for r in results),[False,True])
        self.assertEqual(results[0]['id'],results[1]['id'])
        self.assertEqual(s.snapshot(self.db)['products'][0]['stock'],7)
        self.assertEqual(len(s.snapshot(self.db)['movements']),1)

    def test_rejected_movement_does_not_reserve_request_key(self):
        pid = self.product()
        request = {'product_id':pid,'delta':-1,'note':'Ship','request_key':'pending-ship'}
        with self.assertRaises(ValidationError):
            s.movement_create(self.db,request)
        s.movement_create(self.db,{'product_id':pid,'delta':2,'note':'Receive'})
        self.assertFalse(s.movement_create(self.db,request)['replayed'])
        for invalid in ['', 'bad key', 17, True, 'a'*129]:
            with self.subTest(key=invalid), self.assertRaises(ValidationError):
                s.movement_create(self.db,{**request,'request_key':invalid})

    def test_full_ledger_export_exceeds_preview_and_escapes_spreadsheet_text(self):
        pid=s.product_create(self.db,{'name':'=SUM(1,2)','sku':'@FORMULA','reorder_point':0})['id']
        with self.db:
            for index in range(503):
                self.db.execute('INSERT INTO movements(product_id,delta,note) VALUES (?,?,?)',
                                (pid,1,'Receipt, with comma' if index else '=1+1'))
            self.db.execute('INSERT INTO movements(product_id,delta,note) VALUES (?,?,?)',(pid,-2,'Ship'))
        chunks=list(s.movement_csv(self.db))
        self.assertEqual(len(chunks),3)
        rows=list(csv.DictReader(io.StringIO(''.join(chunks))))
        self.assertEqual(len(rows),504)
        self.assertEqual(len(s.snapshot(self.db)['movements']),100)
        self.assertEqual(rows[0]['SKU'],"'@FORMULA")
        self.assertEqual(rows[0]['Product'],"'=SUM(1,2)")
        self.assertEqual(rows[0]['Reason'],"'=1+1")
        self.assertEqual(rows[1]['Reason'],'Receipt, with comma')
        self.assertEqual(rows[-1]['Quantity change'],'-2')
        self.assertEqual(rows[-1]['Balance after movement'],'501')

    def test_empty_ledger_export_still_contains_headers(self):
        rows=list(csv.reader(io.StringIO(''.join(s.movement_csv(self.db)))))
        self.assertEqual(len(rows),1)
        self.assertIn('Balance after movement',rows[0])

    def test_experiment_rates_and_zero_baseline(self):
        s.experiment_create(self.db, {'name':'CTA','a_visitors':100,'a_conversions':0,'b_visitors':100,'b_conversions':10})
        result = s.snapshot(self.db)['experiments'][0]
        self.assertIsNone(result['relative_lift'])
        self.assertAlmostEqual(result['difference'], .1)
        self.assertAlmostEqual(s.wilson(50,100)[0], .4038315, places=6)
        for successes in [0, 50, 100]:
            lower, upper = s.wilson(successes,100)
            self.assertTrue(0 <= lower <= upper <= 1)

    def test_comparison_matches_published_nist_examples(self):
        # NIST Dataplot binotest.htm: 32/38 vs 39/44, A minus B z=-0.58640.
        result=s.experiment_comparison(32,38,39,44)
        self.assertAlmostEqual(result['z_statistic'],.58640,places=5)
        self.assertAlmostEqual(result['p_value'],.55760,delta=1e-5)  # Published output truncates decimals.
        # NIST diffprop.htm: Agresti-Caffo A minus B [-.36936,.04794].
        interval=s.experiment_comparison(8,40,11,30)['difference_interval']
        self.assertAlmostEqual(interval[0],-.04794,places=5)
        self.assertAlmostEqual(interval[1],.36936,places=5)

    def test_comparison_reverses_direction_but_not_evidence(self):
        forward=s.experiment_comparison(100,1000,150,1000)
        reverse=s.experiment_comparison(150,1000,100,1000)
        self.assertEqual(forward['status'],'difference_detected')
        self.assertAlmostEqual(forward['p_value'],reverse['p_value'])
        self.assertAlmostEqual(forward['z_statistic'],-reverse['z_statistic'])
        self.assertAlmostEqual(forward['difference_interval'][0],-reverse['difference_interval'][1])
        same=s.experiment_comparison(50,100,50,100)
        self.assertEqual(same['p_value'],1)
        self.assertEqual(same['status'],'inconclusive')

    def test_sparse_comparison_has_no_misleading_p_value(self):
        for counts in [(0,100,0,100),(100,100,100,100),(1,10,2,10),(0,1,1,1)]:
            with self.subTest(counts=counts):
                result=s.experiment_comparison(*counts)
                self.assertIsNone(result['p_value'])
                self.assertIsNone(result['z_statistic'])
                self.assertEqual(result['status'],'insufficient_counts')
                low,high=result['difference_interval']
                self.assertTrue(-1<=low<high<=1)

    def test_invalid_counts_and_bool_rejected(self):
        for visitors, conversions in [(0,0),(10,11),(True,1)]:
            with self.assertRaises(ValidationError):
                s.experiment_create(self.db, {'name':'Invalid','a_visitors':visitors,'a_conversions':conversions,'b_visitors':10,'b_conversions':2})

    def test_snapshot_is_consistent_during_concurrent_movement(self):
        pid = self.product()
        other = connect(self.path)
        wrote = []
        def concurrent_write(statement):
            if statement.startswith('SELECT m.*') and not wrote:
                s.movement_create(other,{'product_id':pid,'delta':5,'note':'Concurrent receipt'})
                wrote.append(True)
        self.db.set_trace_callback(concurrent_write)
        try:
            snapshot = s.snapshot(self.db)
        finally:
            self.db.set_trace_callback(None)
            other.close()
        self.assertEqual(wrote,[True])
        self.assertEqual(snapshot['products'][0]['stock'],0)
        self.assertEqual(snapshot['movements'],[])
        self.assertEqual(s.snapshot(self.db)['products'][0]['stock'],5)

    def test_snapshot_preserves_callers_uncommitted_transaction(self):
        self.db.execute("INSERT INTO products(sku,name,reorder_point) VALUES ('UNCOMMITTED','Draft',0)")
        self.assertEqual(len(s.snapshot(self.db)['products']),1)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertEqual(s.snapshot(self.db)['products'],[])

    def test_persistence_across_connections_and_sql_input(self):
        title = "Robert'); DROP TABLE tickets; --"
        s.ticket_create(self.db, {'title':title,'description':'<script>alert(1)</script>','priority':'low'})
        other = connect(self.path)
        try:
            self.assertEqual(s.snapshot(other)['tickets'][0]['title'], title)
        finally:
            other.close()

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        path = str(Path(cls.temp.name) / 'http.db')
        initialize(path)
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),handler_for(path))
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.temp.cleanup()

    def request(self, path, data=None, headers=None):
        request = Request(self.url+path, data=data, headers=headers or {})
        try:
            return urlopen(request,timeout=5)
        except HTTPError as error:
            return error

    def test_only_unambiguous_loopback_hosts_are_accepted(self):
        for host in ('localhost','LOCALHOST:8000','127.0.0.1:8000','[::1]:8000','localhost  '):
            with self.subTest(host=host),self.request('/api/state',headers={'Host':host}) as response:
                self.assertEqual(response.status,200)
        for host in ('example.invalid','localhost.evil.invalid','user@localhost','127.0.0.1:0','localhost:99999','localhost,127.0.0.1'):
            for path in ('/api/state','/api/v1/notes','/api/movements.csv','/'):
                with self.subTest(host=host,path=path),self.request(path,headers={'Host':host}) as response:
                    self.assertEqual(response.status,400)
                    self.assertIn('loopback Host',json.load(response)['error'])

    def test_untrusted_host_cannot_mutate_workspace(self):
        with self.request('/api/state') as response:
            before=json.load(response)['tickets']
        headers={'Host':'untrusted.invalid','Content-Type':'application/json','X-Portfolio-Client':'browser'}
        with self.request('/api/tickets',b'{"title":"Blocked","description":"Fixture","priority":"low"}',headers) as response:
            self.assertEqual(response.status,400)
        with self.request('/api/state') as response:
            self.assertEqual(json.load(response)['tickets'],before)

    def test_missing_or_duplicate_host_is_rejected_before_dispatch(self):
        for hosts in ([],['localhost','127.0.0.1']):
            connection=HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            try:
                connection.putrequest('GET','/api/state',skip_host=True)
                for host in hosts:
                    connection.putheader('Host',host)
                connection.endheaders()
                response=connection.getresponse()
                self.assertEqual(response.status,400)
                self.assertIn('loopback Host',json.loads(response.read())['error'])
            finally:
                connection.close()

    def test_static_assets_and_security_headers(self):
        for path in ['/', '/app.js', '/style.css', '/observatory.js', '/observatory.css', '/csv_columns.js']:
            with self.request(path) as response:
                self.assertEqual(response.status,200)
                self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])

    def test_head_and_static_query_parameters(self):
        for path in ['/?preview=1','/app.js?v=1','/api/state','/api/movements.csv']:
            with self.subTest(path=path):
                response=urlopen(Request(self.url+path,method='HEAD'),timeout=5)
                with response:
                    self.assertEqual(response.status,200)
                    self.assertEqual(response.read(),b'')
                    self.assertIsNotNone(response.headers['Content-Type'])

    def test_truncated_body_and_duplicate_lengths_are_rejected(self):
        for headers in ['Content-Length: 20', 'Content-Length: 2\r\nContent-Length: 2']:
            with self.subTest(headers=headers), socket.create_connection(self.server.server_address,timeout=5) as connection:
                request=('POST /api/extensions/experiment-plan HTTP/1.0\r\nHost: localhost\r\n'
                         'Content-Type: application/json\r\nX-Portfolio-Client: browser\r\n'+headers+'\r\n\r\n{}')
                connection.sendall(request.encode('ascii'))
                connection.shutdown(socket.SHUT_WR)
                response=http.client.HTTPResponse(connection);response.begin()
                self.assertEqual(response.status,400)
                self.assertIn('error',json.loads(response.read()))

    def test_slow_request_body_returns_timeout_error(self):
        class FastTimeoutHandler(self.server.RequestHandlerClass):
            def setup(self):
                super().setup()
                self.connection.settimeout(.05)
        server=ThreadingHTTPServer(('127.0.0.1',0),FastTimeoutHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with socket.create_connection(server.server_address,timeout=5) as connection:
                connection.sendall(b'POST /api/extensions/experiment-plan HTTP/1.0\r\nHost: localhost\r\nContent-Type: application/json\r\nX-Portfolio-Client: browser\r\nContent-Length: 20\r\n\r\n{}')
                response=http.client.HTTPResponse(connection);response.begin()
                self.assertEqual(response.status,408)
                self.assertEqual(json.loads(response.read())['error'],'Request body timed out')
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_http_validation_and_not_found(self):
        headers = {'Content-Type':'application/json','X-Portfolio-Client':'browser'}
        for path, body, status in [('/api/tickets',b'{',400),('/api/tickets',b'[]',400),('/api/tickets/999/status',b'{"status":"done"}',404),('/api/missing',b'{}',404)]:
            with self.request(path,body,headers) as response:
                self.assertEqual(response.status,status)
        with self.request('/api/tickets',b'{}') as response:
            self.assertEqual(response.status,403)

    def test_strict_json_rejects_ambiguous_and_nonfinite_input(self):
        headers = {'Content-Type':'application/json; charset=utf-8','X-Portfolio-Client':'browser'}
        invalid = [b'{"baseline":0.1,"baseline":0.2}', b'{"baseline":NaN}',
                   b'{"baseline":Infinity}', b'{"baseline":1e999}',
                   b'{"nested":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}']
        for body in invalid:
            with self.subTest(body=body[:50]), self.request('/api/extensions/experiment-plan',body,headers) as response:
                self.assertEqual(response.status,400)
                self.assertEqual(json.load(response),{'error':'Malformed JSON body'})
        with self.request('/api/extensions/experiment-plan',b'{}',headers) as response:
            self.assertEqual(response.status,200)

    def test_http_create_and_duplicate_sku(self):
        headers = {'Content-Type':'application/json','X-Portfolio-Client':'browser'}
        body = json.dumps({'name':'Mouse','sku':'MOUSE','reorder_point':2}).encode()
        for status in [201,409]:
            with self.request('/api/products',body,headers) as response:
                self.assertEqual(response.status,status)
        with self.request('/api/state') as response:
            self.assertEqual(json.load(response)['products'][0]['sku'],'MOUSE')

    def test_movement_retry_and_conflict_http(self):
        headers = {'Content-Type':'application/json','X-Portfolio-Client':'browser'}
        with self.request('/api/products',b'{"name":"Retry product","sku":"RETRY-SKU","reorder_point":1}',headers) as response:
            pid = json.load(response)['id']
        payload = {'product_id':pid,'delta':3,'note':'Receipt','request_key':'http-receipt'}
        for replayed in (False,True):
            with self.request('/api/movements',json.dumps(payload).encode(),headers) as response:
                self.assertEqual(response.status,201)
                self.assertEqual(json.load(response)['replayed'],replayed)
        with self.request('/api/movements',json.dumps({**payload,'delta':4}).encode(),headers) as response:
            self.assertEqual(response.status,409)

    def test_ledger_download_headers_and_csv_shape(self):
        with self.request('/api/movements.csv') as response:
            self.assertEqual(response.status,200)
            self.assertEqual(response.headers['Content-Type'],'text/csv; charset=utf-8')
            self.assertIn('attachment;',response.headers['Content-Disposition'])
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
            records=list(csv.reader(io.StringIO(response.read().decode('utf-8'))))
            self.assertEqual(records[0][0],'Movement ID')
            self.assertTrue(all(len(row)==7 for row in records))

    def test_extension_routes_and_validation(self):
        headers={'Content-Type':'application/json','X-Portfolio-Client':'browser'}
        for path in ['/api/extensions/experiment-plan','/api/extensions/stock-plan']:
            with self.request(path,b'{}',headers) as response:self.assertEqual(response.status,200)
        model={'features':['x'],'weights':[1],'means':[0],'scales':[1],'intercept':0}
        with self.request('/api/extensions/predict',json.dumps({'model':model,'csv':'x\n0'}).encode(),headers) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(json.load(response)['predictions'][0]['score'],.5)
        with self.request('/api/extensions/predict',b'{"model":{}}',headers) as response:self.assertEqual(response.status,400)
        with self.request('/capabilities.js') as response:self.assertEqual(response.status,200)
        with self.request('/rest_transport.js') as response:self.assertEqual(response.status,200)
        with self.request('/api/extensions/model',json.dumps({'text':json.dumps(model)}).encode(),headers) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(json.load(response)['model']['features'],['x'])
        with self.request('/api/extensions/model',b'{"text":"invalid"}',headers) as response:
            self.assertEqual(response.status,400)

    def test_product_metadata_endpoint_and_version_conflict(self):
        headers={'Content-Type':'application/json','X-Portfolio-Client':'browser'}
        with self.request('/api/products',b'{"name":"HTTP product","sku":"EDIT-HTTP","reorder_point":2}',headers) as response:
            product=json.load(response)['id']
        route=f'/api/products/{product}/details'
        with self.request(route,b'{"name":"Updated label","expected_version":1}',headers) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(json.load(response)['version'],2)
        with self.request(route,b'{"reorder_point":5,"expected_version":1}',headers) as response:
            self.assertEqual(response.status,409)
        with self.request(route,b'{"name":"Missing version"}',headers) as response:
            self.assertEqual(response.status,400)

    def test_assignment_endpoint_persists_and_audits(self):
        headers={'Content-Type':'application/json','X-Portfolio-Client':'browser'}
        with self.request('/api/tickets',json.dumps({'title':'Assignment test','description':'HTTP','priority':'low'}).encode(),headers) as response:ticket=json.load(response)['id']
        with self.request(f'/api/tickets/{ticket}/details',b'{"assignee":"Team","due_date":"2026-12-01"}',headers) as response:self.assertEqual(response.status,200)
        with self.request('/api/state') as response:
            state=json.load(response)
            self.assertEqual(next(t for t in state['tickets'] if t['id']==ticket)['assignee'],'Team')
        with self.request(f'/api/tickets/{ticket}/details',b'{"due_date":"invalid"}',headers) as response:self.assertEqual(response.status,400)

if __name__ == '__main__':
    unittest.main()
