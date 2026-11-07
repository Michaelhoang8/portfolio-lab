const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../portfolio/static/identities.js'), 'utf8');

function harness(fetch) {
  const events = new Map();
  let timeout, cleared = 0;
  const window = {addEventListener: (name, callback) => events.set(name, callback)};
  const context = {window, document: {addEventListener() {}}, fetch, AbortController, TypeError,
    setTimeout: callback => {timeout = callback; return 1;}, clearTimeout: () => cleared++};
  vm.runInNewContext(source, context);
  return {request: window.analysisRequest, event: name => events.get(name)(),
    timeout: () => timeout(), cleared: () => cleared};
}
function pendingFetch(_url, options) {
  return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () =>
    reject(new DOMException('Aborted', 'AbortError')), {once:true}));
}

test('analysis sends the supplied input once and returns the server report', async () => {
  let calls = 0;
  const h = harness(async (url, options) => {
    calls++;
    assert.equal(url, '/api/data/profile');
    assert.equal(options.headers['X-Portfolio-Client'], 'browser');
    assert.deepEqual(JSON.parse(options.body), {csv:'x\n1'});
    return {ok:true, json:async () => ({rows:1})};
  });
  assert.deepEqual(await h.request('/api/data/profile', {csv:'x\n1'}), {rows:1});
  assert.equal(calls, 1);
  assert.equal(h.cleared(), 1);
});
test('validation errors are shown without retrying the request', async () => {
  let calls=0;
  const h=harness(async () => {calls++;return {ok:false,status:400,json:async()=>({error:'Include a data row'})};});
  await assert.rejects(h.request('/api/data/profile',{}), /Include a data row/);
  assert.equal(calls,1);
  assert.equal(h.cleared(),1);
});
test('malformed responses have an actionable error', async () => {
  const h=harness(async()=>({ok:true,json:async()=>{throw new SyntaxError('Unexpected HTML');}}));
  await assert.rejects(h.request('/api/data/profile',{}), /unreadable response/);
  assert.equal(h.cleared(),1);
});
test('offline failures explain how to recover', async () => {
  const h=harness(async()=>{throw new TypeError('Failed to fetch');});
  await assert.rejects(h.request('/api/data/profile',{}), /Check that it is running/);
});
test('changing mode cancels the active request and clears its timer', async () => {
  const h=harness(pendingFetch);
  const request=h.request('/api/ml/train',{csv:'unchanged'});
  h.event('hashchange');
  await assert.rejects(request,/cancelled.*input is preserved/);
  assert.equal(h.cleared(),1);
});
test('timeout aborts the fetch and distinguishes it from user cancellation', async () => {
  const h=harness(pendingFetch);
  const request=h.request('/api/ml/train',{});
  h.timeout();
  await assert.rejects(request,/timed out after 60 seconds/);
  assert.equal(h.cleared(),1);
});
