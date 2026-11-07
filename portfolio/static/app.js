/* DOM text is escaped before markup interpolation; all writes go through the API. */
'use strict';
let state = {tickets: [], events: [], products: [], movements: [], experiments: []};
const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const percent = value => `${(value * 100).toFixed(2)}%`;
const empty = message => `<p class="empty">${message}</p>`;
function notice(message, error = false) { $('#notice').textContent = message; $('#notice').className = message ? `notice${error ? ' error' : ''}` : ''; }
function stats(target, items) { $(target).innerHTML = items.map(([label, value]) => `<div class="stat"><small>${label}</small><strong>${value}</strong></div>`).join(''); }
async function refresh() {
  const response = await fetch('/api/state');
  if (!response.ok) throw new Error('Could not load workspace. Check the server and refresh.');
  const next = await response.json();
  const stockChanged = JSON.stringify([state.products,state.movements]) !== JSON.stringify([next.products,next.movements]);
  state = next; render();
  if (stockChanged) document.dispatchEvent(new Event('stock-updated'));
}
function localToday() { const now=new Date(); return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`; }
const ticketDrafts = new Map();
const editFields = ['title','description','priority','assignee','due'];
function renderTickets() {
  const opened = new Set([...document.querySelectorAll('.ticket-assignment[open]')].map(panel=>panel.querySelector('[data-save-assignment]').dataset.saveAssignment));
  stats('#ticket-stats', [['Total issues', state.tickets.length], ['In progress', state.tickets.filter(t => t.status === 'active').length], ['Completed', state.tickets.filter(t => t.status === 'done').length]]);
  const search = $('#search').value.trim().toLowerCase(), priority = $('#priority-filter').value;
  const due=$('#due-filter').value,order=$('#issue-sort').value,today=localToday();
  const filtered = state.tickets.filter(t => {
    const matchesText=`${t.title} ${t.description} ${t.assignee || ""} #${t.id}`.toLowerCase().includes(search);
    const matchesDue=!due || t.status!=='done' && (due==='overdue'?t.due_date && t.due_date<today:due==='today'?t.due_date===today:!t.due_date);
    return matchesText && (!priority || t.priority===priority) && matchesDue;
  });
  const priorityRank={high:0,medium:1,low:2};
  filtered.sort((a,b)=>{
    if(order==='due') {const byDate=(a.due_date||'9999-99-99').localeCompare(b.due_date||'9999-99-99');if(byDate)return byDate;}
    if(order!=='newest') {const byPriority=priorityRank[a.priority]-priorityRank[b.priority];if(byPriority)return byPriority;}
    return b.id-a.id;
  });
  $('#filter-summary').textContent = `${filtered.length} of ${state.tickets.length} issues shown`;
  $('#reset-filters').hidden = !$('#search').value && !priority && !due && order==='newest';
  $('#issue-view-options summary').textContent=due || order!=='newest'?'View options · customized':'View options';
  $('#board').innerHTML = ['backlog', 'active', 'done'].map(status => {
    const tickets = filtered.filter(t => t.status === status);
    return `<div class="column"><h2>${status}<span>${tickets.length}</span></h2>${tickets.map(t => `<article class="card"><span class="tag ${t.priority}">#${t.id} · ${t.priority}</span><h3>${escape(t.title)}</h3><p>${escape(t.description)}</p><details class="ticket-assignment" data-version="${t.version}"><summary>Edit issue · ${escape(t.assignee || "Unassigned")} · ${escape(t.due_date || "No due date")}${t.due_date && t.status!=="done" && t.due_date < localToday() ? " · Overdue" : ""}</summary><label>Title<input data-title="${t.id}" value="${escape(t.title)}" maxlength="200" required></label><label>Description<textarea data-description="${t.id}" maxlength="4000" required>${escape(t.description)}</textarea></label><label>Priority<select data-priority="${t.id}">${["low","medium","high"].map(p=>`<option ${p===t.priority?"selected":""}>${p}</option>`).join("")}</select></label><label>Assignee<input data-assignee="${t.id}" value="${escape(t.assignee || "")}" maxlength="120"></label><label>Due date<input data-due="${t.id}" type="date" value="${escape(t.due_date || "")}"></label><button type="button" data-save-assignment="${t.id}">Save changes</button><p class="assignment-feedback" role="status"></p></details><label>Move issue<select data-ticket="${t.id}" aria-label="Status for ${escape(t.title)}">${['backlog','active','done'].map(s => `<option ${s === t.status ? 'selected' : ''}>${s}</option>`).join('')}</select></label></article>`).join('') || empty('No issues here.')}</div>`;
  }).join('');
  document.querySelectorAll('.ticket-assignment').forEach(panel=>{
    const id=panel.querySelector('[data-save-assignment]').dataset.saveAssignment,draft=ticketDrafts.get(id);
    panel.open=opened.has(id);
    if(draft){for(const key of editFields)panel.querySelector(`[data-${key}]`).value=draft.values[key];panel.dataset.version=draft.version;panel.querySelector('.assignment-feedback').textContent='Unsaved changes preserved.';}
  });
  $('#activity').innerHTML = state.events.slice(0, 8).map(e => `<div class="activity">#${e.ticket_id} · ${escape(e.detail)}<small>${escape(new Date(e.created_at).toLocaleString())}</small></div>`).join('') || empty('Create an issue to start the activity trail.');
}
function comparisonReport(comparison) {
  const interval=comparison.difference_interval.map(value=>(value*100).toFixed(2)).join(' to ');
  const p=comparison.p_value===null?'Unavailable':comparison.p_value<.0001?'< 0.0001':comparison.p_value.toFixed(4);
  const status={insufficient_counts:'Counts are too sparse for the normal-approximation test.',difference_detected:'Evidence of a difference at the 5% level.',inconclusive:'No clear evidence of a difference at the 5% level. This does not establish equivalence.'}[comparison.status];
  return `<p class="help">95% interval for B − A: <strong>${interval} pp</strong></p><details class="comparison-details"><summary>Comparison method &amp; evidence</summary><p>${escape(status)}</p><p>Two-sided p-value: <strong>${escape(p)}</strong></p><p class="help">The adjusted interval uses Agresti–Caffo; the test uses pooled variance. These methods can disagree near a cutoff. The test requires at least 5 expected successes and failures in each variant.</p><p class="help">Assumes independent randomized groups and a fixed stopping point. No correction for repeated looks or multiple comparisons. A p-value is not the probability that B is better, and statistical evidence does not measure business value.</p></details>`;
}
function render() {
  renderTickets();
  stats('#inventory-stats', [['Products', state.products.length], ['Units on hand', state.products.reduce((n,p) => n+p.stock,0)], ['At reorder point', state.products.filter(p => p.stock <= p.reorder_point).length]]);
  $('#products').innerHTML = state.products.map(p => `<tr><td>${escape(p.name)}<small>${escape(p.sku)}</small></td><td>${p.stock}</td><td>${p.reorder_point}</td><td class="${p.stock <= p.reorder_point ? 'warning' : ''}">${p.stock <= p.reorder_point ? 'Reorder' : 'Healthy'}</td></tr>`).join('') || '<tr><td colspan="4">No products yet. Add your first product below.</td></tr>';
  const previous = $('#product-select').value;
  $('#product-select').innerHTML = '<option value="">Select a product</option>' + state.products.map(p => `<option value="${p.id}">${escape(p.name)} · ${p.stock} available</option>`).join('');
  $('#product-select').value = previous;
  $('#movements').innerHTML = state.movements.map(m => `<div class="activity"><strong>${m.delta > 0 ? '+' : ''}${m.delta}</strong> · ${escape(m.sku)} · ${escape(m.note)}<small>${escape(new Date(m.created_at).toLocaleString())}</small></div>`).join('') || empty('Stock movements will appear here.');
  $('#experiment-results').innerHTML = state.experiments.map(e => `<article class="panel"><h2>${escape(e.name)}</h2>${['a','b'].map(v => `<div class="rate"><label>Variant ${v.toUpperCase()}<strong>${percent(e[v+'_rate'])}</strong></label><meter min="0" max="1" value="${e[v+'_rate']}" aria-label="Variant ${v} conversion rate"></meter><small>${e[v+'_conversions']} / ${e[v+'_visitors']} · 95% CI ${percent(e[v+'_interval'][0])}–${percent(e[v+'_interval'][1])}</small></div>`).join('')}<div class="result-bottom"><div>Absolute difference<strong>${(e.difference*100).toFixed(2)} pp</strong></div><div>Relative lift<strong>${e.relative_lift === null ? 'N/A' : percent(e.relative_lift)}</strong></div></div>${comparisonReport(e.comparison)}</article>`).join('') || `<div class="panel"><h2>Your next insight starts here.</h2>${empty('Enter visitor and conversion counts for two variants to compare rates and uncertainty.')}</div>`;
}
async function post(path, data) {
  const response = await fetch(path, {method:'POST',headers:{'Content-Type':'application/json','X-Portfolio-Client':'browser'},body:JSON.stringify(data)});
  const result = await response.json();
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
wireForm('#product-form','/api/products',['reorder_point']);
wireForm('#movement-form','/api/movements',['product_id','delta']);
wireForm('#experiment-form','/api/experiments',['a_visitors','a_conversions','b_visitors','b_conversions']);
$('#board').addEventListener('change', async event => {
  const select = event.target; if (!select.dataset.ticket) return;
  select.disabled = true;
  try { await post(`/api/tickets/${select.dataset.ticket}/status`,{status:select.value}); await refresh(); notice('Issue status updated.'); }
  catch(error) { renderTickets(); notice(error.message,true); }
});
function readIssueFilters(){
  const params=new URLSearchParams(location.search);
  $('#search').value=(params.get('issue_q')||'').slice(0,200);
  const priority=params.get('issue_priority');
  $('#priority-filter').value=['low','medium','high'].includes(priority)?priority:'';
  const due=params.get('issue_due'),order=params.get('issue_sort');
  $('#due-filter').value=['overdue','today','unscheduled'].includes(due)?due:'';
  $('#issue-sort').value=['priority','due'].includes(order)?order:'newest';
}
function updateIssueFilters(){
  const url=new URL(location.href),query=$('#search').value.trim(),priority=$('#priority-filter').value;
  if(query)url.searchParams.set('issue_q',query);else url.searchParams.delete('issue_q');
  if(priority)url.searchParams.set('issue_priority',priority);else url.searchParams.delete('issue_priority');
  const due=$('#due-filter').value,order=$('#issue-sort').value;
  if(due)url.searchParams.set('issue_due',due);else url.searchParams.delete('issue_due');
  if(order!=='newest')url.searchParams.set('issue_sort',order);else url.searchParams.delete('issue_sort');
  history.replaceState(null,'',url);renderTickets();
}
$('#reset-filters').addEventListener('click',()=>{$('#search').value='';$('#priority-filter').value='';$('#due-filter').value='';$('#issue-sort').value='newest';updateIssueFilters();$('#search').focus();});
$('#search').addEventListener('input',updateIssueFilters);
$('#priority-filter').addEventListener('change',updateIssueFilters);
$('#due-filter').addEventListener('change',updateIssueFilters);
$('#issue-sort').addEventListener('change',updateIssueFilters);
window.addEventListener('popstate',()=>{readIssueFilters();renderTickets();});
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
      const response=await fetch('/api/state');
      if(!response.ok)throw Error('Could not fetch the latest version. Your draft is preserved.');
      const latestState=await response.json(),latest=latestState.tickets.find(ticket=>String(ticket.id)===id);
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
 if(fields.some(field=>field.disabled))return;
 const invalid=fields.find(field=>field.checkValidity&&!field.checkValidity());
 if(invalid){invalid.reportValidity();return;}
 fields.forEach(field=>field.disabled=true);feedback.textContent='Saving issue…';
 let saved=false;
 try{
  await post(`/api/tickets/${id}/details`,{title:details.querySelector('[data-title]').value,description:details.querySelector('[data-description]').value,priority:details.querySelector('[data-priority]').value,assignee:details.querySelector('[data-assignee]').value,due_date:details.querySelector('[data-due]').value,expected_version:Number(details.dataset.version)});
  saved=true;ticketDrafts.delete(id);
  await refresh();notice('Issue details saved.');
  const updated=document.querySelector(`[data-save-assignment="${id}"]`)?.closest('details');
  if(updated){updated.open=true;updated.querySelector('.assignment-feedback').textContent='Issue details saved.';updated.querySelector('summary').focus();}
 }catch(error){
  const message=saved?'Issue details saved, but the workspace could not refresh. Reload to see the saved version.':error.message;
  notice(message,true);feedback.textContent=message;fields.forEach(field=>field.disabled=false);
  if(!saved && error.status===409)reviewIssueConflict(id,details);
 }
});
