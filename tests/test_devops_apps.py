import json
import unittest
import test_portfolio
from portfolio import devops_apps as d
from portfolio.validation import ValidationError

def plan(jobs,workers=2):
    return d.pipeline({'text':json.dumps({'jobs':jobs}),'workers':workers})

def manifest():
    return {'apiVersion':'apps/v1','kind':'Deployment','spec':{'replicas':2,'selector':{'matchLabels':{'app':'demo'}},'template':{'metadata':{'labels':{'app':'demo'}},'spec':{'securityContext':{'runAsNonRoot':True},'containers':[{'name':'api','image':'example.invalid/api@sha256:'+'a'*64,'resources':{'requests':{'cpu':'100m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'128Mi'}},'readinessProbe':{'httpGet':{}},'livenessProbe':{'exec':{}},'securityContext':{'allowPrivilegeEscalation':False}}]}}}}

class DevOpsTests(unittest.TestCase):
    def test_manifest_selected_controls_and_inherited_nonroot(self):
        r=d.manifest({'text':json.dumps(manifest())})
        self.assertEqual(r['review_count'],0)
        self.assertEqual(r['containers'],1)

    def test_manifest_flags_replica_image_and_selector(self):
        doc=manifest();doc['spec']['replicas']=1
        doc['spec']['selector']['matchLabels']['app']='wrong'
        doc['spec']['template']['spec']['containers'][0]['image']='demo:latest'
        r=d.manifest({'text':json.dumps(doc)})
        self.assertEqual(r['review_count'],3)

    def test_manifest_rejects_unsupported_and_bad_shapes(self):
        for doc in [{'kind':'Pod'}, {**manifest(),'spec':[]}, {'apiVersion':'apps/v1','kind':'Deployment','spec':{'template':{'spec':{'containers':[]}}}}]:
            with self.assertRaises(ValidationError):
                d.manifest({'text':json.dumps(doc)})

    def test_embedded_documents_reject_duplicate_and_nonfinite_json(self):
        for text in ['{"jobs":[],"jobs":[]}', '{"metadata":{"x":NaN}}',
                     '{"metadata":{"x":1e999}}', '{"x":'+'['*100+'0'+']'*100+'}']:
            with self.subTest(text=text[:50]), self.assertRaises(ValidationError):
                d.document({'text':text})

    def test_parallel_scheduling_and_critical_path(self):
        jobs=[{'id':'a','duration':10},{'id':'b','duration':20},{'id':'c','needs':['a','b'],'duration':5}]
        parallel=plan(jobs)
        self.assertEqual((parallel['elapsed'],parallel['ideal_critical_path']),(25,25))
        self.assertEqual(plan(jobs,1)['elapsed'],35)
        self.assertEqual(parallel['jobs'][-1]['start'],20)

    def test_queue_time_excludes_dependencies_and_separates_retries(self):
        jobs=[{'id':'a','duration':10,'retries':1,'fail_attempts':1},
              {'id':'b','duration':5},{'id':'c','needs':['a'],'duration':6}]
        serial=plan(jobs,1);parallel=plan(jobs,2)
        records={job['id']:job for job in serial['jobs']}
        self.assertEqual(serial['ideal_critical_jobs'],['a','c'])
        self.assertEqual(serial['ideal_critical_path'],16)
        self.assertEqual((serial['elapsed'],serial['work_seconds'],serial['retry_job_seconds']),(31,31,10))
        self.assertEqual((records['b']['ready_at'],records['b']['queue_wait']),(0,20))
        self.assertEqual((records['c']['ready_at'],records['c']['queue_wait']),(20,5))
        self.assertEqual(serial['queued_job_seconds'],25)
        self.assertEqual((parallel['elapsed'],parallel['queued_job_seconds'],parallel['work_seconds']),(26,0,31))

    def test_critical_chain_ties_are_deterministic_and_skips_have_no_wait(self):
        jobs=[{'id':'z','duration':10},{'id':'a','duration':10},
              {'id':'last','needs':['z','a'],'duration':5}]
        self.assertEqual(plan(jobs)['ideal_critical_jobs'],['a','last'])
        self.assertEqual(plan(list(reversed(jobs)))['ideal_critical_jobs'],['a','last'])
        failed=plan([{'id':'a','duration':10,'fail_attempts':1},{'id':'b','needs':['a'],'duration':5}])
        skipped=next(job for job in failed['jobs'] if job['id']=='b')
        self.assertIsNone(skipped['ready_at'])
        self.assertIsNone(skipped['queue_wait'])
        self.assertEqual(skipped['execution_seconds'],0)

    def test_retry_success_and_exhaustion_skip(self):
        jobs=[{'id':'build','duration':10,'retries':1,'fail_attempts':1},{'id':'deploy','needs':['build'],'duration':5}]
        r=plan(jobs)
        self.assertEqual((r['elapsed'],r['status'],r['jobs'][0]['attempts']),(25,'passed',2))
        jobs[0]['fail_attempts']=2
        r=plan(jobs)
        self.assertEqual((r['elapsed'],r['status'],r['jobs'][1]['status']),(20,'failed','skipped'))

    def test_failure_propagates_transitively_but_independent_job_finishes(self):
        r=plan([{'id':'a','duration':1,'fail_attempts':1},{'id':'b','needs':['a'],'duration':2},{'id':'c','needs':['b'],'duration':2},{'id':'z','duration':8}])
        states={j['id']:j['status'] for j in r['jobs']}
        self.assertEqual(states,{'a':'failed','b':'skipped','c':'skipped','z':'passed'})
        self.assertEqual(r['elapsed'],8)

    def test_cycles_missing_dependencies_duplicate_ids_and_bool_rejected(self):
        invalid=[[{'id':'a','duration':1,'needs':['a']}],[{'id':'a','duration':1,'needs':['missing']}],[{'id':'a','duration':1},{'id':'a','duration':2}],[{'id':'a','duration':True}]]
        for jobs in invalid:
            with self.assertRaises(ValidationError):
                plan(jobs)

    def test_worker_capacity_never_exceeded(self):
        r=plan([{'id':f'job-{i}','duration':i+1} for i in range(10)],3)
        for time in range(r['elapsed']):
            self.assertLessEqual(sum(j['start']<=time<j['end'] for j in r['jobs']),3)

    def test_budget_and_weighted_burn(self):
        r=d.reliability({'csv':'timestamp,total,bad\n2026-01-01T00:00:00Z,1000,1\n2026-01-01T01:00:00Z,9000,18','target':99.9})
        self.assertEqual((r['allowed_bad'],r['remaining_bad']),(10,-9))
        self.assertAlmostEqual(r['burn_rate'],1.9)
        self.assertAlmostEqual(r['latest_hour_burn'],2)

    def test_gaps_zero_traffic_and_complete_six_hour_window(self):
        csv='timestamp,total,bad\n'+'\n'.join(f'2026-01-01T0{i}:00:00Z,1000,1' for i in range(6))
        self.assertEqual(d.reliability({'csv':csv})['recent_six_hour_burn'],1)
        gap=d.reliability({'csv':'timestamp,total,bad\n2026-01-01T00:00:00Z,0,0\n2026-01-01T02:00:00Z,0,0'})
        self.assertEqual(gap['missing_hours'],1)
        self.assertIsNone(gap['burn_rate'])
        self.assertIsNone(gap['recent_six_hour_burn'])

    def test_gap_ranges_are_normalized_sorted_and_inclusive(self):
        result=d.reliability({'csv':'timestamp,total,bad\n2026-01-02T05:00:00Z,1000,0\n2026-01-02T00:00:00+01:00,1000,0\n2026-01-02T01:00:00Z,1000,0'})
        self.assertEqual(result['missing_ranges'],[
            {'first_missing':'2026-01-02T00:00:00+00:00','last_missing':'2026-01-02T00:00:00+00:00','hours':1},
            {'first_missing':'2026-01-02T02:00:00+00:00','last_missing':'2026-01-02T04:00:00+00:00','hours':3}])
        self.assertEqual(result['missing_hours'],4)
        self.assertEqual(result['coverage']['observed_hours'],3)
        self.assertEqual(result['coverage']['expected_hours'],7)
        self.assertIsNone(result['recent_six_hour_burn'])

    def test_gap_ranges_do_not_expand_large_spans_or_infer_outer_coverage(self):
        result=d.reliability({'csv':'timestamp,total,bad\n0001-01-01T00:00:00Z,1,0\n9999-12-31T23:00:00Z,1,0'})
        self.assertEqual(len(result['missing_ranges']),1)
        self.assertEqual(result['missing_ranges'][0]['hours'],result['missing_hours'])
        self.assertEqual(result['coverage']['expected_hours'],87649416)
        single=d.reliability({'csv':'timestamp,total,bad\n2026-01-01T00:00:00Z,0,0'})
        self.assertEqual(single['missing_ranges'],[])
        self.assertEqual(single['coverage']['expected_hours'],1)

    def test_invalid_metric_timestamps_counts_and_duplicates(self):
        for records in ['2026-01-01T00:30:00Z,10,1','2026-01-01T00:00:00,10,1','2026-01-01T00:00:00Z,10,11','2026-01-01T00:00:00Z,10,1\n2026-01-01T01:00:00+01:00,10,1']:
            with self.assertRaises(ValidationError):
                d.reliability({'csv':'timestamp,total,bad\n'+records})

class DevOpsHttpTests(unittest.TestCase):
    setUpClass=classmethod(test_portfolio.HttpTests.setUpClass.__func__)
    tearDownClass=classmethod(test_portfolio.HttpTests.tearDownClass.__func__)
    request=test_portfolio.HttpTests.request

    def test_all_routes_and_assets(self):
        for route,data in [('manifest',{'text':json.dumps(manifest())}),('pipeline',{'text':json.dumps({'jobs':[{'id':'test','duration':10}]})}),('reliability',{'csv':'timestamp,total,bad\n2026-01-01T00:00:00Z,10,0'})]:
            with self.request('/api/devops/'+route,json.dumps(data).encode(),{'Content-Type':'application/json','X-Portfolio-Client':'browser'}) as response:
                self.assertEqual(response.status,200)
        for path in ['/devops','/devops.js','/devops.css']:
            with self.request(path) as response:
                self.assertEqual(response.status,200)

    def test_bad_pipeline_returns_400(self):
        with self.request('/api/devops/pipeline',b'{"text":"{}"}',{'Content-Type':'application/json','X-Portfolio-Client':'browser'}) as response:
            self.assertEqual(response.status,400)
