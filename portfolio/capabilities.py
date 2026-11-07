"""Inspectable planning and diagnostic extensions; no external services required."""
import math
import statistics
from collections import Counter, defaultdict
from decimal import Decimal
from . import data_apps, ml_apps, security_apps, devops_apps, json_input
from .validation import ValidationError, integer


def table(title, headers, rows):
    return {'title': title, 'headers': headers, 'rows': rows}


def enrich(path, data, result):
    """Attach diagnostics without changing existing response fields."""
    tables, notes = [], []
    if path == '/api/data/profile':
        headers, rows = data_apps.parse(data)
        numeric = {}
        outliers = []
        for col in result['columns']:
            if col['type'] != 'numeric':
                continue
            index = headers.index(col['name'])
            values = [data_apps.numeric(row[index].strip()) if row[index].strip() else None for row in rows]
            present = sorted(v for v in values if v is not None)
            if len(present) >= 4:
                q1, _, q3 = statistics.quantiles(present, n=4, method='inclusive')
                low, high = q1-1.5*(q3-q1), q3+1.5*(q3-q1)
                flagged = [i+2 for i, v in enumerate(values) if v is not None and (v < low or v > high)]
                outliers.append([col['name'], q1, q3, len(flagged), ', '.join(map(str, flagged[:20])) or 'None'])
            numeric[col['name']] = values
        correlations = []
        names = list(numeric)[:12]
        for i, left in enumerate(names):
            for right in names[i+1:]:
                pairs = [(a,b) for a,b in zip(numeric[left],numeric[right]) if a is not None and b is not None]
                value = None
                if len(pairs) >= 3:
                    x,y = zip(*pairs)
                    try:
                        # Pearson correlation is unchanged by translation and positive
                        # scaling; normalize first to avoid underflow for tiny units.
                        centered_x=[v-x[0] for v in x];centered_y=[v-y[0] for v in y]
                        scale_x=max(map(abs,centered_x)) or 1
                        scale_y=max(map(abs,centered_y)) or 1
                        value = statistics.correlation([v/scale_x for v in centered_x],
                                                       [v/scale_y for v in centered_y])
                    except statistics.StatisticsError:
                        pass
                correlations.append([left,right,len(pairs),round(value,5) if value is not None else 'Undefined'])
        tables = [table('IQR outlier diagnostics', ['Column','Q1','Q3','Flagged rows','First 20 record numbers'], outliers),
                  table('Pairwise Pearson correlations', ['Column A','Column B','Complete pairs','Correlation'],correlations)]
        notes = ['Outliers use inclusive quartiles and 1.5×IQR fences; they are not automatically errors. Correlations use pairwise complete records, at least three pairs, and the first 12 numeric columns. Constant columns are undefined.']
    elif path == '/api/data/clean':
        headers, rows = data_apps.parse(data)
        options = data.get('options',{})
        audit, seen = [], {}
        output_number = 1
        for record, original in enumerate(rows,2):
            row = [v.strip() for v in original] if options.get('trim',True) else original[:]
            changed = [headers[i] for i,(a,b) in enumerate(zip(original,row)) if a!=b]
            key = tuple(row)
            duplicate_of = ''
            if options.get('drop_empty',True) and all(not v.strip() for v in row):
                action = 'Dropped blank row'; output_record = ''
            elif options.get('deduplicate',True) and key in seen:
                action = 'Removed duplicate'; duplicate_of = seen[key]; output_record = ''
            else:
                seen.setdefault(key,record)
                output_number += 1; output_record = output_number
                action = 'Trimmed' if changed else 'Unchanged'
            audit.append([record,action,output_record,duplicate_of,', '.join(changed)])
        result['row_audit'] = audit
        result['audit_csv'] = data_apps.safe_csv(['source_record','action','output_record','duplicate_of','trimmed_columns'],[[str(v) for v in row] for row in audit])
        tables = [table('Cleaning provenance · first 50 records',['Source record','Action','Output record','Duplicate of','Trimmed columns'],audit[:50])]
        notes = ['Record numbers include the header as record 1. Audit exports contain all records; original field values are omitted. A duplicate points to the first retained source record.']
    elif path == '/api/data/sales':
        trend = []
        previous = None
        for item in result['monthly']:
            value = Decimal(item['amount']); label = item['label']
            growth = None; reason = 'First observed month'
            if previous:
                y,m = map(int,label.split('-')); py,pm = map(int,previous[0].split('-'))
                if y*12+m != py*12+pm+1: reason = 'Gap in observed months'
                elif previous[1] <= 0: reason = 'Prior net amount is nonpositive'
                else: growth = (value-previous[1])/previous[1]*100; reason = 'Consecutive observed months'
            trend.append([label,str(value),round(float(growth),2) if growth is not None else 'N/A',reason]); previous=(label,value)
        headers, rows = data_apps.parse(data)
        idx = headers.index(data.get('mapping',{}).get('amount','amount'))
        rejected = {r['record'] for r in result['rejections']}
        amounts = [Decimal(row[idx].strip()) for i,row in enumerate(rows,2) if i not in rejected]
        gross = sum((v for v in amounts if v>0),Decimal(0)); refunds = -sum((v for v in amounts if v<0),Decimal(0))
        tables = [table('Monthly growth', ['Month','Net amount','Growth %','Comparison'],trend),table('Revenue reconciliation',['Gross positive sales','Refund magnitude','Net amount','Refund / gross %'],[[str(gross),str(refunds),result['total'],round(float(refunds/gross*100),2) if gross else 'N/A']])]
        notes = ['Growth does not bridge missing months. Partial-month coverage is not inferred; compare equivalent reporting periods. Refund ratio uses gross positive sales as the denominator.']
    elif path == '/api/security/logs':
        grouped = defaultdict(list)
        for alert in result['alerts']: grouped[alert['ip']].append(alert)
        incidents=[]
        for ip,alerts in grouped.items():
            incidents.append([ip,'high' if any(a['severity']=='high' for a in alerts) else 'medium',len(alerts),len({a['user'] for a in alerts}),min(a['timestamp'] for a in alerts),max(a['timestamp'] for a in alerts),', '.join(sorted({a['rule'] for a in alerts}))])
        incidents.sort(key=lambda r:(r[1]!='high',-r[2],r[0]))
        tables=[table('Source-level incident queue',['Source IP','Priority','Alerts','Users in alerts','First alert','Last alert','Rules'],incidents)]
        notes=['Groups alerts by source across the supplied batch, not by threat actor. Shared IPs can represent different users. Users counted here appear in alerts, not all authentication events.']
    elif path == '/api/security/headers':
        baseline=data.get('baseline_text','')
        if not isinstance(baseline,str): raise ValidationError('baseline_text must be text')
        if baseline.strip():
            old=security_apps.inspect_headers({'text':baseline})
            before={f['control']:f['status'] for f in old['findings']}; after={f['control']:f['status'] for f in result['findings']}
            rows=[]
            for control in sorted(set(before)|set(after)):
                a,b=before.get(control,'absent'),after.get(control,'absent')
                change='unchanged' if a==b else ('regression' if a=='observed' and b!='observed' else 'improvement' if b=='observed' else 'changed')
                rows.append([control,a,b,change])
            tables=[table('Policy baseline comparison',['Control','Baseline','Current','Change'],rows)]
            notes=['Compares heuristic statuses, not raw header values. Cookie controls are compared by ordinal position; changing cookie order can change their correspondence.']
        else:
            notes=['Paste an optional baseline header block to identify improvements and regressions. Header and cookie values are never included in the comparison report.']
    elif path == '/api/security/secrets':
        level=data.get('gate_severity','high')
        if level not in ('medium','high'): raise ValidationError('gate_severity must be medium or high')
        blocked=[f for f in result['findings'] if f['severity']=='high' or level=='medium']
        result['gate']={'minimum_severity':level,'blocked':bool(blocked),'blocking_findings':len(blocked)}
        counts=Counter((f['rule'],f['severity']) for f in result['findings'])
        tables=[table('Scan policy gate',['Minimum severity','Gate','Blocking findings'],[[level,'BLOCK' if blocked else 'PASS',len(blocked)]]),table('Rule summary',['Rule','Severity','Count'],[[r,s,c] for (r,s),c in sorted(counts.items())])]
        result['findings_csv']=data_apps.safe_csv(['rule','severity','line','action'],[[f['rule'],f['severity'],str(f['line']),f['action']] for f in result['findings']])
        notes=['PASS means no matching findings at the configured severity; it is not proof that the text contains no secrets. Exported findings contain locations and remediation, never matched values.']
    elif path == '/api/ml/evaluate':
        fp=ml_apps.number(data.get('false_positive_cost',1),'False positive cost',0,1e6)
        fn=ml_apps.number(data.get('false_negative_cost',5),'False negative cost',0,1e6)
        candidates=[]
        for row in result['thresholds']:
            c=row['confusion'];cost=c['fp']*fp+c['fn']*fn
            candidates.append([row['threshold'],c['fp'],c['fn'],cost,round(cost/result['rows'],5)])
        best=min(candidates,key=lambda row:(row[3],-row[0]))
        result['cost_analysis']={'fp_cost':fp,'fn_cost':fn,'best_grid_threshold':best[0],'minimum_cost':best[3]}
        tables=[table('Cost-sensitive threshold grid',['Threshold','False positives','False negatives','Total cost','Cost / row'],candidates)]
        notes=[f'Lowest cost on this 0.1-step grid: threshold {best[0]} (cost {best[3]:g}). Ties choose the higher threshold. Select thresholds on validation data, then assess once on an untouched test set. Costs are user-specified units.']
    elif path == '/api/devops/manifest':
        doc=devops_apps.document(data);spec=doc['spec'];replicas=spec.get('replicas',1)
        if type(replicas) is not int or not 0<=replicas<=100000: raise ValidationError('replicas must be an integer between 0 and 100000 for capacity analysis')
        rows=[];total=[Decimal(0)]*4; valid=[True]*4
        for c in spec['template']['spec']['containers']:
            vals=[]
            for i,(field,resource) in enumerate([('requests','cpu'),('limits','cpu'),('requests','memory'),('limits','memory')]):
                amount=quantity(c.get('resources',{}).get(field,{}).get(resource),resource)
                if amount is None: valid[i]=False
                else: total[i]+=amount
                vals.append(float(amount) if amount is not None else 'Unknown')
            rows.append([c.get('name','unnamed'),*vals])
        rows.append(['Deployment total × '+str(replicas),*[float(total[i]*replicas) if valid[i] else 'Unknown' for i in range(4)]])
        tables=[table('Steady-state resource envelope',['Container','CPU request cores','CPU limit cores','Memory request MiB','Memory limit MiB'],rows)]
        notes=['Totals exclude init containers, pod overhead, sidecars outside the containers array, and rolling-update surge. Missing or unsupported quantities make that total unknown. CPU supports cores/m; memory supports bytes, Ki/Mi/Gi/Ti and K/M/G/T. This is an estimate, not Kubernetes validation.']
    elif path == '/api/devops/pipeline':
        rows=[]
        for workers in range(1,9):
            run=result if workers==result['workers'] else devops_apps.pipeline({**data,'workers':workers})
            work=sum(j['end']-j['start'] for j in run['jobs'] if j['start'] is not None)
            rows.append([workers,run['elapsed'],round(work/(workers*run['elapsed'])*100,2),run['status']])
        tables=[table('Worker capacity comparison',['Workers','Elapsed seconds','Worker utilization %','Outcome'],rows),
                table('Where job time goes',['Job','Ready at','Runner wait','Execution','Retry time'],
                      [[j['id'],j['ready_at'],j['queue_wait'],j['execution_seconds'],j['retry_seconds']] for j in result['jobs']])]
        notes=['Uses the same deterministic jobs, retries, and alphabetical scheduling for each capacity. Utilization includes retry time; skipped jobs consume no worker time. This is not a cloud cost prediction.',
               'All timing values are seconds. Ready at is when dependencies have passed. Runner wait measures time eligible but waiting for capacity; dependency waiting is excluded. Execution includes retries. Job-seconds overlap across concurrent workers and should not be added to elapsed wall time.']
    elif path == '/api/devops/reliability':
        threshold=ml_apps.number(data.get('burn_threshold',2),'Burn threshold',.01,10000)
        short,long=result['latest_hour_burn'],result['recent_six_hour_burn']
        state='insufficient data' if short is None or long is None else 'firing' if short>=threshold and long>=threshold else 'not firing'
        result['burn_alert']={'threshold':threshold,'state':state,'short_hours':1,'long_hours':6}
        tables=[table('Two-window burn check',['1-hour burn','6-hour burn','Threshold','Status'],[[short if short is not None else 'N/A',long if long is not None else 'N/A',threshold,state]])]
        notes=['Both windows must reach the threshold. Missing buckets or zero traffic can make the check unavailable. This evaluates the end of the supplied dataset; no live monitor or notification is configured.']
    if tables or notes: result['capabilities']={'tables':tables,'notes':notes}
    return result


def quantity(value, resource):
    import re
    if isinstance(value,bool) or value is None: return None
    match=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)([A-Za-z]*)',str(value))
    if not match: return None
    amount=Decimal(match[1]);unit=match[2]
    units={'':Decimal(1),'m':Decimal('.001')} if resource=='cpu' else {'':Decimal(1),'Ki':Decimal(1024),'Mi':Decimal(1024**2),'Gi':Decimal(1024**3),'Ti':Decimal(1024**4),'K':Decimal(1000),'M':Decimal(1000**2),'G':Decimal(1000**3),'T':Decimal(1000**4)}
    if unit not in units or amount>Decimal('1e15'): return None
    return amount*units[unit]/(1 if resource=='cpu' else 1024**2)


def validated_model(model):
    algorithm='standardized binary logistic regression'
    if isinstance(model,dict) and model.get('algorithm',algorithm)!=algorithm:
        raise ValidationError('Unsupported model algorithm')
    if not isinstance(model,dict): raise ValidationError('Provide a trained model object')
    features=model.get('features')
    if not isinstance(features,list) or not 1<=len(features)<=12 or any(not isinstance(f,str) or not f.strip() or len(f)>1000 for f in features) or len(set(features))!=len(features): raise ValidationError('Model requires 1–12 unique feature names')
    vectors=[]
    for key in ('weights','means','scales'):
        values=model.get(key)
        if not isinstance(values,list) or len(values)!=len(features): raise ValidationError(f'Model {key} must match features')
        vectors.append([ml_apps.number(v,key,1e-12 if key=='scales' else -1e12,1e12) for v in values])
    weights,means,scales=vectors
    intercept=ml_apps.number(model.get('intercept'),'intercept',-1e12,1e12)
    threshold=ml_apps.number(model.get('threshold',.5),'threshold',0,1)
    return {'algorithm':algorithm,'features':features,'weights':weights,'means':means,
            'scales':scales,'intercept':intercept,'threshold':threshold}


def load_model(data):
    raw=data.get('text')
    if not isinstance(raw,str) or not raw.strip() or len(raw.encode('utf-8'))>200_000:
        raise ValidationError('Choose a model JSON file under 200 KB')
    try:
        parsed=json_input.decode(raw)
    except ValueError:
        raise ValidationError('Invalid model JSON: use unique fields and finite numbers') from None
    if isinstance(parsed,dict) and 'model' in parsed:
        parsed=parsed['model']
    return {'model':validated_model(parsed)}


def predict(data):
    model=validated_model(data.get('model'))
    features=model['features']
    weights,means,scales=(model[key] for key in ('weights','means','scales'))
    intercept=model['intercept']
    threshold=ml_apps.number(data.get('threshold',model['threshold']),'threshold',0,1)
    headers,rows=data_apps.parse(data)
    if any(f not in headers for f in features): raise ValidationError('Prediction CSV must include every model feature')
    predictions=[]
    for index,row in enumerate(rows,2):
        values=[ml_apps.number(row[headers.index(f)],f,-1e9,1e9) for f in features]
        contributions=[w*(v-mean)/scale for w,v,mean,scale in zip(weights,values,means,scales)]
        score=ml_apps.sigmoid(intercept+sum(contributions))
        predictions.append({'record':index,'score':score,'predicted':int(score>=threshold)})
    return {'threshold':threshold,'rows':len(rows),'predictions':predictions,'csv':data_apps.safe_csv(['record','score','predicted'],[[str(p[k]) for k in ('record','score','predicted')] for p in predictions])}


def experiment_plan(data):
    baseline=ml_apps.number(data.get('baseline',.1),'Baseline rate',.0001,.9999)
    lift=ml_apps.number(data.get('absolute_lift',.02),'Absolute lift',.0001,.99)
    if baseline+lift>=1: raise ValidationError('Baseline plus lift must be below 1')
    power=ml_apps.number(data.get('power',.8),'Power',.5,.99)
    alpha=ml_apps.number(data.get('alpha',.05),'Alpha',.001,.2)
    normal=statistics.NormalDist();p2=baseline+lift;pooled=(baseline+p2)/2
    n=math.ceil(((normal.inv_cdf(1-alpha/2)*math.sqrt(2*pooled*(1-pooled))+normal.inv_cdf(power)*math.sqrt(baseline*(1-baseline)+p2*(1-p2)))/lift)**2)
    return {'per_variant':n,'total':n*2,'baseline':baseline,'detectable_rate':p2,'power':power,'alpha':alpha,'note':'Approximate two-sided, equal-allocation two-proportion normal design. Assumes independent observations and a fixed horizon; no repeated peeking, clustering, or multiple-testing adjustment.'}


def stock_plan(db,data):
    lead=integer(data,'lead_days',1,365) if 'lead_days' in data else 7
    safety=integer(data,'safety_days',0,365) if 'safety_days' in data else 7
    rows=db.execute("SELECT p.*, COALESCE(SUM(m.delta),0) stock, COALESCE(SUM(CASE WHEN m.delta<0 AND julianday(m.created_at)>=julianday('now','-30 days') AND julianday(m.created_at)<=julianday('now') THEN -m.delta ELSE 0 END),0) demand FROM products p LEFT JOIN movements m ON m.product_id=p.id GROUP BY p.id ORDER BY p.name").fetchall()
    items=[]
    for row in rows:
        daily=row['demand']/30
        target=max(row['reorder_point']+1,math.ceil(daily*(lead+safety)))
        items.append({'sku':row['sku'],'name':row['name'],'stock':row['stock'],'withdrawals_30d':row['demand'],'daily_demand':round(daily,3),'days_cover':round(row['stock']/daily,1) if daily else None,'target':target,'order_quantity':max(0,target-row['stock'])})
    return {'items':items,'lead_days':lead,'safety_days':safety,'note':'Uses gross withdrawals over the trailing 30 calendar days, including days with no movements. Returns/receipts do not reduce measured demand. Target is max(reorder point + 1, expected lead + safety demand); this is a scenario, not a forecast or purchase order.'}
