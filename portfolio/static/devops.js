'use strict';
const $=s=>document.querySelector(s);
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>n===null?'N/A':Number(n.toFixed(4)).toLocaleString(undefined,{maximumFractionDigits:4});
const burn=n=>n===null?'N/A':`${fmt(n)}×`;
let mode='manifest',result=null,busy=false,fileRevision=0,manifestView=null;
const manifestPageSize=25;
const config={manifest:['Deployment manifest','Policy report','Review manifest →','One Linux apps/v1 Deployment in JSON, up to 200 KB. Reviews selected pod and regular-container policies; excludes init/ephemeral containers and full schema validation.'],pipeline:['Pipeline definition','Execution plan','Simulate pipeline →','JSON object with jobs: id, needs, duration (seconds), optional retries and fail_attempts. 1–50 jobs. Commands are never run.'],reliability:['Hourly service metrics','Reliability report','Calculate reliability →','CSV: timestamp,total,bad. Use unique hour-aligned timestamps with timezone. Up to 5,000 completed hourly buckets.']};
const manifestSample={apiVersion:'apps/v1',kind:'Deployment',metadata:{name:'demo-api'},spec:{replicas:1,selector:{matchLabels:{app:'demo-api'}},template:{metadata:{labels:{app:'demo-api'}},spec:{containers:[{name:'api',image:'example.invalid/demo-api:latest',resources:{requests:{cpu:'100m',memory:'128Mi'},limits:{cpu:'500m',memory:'256Mi'}},readinessProbe:{httpGet:{path:'/ready',port:8080}},securityContext:{runAsNonRoot:true,allowPrivilegeEscalation:false}}]}}}};
const pipelineSample={jobs:[{id:'lint',needs:[],duration:20},{id:'unit-tests',needs:[],duration:40},{id:'build',needs:['lint','unit-tests'],duration:35},{id:'integration',needs:['build'],duration:30,retries:1,fail_attempts:1},{id:'security-scan',needs:['build'],duration:25},{id:'deploy-staging',needs:['integration','security-scan'],duration:20}]};
const samples={manifest:JSON.stringify(manifestSample,null,2),pipeline:JSON.stringify(pipelineSample,null,2),reliability:'timestamp,total,bad\n2026-01-15T00:00:00Z,100000,20\n2026-01-15T01:00:00Z,100000,35\n2026-01-15T02:00:00Z,100000,50\n2026-01-15T03:00:00Z,100000,45\n2026-01-15T04:00:00Z,100000,120\n2026-01-15T05:00:00Z,100000,250'};
function message(text,error=false){$('#notice').textContent=text;$('#notice').className=error?'error':'';}
function invalidate(){manifestView=null;result=null;$('#download').disabled=true;$('#result').innerHTML=window.analysisEmpty(mode);}
function switchMode(next){if(busy)return;fileRevision++;mode=config[next]?next:'manifest';window.designIdentity(mode);document.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));$('#pipeline-options').hidden=mode!=='pipeline';$('#reliability-options').hidden=mode!=='reliability';$('#input-title').textContent=config[mode][0];$('#result-title').textContent=config[mode][1];$('#run').textContent=config[mode][2];$('#input-help').textContent=config[mode][3];$('#file-label').textContent=mode==='reliability'?'Choose a metrics CSV':'Choose a JSON file';$('#file').accept=mode==='reliability'?'.csv,text/csv':'.json,application/json';$('#source').value='';invalidate();message('');}
const stats=items=>`<div class="stats">${items.map(([k,v])=>`<div class="stat"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('')}</div>`;
const table=(headers,rows)=>`<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
function timeline(r){
 const height=r.jobs.length*34+35;
 const jobs=r.jobs.map((job,index)=>{
  const label=job.id.length>22?job.id.slice(0,21)+'…':job.id;
  const timing=job.start===null?'skipped':`${job.start}–${job.end} seconds · ${job.attempts} ${job.attempts===1?'attempt':'attempts'}`;
  return `<text class="job-label" x="0" y="${index*34+20}"><title>${esc(job.id)}</title>${esc(label)}</text><rect class="${job.status==='passed'?'job':job.status}" x="${170+(job.start||0)/r.elapsed*400}" y="${index*34+5}" width="${job.start===null?4:Math.max(2,(job.end-job.start)/r.elapsed*400)}" height="20" rx="3"><title>${esc(job.id)} · ${esc(timing)} · ${esc(job.status)}</title></rect><text x="580" y="${index*34+20}">${job.end===null?'skipped':`${job.start}–${job.end}`}</text>`;
 }).join('');
 return `<div class="timeline"><h3>Runner timeline · seconds</h3><svg viewBox="0 0 660 ${height}" role="img" aria-label="Simulated job start and end times; full job IDs are listed in the table below">${jobs}<text x="170" y="${height-5}">0</text><text x="545" y="${height-5}">${r.elapsed}s</text></svg>${r.jobs.some(job=>job.id.length>22)?'<p class="hint">Long job IDs are shortened in the chart. Hover for the full name, or read the table below.</p>':''}</div>`;
}
function manifestFindings(){
 const {items,filter}=manifestView;
 const matches=items.filter(item=>filter==='all'||item.status===filter);
 const last=Math.max(0,Math.ceil(matches.length/manifestPageSize)-1);
 manifestView.page=Math.max(0,Math.min(last,manifestView.page));
 const start=manifestView.page*manifestPageSize,end=Math.min(start+manifestPageSize,matches.length);
 const controls=`<label>Show checks<select id="manifest-filter"><option value="review" ${filter==='review'?'selected':''}>Review needed</option><option value="all" ${filter==='all'?'selected':''}>All checks</option><option value="observed" ${filter==='observed'?'selected':''}>Observed</option></select></label><p role="status">${matches.length?`${start+1}–${end} of ${matches.length}`:'0'} matching checks · ${items.length} checks in full report</p>`;
 const cards=matches.slice(start,end).map(f=>`<article class="finding ${f.status}"><h3>${esc(f.rule)}<small>${f.status}</small></h3><code>${esc(f.path)}</code><p>${esc(f.action)}</p></article>`).join('');
 const empty=filter==='review'?'No selected checks require review. This is not a security certification; inspect All checks and the report scope.':'No checks match this view.';
 const pager=matches.length>manifestPageSize?`<div class="response-pagination" role="group" aria-label="Manifest finding pages"><button type="button" data-manifest-page="-1" ${manifestView.page===0?'disabled':''}>Previous checks</button><button type="button" data-manifest-page="1" ${manifestView.page===last?'disabled':''}>Next checks</button></div>`:'';
 return controls+(cards||`<p>${empty}</p>`)+pager;
}
function updateManifestView(){
 $('#manifest-findings').innerHTML=manifestFindings();
 $('#manifest-filter').focus({preventScroll:true});
 $('#manifest-findings').scrollIntoView({block:'start'});
}
$('#result').addEventListener('change',event=>{
 if(event.target.id!=='manifest-filter'||!manifestView)return;
 const value=event.target.value;if(!['review','all','observed'].includes(value))return;
 manifestView.filter=value;manifestView.page=0;updateManifestView();
});
$('#result').addEventListener('click',event=>{
 const button=event.target.closest('[data-manifest-page]');if(!button||button.disabled||!manifestView)return;
 const step=Number(button.dataset.manifestPage);if(![-1,1].includes(step))return;
 manifestView.page+=step;updateManifestView();
});
function render(r){
 if(mode==='manifest'){
  manifestView={items:r.findings,filter:'review',page:0};
  $('#result').innerHTML=stats([['Containers',r.containers],['Checks',r.findings.length],['Review needed',r.review_count]])+`<p class="summary">${esc(r.note)}</p>`+`<div id="manifest-findings">${manifestFindings()}</div>`;
 }else if(mode==='pipeline'){
  $('#result').innerHTML=stats([['Elapsed',`${r.elapsed}s`],['Workers',r.workers],['Ideal critical path',`${r.ideal_critical_path}s`]])+`<span class="status ${r.status}">${r.status.toUpperCase()}</span><p class="summary">${esc(r.note)}</p><p class="hint">Ideal dependency chain: ${r.ideal_critical_jobs.map(esc).join(' → ')}</p>`+timeline(r)+table(['Job','Dependencies','Attempts','Status'],r.jobs.map(j=>[j.id,j.needs.join(', ')||'none',j.attempts,j.status]));
 }else{
  $('#result').innerHTML=stats([['Request success',r.success_rate===null?'N/A':`${(r.success_rate*100).toFixed(4)}%`],['Budget consumed',r.budget_used===null?'N/A':`${(r.budget_used*100).toFixed(1)}%`],['Latest-hour burn',burn(r.latest_hour_burn)]])+`<p class="summary">${esc(r.note)}</p>`+table(['Total requests','Bad requests','Allowed bad','Remaining budget'],[[fmt(r.total),fmt(r.bad),fmt(r.allowed_bad),fmt(r.remaining_bad)]])+`<h3>Burn-rate context</h3><p>Aggregate burn: <strong>${burn(r.burn_rate)}</strong> · Six-hour burn: <strong>${burn(r.recent_six_hour_burn)}</strong> · Missing hours: <strong>${r.missing_hours}</strong></p><p class="hint">1× means the error ratio matches the SLO allowance. Remaining budget can be negative. Supplied buckets define the reporting period; this is not an assumed monthly budget.</p>`+table(['UTC bucket start','Requests','Bad','Burn rate'],r.buckets.slice(-48).map(b=>[b.timestamp,fmt(b.total),fmt(b.bad),burn(b.burn_rate)]))+'<p class="hint">Latest 48 buckets displayed; full report is downloadable.</p>';
 }
}
document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',()=>{location.hash=b.dataset.mode;}));
window.addEventListener('hashchange',()=>switchMode(location.hash.slice(1)));
$('#sample').addEventListener('click',()=>{fileRevision++;$('#source').value=samples[mode];invalidate();message('Fictional sample loaded.');});
document.querySelectorAll('textarea,input:not([type=file])').forEach(input=>input.addEventListener('input',()=>{fileRevision++;invalidate();message('Input changed. Run the analysis to update the report.');}));
$('#file').addEventListener('change',async()=>{
 const file=$('#file').files?.[0];$('#file').value='';if(!file)return;
 const revision=++fileRevision;
 const limit=mode==='reliability'?1000000:200000,limitLabel=mode==='reliability'?'1 MB':'200 KB';
 try{
  message(`Reading ${file.name}…`);
  const text=await window.localTextFile.read(file,limit,limitLabel);
  if(revision!==fileRevision||busy)return;
  $('#source').value=text;invalidate();message(`Loaded ${file.name}. Review the input, then run the analysis.`);
 }catch(error){if(revision===fileRevision)message(error.message,true);}
});
$('#run').addEventListener('click',async()=>{
 if(busy)return;fileRevision++;busy=true;window.analysisBusy(true);result=null;const controls=[...document.querySelectorAll('input,select,textarea,button')];const disabled=controls.map(c=>c.disabled);controls.forEach(c=>c.disabled=true);message('Analyzing locally…');
 try{const text=$('#source').value;const body=mode==='reliability'?{csv:text,target:Number($('#target').value)}:{text,workers:Number($('#workers').value)};const data=await window.analysisRequest(`/api/devops/${mode}`,{...body,...window.capabilityInputs()});result=data;render(data);window.renderCapabilities(data);message('Complete. No external resources were contacted or changed.');}catch(e){invalidate();message(e.message,true);}finally{busy=false;controls.forEach((c,index)=>c.disabled=disabled[index]);$('#download').disabled=!result;window.analysisBusy(false,!!result);if((config[location.hash.slice(1)]?location.hash.slice(1):'manifest')!==mode)switchMode(location.hash.slice(1));}
});
$('#download').addEventListener('click',()=>{if(!result)return;const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`devops-${mode}-report.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
switchMode(location.hash.slice(1));
