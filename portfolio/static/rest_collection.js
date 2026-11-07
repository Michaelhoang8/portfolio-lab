/* Parse local request collections into form values; never execute imported requests. */
((root)=>{
 const fields=['operation','note-id','page','page-size','status-filter','query','etag','read-etag','idem','body'];
 const record=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
 function parse(text){
  let collection;try{collection=JSON.parse(text);}catch{throw Error('The collection must be valid JSON.');}
  if(!record(collection)||collection.format!=='portfolio-lab-request-collection-v1'||!Array.isArray(collection.requests)||!collection.requests.length||collection.requests.length>10)
   throw Error('Choose a Portfolio Lab v1 collection containing 1–10 requests.');
  return collection.requests.map((entry,index)=>{
   const fail=message=>{throw Error(`Request ${index+1}: ${message}`);};
   if(!record(entry)||typeof entry.path!=='string'||entry.path.length>10000)fail('invalid request path.');
   const match=entry.path.match(/^\/api\/v1\/notes(?:\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}))?(\?[^#]*)?$/);
   if(!match)fail('only local /api/v1/notes paths are supported.');
   const id=match[1]||'',method=entry.method;
   if(!['GET','HEAD','POST','PUT','PATCH','DELETE'].includes(method))fail('unsupported request method.');
   const operation=(id?{GET:'get',HEAD:'head',PUT:'replace',PATCH:'update',DELETE:'delete'}:{GET:'list',POST:'create'})[method];
   if(!operation)fail('unsupported method for this path.');
   if(match[2]&&operation!=='list')fail('query parameters are supported only for listing notes.');
   const form=Object.fromEntries(fields.map(field=>[field,'']));
   Object.assign(form,{operation,'note-id':id,page:'1','page-size':'10'});
   const params=new URLSearchParams(match[2]||'');
   for(const key of params.keys())if(!['page','page_size','status','q'].includes(key)||params.getAll(key).length!==1)fail('unsupported or repeated query parameter.');
   for(const [key,field,max] of [['page','page',100000],['page_size','page-size',100]]){
    if(params.has(key)){const value=params.get(key);if(!/^[1-9][0-9]*$/.test(value)||Number(value)>max)fail(`invalid ${key}.`);form[field]=value;}
   }
   if(params.has('status')){const value=params.get('status');if(!['draft','published'].includes(value))fail('invalid status filter.');form['status-filter']=value;}
   if(params.has('q')){if(params.get('q').length>200)fail('search exceeds 200 characters.');form.query=params.get('q');}
   if(entry.headers!==undefined&&!record(entry.headers))fail('headers must be an object.');
   const seen=new Set();
   for(const [key,value] of Object.entries(entry.headers||{})){
    const name=key.toLowerCase();
    if(seen.has(name))fail('repeated header.');seen.add(name);
    if(typeof value!=='string'||value.length>8192||/[\r\n\0]/.test(value))fail('invalid header value.');
    if(name==='content-type'&&['create','replace','update'].includes(operation)&&value.toLowerCase()==='application/json')continue;
    const target=name==='if-match'&&['replace','update','delete'].includes(operation)?'etag':
     name==='if-none-match'&&['get','head'].includes(operation)?'read-etag':
     name==='idempotency-key'&&operation==='create'?'idem':null;
    if(!target)fail('unsupported header; supply authentication separately.');
    form[target]=value;
   }
   if(entry.body!==null&&entry.body!==undefined&&typeof entry.body!=='string')fail('body must be text or null.');
   if(entry.body&& !['create','replace','update'].includes(operation))fail('this operation cannot contain a body.');
   form.body=entry.body||'';
   return {method,path:entry.path,form};
  });
 }
 if(typeof module!=='undefined'&&module.exports)module.exports={parse};
 else root.requestCollection={parse};
})(typeof window==='undefined'?globalThis:window);
