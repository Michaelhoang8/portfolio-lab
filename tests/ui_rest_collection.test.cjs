const test=require('node:test');
const assert=require('node:assert/strict');
const {parse}=require('../portfolio/static/rest_collection.js');
const id='12345678-1234-1234-1234-123456789abc';
const collection=requests=>JSON.stringify({format:'portfolio-lab-request-collection-v1',requests});
test('request collections reconstruct list filters and every supported operation',()=>{
 const entries=[{method:'GET',path:'/api/v1/notes?page=3&page_size=25&status=published&q=hello%20%26%20world'},
 {method:'POST',path:'/api/v1/notes',headers:{'Content-Type':'application/json','Idempotency-Key':'same-operation'},body:'{"title":"Draft"}'},
 ...['GET','HEAD','PUT','PATCH','DELETE'].map(method=>({method,path:`/api/v1/notes/${id}`,headers:{[method==='GET'||method==='HEAD'?'If-None-Match':'If-Match']:'"v2"'},body:['PUT','PATCH'].includes(method)?'{ deliberately invalid JSON':null}))];
 const result=parse(collection(entries));
 assert.deepEqual(result.map(entry=>entry.form.operation),['list','create','get','head','replace','update','delete']);
 assert.equal(result[0].form.query,'hello & world');assert.equal(result[0].form.page,'3');assert.equal(result[0].form['page-size'],'25');
 assert.equal(result[0].form['status-filter'],'published');
 assert.equal(result[1].form.idem,'same-operation');assert.equal(result[1].form.body,entries[1].body);
 assert.equal(result[2].form['read-etag'],'"v2"');assert.equal(result[4].form.etag,'"v2"');
 assert.equal(result[4].form.body,'{ deliberately invalid JSON');
 assert.equal(result[6].form['note-id'],id);
 assert.ok(result.every(entry=>!('key' in entry.form)));
});
test('collection import rejects external paths, credentials, incompatible methods, and malformed filters',()=>{
 const invalid=[
 {method:'GET',path:'https://example.invalid/api/v1/notes'},
 {method:'GET',path:'//example.invalid/api/v1/notes'},
 {method:'GET',path:'/api/v1/notes/../notes'},
 {method:'GET',path:'/api/v1/notes#fragment'},
 {method:'GET',path:'/api/v1/notes?redirect=https://example.invalid'},
 {method:'GET',path:'/api/v1/notes?page=1&page=2'},
 {method:'GET',path:'/api/v1/notes?page_size=101'},
 {method:'GET',path:'/api/v1/notes?page=0'},
 {method:'GET',path:'/api/v1/notes?status=wrong'},
 {method:'GET',path:'/api/v1/notes?q='+'x'.repeat(201)},
 {method:'POST',path:`/api/v1/notes/${id}`},
 {method:'HEAD',path:'/api/v1/notes'},
 {method:'__proto__',path:'/api/v1/notes'},
 {method:'GET',path:`/api/v1/notes/${id}?page=1`},
 {method:'GET',path:'/api/v1/notes',headers:{'X-API-Key':'should-not-load'}},
 {method:'GET',path:`/api/v1/notes/${id}`,headers:{'If-None-Match':'x\r\nInjected: value'}},
 {method:'GET',path:`/api/v1/notes/${id}`,headers:{'If-None-Match':'x','if-none-match':'y'}},
 {method:'GET',path:'/api/v1/notes',body:'not supported'},
 {method:'POST',path:'/api/v1/notes',body:{}},
 {method:'GET',path:'/api/v1/notes',headers:[]},null];
 for(const entry of invalid)assert.throws(()=>parse(collection([entry])),/Request 1:/);
});
test('collection import is atomic, bounded, and does not trust historical response metadata',()=>{
 const valid={method:'GET',path:'/api/v1/notes',status:201,elapsed_ms:1};
 assert.throws(()=>parse(collection([valid,{method:'DELETE',path:'/api/v1/notes'}])),/Request 2:/);
 for(const content of ['{','null',collection([]),collection(Array(11).fill(valid)),JSON.stringify({format:'unknown',requests:[valid]})])assert.throws(()=>parse(content));
 const entries=parse(collection([valid]));
 assert.deepEqual(Object.keys(entries[0]).sort(),['form','method','path']);
 assert.equal(entries[0].form.page,'1');assert.equal(entries[0].form['page-size'],'10');
});
