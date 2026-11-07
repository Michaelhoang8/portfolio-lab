import json
import unittest
import test_portfolio
from portfolio import security_apps as s
from portfolio.validation import ValidationError

def event(minute, status='failure', user='alice', ip='192.0.2.10'):
    return json.dumps({'timestamp':f'2026-01-01T10:{minute:02}:00Z','ip':ip,'user':user,'status':status})

class SecurityTests(unittest.TestCase):
    def test_logs_sort_and_correlate_success(self):
        text='\n'.join([event(5,'success'),event(4),event(0),event(3),event(1),event(2)])
        r=s.auth_logs({'text':text})
        self.assertEqual([a['rule'] for a in r['alerts']],['Failure burst','Success after failures'])
        self.assertEqual(r['alerts'][1]['line'],1)

    def test_window_is_inclusive_and_success_clears_account(self):
        r=s.auth_logs({'text':'\n'.join([event(0),event(10),event(10,'success'),event(11,'success')]),'threshold':2})
        self.assertEqual(sum(a['rule']=='Success after failures' for a in r['alerts']),1)
        outside=s.auth_logs({'text':'\n'.join([event(0),event(11)]),'threshold':2})
        self.assertEqual(outside['alerts'],[])

    def test_spraying_requires_distinct_users_and_no_cross_account_success(self):
        r=s.auth_logs({'text':'\n'.join([event(i,user=f'user-{i}') for i in range(5)]+[event(6,'success','other')])})
        self.assertIn('Multiple accounts targeted',[a['rule'] for a in r['alerts']])
        self.assertNotIn('Success after failures',[a['rule'] for a in r['alerts']])

    def test_bad_events_are_reported_without_echoing_input(self):
        r=s.auth_logs({'text':'not-json\n[]\n{"timestamp":"2026-01-01T00:00:00","ip":"bad","user":"x","status":"failure"}'})
        self.assertEqual((r['accepted'],len(r['rejected'])),(0,3))
        self.assertNotIn('not-json',json.dumps(r))
        with self.assertRaises(ValidationError):
            s.auth_logs({'text':event(0),'threshold':True})

    def test_logs_reject_ambiguous_json_and_numeric_ip_addresses(self):
        duplicate=event(0)[:-1]+',"status":"success"}'
        deep=event(0)[:-1]+',"extra":'+'['*100+'0'+']'*100+'}'
        invalid=[event(0,ip=1),event(0,ip=True),duplicate,deep,event(0)[:-1]+',"extra":NaN}']
        result=s.auth_logs({'text':'\n'.join([event(0),*invalid])})
        self.assertEqual(result['accepted'],1)
        self.assertEqual(len(result['rejected']),5)
        self.assertEqual(result['failures'],1)

    def test_failure_burst_rearms_after_window_expires(self):
        r=s.auth_logs({'text':'\n'.join([event(0),event(1),event(20),event(21)]),'threshold':2})
        self.assertEqual(sum(a['rule']=='Failure burst' for a in r['alerts']),2)

    def test_headers_case_insensitive_and_cookie_values_omitted(self):
        r=s.inspect_headers({'text':"CONTENT-SECURITY-POLICY: default-src 'self'; frame-ancestors 'none'\nStrict-Transport-Security: max-age=31536000\nX-Content-Type-Options: nosniff\nReferrer-Policy: no-referrer\nSet-Cookie: session=DO_NOT_ECHO; Secure; HttpOnly; SameSite=Lax"})
        self.assertEqual(r['review_count'],0)
        self.assertNotIn('DO_NOT_ECHO',json.dumps(r))

    def test_report_only_csp_does_not_count_as_enforcement(self):
        r=s.inspect_headers({'text':"Content-Security-Policy-Report-Only: default-src 'none'\nX-Frame-Options: DENY"})
        self.assertEqual(r['findings'][0]['status'],'review')
        self.assertEqual(r['findings'][1]['status'],'observed')

    def test_ambiguous_headers_and_broad_policies_need_review(self):
        r=s.inspect_headers({'text':"X-Content-Type-Options: nosniff\nX-Content-Type-Options: none\nContent-Security-Policy: script-src *; frame-ancestors *\nnot a header\nStrict-Transport-Security: max-age=0"})
        self.assertEqual(r['duplicate_headers'],['x-content-type-options'])
        self.assertEqual(r['malformed_lines'],[4])
        self.assertEqual(r['observed_count'],0)

    def test_secret_overlap_is_deduplicated_without_leakage(self):
        fake='ghp_'+'A'*36
        r=s.scan_secrets({'text':f'api_key = "{fake}"'})
        self.assertEqual(r['count'],1)
        self.assertNotIn(fake,json.dumps(r))
        self.assertEqual(r['findings'][0]['severity'],'high')

    def test_private_key_multiline_and_bearer(self):
        text='comment\n-----BEGIN PRIVATE KEY-----\nFAKE_DATA\n-----END PRIVATE KEY-----\nAuthorization: Bearer FICTIONAL_BEARER_VALUE'
        r=s.scan_secrets({'text':text})
        self.assertEqual([f['line'] for f in r['findings']],[2,5])
        self.assertNotIn('FAKE_DATA',json.dumps(r))
        self.assertNotIn('FICTIONAL_BEARER_VALUE',json.dumps(r))

    def test_secret_no_match_and_size_limits(self):
        self.assertEqual(s.scan_secrets({'text':'ordinary text'})['count'],0)
        for text in ['', 'a'*500001, 'x\n'*5001]:
            with self.assertRaises(ValidationError):
                s.scan_secrets({'text':text})

class SecurityHttpTests(unittest.TestCase):
    setUpClass=classmethod(test_portfolio.HttpTests.setUpClass.__func__)
    tearDownClass=classmethod(test_portfolio.HttpTests.tearDownClass.__func__)
    request=test_portfolio.HttpTests.request

    def test_endpoints_and_static_assets(self):
        for mode, text in [('logs',event(0)),('headers','X-Frame-Options: DENY'),('secrets','password=FICTIONAL_VALUE')]:
            with self.request('/api/security/'+mode,json.dumps({'text':text}).encode(),{'Content-Type':'application/json','X-Portfolio-Client':'browser'}) as response:
                self.assertEqual(response.status,200)
                self.assertNotIn('FICTIONAL_VALUE',response.read().decode())
        for path in ['/security','/security.js','/security.css']:
            with self.request(path) as response:
                self.assertEqual(response.status,200)

    def test_invalid_security_request(self):
        with self.request('/api/security/secrets',b'{"text":[]}',{'Content-Type':'application/json','X-Portfolio-Client':'browser'}) as response:
            self.assertEqual(response.status,400)
