'use strict';
const $=s=>document.querySelector(s);
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let pageResult=null;
const methods={list:'GET',create:'POST',get:'GET',replace:'PUT',update:'PATCH',delete:'DELETE'};
function view(){const op=$('#operation').value;$('#filters').hidden=op!=='list';$('#id-label').hidden=['list','create'].includes(op);$('#etag-label').hidden=!['replace','update','delete'].includes(op);$('#idem-label').hidden=op!=='create';$('#body-label').hidden=!['create','replace','update'].includes(op);}
function notice(text,error=false){$('#notice').textContent=text;$('#notice').className=error?'error':'';}
$('#operation').addEventListener('change',view);
$('#sample').addEventListener('click',()=>{$('#operation').value='create';$('#body').value=JSON.stringify({title:'API design review',content:'Verify pagination, optimistic concurrency, and idempotent retries.',status:'draft'},null,2);$('#idem').value=crypto.randomUUID();view();notice('Sample ready. Send it to create a real note.');});
$('#run').addEventListener('click',async()=>{
 const op=$('#operation').value,method=methods[op];let path='/api/v1/notes';const headers={'X-API-Key':$('#key').value};
 if(!headers['X-API-Key']){notice('Enter the key configured on your server.',true);return;}
 if(!['list','create'].includes(op)){const id=$('#note-id').value.trim();if(!/^[0-9a-f-]{36}$/.test(id)){notice('Enter a note UUID.',true);return;}path+='/'+id;}
 if(op==='list'){const invalid=[...$('#filters').querySelectorAll('input')].find(input=>!input.checkValidity());if(invalid){$('#filters').open=true;invalid.reportValidity();return;}const params=new URLSearchParams({page:$('#page').value,page_size:$('#page-size').value});if($('#status-filter').value)params.set('status',$('#status-filter').value);if($('#query').value)params.set('q',$('#query').value);path+='?'+params;}
 if(['replace','update','delete'].includes(op))headers['If-Match']=$('#etag').value;
 if(op==='create'&&$('#idem').value)headers['Idempotency-Key']=$('#idem').value;
 const options={method,headers};if(['create','replace','update'].includes(op)){headers['Content-Type']='application/json';options.body=$('#body').value;}
 const snapshot=Object.fromEntries(historyFields.map(id=>[id,$('#'+id).value]));
 const controls=[...document.querySelectorAll('input,select,textarea,button')];const disabled=controls.map(c=>c.disabled);controls.forEach(c=>c.disabled=true);$('#copy-response').textContent='Copy body';document.querySelector('.results').setAttribute('aria-busy','true');$('#request-caption').textContent=`${method} ${path} · Sending…`;const start=performance.now();notice('Sending request…');
 try{const response=await fetch(path,options);const text=await response.text();let data;try{data=text?JSON.parse(text):null;}catch{data=text;}
 $('#summary').innerHTML=[['HTTP status',response.status],['Method',method],['Elapsed',`${Math.round(performance.now()-start)} ms`]].map(([k,v])=>`<div class="stat"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('');
 $('#headers').textContent=['content-type','location','etag','idempotency-replayed','x-request-id','allow'].filter(h=>response.headers.has(h)).map(h=>`${h}: ${response.headers.get(h)}`).join('\n');
 recordHistory({method,path,status:response.status,elapsed_ms:Math.round(performance.now()-start),body:options.body||null,headers:Object.fromEntries(Object.entries(headers).filter(([key])=>key!=='X-API-Key')),form:snapshot});
 $('#request-caption').textContent=`${method} ${path} · ${response.status} · ${new Date().toLocaleTimeString()}`;
 $('#response').textContent=data===null?'(empty body)':typeof data==='string'?data:JSON.stringify(data,null,2);
 $('#notes').innerHTML=Array.isArray(data?.items)?data.items.map(n=>`<div class="note"><div><strong>${esc(n.title)}</strong><small>${esc(n.status)} · v${n.version}</small></div><button data-id="${esc(n.id)}">Select note</button></div>`).join(''):'';
 pageResult=response.ok&&op==='list'&&Array.isArray(data?.items)?{data,form:snapshot}:null;renderPagination();
 if(response.ok&&data?.id){$('#note-id').value=data.id;if(response.headers.has('etag'))$('#etag').value=response.headers.get('etag');}
 notice(response.ok?'Request succeeded. Inspect the status, headers, and body below.':data?.detail||'Request failed.',!response.ok);
 }catch(error){notice(error.message,true);$('#request-caption').textContent=`${method} ${path} · Network failure; any response below is from the previous request.`;}finally{controls.forEach((c,i)=>c.disabled=disabled[i]);$('#copy-response').disabled=$('#response').textContent==='No request sent.';document.querySelector('.results').setAttribute('aria-busy','false');renderPagination();$('#export-requests').disabled=!requestHistory.length;}
});
$('#notes').addEventListener('click',event=>{const id=event.target.dataset.id;if(!id)return;$('#note-id').value=id;$('#etag').value='';$('#operation').value='get';view();notice('Note selected. Send GET to retrieve its current ETag.');});
$('#body').value=JSON.stringify({title:'Example note',content:'Created through the versioned REST API.',status:'draft'},null,2);view();

$('#copy-response').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('#response').textContent);$('#copy-response').textContent='Copied';}catch{notice('Clipboard unavailable. Select and copy the response body manually.',true);}});

const historyFields=['operation','note-id','page','page-size','status-filter','query','etag','idem','body'];
const requestHistory=[];
const historyPanel=document.createElement('section');historyPanel.className='extension-report';
historyPanel.innerHTML='<h3>Request history · this session</h3><p class="hint">Last 10 completed responses. Preparing a request does not send it. API keys are excluded; request bodies may contain note content. History clears when you leave the page.</p><div id="request-history"></div><button id="export-requests" disabled>Export request collection</button>';
document.querySelector('.results').append(historyPanel);
function recordHistory(entry){
 requestHistory.unshift(entry);requestHistory.splice(10);
 $('#request-history').innerHTML=requestHistory.map((r,i)=>`<div class="note"><div><strong>${esc(r.method)} · ${r.status}</strong><small>${esc(r.path)} · ${r.elapsed_ms} ms</small></div><button data-prepare="${i}" type="button">Prepare</button></div>`).join('');
}
$('#request-history').addEventListener('click',event=>{
 if(event.target.dataset.prepare===undefined||$('#run').disabled)return;
 const entry=requestHistory[Number(event.target.dataset.prepare)];
 for(const id of historyFields)$('#'+id).value=entry.form[id];
 view();notice('Historical request prepared. Review its body, version, and idempotency key before sending.');$('#operation').focus();
});
$('#export-requests').addEventListener('click',()=>{
 const collection={format:'portfolio-lab-request-collection-v1',authentication:'Supply X-API-Key separately',requests:requestHistory.map(({form,...entry})=>entry)};
 const url=URL.createObjectURL(new Blob([JSON.stringify(collection,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='request-collection.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});

const pagination=document.createElement('div');pagination.className='response-pagination';pagination.hidden=true;
pagination.setAttribute('role','group');pagination.setAttribute('aria-label','Note result pages');
pagination.innerHTML='<button type="button" data-page-step="-1">← Previous</button><span role="status" aria-live="polite"></span><button type="button" data-page-step="1">Next →</button>';
$('#notes').after(pagination);
function renderPagination(){
 pagination.hidden=!pageResult;if(!pageResult)return;
 const {page,page_size,total,next}=pageResult.data,busy=$('#run').disabled;
 pagination.querySelector('span').textContent=`Page ${page} · ${total} ${total===1?'note':'notes'} · ${page_size} per page`;
 pagination.querySelector('[data-page-step="-1"]').disabled=busy||page<=1;
 pagination.querySelector('[data-page-step="1"]').disabled=busy||!next;
}
pagination.addEventListener('click',event=>{
 const button=event.target.closest('[data-page-step]');if(!button||button.disabled||!pageResult)return;
 const page=pageResult.data.page+Number(button.dataset.pageStep);
 for(const id of ['page-size','status-filter','query'])$('#'+id).value=pageResult.form[id];
 $('#page').value=page;$('#operation').value='list';view();$('#run').click();
});
