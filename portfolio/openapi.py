"""Generate the checked-in Notes API contract: python -m portfolio.openapi."""
import json
from pathlib import Path

def build_spec():
    fields={'title':{'type':'string','minLength':1,'maxLength':200},
            'content':{'type':'string','minLength':1,'maxLength':10000},
            'status':{'type':'string','enum':['draft','published']}}
    note_fields={**fields,'id':{'type':'string','format':'uuid'},'version':{'type':'integer','minimum':1},
                 'created_at':{'type':'string','format':'date-time'},'updated_at':{'type':'string','format':'date-time'}}
    schemas={'NoteInput':{'type':'object','additionalProperties':False,'required':list(fields),'properties':fields},
             'NotePatch':{'type':'object','additionalProperties':False,'minProperties':1,'properties':fields},
             'Note':{'type':'object','required':list(note_fields),'properties':note_fields},
             'Problem':{'type':'object','required':['type','title','status','detail','instance'],
                        'properties':{k:{'type':'integer' if k=='status' else 'string'} for k in ['type','title','status','detail','instance']}},
             'NotePage':{'type':'object','required':['items','page','page_size','total','next'],
                         'properties':{'items':{'type':'array','items':{'$ref':'#/components/schemas/Note'}},
                                       'page':{'type':'integer'},'page_size':{'type':'integer'},'total':{'type':'integer'},'next':{'type':['string','null']}}}}
    def response(code,schema=None):
        result={'description':str(code),'headers':{'X-Request-ID':{'schema':{'type':'string','format':'uuid'}}}}
        if schema:
            result['content']={'application/json':{'schema':{'$ref':'#/components/schemas/'+schema}}}
        return result
    problem={'description':'Problem details: 400 malformed request, 401 invalid key, 404 missing resource, 405 unsupported method, 409 idempotency conflict, 412 stale ETag, 413 large body, 415 unsupported media type, 422 invalid fields, 428 missing If-Match, 500 internal error, or 503 API key not configured.',
             'content':{'application/problem+json':{'schema':{'$ref':'#/components/schemas/Problem'}}}}
    def operation(summary,code,schema=None,input_schema=None):
        result={'summary':summary,'responses':{str(code):response(code,schema),'default':problem}}
        if input_schema:
            result['requestBody']={'required':True,'content':{'application/json':{'schema':{'$ref':'#/components/schemas/'+input_schema}}}}
        if schema=='Note':
            result['responses'][str(code)]['headers']['ETag']={'description':'Strong entity tag for this note version','schema':{'type':'string'}}
        return result
    listing=operation('List notes with stable ordering and offset pagination',200,'NotePage')
    listing['parameters']=[{'name':name,'in':'query','schema':schema} for name,schema in [
        ('page',{'type':'integer','minimum':1,'maximum':100000,'default':1}),
        ('page_size',{'type':'integer','minimum':1,'maximum':100,'default':20}),
        ('status',fields['status']),('q',{'type':'string','maxLength':200})]]
    create=operation('Create a note; optionally replay safely with an idempotency key',201,'Note','NoteInput')
    create['parameters']=[{'name':'Idempotency-Key','in':'header','schema':{'type':'string','pattern':'^[A-Za-z0-9_.:-]{1,128}$'}}]
    create['responses']['201']['headers'].update({'Location':{'schema':{'type':'string'}},'Idempotency-Replayed':{'schema':{'type':'string','enum':['true','false']}}})
    item={'parameters':[{'name':'id','in':'path','required':True,'schema':{'type':'string','format':'uuid'}}],
          'get':operation('Get a note and its current ETag',200,'Note')}
    for method,schema,code in [('put','NoteInput',200),('patch','NotePatch',200),('delete',None,204)]:
        item[method]=operation({'put':'Replace a note','patch':'Partially update a note','delete':'Delete a note'}[method],code,'Note' if code==200 else None,schema)
        item[method]['parameters']=[{'name':'If-Match','in':'header','required':True,'description':'Exact current ETag. Wildcards, weak tags, and lists are not supported.','schema':{'type':'string'}}]
    options=operation('Discover allowed methods',204)
    options['responses']['204']['headers']['Allow']={'schema':{'type':'string'}}
    item['options']=options
    return {'openapi':'3.1.1','info':{'title':'Portfolio Notes API','version':'1.0.0',
            'description':'Local single-workspace demo. Only these /api/v1 routes require the configured key. Request bodies are limited to 64 KiB. See REST_API.md for concurrency and replay semantics.'},
            'servers':[{'url':'/'}],'security':[{'ApiKey':[]}],
            'components':{'securitySchemes':{'ApiKey':{'type':'apiKey','in':'header','name':'X-API-Key'}},'schemas':schemas},
            'paths':{'/api/v1/notes':{'get':listing,'post':create,'options':options},'/api/v1/notes/{id}':item}}

if __name__=='__main__':
    path=Path(__file__).parent/'static'/'openapi.json'
    path.write_text(json.dumps(build_spec(),indent=2)+'\n',encoding='utf-8')
    print(f'Wrote {path}')
