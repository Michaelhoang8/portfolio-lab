import json
import csv
import io
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from portfolio import capabilities as c, data_apps as d, ml_apps as ml, security_apps as security, devops_apps as ops, services
from portfolio.db import initialize, connect, SCHEMA
from portfolio.validation import ValidationError, NotFoundError


def enhanced(path, data, function):
    return c.enrich(path,data,function(data))


class AnalysisCapabilities(unittest.TestCase):
    def test_revenue_rejects_nonplain_amounts_without_breaking_reconciliation(self):
        values=['1e2','1_000','1.000','NaN','Infinity','100.00','-25.25']
        data={'csv':'date,category,amount\n'+'\n'.join(f'2026-01-01,A,{v}' for v in values)}
        r=enhanced('/api/data/sales',data,d.sales)
        self.assertEqual((r['accepted_rows'],r['rejected_rows'],r['total']),(2,5,'74.75'))
        self.assertEqual(r['capabilities']['tables'][1]['rows'][0][:3],['100.00','25.25','74.75'])

    def test_evaluation_audit_reconciles_threshold_errors_and_costs(self):
        data={'csv':'actual,score,private_note\n0,0.2,OMIT_THIS\n1,0.7,OMIT_THIS\n0,0.7,OMIT_THIS\n1,0.69,OMIT_THIS',
              'threshold':.7,'false_positive_cost':2,'false_negative_cost':9}
        result=enhanced('/api/ml/evaluate',data,ml.evaluate)
        rows=list(csv.DictReader(io.StringIO(result['prediction_audit_csv'])))
        self.assertEqual([row['outcome'] for row in rows],
                         ['true negative','true positive','false positive','false negative'])
        self.assertEqual([row['record'] for row in rows],['2','3','4','5'])
        self.assertEqual([float(row['error_cost']) for row in rows],[0,0,2,9])
        self.assertTrue(all(float(row['threshold'])==.7 for row in rows))
        self.assertEqual(result['metrics']['confusion'],{'tp':1,'fp':1,'tn':1,'fn':1})
        self.assertEqual([row[0] for row in result['capabilities']['tables'][-1]['rows']],[4,5])
        self.assertNotIn('OMIT_THIS',json.dumps(result))

    def test_evaluation_audit_exports_every_record_beyond_error_preview(self):
        result=enhanced('/api/ml/evaluate',{'csv':'actual,score\n'+'1,0.123456789012345\n'*5000},ml.evaluate)
        rows=list(csv.DictReader(io.StringIO(result['prediction_audit_csv'])))
        self.assertEqual(len(rows),5000)
        self.assertEqual(rows[-1]['record'],'5001')
        self.assertEqual(rows[0]['score'],'0.123456789012345')
        self.assertEqual(len(result['capabilities']['tables'][-1]['rows']),20)
        self.assertEqual(result['metrics']['confusion']['fn'],5000)

    def test_cost_analysis_zero_costs_and_null_validation(self):
        data={'csv':'actual,score\n1,0.2\n0,0.8','false_positive_cost':0,'false_negative_cost':0}
        r=enhanced('/api/ml/evaluate',data,ml.evaluate)
        self.assertEqual(r['cost_analysis']['best_grid_threshold'],1)
        with self.assertRaises(ValidationError):enhanced('/api/ml/evaluate',{**data,'false_negative_cost':None},ml.evaluate)

    def test_burn_zero_traffic_is_insufficient_even_with_six_buckets(self):
        csv='timestamp,total,bad\n'+'\n'.join(f'2026-01-01T0{i}:00:00Z,0,0' for i in range(6))
        r=enhanced('/api/devops/reliability',{'csv':csv},ops.reliability)
        self.assertEqual(r['burn_alert']['state'],'insufficient data')

    def test_prediction_header_escaping_in_saved_model(self):
        model={'features':['quoted,feature'],'weights':[1],'means':[0],'scales':[1],'intercept':0}
        r=c.predict({'model':model,'csv':'"quoted,feature"\n0'})
        self.assertEqual(r['predictions'][0]['score'],.5)

    def test_profile_correlation_is_stable_for_tiny_and_mixed_units(self):
        for left_scale,right_scale in [(1e-200,1e-200),(1e99,1e-200),(1e-310,1e99)]:
            data={'csv':'left,right,constant\n'+'\n'.join(
                f'{index*left_scale},{-index*right_scale},1e-200' for index in range(1,5))}
            rows=enhanced('/api/data/profile',data,d.profile)['capabilities']['tables'][1]['rows']
            self.assertEqual(rows[0],['left','right',4,-1.0])
            self.assertEqual(rows[1][-1],'Undefined')
            self.assertEqual(rows[2][-1],'Undefined')

    def test_profile_correlation_outlier_and_constant(self):
        data={'csv':'x,y,constant\n1,2,5\n2,4,5\n3,6,5\n4,8,5\n100,200,5\n'}
        r=enhanced('/api/data/profile',data,d.profile)['capabilities']['tables']
        self.assertEqual(r[0]['rows'][0][3],1)
        self.assertEqual(r[1]['rows'][0],['x','y',5,1.0])
        self.assertEqual(r[1]['rows'][1][-1],'Undefined')

    def test_profile_pairwise_missing_and_large_numbers_are_json_safe(self):
        data={'csv':'a,b\n1e100,2e99\n2e99,4e99\n,6e99\n5e99,1e99\n'}
        r=enhanced('/api/data/profile',data,d.profile)
        self.assertEqual(r['capabilities']['tables'][1]['rows'][0][2],3)
        json.dumps(r,allow_nan=False)

    def test_clean_provenance_reconciles_and_escapes_headers(self):
        data={'csv':'=name,value\n A , 1 \nA,1\n,\nB,2\n'}
        r=enhanced('/api/data/clean',data,d.clean)
        self.assertEqual(r['row_audit'][0][1:3],['Trimmed',2])
        self.assertEqual(r['row_audit'][1][1:4],['Removed duplicate','',2])
        self.assertEqual(r['row_audit'][2][1],'Dropped blank row')
        self.assertEqual(r['row_audit'][3][2],3)
        self.assertIn("'=name",r['audit_csv'])

    def test_clean_audit_with_disabled_steps(self):
        data={'csv':'x\n a \na\na\n','options':{'trim':False,'deduplicate':False}}
        r=enhanced('/api/data/clean',data,d.clean)
        self.assertTrue(all(row[1]=='Unchanged' for row in r['row_audit']))
        self.assertEqual(r['output_rows'],3)

    def test_revenue_growth_gaps_refunds_and_invalid_rows(self):
        data={'csv':'date,category,amount\n2026-01-01,A,100\n2026-02-01,A,120\n2026-02-02,A,-20\n2026-04-01,A,50\nbad,A,999\n'}
        tables=enhanced('/api/data/sales',data,d.sales)['capabilities']['tables']
        self.assertEqual(tables[0]['rows'][1][2],0)
        self.assertEqual(tables[0]['rows'][2][2],'N/A')
        self.assertEqual(tables[1]['rows'][0][:3],['270','20','250.00'])

    def test_header_regression_and_no_header_values_returned(self):
        data={'text':'X-Content-Type-Options: wrong','baseline_text':'X-Content-Type-Options: nosniff\nAuthorization: PRIVATE_VALUE'}
        r=enhanced('/api/security/headers',data,security.inspect_headers)
        row=next(row for row in r['capabilities']['tables'][0]['rows'] if row[0]=='MIME sniffing')
        self.assertEqual(row[-1],'regression')
        self.assertNotIn('PRIVATE_VALUE',json.dumps(r))

    def test_secret_gate_and_export_are_value_free(self):
        data={'text':'password="FICTIONAL_CREDENTIAL"','gate_severity':'high'}
        r=enhanced('/api/security/secrets',data,security.scan_secrets)
        self.assertFalse(r['gate']['blocked'])
        self.assertNotIn('FICTIONAL_CREDENTIAL',json.dumps(r))
        data['gate_severity']='medium'
        self.assertTrue(enhanced('/api/security/secrets',data,security.scan_secrets)['gate']['blocked'])
        data['gate_severity']='unknown'
        with self.assertRaises(ValidationError): enhanced('/api/security/secrets',data,security.scan_secrets)

    def test_incident_queue_groups_source_not_each_alert(self):
        data={'text':'\n'.join(json.dumps({'timestamp':f'2026-01-01T00:0{i}:00Z','ip':'192.0.2.1','user':f'user{i}','status':'failure'}) for i in range(3)), 'threshold':2}
        result=enhanced('/api/security/logs',data,security.auth_logs)
        rows=result['capabilities']['tables'][0]['rows']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][2],len(result['alerts']))
        self.assertEqual(rows[0][1],'high')

    def test_model_import_roundtrip_and_report_wrapper(self):
        model={'features':['a'],'weights':[2],'means':[3],'scales':[4],'intercept':1,'threshold':.7}
        expected=c.predict({'model':model,'csv':'a\n3\n7'})
        for payload in (model,{'model':model,'metrics':{}}):
            imported=c.load_model({'text':json.dumps(payload)})['model']
            self.assertEqual(c.predict({'model':imported,'csv':'a\n3\n7'}),expected)
            self.assertEqual(imported['threshold'],.7)

    def test_model_import_rejects_ambiguous_or_unsupported_files(self):
        model={'features':['x'],'weights':[1],'means':[0],'scales':[1],'intercept':0}
        invalid=['{}','[]','null','{bad','{"model":{},"model":{}}',
                 json.dumps({**model,'algorithm':'unknown'}),json.dumps({**model,'features':['']}),
                 json.dumps({**model,'scales':[0]}),json.dumps({**model,'threshold':2}),
                 json.dumps({**model,'weights':[float('inf')]}),' '*200001]
        for raw in invalid:
            with self.subTest(raw=raw[:100]),self.assertRaises(ValidationError):
                c.load_model({'text':raw})

    def test_inference_reuses_scaler_and_aligns_reordered_columns(self):
        model={'features':['a','b'],'weights':[1,2],'means':[10,20],'scales':[2,4],'intercept':0}
        r=c.predict({'model':model,'csv':'b,extra,a\n20,ignore,10\n24,ignore,12\n'})
        self.assertEqual(r['predictions'][0]['score'],.5)
        self.assertAlmostEqual(r['predictions'][1]['score'],ml.sigmoid(3))
        self.assertEqual(r['predictions'][1]['predicted'],1)

    def test_invalid_model_vectors_scales_and_features_rejected(self):
        model={'features':['x'],'weights':[1],'means':[0],'scales':[1],'intercept':0}
        for patch in ({'scales':[0]},{'weights':[]},{'means':[float('nan')]},{'features':['x','x']}):
            with self.subTest(patch=patch),self.assertRaises(ValidationError):c.predict({'model':{**model,**patch},'csv':'x\n1'})
        with self.assertRaises(ValidationError):c.predict({'model':model,'csv':'missing\n1'})

    def test_training_model_predicts_heldout_rows_identically(self):
        csv='x,label\n'+'\n'.join(f'{i},{int(i>=0)}' for i in range(-8,8))
        fitted=ml.train({'csv':csv})
        r=c.predict({'model':fitted['model'],'csv':csv})
        by_record={p['record']:p['score'] for p in r['predictions']}
        for row in fitted['predictions']:self.assertAlmostEqual(by_record[row['record']],row['score'])

    def test_bm25_prefers_concise_document_and_limits_results(self):
        data={'documents':'needle\n---\nneedle '+('hay '*100)+'\n---\nother terms','query':'needle','algorithm':'bm25','top_k':1}
        result=ml.search(data)
        self.assertEqual(result['results'][0]['document'],1)
        self.assertEqual(len(result['results']),1)
        self.assertGreater(result['results'][0]['bm25_score'],0)
        with self.assertRaises(ValidationError):ml.search({**data,'top_k':0})
        with self.assertRaises(ValidationError):ml.search({**data,'algorithm':'unknown'})

    def test_cost_threshold_changes_with_error_costs(self):
        data={'csv':'actual,score\n1,0.4\n0,0.6\n','false_positive_cost':1,'false_negative_cost':100}
        result=enhanced('/api/ml/evaluate',data,ml.evaluate)
        self.assertEqual(result['cost_analysis']['best_grid_threshold'],.4)
        self.assertEqual(result['cost_analysis']['minimum_cost'],1)
        data['false_negative_cost']=-1
        with self.assertRaises(ValidationError):enhanced('/api/ml/evaluate',data,ml.evaluate)

    def test_resource_units_and_unknown_totals(self):
        self.assertEqual(c.quantity('500m','cpu'),.5)
        self.assertEqual(c.quantity('1Gi','memory'),1024)
        self.assertIsNone(c.quantity('-1Gi','memory'))
        doc={'apiVersion':'apps/v1','kind':'Deployment','spec':{'replicas':3,'template':{'spec':{'containers':[{'resources':{'requests':{'cpu':'500m','memory':'1Gi'}}}]}}}}
        result=enhanced('/api/devops/manifest',{'text':json.dumps(doc)},ops.manifest)
        self.assertEqual(result['capabilities']['tables'][0]['rows'][-1][1:],[1.5,'Unknown',3072.0,'Unknown'])

    def test_worker_capacity_and_retry_utilization(self):
        data={'text':json.dumps({'jobs':[{'id':'a','duration':10},{'id':'b','duration':10,'retries':1,'fail_attempts':1}]}),'workers':2}
        rows=enhanced('/api/devops/pipeline',data,ops.pipeline)['capabilities']['tables'][0]['rows']
        self.assertEqual(rows[0],[1,30,100.0,'passed'])
        self.assertEqual(rows[1],[2,20,75.0,'passed'])

    def test_burn_requires_both_windows_and_complete_data(self):
        csv='timestamp,total,bad\n'+'\n'.join(f'2026-01-01T0{i}:00:00Z,1000,10' for i in range(6))
        data={'csv':csv,'target':99.9,'burn_threshold':2}
        self.assertEqual(enhanced('/api/devops/reliability',data,ops.reliability)['burn_alert']['state'],'firing')
        data['csv']=csv.rsplit('\n',1)[0]
        self.assertEqual(enhanced('/api/devops/reliability',data,ops.reliability)['burn_alert']['state'],'insufficient data')

    def test_experiment_planner_power_and_effect_size(self):
        base=c.experiment_plan({})
        self.assertTrue(3800<base['per_variant']<3900)
        self.assertGreater(c.experiment_plan({'power':.9})['per_variant'],base['per_variant'])
        self.assertLess(c.experiment_plan({'absolute_lift':.04})['per_variant'],base['per_variant'])
        with self.assertRaises(ValidationError):c.experiment_plan({'baseline':.9,'absolute_lift':.2})


class PersistentCapabilities(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=str(Path(self.temp.name)/'test.db')
        initialize(self.path);self.db=connect(self.path)
    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def test_assignment_roundtrip_idempotent_audit_and_invalid_date(self):
        ticket=services.ticket_create(self.db,{'title':'Ship','description':'Review','priority':'high','assignee':'Ada','due_date':'2026-12-01'})['id']
        for _ in range(2): services.ticket_details(self.db,ticket,{'assignee':'Bea','due_date':'2026-12-02'})
        result=services.snapshot(self.db)
        self.assertEqual(result['tickets'][0]['assignee'],'Bea')
        self.assertEqual(len(result['events']),2)
        with self.assertRaises(ValidationError):services.ticket_details(self.db,ticket,{'due_date':'2026-02-30'})
        with self.assertRaises(NotFoundError):services.ticket_details(self.db,999,{})

    def test_existing_schema_upgrade_is_repeatable_and_preserves_rows(self):
        path=str(Path(self.temp.name)/'old.db')
        with closing(sqlite3.connect(path)) as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO tickets(title,description,priority) VALUES ('Old','Existing','low')")
            db.execute("INSERT INTO products(sku,name,reorder_point) VALUES ('OLD','Original product',3)")
            db.commit()
        initialize(path);initialize(path)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT title,assignee,due_date FROM tickets').fetchone(),('Old','',''))
            self.assertEqual(db.execute('SELECT sku,name,reorder_point,version FROM products').fetchone(),('OLD','Original product',3,1))

    def test_replenishment_uses_withdrawals_and_preserves_ledger(self):
        pid=services.product_create(self.db,{'name':'Item','sku':'ONE','reorder_point':3})['id']
        services.movement_create(self.db,{'product_id':pid,'delta':100,'note':'Receipt'})
        services.movement_create(self.db,{'product_id':pid,'delta':-90,'note':'Fulfillment'})
        item=c.stock_plan(self.db,{'lead_days':7,'safety_days':7})['items'][0]
        self.assertEqual((item['daily_demand'],item['target'],item['order_quantity']),(3,42,32))
        self.assertEqual(services.snapshot(self.db)['products'][0]['stock'],10)

    def test_replenishment_zero_demand_has_undefined_coverage(self):
        services.product_create(self.db,{'name':'New','sku':'NEW','reorder_point':3})
        item=c.stock_plan(self.db,{})['items'][0]
        self.assertIsNone(item['days_cover'])
        self.assertEqual(item['order_quantity'],4)

    def test_replenishment_excludes_old_and_future_demand(self):
        pid=services.product_create(self.db,{'name':'Dated','sku':'DATES','reorder_point':1})['id']
        with self.db:
            self.db.execute("INSERT INTO movements(product_id,delta,note) VALUES (?,100,'Receive')",(pid,))
            for modifier in ['-31 days','+1 day','-1 day']:
                self.db.execute("INSERT INTO movements(product_id,delta,note,created_at) VALUES (?,-10,'Dated',datetime('now',?))",(pid,modifier))
        item=c.stock_plan(self.db,{})['items'][0]
        self.assertEqual(item['withdrawals_30d'],10)
        self.assertEqual(item['stock'],70)


if __name__=='__main__':unittest.main()
