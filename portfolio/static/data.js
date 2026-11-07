'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sample = 'date,category,amount,customer\n2026-01-03,Software,149.00,Acme\n2026-01-14,Services,320.00,Beacon\n2026-02-02,Software,199.00,Acme\n2026-02-12,Services,450.00,Cedar\n2026-03-01,Software,249.00,Delta\n2026-03-10,Services,600.00,Elm\n2026-03-12,Software,-49.00,Acme\n2026-03-15, Software ,99.00, Fir \n2026-03-15,Software,99.00,Fir\ninvalid,Services,120.00,Example\n2026-03-19,Software,,\n,,,\n';
let mode = 'profile', result = null, busy = false, fileRevision = 0;
const config = {profile:['Dataset overview','Profile dataset →'],clean:['Pipeline results','Run cleaning pipeline →'],sales:['Revenue overview','Analyze sales →']};
function message(text,error=false){$('#notice').textContent=text;$('#notice').className=error?'error':'';}
function invalidate(){result=null;$('#download').disabled=true;$('#result').innerHTML=window.analysisEmpty(mode);}
function switchMode(next){if(busy)return;fileRevision++;mode=config[next]?next:'profile';window.designIdentity(mode);document.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));$('#clean-options').hidden=mode!=='clean';$('#sales-options').hidden=mode!=='sales';$('#result-title').textContent=config[mode][0];$('#run').textContent=config[mode][1];invalidate();message('');}
const table=(headers,rows)=>`<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${esc(v ?? '—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
const stats=items=>`<div class="stats">${items.map(([label,value])=>`<div class="stat"><small>${esc(label)}</small><strong>${esc(value)}</strong></div>`).join('')}</div>`;
function bars(title,items){const low=Math.min(0,...items.map(i=>Number(i.amount))),high=Math.max(1,...items.map(i=>Number(i.amount)));return `<div class="chart"><h3>${title}</h3>${items.map(i=>`<div class="bar-row"><span>${esc(i.label)}</span><meter min="${low}" max="${high}" value="${Number(i.amount)}" aria-label="${esc(i.label)} amount"></meter><strong>${esc(i.amount)}</strong></div>`).join('') || '<p>No valid rows to chart.</p>'}</div>`;}
function render(r){
 if(mode==='profile'){
  $('#result').innerHTML=stats([['Rows',r.rows],['Columns',r.columns.length],['Missing cells',r.missing_cells]])+`<p class="summary">${r.duplicate_rows} exact duplicate rows. Blank or whitespace-only cells count as missing. Numeric inference requires every nonblank value to be a finite number within ±1e100.</p>`+table(['Column','Type','Missing','Distinct','Mean / median'],r.columns.map(c=>[c.name,c.type,c.missing,c.distinct,c.type==='numeric'?`${Number(c.mean.toPrecision(6))} / ${Number(c.median.toPrecision(6))}`:'—']))+'<h3>Frequent values</h3>'+table(['Column','Top values (up to five)'],r.columns.map(c=>[c.name,c.top.map(v=>`${v.value} (${v.count})`).join(', ')]))+'<h3>Preview · first 10 rows</h3>'+table(r.columns.map(c=>c.name),r.preview);
 }else if(mode==='clean'){
  $('#result').innerHTML=stats([['Input rows',r.input_rows],['Output rows',r.output_rows],['Trimmed cells',r.trimmed_cells]])+`<p class="summary">Removed ${r.duplicates_removed} duplicate rows and ${r.empty_rows_removed} blank rows. Original input is preserved. Download the cleaned CSV to continue your workflow.</p><h3>Preview · first 20 rows</h3>`+table(r.headers,r.preview);
 }else{
  $('#result').innerHTML=stats([['Net amount',r.total],['Accepted rows',r.accepted_rows],['Rejected rows',r.rejected_rows]])+`<p class="summary">Average transaction: ${esc(r.average??'N/A')}. ${r.refund_rows} negative transactions included. Currency is not inferred or converted. Duplicate transactions are retained; clean duplicates first if appropriate.</p>`+bars('Monthly net amount',r.monthly)+bars('Category breakdown',r.categories)+'<h3>Rejected records · first 20</h3>'+table(['Record','Reason'],r.rejections.slice(0,20).map(e=>[e.record,e.reason]))+'<p class="hint">Download report includes all rejection details and a spreadsheet-safe rejection CSV.</p>';
 }
}
document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',()=>{location.hash=b.dataset.mode;}));
window.addEventListener('hashchange',()=>switchMode(location.hash.slice(1)));
$('#sample').addEventListener('click',()=>{fileRevision++;$('#source').value=sample;invalidate();message('Fictional sample loaded. Includes duplicates, missing cells, and invalid dates.');});
document.querySelectorAll('textarea, fieldset input').forEach(input=>input.addEventListener('input',()=>{fileRevision++;invalidate();message('Input changed. Run the analysis to update the report.');}));
$('#file').addEventListener('change',async()=>{
 const file=$('#file').files[0];if(!file)return;$('#file').value='';const revision=++fileRevision;
 try{
  if(file.size>1000000)throw Error('Choose a CSV no larger than 1 MB.');
  message(`Reading ${file.name}…`);
  const buffer=await file.arrayBuffer();
  if(revision!==fileRevision||busy)return;
  $('#source').value=new TextDecoder('utf-8',{fatal:true}).decode(buffer);invalidate();message(`Loaded ${file.name}`);document.dispatchEvent(new Event('source-loaded'));
 }catch(error){if(revision===fileRevision)message(error.message,true);}
 finally{if(revision===fileRevision)$('#file').value='';}
});
$('#run').addEventListener('click',async()=>{
 if(busy)return;fileRevision++;busy=true;window.analysisBusy(true);result=null;$('#download').disabled=true;const controls=[...document.querySelectorAll('input,select,textarea,button')];controls.forEach(c=>c.disabled=true);message('Processing locally…');
 try{const body={csv:$('#source').value,options:{trim:$('#trim').checked,deduplicate:$('#deduplicate').checked,drop_empty:$('#drop-empty').checked},mapping:{date:$('#date-column').value,category:$('#category-column').value,amount:$('#amount-column').value}};const data=await window.analysisRequest(`/api/data/${mode}`,{...body,...window.capabilityInputs()});result=data;render(data);window.renderCapabilities(data);message('Analysis complete. Source data was not saved.');}catch(e){invalidate();message(e.message,true);}finally{busy=false;controls.forEach(c=>c.disabled=false);$('#download').disabled=!result;window.analysisBusy(false,!!result);if((config[location.hash.slice(1)]?location.hash.slice(1):'profile')!==mode)switchMode(location.hash.slice(1));}
});
$('#download').addEventListener('click',()=>{if(!result)return;const csv=mode==='clean';const blob=new Blob([csv?result.csv:JSON.stringify(result,null,2)],{type:csv?'text/csv;charset=utf-8':'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`${mode}-result.${csv?'csv':'json'}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
switchMode(location.hash.slice(1));
