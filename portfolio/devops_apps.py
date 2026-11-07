"""Offline deployment policy checks, deterministic pipeline simulation, and SLO math."""
import heapq
import json
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from .data_apps import parse
from .validation import ValidationError, integer
from .ml_apps import number

def document(data):
    text=data.get('text')
    if not isinstance(text,str) or not text.strip() or len(text.encode())>200_000:
        raise ValidationError('Provide a JSON object of 1–200,000 bytes')
    try:
        value=json.loads(text)
    except (ValueError,RecursionError):
        raise ValidationError('Input must be valid JSON') from None
    if not isinstance(value,dict):
        raise ValidationError('Input must be a JSON object')
    return value

def obj(value,name):
    if not isinstance(value,dict):
        raise ValidationError(f'{name} must be an object')
    return value

def manifest(data):
    doc=document(data)
    if doc.get('kind')!='Deployment' or doc.get('apiVersion')!='apps/v1':
        raise ValidationError('Supported input: one apps/v1 Kubernetes Deployment in JSON')
    spec=obj(doc.get('spec'),'spec')
    template=obj(spec.get('template'),'spec.template')
    pod=obj(template.get('spec'),'spec.template.spec')
    containers=pod.get('containers')
    if not isinstance(containers,list) or not 1<=len(containers)<=30:
        raise ValidationError('Provide 1–30 containers')
    findings=[]
    def check(path,rule,ok,action):
        findings.append({'path':path,'rule':rule,'status':'observed' if ok else 'review','action':action})
    replicas=spec.get('replicas',1)
    check('spec.replicas','Redundant replicas',type(replicas) is int and replicas>=2,'Consider at least two replicas where availability requirements justify them.')
    strategy=obj(spec.get('strategy',{}),'strategy')
    check('spec.strategy','Rolling update',strategy.get('type','RollingUpdate')=='RollingUpdate','Review service impact before using Recreate; rollout availability also depends on readiness and capacity.')
    selector=obj(spec.get('selector',{}),'selector')
    labels=obj(obj(template.get('metadata',{}),'template.metadata').get('labels',{}),'template labels')
    match=obj(selector.get('matchLabels',{}),'selector.matchLabels')
    check('spec.selector.matchLabels','Selector matches template',bool(match) and all(labels.get(k)==v for k,v in match.items()),'Use nonempty matchLabels consistent with pod labels; matchExpressions are outside this checker.')
    pod_security=obj(pod.get('securityContext',{}),'pod.securityContext')
    for index,container in enumerate(containers):
        container=obj(container,f'container {index}')
        path=f'spec.template.spec.containers[{index}]'
        image=container.get('image','')
        check(path+'.image','Immutable image reference',isinstance(image,str) and bool(re.search(r'@sha256:[0-9a-fA-F]{64}$',image)),'Pin a verified image digest for reproducible deployments. Digest presence does not verify provenance.')
        resources=obj(container.get('resources',{}),'resources')
        for field in ('requests','limits'):
            values=obj(resources.get(field,{}),f'resources.{field}')
            present=all(isinstance(values.get(k),(str,int,float)) and not isinstance(values.get(k),bool) and str(values[k]).strip() not in ('','0','0m','0Mi') for k in ('cpu','memory'))
            check(path+'.resources.'+field,f'CPU / memory {field}',present,'Set appropriate CPU and memory quantities based on measurements. This check only verifies presence, not quantity syntax or sizing.')
        for probe in ('readinessProbe','livenessProbe'):
            value=container.get(probe)
            present=isinstance(value,dict) and any(isinstance(value.get(k),dict) for k in ('httpGet','tcpSocket','exec','grpc'))
            check(path+'.'+probe,probe,present,'Choose a suitable probe and timings. A declared probe does not prove application health.')
        security=obj(container.get('securityContext',{}),'container.securityContext')
        check(path+'.securityContext.runAsNonRoot','Non-root execution',security.get('runAsNonRoot',pod_security.get('runAsNonRoot')) is True,'Set runAsNonRoot and use an image compatible with a non-root user.')
        check(path+'.securityContext.allowPrivilegeEscalation','Privilege escalation disabled',security.get('allowPrivilegeEscalation') is False,'Set allowPrivilegeEscalation: false where compatible.')
        check(path+'.securityContext.privileged','Privileged mode disabled',security.get('privileged',False) is False,'Avoid privileged containers unless explicitly required and isolated.')
    return {'containers':len(containers),'findings':findings,'review_count':sum(f['status']=='review' for f in findings),
            'note':'Static review only, not Kubernetes schema validation or a security certification. No cluster is contacted.'}

def pipeline(data):
    doc=document(data)
    workers=integer(data,'workers',1,8) if 'workers' in data else 2
    items=doc.get('jobs')
    if not isinstance(items,list) or not 1<=len(items)<=50:
        raise ValidationError('Provide 1–50 jobs')
    jobs={}
    for item in items:
        item=obj(item,'job')
        name=item.get('id')
        if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}',name) or name in jobs:
            raise ValidationError('Job IDs must be unique, 1–60 letters/digits/underscores/hyphens')
        needs=item.get('needs',[])
        if not isinstance(needs,list) or any(not isinstance(n,str) for n in needs) or len(set(needs))!=len(needs):
            raise ValidationError('needs must contain unique job ID strings')
        duration=integer(item,'duration',1,3600)
        retries=integer(item,'retries',0,3) if 'retries' in item else 0
        failures=integer(item,'fail_attempts',0,4) if 'fail_attempts' in item else 0
        jobs[name]={'needs':needs,'duration':duration,'retries':retries,'fail_attempts':failures}
    if any(dep not in jobs for job in jobs.values() for dep in job['needs']):
        raise ValidationError('Every dependency must name an existing job')
    ordered=[]
    while len(ordered)<len(jobs):
        ready=sorted(name for name,job in jobs.items() if name not in ordered and all(dep in ordered for dep in job['needs']))
        if not ready:
            raise ValidationError('Pipeline contains a dependency cycle')
        ordered.extend(ready)
    critical={}
    for name in ordered:
        critical[name]=jobs[name]['duration']+max((critical[d] for d in jobs[name]['needs']),default=0)
    pending=set(jobs); results={}; running=[]; now=0
    while pending or running:
        while running and running[0][0]<=now:
            _,name=heapq.heappop(running)
            results[name]['status']='failed' if jobs[name]['fail_attempts']>jobs[name]['retries'] else 'passed'
        changed=True
        while changed:
            changed=False
            for name in sorted(pending):
                if any(results.get(dep,{}).get('status') in ('failed','skipped') for dep in jobs[name]['needs']):
                    results[name]={'id':name,'status':'skipped','start':None,'end':None,'attempts':0,'needs':jobs[name]['needs']}
                    pending.remove(name); changed=True
        ready=sorted(name for name in pending if all(results.get(dep,{}).get('status')=='passed' for dep in jobs[name]['needs']))
        for name in ready[:workers-len(running)]:
            job=jobs[name]
            attempts=min(job['fail_attempts']+1,job['retries']+1)
            end=now+job['duration']*attempts
            results[name]={'id':name,'status':'running','start':now,'end':end,'attempts':attempts,'needs':job['needs']}
            heapq.heappush(running,(end,name));pending.remove(name)
        if running:
            now=running[0][0]
        elif pending:
            raise ValidationError('Pipeline cannot progress')
    timeline=sorted(results.values(),key=lambda r:(r['start'] is None,r['start'] or 0,r['id']))
    return {'jobs':timeline,'workers':workers,'elapsed':now,'ideal_critical_path':max(critical.values()),
            'status':'failed' if any(r['status']=='failed' for r in timeline) else 'passed',
            'note':'Deterministic simulation only. No commands execute. Alphabetical scheduling; retries hold a worker without backoff. Ideal critical path assumes unlimited workers and first-attempt success.'}

def reliability(data):
    headers,rows=parse(data)
    if not all(name in headers for name in ('timestamp','total','bad')):
        raise ValidationError('CSV requires timestamp,total,bad columns')
    target=number(data.get('target',99.9),'SLO percentage',90,99.9999)
    buckets=[];seen=set()
    for index,row in enumerate(rows,2):
        try:
            stamp=datetime.fromisoformat(row[headers.index('timestamp')].replace('Z','+00:00'))
            if stamp.utcoffset() is None:
                raise ValueError()
            stamp=stamp.astimezone(timezone.utc)
            if stamp.minute or stamp.second or stamp.microsecond or stamp in seen:
                raise ValueError()
            counts=[]
            for name in ('total','bad'):
                raw=row[headers.index(name)].strip()
                if not re.fullmatch(r'[0-9]{1,12}',raw):
                    raise ValueError()
                counts.append(int(raw))
            total,bad=counts
            if bad>total:
                raise ValueError()
        except (ValueError,OverflowError):
            raise ValidationError(f'Record {index}: use a unique UTC-hour-aligned timestamp with timezone and integer counts 0 ≤ bad ≤ total') from None
        seen.add(stamp);buckets.append({'timestamp':stamp,'total':total,'bad':bad})
    buckets.sort(key=lambda b:b['timestamp'])
    total=sum(b['total'] for b in buckets);bad=sum(b['bad'] for b in buckets)
    allowance=Decimal(1)-Decimal(str(target))/100
    budget=Decimal(total)*allowance
    def burn(selected):
        requests=sum(b['total'] for b in selected)
        return float(Decimal(sum(b['bad'] for b in selected))/requests/allowance) if requests else None
    last=buckets[-1]['timestamp']
    recent=[b for b in buckets if last-b['timestamp']<=timedelta(hours=5)]
    gaps=int((last-buckets[0]['timestamp']).total_seconds()/3600)+1-len(buckets)
    return {'target':target,'total':total,'bad':bad,'success_rate':(total-bad)/total if total else None,
            'allowed_bad':float(budget),'remaining_bad':float(budget-bad),
            'budget_used':float(Decimal(bad)/budget) if budget else None,
            'burn_rate':burn(buckets),'latest_hour_burn':burn([buckets[-1]]),
            'recent_six_hour_burn':burn(recent) if len(recent)==6 else None,
            'missing_hours':gaps,'buckets':[{**b,'timestamp':b['timestamp'].isoformat(),'burn_rate':burn([b])} for b in buckets],
            'note':'Request-based SLO for the supplied hourly buckets only. Missing hours are not assumed healthy. Six-hour burn is unavailable without six consecutive buckets. Zero traffic gives undefined rates; no forecast or live alerting is performed.'}
