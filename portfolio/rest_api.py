"""Versioned Notes API with optimistic concurrency and retry-safe creation."""
import hashlib
import hmac
import json
import re
import sqlite3
import uuid
from http import HTTPStatus
from urllib.parse import parse_qs, urlencode, urlsplit
from .db import connect
from .json_input import decode, read_exact

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_notes (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('draft','published')), version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE INDEX IF NOT EXISTS api_notes_status ON api_notes(status);
CREATE TABLE IF NOT EXISTS api_idempotency (
 scope TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL,
 response TEXT NOT NULL, PRIMARY KEY(scope,key));
"""

class Problem(Exception):
    def __init__(self,status,detail):
        self.status=status;self.detail=detail

def single_header(headers,name,default=None):
    values=headers.get_all(name,[])
    if len(values)>1:
        raise Problem(400,f'Provide at most one {name} header')
    return values[0] if values else default


def etag(note):
    return f'"{note["id"]}:{note["version"]}"'

def if_none_matches(value,current):
    """Weak comparison for bounded RFC 9110 entity-tag lists (commas can be inside tags)."""
    if len(value)>8192:
        raise Problem(400,'If-None-Match must be at most 8192 characters')
    value=value.strip(' \t')
    if value=='*':
        return True
    pattern=r'(?:W/)?"[\x21\x23-\x7e\x80-\xff]*"'
    tags=[]
    while value.strip(' \t,'):
        value=value.lstrip(' \t,')
        match=re.match(pattern,value)
        if match is None or len(tags)>=100:
            raise Problem(400,'If-None-Match must contain at most 100 entity tags or a single wildcard')
        tags.append(match[0])
        value=value[match.end():].lstrip(' \t')
        if value and not value.startswith(','):
            raise Problem(400,'If-None-Match entity tags must be comma-separated')
    return any(tag.removeprefix('W/')==current for tag in tags)


def validate(data,partial=False):
    if not isinstance(data,dict) or not data or set(data)-{'title','content','status'}:
        raise Problem(422,'Provide an object containing only title, content, and status')
    if not partial and not {'title','content','status'}<=set(data):
        raise Problem(422,'title, content, and status are required')
    output={}
    for name,value in data.items():
        if name=='status':
            if value not in ('draft','published'):
                raise Problem(422,'status must be draft or published')
        elif not isinstance(value,str) or not value.strip() or len(value)>({'title':200,'content':10000}[name]):
            raise Problem(422,f'{name} must be nonempty text within its length limit')
        output[name]=value.strip() if name=='title' else value
    return output

def handle(handler,database,api_key):
    request_id=str(uuid.uuid4())
    parsed=urlsplit(handler.path)
    path=parsed.path
    db=None
    def send(status,body=None,headers=None,problem=False):
        raw=b'' if body is None else json.dumps(body).encode('utf-8')
        try:
            handler.send_response(status)
            if status not in (204,304):
                handler.send_header('Content-Type','application/problem+json' if problem else 'application/json')
                handler.send_header('Content-Length',str(len(raw)))
            handler.send_header('Cache-Control','no-store')
            handler.send_header('X-Content-Type-Options','nosniff')
            handler.send_header('X-Request-ID',request_id)
            for key,value in (headers or {}).items():
                handler.send_header(key,value)
            handler.end_headers()
            if handler.command!='HEAD':
                handler.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            handler.close_connection=True

    try:
        if not api_key:
            raise Problem(503,'Set PORTFOLIO_API_KEY in the server environment to enable the Notes API')
        supplied=single_header(handler.headers,'X-API-Key','')
        if not hmac.compare_digest(supplied.encode(),api_key.encode()):
            raise Problem(401,'A valid X-API-Key header is required')
        item=re.fullmatch(r'/api/v1/notes/([0-9a-f-]{36})',path)
        collection=path=='/api/v1/notes'
        if not collection and not item:
            raise Problem(404,'Resource not found')
        allowed='GET, HEAD, POST, OPTIONS' if collection else 'GET, HEAD, PUT, PATCH, DELETE, OPTIONS'
        if handler.command=='OPTIONS':
            send(204,headers={'Allow':allowed});return
        if handler.command not in allowed.split(', '):
            send(405,{'type':'about:blank','title':'Method Not Allowed','status':405,'detail':'Method not supported on this resource','instance':path},headers={'Allow':allowed},problem=True);return
        conditional=handler.headers.get_all('If-None-Match',[])
        if conditional and (not item or handler.command not in ('GET','HEAD')):
            raise Problem(400,'If-None-Match is supported only for individual-note GET and HEAD')
        db=connect(database)
        if handler.command in ('GET','HEAD') and collection:
            query=parse_qs(parsed.query,keep_blank_values=True,max_num_fields=10)
            if set(query)-{'page','page_size','status','q'} or any(len(v)!=1 for v in query.values()):
                raise Problem(400,'Use each supported query parameter at most once')
            def page_number(name,default,maximum):
                raw=query.get(name,[str(default)])[0]
                if not re.fullmatch(r'[0-9]{1,6}',raw) or not 1<=int(raw)<=maximum:
                    raise Problem(400,f'{name} must be between 1 and {maximum}')
                return int(raw)
            page=page_number('page',1,100000);size=page_number('page_size',20,100)
            conditions=[];args=[]
            if 'status' in query:
                if query['status'][0] not in ('draft','published'):
                    raise Problem(400,'Invalid status filter')
                conditions.append('status=?');args.append(query['status'][0])
            if 'q' in query:
                q=query['q'][0]
                if len(q)>200:
                    raise Problem(400,'q must be at most 200 characters')
                conditions.append('(instr(lower(title),lower(?))>0 OR instr(lower(content),lower(?))>0)');args.extend([q,q])
            where=' WHERE '+' AND '.join(conditions) if conditions else ''
            with db:
                db.execute('BEGIN')
                total=db.execute('SELECT COUNT(*) FROM api_notes'+where,args).fetchone()[0]
                notes=[dict(r) for r in db.execute('SELECT * FROM api_notes'+where+' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',(*args,size,(page-1)*size))]
            next_query={k:v[0] for k,v in query.items()};next_query.update(page=page+1,page_size=size)
            send(200,{'items':notes,'page':page,'page_size':size,'total':total,
                      'next':path+'?'+urlencode(next_query) if page*size<total else None});return
        if parsed.query:
            raise Problem(400,'Query parameters are only supported on the collection GET')
        if handler.command in ('GET','HEAD'):
            row=db.execute('SELECT * FROM api_notes WHERE id=?',(item[1],)).fetchone()
            if row is None:
                raise Problem(404,'Note not found')
            note=dict(row)
            if conditional and if_none_matches(','.join(conditional),etag(note)):
                send(304,headers={'ETag':etag(note)});return
            send(200,note,{'ETag':etag(note)});return
        payload=None
        if handler.command in ('POST','PUT','PATCH'):
            single_header(handler.headers,'Content-Type')
            if handler.headers.get_content_type()!='application/json':
                raise Problem(415,'Content-Type must be application/json')
            if handler.headers.get('Transfer-Encoding') or len(handler.headers.get_all('Content-Length', [])) != 1:
                raise Problem(400,'Provide one Content-Length; transfer encoding is not supported')
            raw_length=handler.headers.get('Content-Length','')
            if not re.fullmatch(r'[0-9]{1,8}',raw_length):
                raise Problem(400,'A valid Content-Length is required')
            length=int(raw_length)
            if not 1<=length<=65536:
                raise Problem(413,'JSON body must contain 1–65536 bytes')
            try:
                payload=decode(read_exact(handler.rfile,length,handler.connection,handler.body_timeout))
            except (ValueError,UnicodeError,RecursionError):
                raise Problem(400,'Malformed JSON body') from None
            payload=validate(payload,partial=handler.command=='PATCH')
        with db:
            db.execute('BEGIN IMMEDIATE')
            if handler.command=='POST':
                key=single_header(handler.headers,'Idempotency-Key')
                if key is not None and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',key):
                    raise Problem(400,'Idempotency-Key must be 1–128 ASCII letters, digits, or _ . : -')
                scope=hashlib.sha256(api_key.encode()).hexdigest()
                fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
                old=db.execute('SELECT * FROM api_idempotency WHERE scope=? AND key=?',(scope,key)).fetchone() if key else None
                if old:
                    if old['fingerprint']!=fingerprint:
                        raise Problem(409,'Idempotency-Key was already used with a different payload')
                    note=json.loads(old['response']);replayed=True
                else:
                    note_id=str(uuid.uuid4())
                    db.execute('INSERT INTO api_notes(id,title,content,status) VALUES (?,?,?,?)',(note_id,payload['title'],payload['content'],payload['status']))
                    note=dict(db.execute('SELECT * FROM api_notes WHERE id=?',(note_id,)).fetchone());replayed=False
                    if key:
                        db.execute('INSERT INTO api_idempotency VALUES (?,?,?,?)',(scope,key,fingerprint,json.dumps(note)))
            else:
                row=db.execute('SELECT * FROM api_notes WHERE id=?',(item[1],)).fetchone()
                if row is None:
                    raise Problem(404,'Note not found')
                note=dict(row)
                match=single_header(handler.headers,'If-Match')
                if match is None:
                    raise Problem(428,'If-Match with the current ETag is required')
                if match!=etag(note):
                    raise Problem(412,'ETag is stale or unsupported; fetch the current note before retrying')
                if handler.command=='DELETE':
                    db.execute('DELETE FROM api_notes WHERE id=?',(item[1],))
                else:
                    merged={**note,**payload}
                    db.execute("UPDATE api_notes SET title=?,content=?,status=?,version=version+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(merged['title'],merged['content'],merged['status'],item[1]))
                    note=dict(db.execute('SELECT * FROM api_notes WHERE id=?',(item[1],)).fetchone())
        if handler.command=='POST':
            send(201,note,{'Location':'/api/v1/notes/'+note['id'],'ETag':etag(note),'Idempotency-Replayed':str(replayed).lower()})
        elif handler.command=='DELETE':
            send(204)
        else:
            send(200,note,{'ETag':etag(note)})
    except TimeoutError:
        send(408,{'type':'about:blank','title':'Request Timeout','status':408,'detail':'Request body timed out','instance':path},problem=True)
    except Problem as error:
        send(error.status,{'type':'about:blank','title':HTTPStatus(error.status).phrase,'status':error.status,'detail':error.detail,'instance':path},problem=True)
    except (ValueError,UnicodeError):
        send(400,{'type':'about:blank','title':'Bad Request','status':400,'detail':'Invalid request parameters','instance':path},problem=True)
    except Exception:
        handler.log_error('Notes API internal error; request ID %s',request_id)
        send(500,{'type':'about:blank','title':'Internal Server Error','status':500,'detail':'Unexpected server error','instance':path},problem=True)
    finally:
        if db is not None:
            db.close()
