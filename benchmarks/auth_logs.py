"""Reproduce local Auth Watch timings; optionally compare a reviewed Git revision.

python -m benchmarks.auth_logs --baseline ca152db --events 4000 --runs 5
"""
import argparse
import json
import platform
import statistics
import subprocess
import time
import types
from portfolio.security_apps import auth_logs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events',type=int,default=4000)
    parser.add_argument('--runs',type=int,default=5)
    parser.add_argument('--baseline',help='Local Git revision whose security module should be compared')
    args=parser.parse_args()
    if not 1<=args.events<=4000 or not 1<=args.runs<=100:
        parser.error('Use 1–4000 events and 1–100 runs')
    payload={'text':'\n'.join(json.dumps({'timestamp':'2026-01-01T00:00:00Z','ip':'192.0.2.1',
        'user':f'u{i%100}','status':'failure'},separators=(',',':')) for i in range(args.events)), 'threshold':50}
    expected=auth_logs(payload)
    implementations={'current':auth_logs}
    if args.baseline:
        source=subprocess.check_output(['git','show',f'{args.baseline}:portfolio/security_apps.py']).decode('utf-8')
        baseline=types.ModuleType('portfolio._benchmark_baseline');baseline.__package__='portfolio'
        exec(compile(source,'benchmark_baseline.py','exec'),baseline.__dict__)
        implementations['baseline']=baseline.auth_logs
    report={'python':platform.python_version(),'platform':platform.system(),'events':args.events,'runs':args.runs,'median_ms':{}}
    for name,function in implementations.items():
        assert function(payload)==expected, 'Reports differ; performance comparison is not valid'
        measurements=[]
        for _ in range(args.runs):
            start=time.perf_counter();function(payload);measurements.append(time.perf_counter()-start)
        report['median_ms'][name]=round(statistics.median(measurements)*1000,3)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
