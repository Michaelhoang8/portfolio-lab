const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../portfolio/static/capabilities.js'), 'utf8');

function harness(fetch) {
  const events = new Map(), timers = new Map();
  let next = 0;
  const window = {addEventListener: (name, callback) => events.set(name, callback)};
  vm.runInNewContext(source, {window, document:{addEventListener(){}}, fetch, AbortController, TypeError,
    setTimeout: callback => {timers.set(++next, callback);return next;},
    clearTimeout: id => timers.delete(id)});
  return {request:window.utilityRequest, event:name=>events.get(name)(), timers};
}
function pending(_url, options) {
  return new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>
    reject(new DOMException('Aborted','AbortError')),{once:true}));
}

test('utility requests preserve input, return reports, and clear their timeout',async()=>{
  let calls=0;
  const h=harness(async(url,options)=>{
    calls++;
    assert.equal(url,'/api/extensions/stock-plan');
    assert.equal(options.headers['X-Portfolio-Client'],'browser');
    assert.deepEqual(JSON.parse(options.body),{lead_days:7});
    return {ok:true,json:async()=>({items:[]})};
  });
  assert.deepEqual(await h.request('/api/extensions/stock-plan',{lead_days:7}),{items:[]});
  assert.equal(calls,1);
  assert.equal(h.timers.size,0);
});

test('utility timeout aborts without retrying and cleans up',async()=>{
  let calls=0;
  const h=harness((...args)=>{calls++;return pending(...args);});
  const result=h.request('/api/extensions/predict',{});
  h.timers.get(1)();
  await assert.rejects(result,/timed out after 30 seconds/);
  assert.equal(calls,1);
  assert.equal(h.timers.size,0);
});

test('navigation cancels every concurrent utility request',async()=>{
  for(const event of ['hashchange','pagehide']) {
    const h=harness(pending);
    const requests=[h.request('/api/extensions/model',{}),h.request('/api/extensions/predict',{})];
    h.event(event);
    for(const request of requests)await assert.rejects(request,/cancelled.*inputs are preserved/);
    assert.equal(h.timers.size,0);
  }
});

test('utility failures distinguish validation, offline, and unreadable reports',async()=>{
  const cases=[
    [async()=>({ok:false,status:400,json:async()=>({error:'Missing feature'})}),/Missing feature/],
    [async()=>{throw new TypeError('offline');},/Could not reach/],
    [async()=>({ok:true,json:async()=>{throw new SyntaxError();}}),/unreadable response/],
    ...[null,[],42].map(value=>[async()=>({ok:true,json:async()=>value}),/unreadable response/])
  ];
  for(const [fetch,expected] of cases){
    const h=harness(fetch);
    await assert.rejects(h.request('/api/extensions/predict',{}),expected);
    assert.equal(h.timers.size,0);
  }
});
