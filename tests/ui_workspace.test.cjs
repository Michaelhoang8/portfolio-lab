const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../portfolio/static/app.js'),'utf8');
function harness(){
  const requests=[],events=[],elements=new Map();
  const element=()=>({value:'',dataset:{},classList:{toggle(){}},
    append(){},addEventListener(){},setAttribute(){},querySelectorAll(){return [];}});
  const document={querySelector(selector){if(!elements.has(selector))elements.set(selector,element());return elements.get(selector);},
    querySelectorAll:()=>[],createElement:element,dispatchEvent:event=>events.push(event.type)};
  const transport={send:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject})),
    recoveryMessage:()=> 'The write may have completed. Check current data before retrying.'};
  const context=vm.createContext({document,window:{restTransport:transport,designIdentity(){},addEventListener(){}},
    location:{hash:'#tickets',search:''},URLSearchParams,Event,Date,console});
  vm.runInContext(source,context);
  let renders=0;
  context.render=()=>renders++;
  return {context,requests,events,refresh:()=>context.refresh(),renders:()=>renders,
    state:()=>JSON.parse(vm.runInContext('JSON.stringify(state)',context))};
}
const snapshot=name=>({tickets:[{id:1,title:name}],events:[],products:[{id:1,name}],movements:[],experiments:[]});
const complete=(request,data)=>request.resolve({response:{ok:true},text:JSON.stringify(data)});

test('older workspace responses cannot overwrite a newer completed refresh',async()=>{
  const h=harness(); // Initial page load is pending.
  const newer=h.refresh();
  complete(h.requests[1],snapshot('newer'));await newer;
  complete(h.requests[0],snapshot('older'));await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.state().tickets[0].title,'newer');
  assert.equal(h.renders(),1);
  assert.deepEqual(h.events,['stock-updated']);
});

test('failed newer refresh preserves the last applied state and ignores older pending data',async()=>{
  const h=harness();complete(h.requests[0],snapshot('original'));
  await new Promise(resolve=>setImmediate(resolve));
  const older=h.refresh(),newer=h.refresh();
  h.requests[2].reject(new Error('Offline'));
  await assert.rejects(newer,/Offline/);
  complete(h.requests[1],snapshot('stale'));await older;
  assert.equal(h.state().tickets[0].title,'original');
  assert.equal(h.renders(),1);
});

test('superseded request failures do not report errors over newer valid data',async()=>{
  const h=harness();complete(h.requests[0],snapshot('original'));
  await new Promise(resolve=>setImmediate(resolve));
  const older=h.refresh(),newer=h.refresh();
  complete(h.requests[2],snapshot('newer'));await newer;
  h.requests[1].reject(new Error('Old request failed'));
  await older;
  assert.equal(h.state().tickets[0].title,'newer');
  const stale=h.refresh(),latest=h.refresh();
  complete(h.requests[4],snapshot('latest'));await latest;
  complete(h.requests[3],null);await stale;
  assert.equal(h.state().tickets[0].title,'latest');
});

test('invalid workspace response shapes leave the previous state intact',async()=>{
  const h=harness();complete(h.requests[0],snapshot('original'));
  await new Promise(resolve=>setImmediate(resolve));
  for(const data of [null,[],{}, {...snapshot('invalid'),products:null}]){
    const refresh=h.refresh();complete(h.requests.at(-1),data);
    await assert.rejects(refresh,/unreadable response/);
  }
  assert.equal(h.state().tickets[0].title,'original');
  assert.equal(h.renders(),1);
});

test('workspace write parsing rejects unusable responses without hiding uncertain completion',async()=>{
  const h=harness();complete(h.requests[0],snapshot('original'));
  await new Promise(resolve=>setImmediate(resolve));
  for(const text of ['null','[]','broken']){
    const posted=h.context.post('/api/tickets',{title:'Example'});
    h.requests.at(-1).resolve({response:{ok:true},text});
    await assert.rejects(posted,/write may have completed/);
  }
  const posted=h.context.post('/api/tickets/1/status',{status:'done',expected_version:1});
  h.requests.at(-1).resolve({response:{ok:false,status:409},text:'{"error":"Stale version"}'});
  await assert.rejects(posted,error=>error.status===409&&error.message==='Stale version');
});

test('inventory filters combine SKU search with exact stock boundaries and stable ordering',()=>{
  const h=harness();
  const products=[{name:'Keyboard',sku:'KEY-01',stock:5,reorder_point:5},
    {name:'Dock',sku:'DOCK-01',stock:0,reorder_point:10},
    {name:'Monitor',sku:'MON-01',stock:8,reorder_point:2},
    {name:'Dock',sku:'DOCK-02',stock:2,reorder_point:5}];
  const names=(query,status,order)=>Array.from(h.context.visibleProducts(products,query,status,order),p=>p.sku);
  assert.deepEqual(names(' dock ','reorder','name'),['DOCK-01','DOCK-02']);
  assert.deepEqual(names('','empty','name'),['DOCK-01']);
  assert.deepEqual(names('','healthy','name'),['MON-01']);
  assert.deepEqual(names('KEY-01','reorder','name'),['KEY-01']);
  assert.deepEqual(names('','all','stock'),['DOCK-01','DOCK-02','KEY-01','MON-01']);
  assert.deepEqual(names('','all','shortfall'),['DOCK-01','DOCK-02','KEY-01','MON-01']);
  assert.equal(products[0].sku,'KEY-01'); // Sorting must not mutate the loaded workspace.
});
