/* DOM text is escaped before markup interpolation; all writes go through the API. */
'use strict';
let state = {tickets: [], events: [], products: [], movements: [], experiments: []};
const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const percent = value => `${(value * 100).toFixed(2)}%`;
const empty = message => `<p class="empty">${message}</p>`;
function notice(message, error = false) { $('#notice').textContent = message; $('#notice').className = message ? `notice${error ? ' error' : ''}` : ''; }
function stats(target, items) { $(target).innerHTML = items.map(([label, value]) => `<div class="stat"><small>${label}</small><strong>${value}</strong></div>`).join(''); }
let refreshSequence=0;
async function refresh() {
  const sequence=++refreshSequence;
  let received;
  try{received=await window.restTransport.send('/api/state',{method:'GET'});}
  catch(error){if(sequence!==refreshSequence)return;throw error;}
  if(sequence!==refreshSequence)return;
  const {response,text}=received;
  if (!response.ok) throw new Error('Could not load workspace. Check the server and refresh.');
  let next;try{next=JSON.parse(text);if(!next||!['tickets','events','products','movements','experiments'].every(key=>Array.isArray(next[key])))throw Error();}catch{throw Error('The workspace returned an unreadable response. Check the server and refresh.');}
  const stockChanged = JSON.stringify([state.products,state.movements]) !== JSON.stringify([next.products,next.movements]);
  state = next; render();
  if (stockChanged) document.dispatchEvent(new Event('stock-updated'));
}
function localToday() { const now=new Date(); return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`; }
const ticketDrafts = new Map();
const savingTickets = new Set();
const movingTickets = new Set();
const boardPageSize=10,boardPages={backlog:0,active:0,done:0};
function resetBoardPages(){for(const status of Object.keys(boardPages))boardPages[status]=0;}
const editFields = ['title','description','priority','assignee','due'];
function renderTickets() {
  const opened = new Set([...document.querySelectorAll('.ticket-assignment[open]')].map(panel=>panel.querySelector('[data-save-assignment]').dataset.saveAssignment));
  stats('#ticket-stats', [['Total issues', state.tickets.length], ['In progress', state.tickets.filter(t => t.status === 'active').length], ['Completed', state.tickets.filter(t => t.status === 'done').length]]);
  const search = $('#search').value.trim().toLowerCase(), priority = $('#priority-filter').value;
  const due=$('#due-filter').value,order=$('#issue-sort').value,archive=$('#issue-archive').value,today=localToday();
  const filtered = state.tickets.filter(t => {
    const matchesText=`${t.title} ${t.description} ${t.assignee || ""} #${t.id}`.toLowerCase().includes(search);
    const matchesDue=!due || t.status!=='done' && (due==='overdue'?t.due_date && t.due_date<today:due==='today'?t.due_date===today:!t.due_date);
    const matchesArchive=archive==='all'||(archive==='archived'?!!t.archived:!t.archived);
    return matchesText && (!priority || t.priority===priority) && matchesDue && matchesArchive;
  });
  const priorityRank={high:0,medium:1,low:2};
  filtered.sort((a,b)=>{
    if(order==='due') {const byDate=(a.due_date||'9999-99-99').localeCompare(b.due_date||'9999-99-99');if(byDate)return byDate;}
    if(order!=='newest') {const byPriority=priorityRank[a.priority]-priorityRank[b.priority];if(byPriority)return byPriority;}
    return b.id-a.id;
  });
  const paged=Object.keys(boardPages).some(status=>filtered.filter(ticket=>ticket.status===status).length>boardPageSize);
  $('#filter-summary').textContent = `${filtered.length} of ${state.tickets.length} issues ${paged?'match · 10 per column per page':'shown'}`;
  $('#reset-filters').hidden = !$('#search').value && !priority && !due && order==='newest' && archive==='current';
  $('#issue-view-options summary').textContent=due || order!=='newest' || archive!=='current'?'View options · customized':'View options';
  $('#board').innerHTML = ['backlog', 'active', 'done'].map(status => {
    const tickets = filtered.filter(t => t.status === status);
    const last=Math.max(0,Math.ceil(tickets.length/boardPageSize)-1);
    boardPages[status]=Math.max(0,Math.min(last,boardPages[status]));
    const start=boardPages[status]*boardPageSize,end=Math.min(start+boardPageSize,tickets.length);
    const pager=tickets.length>boardPageSize?`<div class="response-pagination" role="group" aria-label="${status} issue pages"><button type="button" data-board-status="${status}" data-board-step="-1" ${boardPages[status]===0?'disabled':''}>Previous</button><span role="status">${start+1}–${end} of ${tickets.length}</span><button type="button" data-board-status="${status}" data-board-step="1" ${boardPages[status]===last?'disabled':''}>Next</button></div>`:'';

    return `<div class="column" data-board-column="${status}"><h2 tabindex="-1">${status}<span>${tickets.length}</span></h2>${pager}${tickets.slice(start,end).map(t => `<article class="card"><span class="tag ${t.priority}">#${t.id} · ${t.priority}${t.archived?' · archived':''}</span><h3>${escape(t.title)}</h3><p>${escape(t.description)}</p><details class="ticket-assignment" data-version="${t.version}"><summary>Edit issue · ${escape(t.assignee || "Unassigned")} · ${escape(t.due_date || "No due date")}${t.due_date && t.status!=="done" && t.due_date < localToday() ? " · Overdue" : ""}</summary><label>Title<input data-title="${t.id}" value="${escape(t.title)}" maxlength="200" required></label><label>Description<textarea data-description="${t.id}" maxlength="4000" required>${escape(t.description)}</textarea></label><label>Priority<select data-priority="${t.id}">${["low","medium","high"].map(p=>`<option ${p===t.priority?"selected":""}>${p}</option>`).join("")}</select></label><label>Assignee<input data-assignee="${t.id}" value="${escape(t.assignee || "")}" maxlength="120"></label><label>Due date<input data-due="${t.id}" type="date" value="${escape(t.due_date || "")}"></label><button type="button" data-save-assignment="${t.id}">Save changes</button><button type="button" data-archive-ticket="${t.id}" data-archived="${!!t.archived}">${t.archived?'Restore issue':'Archive issue'}</button><p class="assignment-feedback" role="status"></p></details><label>Move issue<select data-ticket="${t.id}" aria-label="Status for ${escape(t.title)}">${['backlog','active','done'].map(s => `<option ${s === t.status ? 'selected' : ''}>${s}</option>`).join('')}</select></label></article>`).join('') || empty('No issues here.')}</div>`;
  }).join('');
  document.querySelectorAll('.ticket-assignment').forEach(panel=>{
    const id=panel.querySelector('[data-save-assignment]').dataset.saveAssignment,draft=ticketDrafts.get(id);
    panel.open=opened.has(id);
    if(draft){for(const key of editFields)panel.querySelector(`[data-${key}]`).value=draft.values[key];panel.dataset.version=draft.version;panel.querySelector('.assignment-feedback').textContent='Unsaved changes preserved.';}
    if(savingTickets.has(id)){panel.querySelectorAll('input,textarea,select,button').forEach(field=>field.disabled=true);panel.querySelector('.assignment-feedback').textContent='Saving issue…';}
  });
  document.querySelectorAll('[data-ticket]').forEach(select=>{select.disabled=movingTickets.has(select.dataset.ticket);});
  $('#activity').innerHTML = state.events.slice(0, 8).map(e => `<div class="activity">#${e.ticket_id} · ${escape(e.detail)}<small>${escape(new Date(e.created_at).toLocaleString())}</small></div>`).join('') || empty('Create an issue to start the activity trail.');
}
function comparisonReport(comparison) {
  const interval=comparison.difference_interval.map(value=>(value*100).toFixed(2)).join(' to ');
  const p=comparison.p_value===null?'Unavailable':comparison.p_value<.0001?'< 0.0001':comparison.p_value.toFixed(4);
  const status={insufficient_counts:'Counts are too sparse for the normal-approximation test.',difference_detected:'Evidence of a difference at the 5% level.',inconclusive:'No clear evidence of a difference at the 5% level. This does not establish equivalence.'}[comparison.status];
  return `<p class="help">95% interval for B − A: <strong>${interval} pp</strong></p><details class="comparison-details"><summary>Comparison method &amp; evidence</summary><p>${escape(status)}</p><p>Two-sided p-value: <strong>${escape(p)}</strong></p><p class="help">The adjusted interval uses Agresti–Caffo; the test uses pooled variance. These methods can disagree near a cutoff. The test requires at least 5 expected successes and failures in each variant.</p><p class="help">Assumes independent randomized groups and a fixed stopping point. No correction for repeated looks or multiple comparisons. A p-value is not the probability that B is better, and statistical evidence does not measure business value.</p></details>`;
}
function visibleProducts(products,query,status,order){
  const search=query.trim().toLowerCase();
  const visible=products.filter(product=>(!search||`${product.name} ${product.sku}`.toLowerCase().includes(search))&&
    (status==='reorder'?product.stock<=product.reorder_point:status==='empty'?product.stock===0:
     status==='healthy'?product.stock>product.reorder_point:true));
  return visible.sort((a,b)=>{
    const difference=order==='stock'?a.stock-b.stock:order==='shortfall'?
      Math.max(0,b.reorder_point-b.stock)-Math.max(0,a.reorder_point-a.stock):0;
    return difference||a.name.localeCompare(b.name)||a.sku.localeCompare(b.sku);
  });
}
function renderInventoryOverview(){
  const query=$('#inventory-search').value,status=$('#inventory-status').value,order=$('#inventory-sort').value;
  const products=visibleProducts(state.products,query,status,order),custom=!!query.trim()||!!status||order!=='name';
  $('#products').innerHTML=products.map(p=>`<tr><td>${escape(p.name)}<small>${escape(p.sku)}</small></td><td>${p.stock}</td><td>${p.reorder_point}</td><td class="${p.stock<=p.reorder_point?'warning':''}">${p.stock<=p.reorder_point?'Reorder':'Healthy'}</td></tr>`).join('')||
    `<tr><td colspan="4">${state.products.length?'No products match these filters.':'No products yet. Add your first product below.'}</td></tr>`;
  $('#inventory-count').textContent=`${products.length} of ${state.products.length} products shown. Overview totals include all products.`;
  $('#inventory-view-options summary').textContent=custom?'Inventory filters · customized':'Filter inventory';
  $('#reset-inventory-filters').hidden=!custom;
}
function readInventoryFilters(){
  const params=new URLSearchParams(location.search);
  $('#inventory-search').value=(params.get('stock_q')||'').slice(0,200);
  $('#inventory-status').value=['reorder','empty','healthy'].includes(params.get('stock_status'))?params.get('stock_status'):'';
  $('#inventory-sort').value=['stock','shortfall'].includes(params.get('stock_sort'))?params.get('stock_sort'):'name';
}
function updateInventoryFilters(){
  const url=new URL(location.href);
  for(const [parameter,value] of [['stock_q',$('#inventory-search').value.trim()],['stock_status',$('#inventory-status').value],
                                 ['stock_sort',$('#inventory-sort').value==='name'?'':$('#inventory-sort').value]]){
    if(value)url.searchParams.set(parameter,value);else url.searchParams.delete(parameter);
  }
  history.replaceState(null,'',url);renderInventoryOverview();
}
$('#inventory-search').addEventListener('input',updateInventoryFilters);
$('#inventory-status').addEventListener('change',updateInventoryFilters);
$('#inventory-sort').addEventListener('change',updateInventoryFilters);
$('#reset-inventory-filters').addEventListener('click',()=>{
  $('#inventory-search').value='';$('#inventory-status').value='';$('#inventory-sort').value='name';
  updateInventoryFilters();$('#inventory-search').focus();
});
window.addEventListener('popstate',()=>{readInventoryFilters();renderInventoryOverview();});
readInventoryFilters();
function experimentContext(experiment){
  if(!experiment.hypothesis&&!experiment.primary_metric)return '';
  return `<details><summary>Experiment context</summary>${experiment.primary_metric?`<p><strong>Primary conversion metric</strong><br>${escape(experiment.primary_metric)}</p>`:''}${experiment.hypothesis?`<p><strong>Hypothesis</strong><br>${escape(experiment.hypothesis)}</p>`:''}</details>`;
}
function render() {
  renderTickets();
  stats('#inventory-stats', [['Products', state.products.length], ['Units on hand', state.products.reduce((n,p) => n+p.stock,0)], ['At reorder point', state.products.filter(p => p.stock <= p.reorder_point).length]]);
  renderInventoryOverview();
  const editing=$('#edit-product').value;
  $('#edit-product').innerHTML='<option value="">Select a product</option>'+state.products.map(p=>`<option value="${p.id}">${escape(p.name)} · ${escape(p.sku)}</option>`).join('');
  $('#edit-product').value=editing;
  const previous = $('#product-select').value;
  $('#product-select').innerHTML = '<option value="">Select a product</option>' + state.products.map(p => `<option value="${p.id}">${escape(p.name)} · ${p.stock} available</option>`).join('');
  $('#product-select').value = previous;
  $('#movements').innerHTML = state.movements.map(m => `<div class="activity"><strong>${m.delta > 0 ? '+' : ''}${m.delta}</strong> · ${escape(m.sku)} · ${escape(m.note)}<small>${escape(new Date(m.created_at).toLocaleString())}</small></div>`).join('') || empty('Stock movements will appear here.');
  $('#experiment-results').innerHTML = state.experiments.map(e => `<article class="panel"><h2>${escape(e.name)}</h2>${experimentContext(e)}${['a','b'].map(v => `<div class="rate"><label>Variant ${v.toUpperCase()}<strong>${percent(e[v+'_rate'])}</strong></label><meter min="0" max="1" value="${e[v+'_rate']}" aria-label="Variant ${v} conversion rate"></meter><small>${e[v+'_conversions']} / ${e[v+'_visitors']} · 95% CI ${percent(e[v+'_interval'][0])}–${percent(e[v+'_interval'][1])}</small></div>`).join('')}<div class="result-bottom"><div>Absolute difference<strong>${(e.difference*100).toFixed(2)} pp</strong></div><div>Relative lift<strong>${e.relative_lift === null ? 'N/A' : percent(e.relative_lift)}</strong></div></div>${comparisonReport(e.comparison)}</article>`).join('') || `<div class="panel"><h2>Your next insight starts here.</h2>${empty('Enter visitor and conversion counts for two variants to compare rates and uncertainty.')}</div>`;
}
async function post(path, data) {
  let response,raw;
  try {
    const received=await window.restTransport.send(path,{method:'POST',headers:{'Content-Type':'application/json','X-Portfolio-Client':'browser'},body:JSON.stringify(data)});
    response=received.response;raw=received.text;
  } catch(error) {
    if(path==='/api/movements' && data.request_key)throw Error(`${error.message} The movement may have been saved. Keep the same inputs to retry with the same request key; it will not change stock twice.`);
    throw Error(window.restTransport.recoveryMessage(error,'POST'));
  }
  let result;try{result=JSON.parse(raw);if(!result||typeof result!=='object'||Array.isArray(result))throw Error();}catch{throw Error('The server returned an unreadable response. The write may have completed; refresh the workspace before retrying.');}
  if (!response.ok) {const error=new Error(result.error || 'Request failed');error.status=response.status;throw error;}
  return result;
}
function wireForm(id, path, numbers) {
  let pendingMovement = null;
  const feedback = document.createElement('p'); feedback.className = 'form-feedback'; feedback.setAttribute('role','status'); $(id).append(feedback);
  $(id).addEventListener('submit', async event => {
    event.preventDefault(); const form = event.currentTarget, button = form.querySelector('button');
    if (form.dataset.saving) return;
    const data = Object.fromEntries(new FormData(form)); numbers.forEach(key => data[key] = Number(data[key]));
    if (path === '/api/movements') {
      const signature = JSON.stringify(data);
      if (!pendingMovement || pendingMovement.signature !== signature) pendingMovement = {signature, key:crypto.randomUUID()};
      data.request_key = pendingMovement.key;
    }
    const controls = [...form.elements], disabled = controls.map(control => control.disabled);
    form.dataset.saving = 'true'; form.setAttribute('aria-busy','true');
    controls.forEach(control => control.disabled = true);
    const originalLabel = button.textContent;
    const feedback = form.querySelector('.form-feedback');
    feedback.textContent = 'Saving…';
    button.disabled = true; button.textContent = 'Saving…';
    try {
      const saved = await post(path,data); pendingMovement = null; form.reset();
      const message = saved.replayed ? 'Previously saved movement confirmed. Stock was not changed twice.' : 'Saved to your workspace.';
      try { await refresh(); notice(message); feedback.textContent = message; }
      catch(error) { const message = 'Saved successfully, but the workspace could not refresh. Reload to see the latest data.'; notice(message,true); feedback.textContent = message; }
    }
    catch(error) { notice(error.message,true); feedback.textContent = error.message; }
    finally { controls.forEach((control,i) => control.disabled = disabled[i]); button.textContent = originalLabel; delete form.dataset.saving; form.setAttribute('aria-busy','false'); }
  });
}
wireForm('#ticket-form','/api/tickets',[]);
function loadProductEditor(){
 const form=$('#product-edit-form'),product=state.products.find(p=>String(p.id)===$('#edit-product').value);
 form.querySelector('[name=name]').value=product?.name||'';
 form.querySelector('[name=reorder_point]').value=product?.reorder_point??'';
 form.dataset.version=product?.version||'';
 form.querySelector('.product-feedback').textContent=product?`Loaded saved version ${product.version}.`:'';
}
$('#edit-product').addEventListener('change',loadProductEditor);
$('#reload-product').addEventListener('click',async()=>{
 const form=$('#product-edit-form'),feedback=form.querySelector('.product-feedback');
 if(form.dataset.saving)return;
 if(!$('#edit-product').value){feedback.textContent='Select a product first.';return;}
 const fields=[...form.elements];form.dataset.saving='true';fields.forEach(field=>field.disabled=true);
 try{await refresh();loadProductEditor();}
 catch(error){feedback.textContent='Could not load saved values. Your edits are preserved.';}
 finally{fields.forEach(field=>field.disabled=false);delete form.dataset.saving;}
});
$('#product-edit-form').addEventListener('submit',async event=>{
 event.preventDefault();const form=event.currentTarget;if(form.dataset.saving)return;
 const id=$('#edit-product').value,feedback=form.querySelector('.product-feedback');
 const data={name:form.querySelector('[name=name]').value,reorder_point:Number(form.querySelector('[name=reorder_point]').value),expected_version:Number(form.dataset.version)};
 const fields=[...form.elements];form.dataset.saving='true';form.setAttribute('aria-busy','true');fields.forEach(field=>field.disabled=true);feedback.textContent='Saving product details…';
 let saved=false;
 try {
  const result=await post(`/api/products/${id}/details`,data);saved=true;form.dataset.version=result.version;
  form.querySelector('[name=name]').value=result.name;form.querySelector('[name=reorder_point]').value=result.reorder_point;
  await refresh();feedback.textContent='Product details saved.';notice('Product details saved.');
 } catch(error){const message=saved?'Product details saved, but the overview could not refresh. Load saved values to refresh it.':error.message;feedback.textContent=message;notice(message,true);}
 finally{fields.forEach(field=>field.disabled=false);delete form.dataset.saving;form.setAttribute('aria-busy','false');}
});
wireForm('#product-form','/api/products',['reorder_point']);
wireForm('#movement-form','/api/movements',['product_id','delta']);
wireForm('#experiment-form','/api/experiments',['a_visitors','a_conversions','b_visitors','b_conversions']);
$('#board').addEventListener('change', async event => {
  const select=event.target,id=select.dataset.ticket;if(!id||movingTickets.has(id))return;
  movingTickets.add(id);select.disabled=true;let saved=false;
  try {await post(`/api/tickets/${id}/status`,{status:select.value,expected_version:state.tickets.find(ticket=>String(ticket.id)===id).version});saved=true;await refresh();notice('Issue status updated.');}
  catch(error){
    if(!saved && error.status===409){
      try{await refresh();notice('This issue changed elsewhere. The board is refreshed; review it before choosing a status again.',true);}
      catch{renderTickets();notice('This issue changed elsewhere, and the latest board could not load. Reload before trying again.',true);}
    }else{renderTickets();notice(saved?'Issue status saved, but the workspace could not refresh. Reload to see the latest data.':error.message,true);}
  }
  finally{movingTickets.delete(id);const current=document.querySelector(`[data-ticket="${id}"]`);if(current)current.disabled=false;}
});
function readIssueFilters(){
  const params=new URLSearchParams(location.search);
  $('#search').value=(params.get('issue_q')||'').slice(0,200);
  const priority=params.get('issue_priority');
  $('#priority-filter').value=['low','medium','high'].includes(priority)?priority:'';
  const archive=params.get('issue_archive');
  $('#issue-archive').value=['archived','all'].includes(archive)?archive:'current';
  const due=params.get('issue_due'),order=params.get('issue_sort');
  $('#due-filter').value=['overdue','today','unscheduled'].includes(due)?due:'';
  $('#issue-sort').value=['priority','due'].includes(order)?order:'newest';
}
function updateIssueFilters(){
  resetBoardPages();
  const url=new URL(location.href),query=$('#search').value.trim(),priority=$('#priority-filter').value;
  if(query)url.searchParams.set('issue_q',query);else url.searchParams.delete('issue_q');
  if(priority)url.searchParams.set('issue_priority',priority);else url.searchParams.delete('issue_priority');
  const due=$('#due-filter').value,order=$('#issue-sort').value;
  if(due)url.searchParams.set('issue_due',due);else url.searchParams.delete('issue_due');
  if(order!=='newest')url.searchParams.set('issue_sort',order);else url.searchParams.delete('issue_sort');
  const archive=$('#issue-archive').value;
  if(archive!=='current')url.searchParams.set('issue_archive',archive);else url.searchParams.delete('issue_archive');
  history.replaceState(null,'',url);renderTickets();
}
$('#reset-filters').addEventListener('click',()=>{$('#search').value='';$('#priority-filter').value='';$('#due-filter').value='';$('#issue-sort').value='newest';$('#issue-archive').value='current';updateIssueFilters();$('#search').focus();});
$('#search').addEventListener('input',updateIssueFilters);
$('#priority-filter').addEventListener('change',updateIssueFilters);
$('#due-filter').addEventListener('change',updateIssueFilters);
$('#issue-sort').addEventListener('change',updateIssueFilters);
$('#issue-archive').addEventListener('change',updateIssueFilters);
window.addEventListener('popstate',()=>{readIssueFilters();resetBoardPages();renderTickets();});
readIssueFilters();
const titles = {tickets:'Issue Desk',inventory:'Stockroom',experiments:'Experiment Studio'};
function navigate(page) {
  if (!titles[page]) page = 'tickets';
  window.designIdentity(page);
  document.querySelectorAll('.page').forEach(section => section.hidden = section.id !== page);
  document.querySelectorAll('[data-page]').forEach(button => {button.classList.toggle('selected',button.dataset.page === page);button.setAttribute('aria-pressed',String(button.dataset.page === page));});
  $('#breadcrumb').textContent = `Workspace / ${titles[page]}`;
  document.title = `${titles[page]} · Portfolio Lab`; notice('');
}
document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => { location.hash = button.dataset.page; }));
window.addEventListener('hashchange', () => navigate(location.hash.slice(1)));
$('#export').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(state,null,2)],{type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'portfolio-workspace.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
});
navigate(location.hash.slice(1));
refresh().catch(error => notice(error.message,true));

$('#board').addEventListener('input',event=>{
 const panel=event.target.closest('.ticket-assignment');if(!panel)return;
 const id=panel.querySelector('[data-save-assignment]').dataset.saveAssignment;
 const values=Object.fromEntries(editFields.map(key=>[key,panel.querySelector(`[data-${key}]`).value]));
 const dirty=editFields.some(key=>{const field=panel.querySelector(`[data-${key}]`);const initial=field.tagName==='SELECT'?[...field.options].find(option=>option.defaultSelected)?.value:field.defaultValue;return field.value!==initial;});
 if(dirty)ticketDrafts.set(id,{values,version:panel.dataset.version});else ticketDrafts.delete(id);
});
function reviewIssueConflict(id,details) {
  const feedback=details.querySelector('.assignment-feedback');
  details.querySelector('.conflict-review')?.remove();
  const review=document.createElement('div');review.className='conflict-review';
  review.innerHTML='<p>Review the latest saved values without changing your draft.</p><button type="button" class="review-latest">Review latest version</button><div class="conflict-values"></div>';
  details.append(review);
  review.querySelector('.review-latest').addEventListener('click',async event=>{
    const button=event.currentTarget,save=details.querySelector('[data-save-assignment]');button.disabled=true;save.disabled=true;
    try {
      const {response,text}=await window.restTransport.send('/api/state',{method:'GET'});
      if(!response.ok)throw Error('Could not fetch the latest version. Your draft is preserved.');
      const latestState=JSON.parse(text),latest=latestState.tickets.find(ticket=>String(ticket.id)===id);
      if(!latest)throw Error('This issue is no longer available. Your draft is preserved.');
      if(!details.isConnected)return;
      const names={title:'Title',description:'Description',priority:'Priority',assignee:'Assignee',due:'Due date'};
      const values=review.querySelector('.conflict-values');
      values.innerHTML=`<p>Saved version ${latest.version}. Your draft remains in the fields above.</p><dl>${editFields.map(key=>`<dt>${names[key]}</dt><dd>${escape(latest[key==='due'?'due_date':key] || 'Not set')}</dd>`).join('')}</dl><button type="button" class="load-latest">Discard this draft and load saved values</button><p class="help">This replaces only your unsaved edits for this issue. Nothing is written to the server.</p>`;
      values.querySelector('.load-latest').addEventListener('click',()=>{
        ticketDrafts.delete(id);state=latestState;render();notice('Latest saved values loaded. You can edit and save from this version.');
        const panel=document.querySelector(`[data-save-assignment="${id}"]`)?.closest('details');
        if(panel){panel.open=true;panel.querySelector('[data-title]').focus();}
      });
      feedback.textContent='Latest version ready to review. Your draft is unchanged.';
    } catch(error) {feedback.textContent=error.message;}
    finally {button.disabled=false;save.disabled=false;}
  });
}
$('#board').addEventListener('click',async event=>{
 const id=event.target.dataset.saveAssignment;if(!id)return;
 const details=event.target.closest('details');
 const fields=[...details.querySelectorAll('input,textarea,select,button')];
 const feedback=details.querySelector('.assignment-feedback');
 if(savingTickets.has(id)||fields.some(field=>field.disabled))return;
 const invalid=fields.find(field=>field.checkValidity&&!field.checkValidity());
 if(invalid){invalid.reportValidity();return;}
 savingTickets.add(id);fields.forEach(field=>field.disabled=true);feedback.textContent='Saving issue…';
 let saved=false;
 try{
  await post(`/api/tickets/${id}/details`,{title:details.querySelector('[data-title]').value,description:details.querySelector('[data-description]').value,priority:details.querySelector('[data-priority]').value,assignee:details.querySelector('[data-assignee]').value,due_date:details.querySelector('[data-due]').value,expected_version:Number(details.dataset.version)});
  saved=true;ticketDrafts.delete(id);
  await refresh();notice('Issue details saved.');
  const updated=document.querySelector(`[data-save-assignment="${id}"]`)?.closest('details');
  if(updated){updated.open=true;updated.querySelector('.assignment-feedback').textContent='Issue details saved.';updated.querySelector('summary').focus();}
 }catch(error){
  const message=saved?'Issue details saved, but the workspace could not refresh. Reload to see the saved version.':error.message;
  const current=document.querySelector(`[data-save-assignment="${id}"]`)?.closest('details')||details;
  notice(message,true);current.querySelector('.assignment-feedback').textContent=message;
  if(!saved && error.status===409)reviewIssueConflict(id,current);
 }finally{
  savingTickets.delete(id);
  const current=document.querySelector(`[data-save-assignment="${id}"]`)?.closest('details');
  (current?[...current.querySelectorAll('input,textarea,select,button')]:fields).forEach(field=>field.disabled=false);
 }
});

$('#board').addEventListener('click',async event=>{
 const button=event.target.closest('[data-archive-ticket]');if(!button)return;
 const id=button.dataset.archiveTicket,details=button.closest('details'),feedback=details.querySelector('.assignment-feedback');
 if(savingTickets.has(id))return;
 if(ticketDrafts.has(id)){feedback.textContent='Save your local edits before archiving or restoring this issue.';return;}
 const archived=button.dataset.archived!=='true',fields=[...details.querySelectorAll('input,textarea,select,button')];
 savingTickets.add(id);fields.forEach(field=>field.disabled=true);feedback.textContent=archived?'Archiving issue…':'Restoring issue…';
 let saved=false;
 try{
  await post(`/api/tickets/${id}/archive`,{archived,expected_version:Number(details.dataset.version)});saved=true;
  await refresh();notice(archived?'Issue archived. Open View options and choose Archived issues to find it.':'Issue restored to the current board.');
  const current=document.querySelector(`[data-save-assignment="${id}"]`)?.closest('details');
  if(current)current.querySelector('.assignment-feedback').textContent=archived?'Issue archived.':'Issue restored.';
  (current?.querySelector('summary')||$('#issue-view-options summary')).focus();
 }catch(error){
  if(!saved&&error.status===409){
   try{await refresh();notice('This issue changed elsewhere. Review the refreshed board before trying again.',true);}
   catch{notice('The issue changed elsewhere and could not refresh. Reload before trying again.',true);}
  }else{notice(saved?'Issue visibility saved, but the board could not refresh. Reload to see the latest data.':error.message,true);}
  const current=document.querySelector(`[data-save-assignment="${id}"]`)?.closest('details');
  if(current)current.querySelector('.assignment-feedback').textContent=$('#notice').textContent;
 }finally{
  savingTickets.delete(id);
  const current=document.querySelector(`[data-save-assignment="${id}"]`)?.closest('details');
  (current?[...current.querySelectorAll('input,textarea,select,button')]:fields).forEach(field=>field.disabled=false);
 }
});

$('#board').addEventListener('click',event=>{
 const button=event.target.closest('[data-board-status]');if(!button||button.disabled)return;
 const status=button.dataset.boardStatus,step=Number(button.dataset.boardStep);
 if(!Object.hasOwn(boardPages,status)||![-1,1].includes(step))return;
 boardPages[status]+=step;renderTickets();
 const column=document.querySelector(`[data-board-column="${status}"]`);
 column.querySelector('h2').focus({preventScroll:true});column.scrollIntoView({block:'start'});
});
