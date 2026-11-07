const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function harness(name){
 const elements=new Map(),controls=[];
 const get=selector=>{
  if(!elements.has(selector))elements.set(selector,{value:'',checked:false,disabled:false,handlers:{},
   addEventListener(type,callback){this.handlers[type]=callback;},setAttribute(){}});
  return elements.get(selector);
 };
 let resolve,reject;
 const response=new Promise((yes,no)=>{resolve=yes;reject=no;});
 controls.push(get('#run'),get('#motion-switch'),get('#source'),get('#download'));
 get('#motion-switch').disabled=true;get('#download').disabled=true;
 const context=vm.createContext({document:{querySelector:get,querySelectorAll:selector=>selector.includes('button')&&selector.includes('textarea')?controls:[]},
  window:{designIdentity(){},analysisEmpty(){return '';},addEventListener(){},analysisBusy(){},capabilityInputs:()=>({}),
   analysisRequest:()=>response,renderCapabilities(){}},location:{hash:''}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,`../portfolio/static/${name}.js`),'utf8'),context);
 context.render=()=>{};
 return {get,controls,resolve,reject,run:()=>get('#run').handlers.click()};
}
for(const name of ['data','ml','security','devops']){
 test(`${name} restores preexisting disabled states after successful analysis and failure`,async()=>{
  for(const success of [true,false]){
   const h=harness(name),request=h.run();
   assert.ok(h.controls.every(control=>control.disabled));
   if(success)h.resolve({});else h.reject(new Error('Synthetic validation failure'));
   await request;
   assert.equal(h.get('#motion-switch').disabled,true);
   assert.equal(h.get('#run').disabled,false);
   assert.equal(h.get('#source').disabled,false);
   assert.equal(h.get('#download').disabled,!success);
  }
 });
}
