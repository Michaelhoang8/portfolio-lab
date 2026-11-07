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
  state = await response.json(); render();
}
function renderTickets() {
  stats('#ticket-stats', [['Total issues', state.tickets.length], ['In progress', state.tickets.filter(t => t.status === 'active').length], ['Completed', state.tickets.filter(t => t.status === 'done').length]]);
  const search = $('#search').value.toLowerCase(), priority = $('#priority-filter').value;
  const filtered = state.tickets.filter(t => `${t.title} ${t.description}`.toLowerCase().includes(search) && (!priority || t.priority === priority));
  $('#filter-summary').textContent = `${filtered.length} of ${state.tickets.length} issues shown`;
  $('#reset-filters').hidden = !search && !priority;
  $('#board').innerHTML = ['backlog', 'active', 'done'].map(status => {
    const tickets = filtered.filter(t => t.status === status);
    return `<div class="column"><h2>${status}<span>${tickets.length}</span></h2>${tickets.map(t => `<article class="card"><span class="tag ${t.priority}">#${t.id} · ${t.priority}</span><h3>${escape(t.title)}</h3><p>${escape(t.description)}</p><label>Move issue<select data-ticket="${t.id}" aria-label="Status for ${escape(t.title)}">${['backlog','active','done'].map(s => `<option ${s === t.status ? 'selected' : ''}>${s}</option>`).join('')}</select></label></article>`).join('') || empty('No issues here.')}</div>`;
  }).join('');
  $('#activity').innerHTML = state.events.slice(0, 8).map(e => `<div class="activity">#${e.ticket_id} · ${escape(e.detail)}<small>${escape(new Date(e.created_at).toLocaleString())}</small></div>`).join('') || empty('Create an issue to start the activity trail.');
}
function render() {
  renderTickets();
  stats('#inventory-stats', [['Products', state.products.length], ['Units on hand', state.products.reduce((n,p) => n+p.stock,0)], ['At reorder point', state.products.filter(p => p.stock <= p.reorder_point).length]]);
  $('#products').innerHTML = state.products.map(p => `<tr><td>${escape(p.name)}<small>${escape(p.sku)}</small></td><td>${p.stock}</td><td>${p.reorder_point}</td><td class="${p.stock <= p.reorder_point ? 'warning' : ''}">${p.stock <= p.reorder_point ? 'Reorder' : 'Healthy'}</td></tr>`).join('') || '<tr><td colspan="4">No products yet. Add your first product below.</td></tr>';
  const previous = $('#product-select').value;
  $('#product-select').innerHTML = '<option value="">Select a product</option>' + state.products.map(p => `<option value="${p.id}">${escape(p.name)} · ${p.stock} available</option>`).join('');
  $('#product-select').value = previous;
  $('#movements').innerHTML = state.movements.map(m => `<div class="activity"><strong>${m.delta > 0 ? '+' : ''}${m.delta}</strong> · ${escape(m.sku)} · ${escape(m.note)}<small>${escape(new Date(m.created_at).toLocaleString())}</small></div>`).join('') || empty('Stock movements will appear here.');
  $('#experiment-results').innerHTML = state.experiments.map(e => `<article class="panel"><h2>${escape(e.name)}</h2>${['a','b'].map(v => `<div class="rate"><label>Variant ${v.toUpperCase()}<strong>${percent(e[v+'_rate'])}</strong></label><meter min="0" max="1" value="${e[v+'_rate']}" aria-label="Variant ${v} conversion rate"></meter><small>${e[v+'_conversions']} / ${e[v+'_visitors']} · 95% CI ${percent(e[v+'_interval'][0])}–${percent(e[v+'_interval'][1])}</small></div>`).join('')}<div class="result-bottom"><div>Absolute difference<strong>${(e.difference*100).toFixed(2)} pp</strong></div><div>Relative lift<strong>${e.relative_lift === null ? 'N/A' : percent(e.relative_lift)}</strong></div></div></article>`).join('') || `<div class="panel"><h2>Your next insight starts here.</h2>${empty('Enter visitor and conversion counts for two variants to compare rates and uncertainty.')}</div>`;
}
async function post(path, data) {
  const response = await fetch(path, {method:'POST',headers:{'Content-Type':'application/json','X-Portfolio-Client':'browser'},body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
function wireForm(id, path, numbers) {
  const feedback = document.createElement('p'); feedback.className = 'form-feedback'; feedback.setAttribute('role','status'); $(id).append(feedback);
  $(id).addEventListener('submit', async event => {
    event.preventDefault(); const form = event.currentTarget, button = form.querySelector('button');
    const data = Object.fromEntries(new FormData(form)); numbers.forEach(key => data[key] = Number(data[key]));
    const originalLabel = button.textContent;
    const feedback = form.querySelector('.form-feedback');
    feedback.textContent = 'Saving…';
    button.disabled = true; button.textContent = 'Saving…';
    try { await post(path,data); form.reset(); await refresh(); notice('Saved to your workspace.'); feedback.textContent = 'Saved to your workspace.'; }
    catch(error) { notice(error.message,true); feedback.textContent = error.message; }
    finally { button.disabled = false; button.textContent = originalLabel; }
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
$('#reset-filters').addEventListener('click',()=>{$('#search').value='';$('#priority-filter').value='';renderTickets();$('#search').focus();});
$('#search').addEventListener('input', renderTickets);
$('#priority-filter').addEventListener('change', renderTickets);
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
