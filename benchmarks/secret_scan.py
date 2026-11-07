"""Reproduce local Secret Sentinel timings; optionally compare a reviewed Git revision.

python -m benchmarks.secret_scan --baseline ba1ccc0 --findings 4000 --runs 5
"""
import argparse
import json
import platform
import statistics
import subprocess
import time
import types
from portfolio.security_apps import scan_secrets


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--findings',type=int,default=4000)
    parser.add_argument('--runs',type=int,default=5)
    parser.add_argument('--baseline',help='Local Git revision whose security module should be compared')
    args=parser.parse_args()
    if not 1<=args.findings<=4000 or not 1<=args.runs<=100:
        parser.error('Use 1–4000 findings and 1–100 runs')
    payload={'text':'\n'.join(f'password="SYNTHETIC_VALUE_{index}_'+'A'*70+'"'
                               for index in range(args.findings))}
    expected=scan_secrets(payload)
    implementations={'current':scan_secrets}
    if args.baseline:
        source=subprocess.check_output(['git','show',f'{args.baseline}:portfolio/security_apps.py']).decode('utf-8')
        baseline=types.ModuleType('portfolio._benchmark_baseline');baseline.__package__='portfolio'
        exec(compile(source,'benchmark_baseline.py','exec'),baseline.__dict__)
        implementations['baseline']=baseline.scan_secrets
    report={'python':platform.python_version(),'platform':platform.system(),'findings':args.findings,'runs':args.runs,'median_ms':{}}
    for name,function in implementations.items():
        assert function(payload)==expected, 'Reports differ; performance comparison is not valid'
        measurements=[]
        for _ in range(args.runs):
            start=time.perf_counter();function(payload);measurements.append(time.perf_counter()-start)
        report['median_ms'][name]=round(statistics.median(measurements)*1000,3)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
