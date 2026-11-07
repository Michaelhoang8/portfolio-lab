/* Domain extensions. Reports and request history stay in memory unless exported. */
(() => {
  const q = s => document.querySelector(s);
  const escape = v => String(v ?? 'N/A').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const controls = {
    headers: '<label>Baseline headers (optional)<textarea id="cap-baseline_text" placeholder="Paste a previous HTTP response header block"></textarea></label>',
    secrets: '<label>Block scan at severity<select id="cap-gate_severity"><option value="high">High only</option><option value="medium">Medium and high</option></select></label>',
    search: '<label>Ranking algorithm<select id="cap-algorithm"><option value="tfidf">TF-IDF cosine</option><option value="bm25">BM25 · length-normalized ranking</option></select></label><label>Maximum matches<input id="cap-top_k" type="number" min="1" max="20" value="10"></label>',
    evaluate: '<label>Cost of a false positive<input id="cap-false_positive_cost" type="number" min="0" max="1000000" value="1"></label><label>Cost of a false negative<input id="cap-false_negative_cost" type="number" min="0" max="1000000" value="5"></label>',
    reliability: '<label>Burn threshold for both windows<input id="cap-burn_threshold" type="number" min="0.01" max="10000" step="0.01" value="2"></label>'
  };
  window.installCapabilities = app => {
    const source=q('.source');
    if (!source || !q('#run')) return;
    q('#capability-options')?.remove();
    if (!controls[app]) return;
    const fieldset=document.createElement('fieldset'); fieldset.id='capability-options';
    fieldset.innerHTML='<legend>Analysis settings</legend>'+controls[app];
    source.insertBefore(fieldset,q('#run'));
    fieldset.addEventListener('input',()=>{window.invalidate();window.message('Settings changed. Run again to update the report.');});
    fieldset.addEventListener('change',()=>{window.invalidate();window.message('Settings changed. Run again to update the report.');});
  };
  window.capabilityInputs = () => Object.fromEntries([...document.querySelectorAll('[id^="cap-"]')].map(el=>[el.id.slice(4),el.type==='number'?Number(el.value):el.value]));
  const table = (headers,rows) => `<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${escape(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${escape(v)}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${headers.length}">No applicable records.</td></tr>`}</tbody></table></div>`;
  function download(name,text,type='application/json') {
    const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function request(path,body) {
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Portfolio-Client':'browser'},body:JSON.stringify(body)});
    const data=await response.json(); if(!response.ok)throw Error(data.error||'Request failed');return data;
  }
  function exportButton(parent,label,name,text,type) {
    const button=document.createElement('button');button.type='button';button.textContent=label;
    button.addEventListener('click',()=>download(name,text,type));parent.append(button);
  }
  window.renderCapabilities = result => {
    const section=document.createElement('section');section.className='extension-report';section.setAttribute('aria-label','Additional analysis');
    const extra=result.capabilities;
    if(extra) section.innerHTML=extra.tables.map(t=>`<h3>${escape(t.title)}</h3>${table(t.headers,t.rows)}`).join('')+extra.notes.map(n=>`<p class="hint">${escape(n)}</p>`).join('');
    for(const [key,label,name] of [['audit_csv','Export full row audit','cleaning-audit.csv'],['findings_csv','Export redacted findings','secret-findings.csv']]){
      if(result[key])exportButton(section,label,name,result[key],'text/csv;charset=utf-8');
    }
    if(result.model) {
      const panel=document.createElement('div');panel.className='prediction-panel';
      panel.innerHTML='<h3>Use this model · batch prediction</h3><p class="hint">Paste CSV with the trained feature names. Training means and scales are reused; no refitting occurs. Extra columns are ignored. Up to 5,000 rows.</p><label>Unlabeled feature rows<textarea class="prediction-input" spellcheck="false"></textarea></label><label>Decision threshold<input class="prediction-threshold" type="number" min="0" max="1" step="0.01" value="0.5"></label><button type="button" class="predict-button">Predict rows</button><p class="prediction-message" role="status"></p><div class="prediction-output"></div>';
      panel.querySelector('textarea').value=result.model.features.join(',')+'\n'+result.model.means.join(',');
      let prediction=null;
      const output=panel.querySelector('.prediction-output'),message=panel.querySelector('.prediction-message');
      panel.addEventListener('input',()=>{prediction=null;output.replaceChildren();message.textContent='Inputs changed. Predict again.';});
      panel.querySelector('button').addEventListener('click',async event=>{
        const fields=[...panel.querySelectorAll('input,textarea,button')];fields.forEach(c=>c.disabled=true);message.textContent='Predicting…';
        try{prediction=await request('/api/extensions/predict',{model:result.model,csv:panel.querySelector('textarea').value,threshold:Number(panel.querySelector('input').value)});
          output.innerHTML=table(['Record','Score','Predicted class'],prediction.predictions.slice(0,50).map(p=>[p.record,p.score.toFixed(5),p.predicted]));
          exportButton(output,'Download all predictions','predictions.csv',prediction.csv,'text/csv;charset=utf-8');message.textContent=`Predicted ${prediction.rows} rows. Showing the first 50.`;
        }catch(error){prediction=null;output.replaceChildren();message.textContent=error.message;}finally{fields.forEach(c=>c.disabled=false);}
      });
      section.append(panel);
    }
    if(section.childNodes.length) q('#result').append(section);
  };
  function panel(sectionId,title,formHtml,handler) {
    const section=q(sectionId);if(!section)return;
    const container=document.createElement('section');container.className='panel extension-report';
    container.innerHTML=`<h2>${title}</h2><form class="extension-form">${formHtml}<button class="primary">Calculate plan</button></form><p class="extension-message" role="status"></p><div class="extension-output"></div>`;
    const form=container.querySelector('form'),message=container.querySelector('.extension-message'),output=container.querySelector('.extension-output');
    form.addEventListener('input',()=>{output.replaceChildren();message.textContent='Settings changed. Calculate again.';});
    form.addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries([...new FormData(form)].map(([k,v])=>[k,Number(v)]));const inputs=[...form.elements];inputs.forEach(c=>c.disabled=true);message.textContent='Calculating…';try{await handler(values,output);message.textContent='Plan ready.';}catch(error){output.replaceChildren();message.textContent=error.message;}finally{inputs.forEach(c=>c.disabled=false);}});
    section.append(container);
  }
  document.addEventListener('DOMContentLoaded',()=>{
    panel('#inventory','Replenishment planner', '<label>Lead time · days<input name="lead_days" type="number" min="1" max="365" value="7" required></label><label>Safety coverage · days<input name="safety_days" type="number" min="0" max="365" value="7" required></label>',async(values,output)=>{
      const plan=await request('/api/extensions/stock-plan',values);const headers=['SKU','Stock','30-day withdrawals','Daily demand','Days cover','Target','Order quantity'];const rows=plan.items.map(p=>[p.sku,p.stock,p.withdrawals_30d,p.daily_demand,p.days_cover??'N/A',p.target,p.order_quantity]);
      output.innerHTML=table(headers,rows)+`<p class="hint">${escape(plan.note)}</p>`;exportButton(output,'Export replenishment plan','replenishment-plan.json',JSON.stringify(plan,null,2));
    });
    panel('#experiments','Plan an experiment before collecting data','<label>Baseline conversion rate<input name="baseline" type="number" min="0.0001" max="0.9999" step="0.0001" value="0.10" required></label><label>Minimum absolute lift · rate units<input name="absolute_lift" type="number" min="0.0001" max="0.99" step="0.0001" value="0.02" required></label><label>Statistical power<input name="power" type="number" min="0.5" max="0.99" step="0.01" value="0.8" required></label><label>Two-sided alpha<input name="alpha" type="number" min="0.001" max="0.2" step="0.001" value="0.05" required></label>',async(values,output)=>{
      const plan=await request('/api/extensions/experiment-plan',values);output.innerHTML=table(['Per variant','Total visitors','Detectable rate'],[[plan.per_variant,plan.total,(plan.detectable_rate*100).toFixed(2)+'%']])+`<p class="hint">${escape(plan.note)}</p>`;exportButton(output,'Export experiment design','experiment-plan.json',JSON.stringify(plan,null,2));
    });
  });
})();
