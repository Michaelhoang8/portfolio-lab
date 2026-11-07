'use strict';
const $=s=>document.querySelector(s);
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const methods={list:'GET',create:'POST',get:'GET',replace:'PUT',update:'PATCH',delete:'DELETE'};
function view(){const op=$('#operation').value;$('#filters').hidden=op!=='list';$('#id-label').hidden=['list','create'].includes(op);$('#etag-label').hidden=!['replace','update','delete'].includes(op);$('#idem-label').hidden=op!=='create';$('#body-label').hidden=!['create','replace','update'].includes(op);}
function notice(text,error=false){$('#notice').textContent=text;$('#notice').className=error?'error':'';}
$('#operation').addEventListener('change',view);
$('#sample').addEventListener('click',()=>{$('#operation').value='create';$('#body').value=JSON.stringify({title:'API design review',content:'Verify pagination, optimistic concurrency, and idempotent retries.',status:'draft'},null,2);$('#idem').value=crypto.randomUUID();view();notice('Sample ready. Send it to create a real note.');});
$('#run').addEventListener('click',async()=>{
 const op=$('#operation').value,method=methods[op];let path='/api/v1/notes';const headers={'X-API-Key':$('#key').value};
 if(!headers['X-API-Key']){notice('Enter the key configured on your server.',true);return;}
 if(!['list','create'].includes(op)){const id=$('#note-id').value.trim();if(!/^[0-9a-f-]{36}$/.test(id)){notice('Enter a note UUID.',true);return;}path+='/'+id;}
 if(op==='list'){const params=new URLSearchParams({page:$('#page').value,page_size:$('#page-size').value});if($('#status-filter').value)params.set('status',$('#status-filter').value);if($('#query').value)params.set('q',$('#query').value);path+='?'+params;}
 if(['replace','update','delete'].includes(op))headers['If-Match']=$('#etag').value;
 if(op==='create'&&$('#idem').value)headers['Idempotency-Key']=$('#idem').value;
 const options={method,headers};if(['create','replace','update'].includes(op)){headers['Content-Type']='application/json';options.body=$('#body').value;}
 const button=$('#run');button.disabled=true;const start=performance.now();notice('Sending request…');
 try{const response=await fetch(path,options);const text=await response.text();let data;try{data=text?JSON.parse(text):null;}catch{data=text;}
 $('#summary').innerHTML=[['HTTP status',response.status],['Method',method],['Elapsed',`${Math.round(performance.now()-start)} ms`]].map(([k,v])=>`<div class="stat"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('');
 $('#headers').textContent=['content-type','location','etag','idempotency-replayed','x-request-id','allow'].filter(h=>response.headers.has(h)).map(h=>`${h}: ${response.headers.get(h)}`).join('\n');
 $('#response').textContent=data===null?'(empty body)':typeof data==='string'?data:JSON.stringify(data,null,2);
 $('#notes').innerHTML=Array.isArray(data?.items)?data.items.map(n=>`<div class="note"><div><strong>${esc(n.title)}</strong><small>${esc(n.status)} · v${n.version}</small></div><button data-id="${esc(n.id)}">Select note</button></div>`).join(''):'';
 if(response.ok&&data?.id){$('#note-id').value=data.id;if(response.headers.has('etag'))$('#etag').value=response.headers.get('etag');}
 notice(response.ok?'Request succeeded. Inspect the status, headers, and body below.':data?.detail||'Request failed.',!response.ok);
 }catch(error){notice(error.message,true);}finally{button.disabled=false;}
});
$('#notes').addEventListener('click',event=>{const id=event.target.dataset.id;if(!id)return;$('#note-id').value=id;$('#etag').value='';$('#operation').value='get';view();notice('Note selected. Send GET to retrieve its current ETag.');});
$('#body').value=JSON.stringify({title:'Example note',content:'Created through the versioned REST API.',status:'draft'},null,2);view();
