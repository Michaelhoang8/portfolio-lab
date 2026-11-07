import json
import math
import statistics
import unittest
import test_portfolio
from portfolio import ml_apps as m
from portfolio.validation import ValidationError

def training_csv():
    return 'signal,constant,label\n'+'\n'.join(f'{i},7,{int(i>0)}' for i in range(-20,21) if i)

class MLTests(unittest.TestCase):
    def test_oversized_numeric_parameters_raise_validation_errors(self):
        with self.assertRaises(ValidationError):
            m.number(10**1000,'threshold',0,1)
        with self.assertRaises(ValidationError):
            m.evaluate({'csv':'actual,score\n0,0.1\n1,0.9','threshold':10**1000})

    def test_auc_known_rankings_and_ties(self):
        self.assertEqual(m.auc([0,0,1,1],[.1,.4,.35,.8]),.75)
        self.assertEqual(m.auc([0,1],[.5,.5]),.5)
        self.assertEqual(m.auc([0,1],[.9,.1]),0)
        self.assertIsNone(m.auc([1,1],[.1,.9]))

    def test_confusion_and_probability_losses(self):
        r=m.metrics([0,1,1,0],[.1,.8,.4,.7])
        self.assertEqual(r['confusion'],{'tp':1,'fp':1,'tn':1,'fn':1})
        self.assertEqual((r['precision'],r['recall'],r['f1']),(.5,.5,.5))
        self.assertAlmostEqual(r['brier'],(.01+.04+.36+.49)/4)
        self.assertEqual(m.metrics([0,1],[0,1])['log_loss'],0)

    def test_undefined_metrics_and_threshold_boundary(self):
        r=m.metrics([0,0],[0,.5],1)
        self.assertIsNone(r['precision'])
        self.assertIsNone(r['recall'])
        self.assertIsNone(r['f1'])
        self.assertEqual(m.metrics([1],[.5],.5)['confusion']['tp'],1)

    def test_evaluation_calibration_includes_endpoints(self):
        r=m.evaluate({'csv':'actual,score\n0,0\n1,1\n1,0.2'})
        self.assertEqual(sum(b['count'] for b in r['calibration']),3)
        self.assertEqual(r['calibration'][0]['count'],1)
        self.assertEqual(r['calibration'][1]['count'],1)
        self.assertEqual(r['calibration'][-1]['count'],1)

    def test_evaluation_rejects_invalid_inputs(self):
        for csv in ['actual,score\n0,NaN','actual,score\n0,1.1','actual,score\n0.5,0.2','x,y\n1,2']:
            with self.assertRaises(ValidationError):
                m.evaluate({'csv':csv})

    def test_training_improves_loss_and_is_reproducible(self):
        a=m.train({'csv':training_csv()})
        b=m.train({'csv':training_csv()})
        self.assertEqual(a,b)
        self.assertLess(a['loss_history'][-1]['log_loss'],a['loss_history'][0]['log_loss'])
        self.assertGreater(a['metrics']['accuracy'],a['baseline_accuracy'])
        self.assertEqual(a['model']['weights'][1],0)

    def test_scaling_fits_train_rows_only_and_split_disjoint(self):
        r=m.train({'csv':training_csv(),'seed':7})
        self.assertFalse(set(r['train_records']) & set(r['test_records']))
        self.assertEqual(len(r['train_records'])+len(r['test_records']),40)
        rows=training_csv().splitlines()
        expected=statistics.mean(float(rows[i-1].split(',')[0]) for i in r['train_records'])
        self.assertEqual(r['features'][0]['mean'],expected)

    def test_exported_model_reproduces_test_predictions(self):
        r=m.train({'csv':training_csv()})
        model=r['model']; rows=training_csv().splitlines()
        for item in r['predictions']:
            x=[float(v) for v in rows[item['record']-1].split(',')[:-1]]
            score=m.sigmoid(model['intercept']+sum(w*(v-mean)/scale for w,v,mean,scale in zip(model['weights'],x,model['means'],model['scales'])))
            self.assertAlmostEqual(score,item['score'])

    def test_training_rejects_duplicates_and_bad_classes(self):
        for text in [training_csv()+'\n1,7,1','x,label\n'+'\n'.join(f'{i},0' for i in range(12))]:
            with self.assertRaises(ValidationError):
                m.train({'csv':text})

    def test_search_ranking_contributions_and_unseen_query(self):
        data={'documents':'database rollback transaction\n---\nflowers garden\n---\ndatabase backups','query':'rollback transaction'}
        r=m.search(data)
        self.assertEqual(r['results'][0]['document'],1)
        self.assertAlmostEqual(sum(t['contribution'] for t in r['results'][0]['matched_terms']),r['results'][0]['score'])
        self.assertEqual(m.search({**data,'query':'spaceships'})['results'],[])

    def test_search_explanations_follow_selected_algorithm_and_reconcile(self):
        data={'documents':'apple apple banana\n---\napple cherry\n---\nbanana cherry cherry cherry','query':'apple banana'}
        reports={algorithm:m.search({**data,'algorithm':algorithm}) for algorithm in ('tfidf','bm25')}
        for algorithm,report in reports.items():
            for item in report['results']:
                self.assertAlmostEqual(sum(term['contribution'] for term in item['matched_terms']),item['score'])
                self.assertAlmostEqual(sum(term['tfidf_contribution'] for term in item['matched_terms']),item['tfidf_score'])
                self.assertAlmostEqual(sum(term['bm25_contribution'] for term in item['matched_terms']),item['bm25_score'])
                self.assertEqual([term['contribution'] for term in item['matched_terms']],
                                 sorted((term['contribution'] for term in item['matched_terms']),reverse=True))
        first=next(item for item in reports['bm25']['results'] if item['document']==1)
        terms={term['term']:term for term in first['matched_terms']}
        # N=3, df=2; this document and corpus average both have length 3.
        import math
        self.assertAlmostEqual(terms['apple']['contribution'],math.log(1.6)*5/3.5)
        self.assertAlmostEqual(terms['banana']['contribution'],math.log(1.6))
        self.assertEqual((terms['apple']['term_frequency'],terms['apple']['document_frequency']),(2,2))
        repeated=m.search({**data,'query':'apple apple banana','algorithm':'bm25'})
        self.assertEqual([(item['document'],item['score']) for item in repeated['results']],
                         [(item['document'],item['score']) for item in reports['bm25']['results']])
        for item in repeated['results']:
            original=next(row for row in reports['bm25']['results'] if row['document']==item['document'])
            self.assertEqual([(term['term'],term['contribution']) for term in item['matched_terms']],
                             [(term['term'],term['contribution']) for term in original['matched_terms']])
        self.assertNotEqual(terms['apple']['contribution'],terms['apple']['tfidf_contribution'])

    def test_search_empty_vocabulary_and_document_limit(self):
        for docs in ['the and\n---\na an','only one document']:
            with self.assertRaises(ValidationError):
                m.search({'documents':docs,'query':'test'})

class MLHttpTests(unittest.TestCase):
    setUpClass=classmethod(test_portfolio.HttpTests.setUpClass.__func__)
    tearDownClass=classmethod(test_portfolio.HttpTests.tearDownClass.__func__)
    request=test_portfolio.HttpTests.request

    def test_all_endpoints_and_assets(self):
        for route,data in [('train',{'csv':training_csv()}),('evaluate',{'csv':'actual,score\n0,0.2\n1,0.8'}),('search',{'documents':'cat dog\n---\nfish bird','query':'cat'})]:
            with self.request('/api/ml/'+route,json.dumps(data).encode(),{'Content-Type':'application/json','X-Portfolio-Client':'browser'}) as response:
                self.assertEqual(response.status,200)
                json.loads(response.read(),parse_constant=lambda value:self.fail('Nonfinite JSON: '+value))
        for path in ['/ml','/ml.js','/ml.css']:
            with self.request(path) as response:
                self.assertEqual(response.status,200)

    def test_invalid_evaluation_returns_400(self):
        with self.request('/api/ml/evaluate',b'{"csv":"actual,score\\n1,nan"}',{'Content-Type':'application/json','X-Portfolio-Client':'browser'}) as response:
            self.assertEqual(response.status,400)
