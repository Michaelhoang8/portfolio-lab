import csv
import io
import json
import unittest
from portfolio import data_apps as d
from portfolio.validation import ValidationError
import test_portfolio

class DataTests(unittest.TestCase):
    def test_csv_quotes_bom_and_embedded_newline(self):
        headers,rows=d.parse({'csv':'\ufeffname,note\nAda,"hello, world\nsecond line"\n'})
        self.assertEqual(headers,['name','note'])
        self.assertEqual(rows,[['Ada','hello, world\nsecond line']])

    def test_csv_rejects_invalid_shapes_and_limits(self):
        for source in ['', 'x,x\n1,2', 'x,\n1,2','x,y\n1', 'x\n"unterminated', 'x\n'+'1\n'*5001, 'x\n'+'a'*1_000_001]:
            with self.subTest(source=source[:30]),self.assertRaises(ValidationError):
                d.parse({'csv':source})

    def test_profile_missing_duplicates_and_numeric_summary(self):
        r=d.profile({'csv':'name,amount\nAda,10\nBen,20\nAda,10\n , \n'})
        self.assertEqual((r['rows'],r['duplicate_rows'],r['missing_cells']),(4,1,2))
        self.assertEqual(r['columns'][1]['median'],10)
        self.assertAlmostEqual(r['columns'][1]['mean'],40/3)

    def test_nonfinite_values_do_not_become_json_numbers(self):
        for value in ['NaN','Infinity','1e999','-inf']:
            result=d.profile({'csv':f'x\n{value}\n'})
            self.assertEqual(result['columns'][0]['type'],'text')
            json.dumps(result,allow_nan=False)

    def test_clean_order_and_formula_export(self):
        result=d.clean({'csv':'name,amount\n Ada , 10 \nAda,10\n,\n=1+1,-20\n'})
        self.assertEqual((result['output_rows'],result['duplicates_removed'],result['empty_rows_removed']),(2,1,1))
        exported=list(csv.reader(io.StringIO(result['csv'])))
        self.assertEqual(exported[-1],["'=1+1","-20"])
        again=d.clean({'csv':result['csv']})
        self.assertEqual(again['csv'],result['csv'])

    def test_disabled_clean_steps_preserve_cells(self):
        r=d.clean({'csv':'x\n a \n a \n', 'options':{'trim':False,'deduplicate':False,'drop_empty':False}})
        self.assertEqual(r['preview'],[[' a '],[' a ']])
        with self.assertRaises(ValidationError):
            d.clean({'csv':'x\n1','options':{'trim':'false'}})

    def test_sales_exact_decimal_refunds_and_rejections(self):
        result=d.sales({'csv':'date,category,amount\n2026-01-01,A,0.10\n2026-01-02,A,0.20\n2026-02-01,B,-0.05\n2026-02-30,A,9\n2026-02-01,A,NaN\n2026-02-01,A,1.001\n'})
        self.assertEqual(result['total'],'0.25')
        self.assertEqual(result['monthly'],[{'label':'2026-01','amount':'0.30'},{'label':'2026-02','amount':'-0.05'}])
        self.assertEqual((result['accepted_rows'],result['rejected_rows'],result['refund_rows']),(3,3,1))

    def test_sales_mapping_and_all_invalid(self):
        result=d.sales({'csv':'day,team,net\nwrong,A,9\n','mapping':{'date':'day','category':'team','amount':'net'}})
        self.assertEqual(result['total'],'0.00')
        self.assertIsNone(result['average'])
        self.assertEqual(result['accepted_rows'],0)
        with self.assertRaises(ValidationError):
            d.sales({'csv':'x\n1', 'mapping':{'date':'x','category':'x','amount':'x'}})

class DataHttpTests(unittest.TestCase):
    setUpClass = classmethod(test_portfolio.HttpTests.setUpClass.__func__)
    tearDownClass = classmethod(test_portfolio.HttpTests.tearDownClass.__func__)
    request = test_portfolio.HttpTests.request
    def test_data_endpoint_and_large_input(self):
        body=json.dumps({'csv':'category,amount\n'+'Software,10\n'*2000}).encode()
        with self.request('/api/data/profile',body,{'Content-Type':'application/json','X-Portfolio-Client':'browser'}) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(json.load(response)['rows'],2000)
        with self.request('/data') as response:
            self.assertEqual(response.status,200)

    def test_data_validation_is_client_error(self):
        with self.request('/api/data/sales',b'{"csv":"x\\n1"}',{'Content-Type':'application/json','X-Portfolio-Client':'browser'}) as response:
            self.assertEqual(response.status,400)
