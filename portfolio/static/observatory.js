/* Original vector instruments + optional synthesized interface sounds. No external assets. */
(() => {
  const instruments={
    tickets:['STICKER DESK','Make room for the next good idea.','stickers',330,'triangle'],
    inventory:['DOCK 02','Goods in. Goods out. Nothing lost.','stack',180,'sine'],
    experiments:['FORM & CHANCE','Two versions. One considered comparison.','bauhaus',440,'triangle'],
    profile:['DATA ATLAS','Map the terrain before the journey.','contours',520,'sine'],
    clean:['THE WASH CYCLE','A fresh start for messy data.','bubbles',660,'sine'],
    sales:['THE REVENUE EDITION','Follow the figures. Find the story.','press',350,'triangle'],
    logs:['AFTER HOURS','Keep an eye on the unexpected.','radar',240,'sine'],
    headers:['PERIMETER','A stronger web starts at the edges.','shield',580,'sine'],
    secrets:['RESTRICTED FILES','Review carefully. Leave no secrets behind.','dossier',200,'triangle'],
    train:['THE MODEL GARDEN','Small observations. Growing understanding.','plant',740,'sine'],
    search:['THE READING ROOM','The right passage is waiting.','books',392,'sine'],
    evaluate:['CALIBRATION / 12','Trust the measurement. Question the model.','target',880,'sine'],
    manifest:['STRUCTURE OFFICE','Draw the system before you build it.','blueprint',294,'triangle'],
    pipeline:['DEPLOYMENT TRANSIT','Every job has a destination.','transit',494,'sine'],
    reliability:['TIDELINE','Stay steady through changing conditions.','tide',262,'sine'],
    rest:['PACKET ARCADE','Request sent. Your move.','arcade',784,'triangle']
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
      const voice=instruments[document.body.dataset.app],base=voice?.[3]||392;
      const notes=kind==='complete'?[base,base*1.5]:kind==='error'?[base*.65,base*.5]:[base];
      notes.forEach((frequency,i)=>{
        const start=audio.currentTime+i*.09,osc=audio.createOscillator(),gain=audio.createGain();
        osc.type=voice?.[4]||'sine';osc.frequency.value=frequency;gain.gain.setValueAtTime(0,start);
        gain.gain.linearRampToValueAtTime(.025,start+.012);gain.gain.exponentialRampToValueAtTime(.0001,start+.18);
        osc.connect(gain);gain.connect(audio.destination);osc.start(start);osc.stop(start+.2);
        osc.onended=()=>{osc.disconnect();gain.disconnect();};
      });
    }catch{/* Audio support is never required for an app action. */}
  }
  function illustration(kind) {
    const ring='<circle cx="130" cy="105" r="72"/><circle cx="130" cy="105" r="48"/><path d="M43 105h174M130 18v174"/>';
    const drawings={
      stickers:'<g class="sticker-bob"><rect x="28" y="40" width="95" height="110" rx="8" fill="#f4cd57"/><path d="m45 80 15 15 40-35M45 115h55" stroke="#272335" stroke-width="5"/></g><g transform="rotate(12 177 115)"><rect x="132" y="66" width="100" height="105" rx="9" fill="#f49bb3"/><circle cx="182" cy="115" r="30" stroke="#272335"/><path d="M168 119q14 22 28 0" stroke="#272335"/><circle cx="171" cy="106" r="3" fill="#272335"/><circle cx="193" cy="106" r="3" fill="#272335"/></g>',
      bauhaus:'<circle cx="95" cy="80" r="52" fill="#e65036" stroke="none"/><path d="M125 35h92v92h-92z" fill="#e9b73c" stroke="none"/><path d="m35 175 82-100 82 100z" fill="#245ba5" stroke="none"/><circle class="pulse-dot" cx="205" cy="166" r="15" fill="#252525" stroke="none"/>',
      contours:'<g class="contour-lines"><path d="M15 140Q30 10 130 30T245 140M30 143Q44 32 130 50T230 142M48 145Q56 54 130 69T211 141M67 146Q73 77 130 86T192 140M87 145Q92 99 130 104T172 140M108 140q22-43 44 0"/><path d="M20 173q70-40 117 0t105-10"/></g><circle cx="130" cy="125" r="5" class="ink-fill"/>',
      bubbles:'<circle cx="130" cy="105" r="76" fill="#e3f9f8"/><circle cx="130" cy="105" r="55"/><path class="wash-wave" d="M79 111q25-25 51 0t51 0M80 126q25-25 51 0t48 0"/><g class="bubble-rise"><circle cx="67" cy="42" r="15"/><circle cx="205" cy="47" r="10"/><circle cx="207" cy="157" r="18"/></g><path d="m108 83 14 14 31-33" stroke-width="5"/>',
      press:'<path d="M42 25h176v165H42zM60 48h140M60 58h140"/><path d="M60 78h60v65H60z" fill="currentColor"/><path d="M137 80h63m-63 14h63m-63 14h63m-63 14h63m-63 14h63M60 161h140M60 174h140"/>',
      dossier:'<path d="M45 54h65l18 17h90v110H45z" fill="#d6c5a8"/><g transform="rotate(-9 130 95)"><path d="M73 28h111v126H73z" fill="#eee4cf"/><path d="M89 52h78M89 69h78M89 87h49" stroke="#302c28" stroke-width="9"/><path d="M89 120h78" stroke="#a42d29" stroke-width="13"/></g>',
      plant:'<path d="M130 175V70" stroke-width="4"/><path class="leaf-sway" d="M129 124Q57 126 55 67q72 0 74 57M132 98q70 0 74-56-68 0-74 56" fill="#9eb897"/><path d="M92 166h76l-12 30h-52z" fill="#b67d58"/><circle cx="60" cy="36" r="12" fill="#e6c568" stroke="none"/>',
      transit:'<path d="M35 30v100q0 45 45 45h145" stroke="#ed7865" stroke-width="10"/><path class="train-line" d="M25 65h130q35 0 35 35v90" stroke="#73bfc9" stroke-width="10"/><g fill="#fff" stroke="#292d43" stroke-width="4"><circle cx="35" cy="65" r="10"/><circle cx="105" cy="65" r="8"/><circle cx="190" cy="130" r="8"/><circle cx="110" cy="175" r="8"/><circle cx="190" cy="175" r="10"/></g>',
      tide:'<circle cx="177" cy="55" r="28" fill="#e5c590" stroke="none"/><g class="tide-drift"><path d="M10 108q30-30 60 0t60 0t60 0t60 0M10 137q30-30 60 0t60 0t60 0t60 0M10 166q30-30 60 0t60 0t60 0t60 0" stroke-width="5"/></g>',
      arcade:'<path d="M60 22h140l18 122-18 48H60l-18-48z" fill="#24233f"/><path d="M77 42h106v75H77z" fill="#121226"/><path class="packet-blink" d="m99 66 16 13-16 13m29 0h28" stroke="#73f6ca" stroke-width="6"/><path d="M59 143h142"/><circle cx="93" cy="158" r="10" fill="#ff8ac6"/><circle cx="162" cy="157" r="6" fill="#f2d66d"/><circle cx="181" cy="157" r="6" fill="#73f6ca"/>',
      stack:'<path d="m130 32 85 45-85 45-85-45Zm-85 72 85 45 85-45M45 132l85 45 85-45M130 122v55"/><path class="heavy" d="M65 64v58m130-58v58"/>',
      radar:ring+'<g class="radar-sweep"><path class="heavy" d="m130 105 51-51"/></g><circle cx="157" cy="77" r="6" class="ink-fill pulse-dot"/><circle cx="101" cy="135" r="4" class="ink-fill"/>',
      shield:'<path d="m130 25 70 26v50q0 55-70 87-70-32-70-87V51z"/><path d="m130 46 49 19v37q0 38-49 62-49-24-49-62V65z"/><path class="heavy" d="m103 102 19 19 38-44"/>',
      books:'<path d="M47 45h35v125H47zM90 30h38v140H90zM140 55l32-9 33 119-32 9zM35 182h190M47 67h35M90 54h38M156 124l32-9"/><circle cx="207" cy="46" r="22"/><path class="heavy" d="m223 62 18 18"/>',
      target:ring+'<path class="heavy" d="M83 153 177 57"/><circle cx="130" cy="105" r="8" class="ink-fill"/><path d="m165 57 12 0v12"/>',
      blueprint:'<path d="M58 28h145v155H58zM80 54h100v100H80zM80 90h100M130 54v100M35 28v155m-5-155h10m-10 155h10M58 199h145"/><circle cx="105" cy="123" r="13"/><path class="heavy" d="M151 109h17v30h-17z"/>',
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
    const plate=document.createElement('figure');plate.className='instrument-plate';plate.setAttribute('aria-hidden','true');
    plate.innerHTML=illustration(settings[2]);
    document.querySelector(".observatory-wordmark").textContent=settings[0];
    target.append(plate);
    const caption=document.createElement('div');caption.className='observatory-caption';
    caption.textContent=settings[1];
    target.after(caption);
    document.body.classList.remove('instrument-arrival');void document.body.offsetWidth;document.body.classList.add('instrument-arrival');
    clearTimeout(arrivalTimer);arrivalTimer=setTimeout(()=>document.body.classList.remove('instrument-arrival'),800);
    preferences();
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const dock=document.createElement('div');dock.className='observatory-controls';dock.setAttribute('aria-label','Atmosphere preferences');
    dock.innerHTML='<span class="observatory-wordmark"></span><div><button id="sound-switch" type="button" aria-pressed="false">♪ Sound off</button><button id="motion-switch" type="button" aria-pressed="true">Motion on</button></div>';
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
