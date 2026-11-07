/* Original vector instruments + optional synthesized interface sounds. No external assets. */
(() => {
  const instruments={
    tickets:['01','MISSION CONTROL','A small constellation of things to ship.','constellation'],
    inventory:['02','SUPPLY DEPOT','Keep the expedition moving.','stack'],
    experiments:['03','HYPOTHESIS CHAMBER','Every discovery begins with a comparison.','orbit'],
    profile:['04','SAMPLE ARCHIVE','Look closer. There is structure in the noise.','grid'],
    clean:['05','REFINERY','Raw material. Deliberate transformation.','flow'],
    sales:['06','THE ALMANAC','A field report on the movement of value.','sun'],
    logs:['07','NIGHT WATCH','Listen for the signal that does not belong.','radar'],
    headers:['08','SHIELD ARRAY','Small controls. A stronger perimeter.','shield'],
    secrets:['09','SEALED ARCHIVE','Some discoveries should stay contained.','lock'],
    train:['10','LEARNING ENGINE','A line becomes a model of the world.','curve'],
    search:['11','SIGNAL LIBRARY','A question sends a ripple through the archive.','books'],
    evaluate:['12','CALIBRATION ROOM','Measure the instrument, not just the result.','target'],
    manifest:['13','BLUEPRINT ROOM','Trace the shape of a system before it exists.','blueprint'],
    pipeline:['14','LAUNCH SEQUENCE','Many small steps. One coordinated departure.','flow'],
    reliability:['15','LIFE SUPPORT','Watch the margins that keep a system alive.','wave'],
    rest:['16','TRANSMISSION DESK','Send a signal. Read the response.','transmit']
  };
  const read=(key,fallback)=>{try{return localStorage.getItem(key)??fallback;}catch{return fallback;}};
  const save=(key,value)=>{try{localStorage.setItem(key,value);}catch{/* Preferences are optional. */}};
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let motion=read('observatory-motion','on')==='on', sound=read('observatory-sound','off')==='on';
  let audio=null,lastTone=0,lastFeedback=0,arrivalTimer;
  function tone(kind='tap') {
    if(!sound||document.hidden)return;
    const now=performance.now();if(kind==='tap'){if(now-lastTone<120)return;lastTone=now;}else{if(now-lastFeedback<120)return;lastFeedback=now;}
    try{
      audio ||= new (window.AudioContext||window.webkitAudioContext)();
      if(audio.state==='suspended')audio.resume().catch(()=>{});
      const notes=kind==='complete'?[523.25,783.99]:kind==='error'?[220,174.61]:[392];
      notes.forEach((frequency,i)=>{
        const start=audio.currentTime+i*.09,osc=audio.createOscillator(),gain=audio.createGain();
        osc.type='sine';osc.frequency.value=frequency;gain.gain.setValueAtTime(0,start);
        gain.gain.linearRampToValueAtTime(.025,start+.012);gain.gain.exponentialRampToValueAtTime(.0001,start+.18);
        osc.connect(gain);gain.connect(audio.destination);osc.start(start);osc.stop(start+.2);
        osc.onended=()=>{osc.disconnect();gain.disconnect();};
      });
    }catch{/* Audio support is never required for an app action. */}
  }
  function illustration(kind) {
    const ring='<circle cx="130" cy="105" r="72"/><circle cx="130" cy="105" r="48"/><path d="M43 105h174M130 18v174"/>';
    const drawings={
      constellation:'<path d="M45 135 88 58 142 94 201 37 225 150 142 94 110 173 45 135"/><g class="ink-fill"><circle cx="45" cy="135" r="6"/><circle cx="88" cy="58" r="10"/><circle cx="142" cy="94" r="7"/><circle cx="201" cy="37" r="5"/><circle cx="225" cy="150" r="9"/><circle cx="110" cy="173" r="5"/></g>',
      stack:'<path d="m130 32 85 45-85 45-85-45Zm-85 72 85 45 85-45M45 132l85 45 85-45M130 122v55"/><path class="heavy" d="M65 64v58m130-58v58"/>',
      orbit:'<circle cx="130" cy="105" r="16" class="ink-fill"/><g class="orbit-spin"><ellipse cx="130" cy="105" rx="100" ry="37"/><ellipse cx="130" cy="105" rx="100" ry="37" transform="rotate(60 130 105)"/><ellipse cx="130" cy="105" rx="100" ry="37" transform="rotate(120 130 105)"/><circle cx="230" cy="105" r="7" class="ink-fill"/></g>',
      grid:'<path d="M55 35h150v140H55zM55 70h150M55 105h150M55 140h150M92 35v140M130 35v140M168 35v140"/><path class="ink-fill" d="M92 70h38v35H92zm38 35h38v35h-38zM168 140h37v35h-37z"/>',
      flow:'<path d="M24 105h45m40 0h40m40 0h45M69 105V50h80v55M109 105v55h80v-55"/><circle cx="89" cy="105" r="20"/><circle cx="169" cy="105" r="20"/><circle cx="24" cy="105" r="6" class="ink-fill"/><path class="ink-fill" d="m234 96 12 9-12 9z"/><circle class="pulse-dot" cx="149" cy="50" r="6"/>',
      sun:'<g class="orbit-spin"><path d="M130 17v28m0 120v28M42 105h28m120 0h28M68 43l20 20m84 84 20 20M68 167l20-20m84-84 20-20"/></g><circle cx="130" cy="105" r="48"/><path d="M85 118h90M89 129h82M99 140h62M116 151h28"/><path class="ink-fill" d="M84 105a46 46 0 0 1 92 0z"/>',
      radar:ring+'<g class="radar-sweep"><path class="heavy" d="m130 105 51-51"/></g><circle cx="157" cy="77" r="6" class="ink-fill pulse-dot"/><circle cx="101" cy="135" r="4" class="ink-fill"/>',
      shield:'<path d="m130 25 70 26v50q0 55-70 87-70-32-70-87V51z"/><path d="m130 46 49 19v37q0 38-49 62-49-24-49-62V65z"/><path class="heavy" d="m103 102 19 19 38-44"/>',
      lock:'<rect x="68" y="85" width="124" height="93" rx="8"/><path d="M92 85V62a38 38 0 0 1 76 0v23M105 85V63a25 25 0 0 1 50 0v22"/><circle cx="130" cy="123" r="12"/><path class="heavy" d="M130 135v20"/>',
      curve:'<path d="M42 30v145h180M42 139h180M42 103h180M42 67h180"/><path class="heavy draw-line" d="M45 154C95 154 88 58 141 58s40-23 77-24"/><circle cx="141" cy="58" r="6" class="ink-fill"/>',
      books:'<path d="M47 45h35v125H47zM90 30h38v140H90zM140 55l32-9 33 119-32 9zM35 182h190M47 67h35M90 54h38M156 124l32-9"/><circle cx="207" cy="46" r="22"/><path class="heavy" d="m223 62 18 18"/>',
      target:ring+'<path class="heavy" d="M83 153 177 57"/><circle cx="130" cy="105" r="8" class="ink-fill"/><path d="m165 57 12 0v12"/>',
      blueprint:'<path d="M58 28h145v155H58zM80 54h100v100H80zM80 90h100M130 54v100M35 28v155m-5-155h10m-10 155h10M58 199h145"/><circle cx="105" cy="123" r="13"/><path class="heavy" d="M151 109h17v30h-17z"/>',
      wave:'<path d="M28 65h204M28 105h204M28 145h204"/><path class="heavy draw-line" d="M28 105h44l12-25 20 66 25-111 25 104 16-34h62"/><circle cx="232" cy="105" r="6" class="ink-fill pulse-dot"/>',
      transmit:'<path d="M30 60h125m-20-20 20 20-20 20M230 150H105m20-20-20 20 20 20"/><circle cx="55" cy="150" r="25"/><circle cx="205" cy="60" r="25"/><circle cx="55" cy="150" r="8" class="ink-fill"/><circle cx="205" cy="60" r="8" class="ink-fill"/>'
    };
    return `<svg viewBox="0 0 260 210" aria-hidden="true"><g class="plate-guide"><path d="M10 20V10h10m220 0h10v10M10 190v10h10m220 0h10v-10"/><path d="M15 105h5m220 0h5M130 10v5m0 180v5"/></g><g class="plate-drawing">${drawings[kind]}</g></svg>`;
  }
  function preferences() {
    document.body.classList.toggle('still-life',!motion||reduced.matches);
    const soundButton=document.querySelector('#sound-switch'),motionButton=document.querySelector('#motion-switch');
    if(soundButton){soundButton.textContent=sound?'♪ Sound on':'♪ Sound off';soundButton.setAttribute('aria-pressed',String(sound));}
    if(motionButton){motionButton.textContent=reduced.matches?'Motion: system reduced':motion?'Motion on':'Motion off';motionButton.setAttribute('aria-pressed',String(motion&&!reduced.matches));motionButton.disabled=reduced.matches;}
  }
  function mount() {
    const app=document.body.dataset.app,settings=instruments[app];if(!settings)return;
    document.querySelectorAll('.instrument-plate,.observatory-caption').forEach(el=>el.remove());
    const hero=document.querySelector('.intro')||document.querySelector(`.page:not([hidden]) .heading`);
    // Product navigation sets hidden flags after changing the identity.
    const target=document.querySelector(`#${app} .heading`)||hero;if(!target)return;
    const plate=document.createElement('figure');plate.className='instrument-plate';plate.setAttribute('aria-hidden','true');plate.dataset.serial=settings[0];
    plate.innerHTML=illustration(settings[3])+`<figcaption>FIG. ${settings[0]} / ${settings[1]}</figcaption><span class="plate-stamp">OBSERVATORY<br>FIELD INSTRUMENTS</span>`;
    target.append(plate);
    const caption=document.createElement('div');caption.className='observatory-caption';
    caption.innerHTML=`<span class="edition-number">${settings[0]} / 16</span><span>${settings[2]}</span><span class="edition-mark" aria-hidden="true">✳</span>`;
    target.after(caption);
    document.body.classList.remove('instrument-arrival');void document.body.offsetWidth;document.body.classList.add('instrument-arrival');
    clearTimeout(arrivalTimer);arrivalTimer=setTimeout(()=>document.body.classList.remove('instrument-arrival'),800);
    preferences();
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const dock=document.createElement('div');dock.className='observatory-controls';dock.setAttribute('aria-label','Atmosphere preferences');
    dock.innerHTML='<span class="observatory-wordmark">✳ THE OBSERVATORY <small>SOFTWARE / FIELD STUDIES</small></span><div><button id="sound-switch" type="button" aria-pressed="false">♪ Sound off</button><button id="motion-switch" type="button" aria-pressed="true">Motion on</button></div>';
    document.querySelector('main').prepend(dock);
    document.querySelector('#sound-switch').addEventListener('click',()=>{sound=!sound;save('observatory-sound',sound?'on':'off');preferences();if(sound)tone('complete');});
    document.querySelector('#motion-switch').addEventListener('click',()=>{motion=!motion;save('observatory-motion',motion?'on':'off');preferences();});
    reduced.addEventListener('change',preferences);
    document.addEventListener('click',event=>{const button=event.target.closest('button');if(button&&!button.disabled&&button.id!=='sound-switch')tone();});
    const observer=new MutationObserver(records=>{
      const notices=new Set();
      for(const record of records){const node=record.target.nodeType===1?record.target:record.target.parentElement;const notice=node?.closest('[role=status]');if(notice)notices.add(notice);}
      if(notices.size)preferences();
      for(const notice of notices){const text=notice.textContent.toLowerCase();if(notice.classList.contains('error')){tone('error');continue;}if(/complete|succeeded|saved|plan ready|predicted \d/.test(text)){tone('complete');const surface=document.querySelector('.results')||notice.closest('.panel');if(surface){surface.classList.remove('signal-complete');void surface.offsetWidth;surface.classList.add('signal-complete');}}}
    });
    observer.observe(document.querySelector('main'),{childList:true,subtree:true,characterData:true});
    document.addEventListener('visibilitychange',()=>{document.body.classList.toggle('observatory-paused',document.hidden);if(document.hidden&&audio?.state==='running')audio.suspend().catch(()=>{});});
    window.addEventListener('hashchange',()=>requestAnimationFrame(mount));
    requestAnimationFrame(mount);
  });
})();
