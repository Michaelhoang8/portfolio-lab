"""Offline defensive analysis. No network requests or persistent input storage."""
import ipaddress
from bisect import bisect_right
from .json_input import decode
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from .validation import ValidationError, integer

def source(data):
    value = data.get('text')
    if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > 500_000:
        raise ValidationError('Provide nonempty text of at most 500 KB')
    if len(value.splitlines()) > 5000:
        raise ValidationError('Limit input to 5,000 lines')
    return value

def auth_logs(data):
    text = source(data)
    threshold = integer(data, 'threshold', 2, 100) if 'threshold' in data else 5
    window = integer(data, 'window_minutes', 1, 60) if 'window_minutes' in data else 10
    events, rejected = [], []
    for line, raw in enumerate(text.splitlines(),1):
        if not raw.strip():
            continue
        try:
            item = decode(raw)
            if not isinstance(item, dict):
                raise ValueError()
            stamp = item.get('timestamp')
            if not isinstance(stamp, str):
                raise ValueError()
            time = datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if time.utcoffset() is None:
                raise ValueError()
            time = time.astimezone(timezone.utc)
            raw_ip = item.get('ip')
            if not isinstance(raw_ip,str):
                raise ValueError()
            ip = str(ipaddress.ip_address(raw_ip))
            user = item.get('user')
            if not isinstance(user,str) or not user.strip() or len(user) > 120:
                raise ValueError()
            status = item.get('status')
            if status not in ('failure','success'):
                raise ValueError()
            events.append(dict(time=time,ip=ip,user=user.strip(),status=status,line=line))
        except (ValueError, TypeError, OverflowError):
            rejected.append({'line':line, 'reason':'Expected timestamp with timezone, valid IP, nonempty user, and success/failure status'})
    events.sort(key=lambda e:(e['time'],e['line']))
    ip_windows, user_windows = defaultdict(deque), defaultdict(deque)
    ip_users = defaultdict(Counter)
    alerts, active = [], set()
    failures = Counter()
    for event in events:
        ip, user, now = event['ip'],event['user'],event['time']
        recent = ip_windows[ip]
        account = user_windows[(ip,user)]
        source_users = ip_users[ip]
        while recent and (now-recent[0]['time']).total_seconds() > window*60:
            expired = recent.popleft()['user']
            source_users[expired] -= 1
            if not source_users[expired]:
                del source_users[expired]
        while account and (now-account[0]['time']).total_seconds() > window*60:
            account.popleft()
        if len(recent) < threshold:
            active.discard(('burst',ip))
        if len(source_users) < threshold:
            active.discard(('spray',ip))
        def alert(rule, severity, count, detail):
            alerts.append({'rule':rule,'severity':severity,'ip':ip,'user':user,
                'timestamp':now.isoformat(), 'line':event['line'],'count':count,'detail':detail})
        if event['status'] == 'failure':
            failures[ip] += 1
            recent.append(event)
            source_users[user] += 1
            account.append(event)
            if len(recent) >= threshold and ('burst',ip) not in active:
                alert('Failure burst','medium',len(recent),'Repeated failures from one source within the rolling window')
                active.add(('burst',ip))
            users = len(source_users)
            if users >= threshold and ('spray',ip) not in active:
                alert('Multiple accounts targeted','high',users,'Failures against distinct accounts from one source; investigate possible spraying')
                active.add(('spray',ip))
        else:
            if len(account) >= threshold:
                alert('Success after failures','high',len(account),'Same account and source succeeded after repeated failures; verify with the account owner')
            account.clear()
    return {'accepted':len(events),'rejected':rejected,'failures':sum(failures.values()),
            'sources':len({e['ip'] for e in events}),'alerts':alerts,
            'top_sources':[{'ip':ip,'failures':count} for ip,count in failures.most_common(10)],
            'threshold':threshold,'window_minutes':window}

def inspect_headers(data):
    text = source(data)
    headers = defaultdict(list)
    malformed = []
    for line, raw in enumerate(text.splitlines(),1):
        if not raw.strip() or raw.startswith('HTTP/'):
            continue
        name, separator, value = raw.partition(':')
        if not separator or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+",name):
            malformed.append(line)
            continue
        headers[name.lower()].append(value.strip())
    findings = []
    def add(control, status, detail, action):
        findings.append(dict(control=control,status=status,detail=detail,action=action))
    # Duplicate policy headers need browser-specific interpretation; never silently choose one.
    duplicates = sorted(name for name, values in headers.items() if len(values)>1 and name!='set-cookie')
    def one(name):
        return headers[name][0] if len(headers[name]) == 1 else ''
    csp = one('content-security-policy')
    directives = {}
    duplicate_directive = False
    for part in csp.split(';'):
        tokens = part.split()
        if tokens:
            key = tokens[0].lower()
            duplicate_directive |= key in directives
            directives.setdefault(key,tokens[1:])
    script = directives.get('script-src',directives.get('default-src'))
    script_policies = [script, directives.get('script-src-elem',script), directives.get('script-src-attr',script)]
    csp_ok = bool(csp) and not duplicate_directive and all(policy is not None and not any(
        token in ("'unsafe-inline'","'unsafe-eval'",'*','data:','http:','https:') for token in policy)
        for policy in script_policies)
    add('Content Security Policy','observed' if csp_ok else 'review',
        'Restrictive script-source syntax observed' if csp_ok else 'Missing, ambiguous, or broad script policy',
        'Review a nonce/hash-based CSP against application requirements; this is a heuristic, not browser policy validation.')
    frame = directives.get('frame-ancestors',[])
    frame_ok = frame in (["'none'"],["'self'"])
    xfo_ok = one('x-frame-options').upper() in ('DENY','SAMEORIGIN')
    add('Framing policy','observed' if frame_ok or (not frame and xfo_ok) else 'review',
        'Restrictive framing header observed' if frame_ok or (not frame and xfo_ok) else 'No unambiguous self-only or deny framing policy found',
        'Use CSP frame-ancestors with the embedding origins your application requires.')
    hsts = one('strict-transport-security')
    ages = re.findall(r'(?:^|;)\s*max-age\s*=\s*([0-9]+)\s*(?=;|$)',hsts,re.I)
    # Decimal-string comparison avoids Python's integer conversion digit limit.
    age=(ages[0].lstrip('0') or '0') if len(ages)==1 else ''
    strong_hsts = len(ages)==1 and (len(age)>8 or len(age)==8 and age>='31536000')
    add('HTTPS persistence','observed' if strong_hsts else 'review',
        'HSTS max-age of at least one year observed' if strong_hsts else 'Missing, ambiguous, or short HSTS lifetime',
        'Only use HSTS on HTTPS. Validate HTTPS support before choosing a long lifetime or includeSubDomains.')
    add('MIME sniffing','observed' if one('x-content-type-options').lower()=='nosniff' else 'review',
        'nosniff observed' if one('x-content-type-options').lower()=='nosniff' else 'nosniff not observed',
        'Serve correct Content-Type values and add X-Content-Type-Options: nosniff.')
    referrer = one('referrer-policy').lower()
    referrer_ok = referrer in ('no-referrer','same-origin','strict-origin','strict-origin-when-cross-origin')
    add('Referrer policy','observed' if referrer_ok else 'review',
        'Restrictive referrer policy observed' if referrer_ok else 'Review absent, complex, or permissive policy',
        'Choose a Referrer-Policy appropriate for the data in page URLs.')
    for index, cookie in enumerate(headers.get('set-cookie',[]),1):
        parts=[part.strip() for part in cookie.split(';')[1:] if part.strip()]
        names=[part.split('=',1)[0].lower() for part in parts]
        attrs = {part.split('=',1)[0].lower():part.partition('=')[2].lower() for part in parts}
        missing = [key for key in ('secure','httponly') if key not in attrs]
        if attrs.get('samesite') not in ('lax','strict','none'):
            missing.append('valid SameSite')
        if len(names)!=len(set(names)):
            missing.append('duplicate attributes')
        cookie_name=cookie.partition('=')[0].strip()
        if cookie_name.startswith('__Host-') and ('domain' in attrs or attrs.get('path')!='/'):
            missing.append('host-prefix requires Path=/ and no Domain')
        add(f'Cookie #{index}','review' if missing else 'observed',
            'Review: '+', '.join(missing) if missing else 'Secure, HttpOnly, and SameSite attributes observed',
            'Assess each cookie by purpose; session cookies generally need Secure and HttpOnly. SameSite=None requires Secure.')
    return {'findings':findings,'review_count':sum(f['status']=='review' for f in findings),
            'observed_count':sum(f['status']=='observed' for f in findings),
            'duplicate_headers':duplicates,'malformed_lines':malformed,
            'note':'Offline heuristic review only. Does not verify TLS, header delivery, CSP validity, or exploitability. Header and cookie values are omitted from reports.'}

SECRET_RULES = [
    ('Private key block', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----|\Z)'), 'high'),
    ('Fine-grained GitHub-style token', re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,255}\b'), 'high'),
    ('GitHub-style token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,255}\b'), 'high'),
    ('AWS-style access key ID', re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'), 'medium'),
    ('Secret assignment', re.compile(r'''(?im)\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token|refresh[_-]?token|secret[_-]?key|aws[_-]?secret[_-]?access[_-]?key|aws[_-]?session[_-]?token)\b["']?\s*[:=]\s*["']?([^\s"'`,;#]{8,256})'''), 'medium'),
    ('Bearer credential', re.compile(r'(?i)\bBearer\s+([A-Za-z0-9._~+/-]{12,512}=*)'), 'high'),
]

def scan_secrets(data):
    text = source(data)
    spans = []
    for name, pattern, severity in SECRET_RULES:
        for match in pattern.finditer(text):
            start,end = match.span(1) if match.lastindex else match.span()
            spans.append((start,end,name,severity))
    spans.sort(key=lambda s:(s[0],-(s[1]-s[0])))
    merged = []
    for start,end,name,severity in spans:
        if merged and start < merged[-1][1]:
            old = merged[-1]
            merged[-1] = (old[0],max(end,old[1]),old[2], 'high' if 'high' in (old[3],severity) else 'medium')
        else:
            merged.append((start,end,name,severity))
    line_starts=[0];offset=0
    for line in text.splitlines(keepends=True):
        offset+=len(line)
        if offset<len(text):line_starts.append(offset)
    findings = [{'rule':name,'severity':severity,'line':bisect_right(line_starts,start),
                 'action':'Verify locally. If real and exposed, revoke/rotate it and remove it from source and history.'}
                for start,end,name,severity in merged]
    return {'findings':findings,'count':len(findings),'lines_scanned':len(text.splitlines()),
            'note':'Pattern-based review; false positives and missed secrets are possible. No raw values, snippets, hashes, or original text are returned. Results do not establish whether credentials are live.'}
