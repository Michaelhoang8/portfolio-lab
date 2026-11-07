import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from portfolio.db import initialize, connect
from portfolio import services as s
from portfolio.server import handler_for
from portfolio.validation import ValidationError

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

    def test_experiment_rates_and_zero_baseline(self):
        s.experiment_create(self.db, {'name':'CTA','a_visitors':100,'a_conversions':0,'b_visitors':100,'b_conversions':10})
        result = s.snapshot(self.db)['experiments'][0]
        self.assertIsNone(result['relative_lift'])
        self.assertAlmostEqual(result['difference'], .1)
        self.assertAlmostEqual(s.wilson(50,100)[0], .4038315, places=6)
        for successes in [0, 50, 100]:
            lower, upper = s.wilson(successes,100)
            self.assertTrue(0 <= lower <= upper <= 1)

    def test_invalid_counts_and_bool_rejected(self):
        for visitors, conversions in [(0,0),(10,11),(True,1)]:
            with self.assertRaises(ValidationError):
                s.experiment_create(self.db, {'name':'Invalid','a_visitors':visitors,'a_conversions':conversions,'b_visitors':10,'b_conversions':2})

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

    def test_static_assets_and_security_headers(self):
        for path in ['/', '/app.js', '/style.css', '/observatory.js', '/observatory.css']:
            with self.request(path) as response:
                self.assertEqual(response.status,200)
                self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])

    def test_http_validation_and_not_found(self):
        headers = {'Content-Type':'application/json','X-Portfolio-Client':'browser'}
        for path, body, status in [('/api/tickets',b'{',400),('/api/tickets',b'[]',400),('/api/tickets/999/status',b'{"status":"done"}',404),('/api/missing',b'{}',404)]:
            with self.request(path,body,headers) as response:
                self.assertEqual(response.status,status)
        with self.request('/api/tickets',b'{}') as response:
            self.assertEqual(response.status,403)

    def test_http_create_and_duplicate_sku(self):
        headers = {'Content-Type':'application/json','X-Portfolio-Client':'browser'}
        body = json.dumps({'name':'Mouse','sku':'MOUSE','reorder_point':2}).encode()
        for status in [201,409]:
            with self.request('/api/products',body,headers) as response:
                self.assertEqual(response.status,status)
        with self.request('/api/state') as response:
            self.assertEqual(json.load(response)['products'][0]['sku'],'MOUSE')

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
