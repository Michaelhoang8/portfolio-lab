const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
function harness(){
  const elements=new Map();
  const get=selector=>{
    if(!elements.has(selector))elements.set(selector,{value:'',handlers:{},addEventListener(type,fn){this.handlers[type]=fn;},focus(){},scrollIntoView(){}});
    return elements.get(selector);
  };
  const context=vm.createContext({document:{querySelector:get,querySelectorAll:()=>[]},
    window:{designIdentity(){},analysisEmpty(){return '';},addEventListener(){}},location:{hash:''}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../portfolio/static/devops.js'),'utf8'),context);
  return {context,get,state:()=>JSON.parse(vm.runInContext('JSON.stringify(manifestView)',context)),
    view:(items,filter='review',page=0)=>{vm.runInContext(`manifestView=${JSON.stringify({items,filter,page})}`,context);return context.manifestFindings();}};
}
const findings=Array.from({length:60},(_,i)=>({rule:`Rule ${i+1}`,path:`container[${i}]`,action:'Inspect <untrusted> & input',status:i<30?'review':'observed'}));
test('manifest pages bound cards and retain full report data',()=>{
  const h=harness();let html=h.view(findings);
  assert.equal((html.match(/<article /g)||[]).length,25);
  assert.match(html,/1–25 of 30/);assert.match(html,/60 checks in full report/);
  assert.match(html,/Inspect &lt;untrusted&gt; &amp; input/);
  assert.equal(h.state().items.length,60);
  html=h.view(findings,'review',1);
  assert.equal((html.match(/<article /g)||[]).length,5);
  assert.match(html,/26–30 of 30/);assert.match(html,/data-manifest-page="1" disabled/);
  html=h.view(findings,'all',2);assert.match(html,/51–60 of 60/);
  html=h.view(findings,'observed',99);assert.equal(h.state().page,1);assert.match(html,/26–30 of 30/);
});
test('manifest filters reset pages, navigation is bounded, and invalidation clears view',()=>{
  const h=harness();h.view(findings,'all',2);
  h.get('#result').handlers.change({target:{id:'manifest-filter',value:'review'}});
  assert.equal(h.state().page,0);assert.equal(h.state().filter,'review');
  const click=step=>h.get('#result').handlers.click({target:{closest:()=>({dataset:{manifestPage:String(step)}})}});
  click(1);assert.equal(h.state().page,1);
  click(1);assert.equal(h.state().page,1);
  click(500);assert.equal(h.state().page,1);
  click(-1);assert.equal(h.state().page,0);
  h.context.invalidate();assert.equal(h.state(),null);
});
test('manifest zero-review view explains scope and keeps observed checks accessible',()=>{
  const h=harness();const items=findings.filter(item=>item.status==='observed');
  const html=h.view(items);
  assert.match(html,/No selected checks require review/);assert.match(html,/not a security certification/);
  assert.match(html,/All checks/);assert.ok(!html.includes('<article '));
  assert.equal(h.state().items.length,30);
});
