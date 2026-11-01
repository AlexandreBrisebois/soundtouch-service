/* Shared library inspection. Rows inspect; actions are deliberate and target-verified. */
(function (root) {
  'use strict';
  function create(deps) {
    const doc = deps.document, el = id => doc.getElementById(id);
    let active = false, generation = 0, readController = null, writing = false;
    let libraries = [], speakers = [], library = null, frames = [], action = null, session = null;
    let changingSchedule = false, pollTimer = null;
    const message = value => { el('music-message').textContent = value; };
    const node = (tag, value, cls) => { const e = doc.createElement(tag); e.textContent = value || ''; if (cls) e.className = cls; return e; };
    function button(label, handler, disabled) { const e = node('button',label,'preset-action'); e.type='button';e.disabled=!!disabled;e.addEventListener('click',handler);return e; }
    const post = value => ({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
    async function request(path,options={}) {
      const deadline=new AbortController(), signal=options.signal;
      const cancel=()=>deadline.abort();signal?.addEventListener('abort',cancel,{once:true});if(signal?.aborted)deadline.abort();
      let timedOut=false;const timeout=setTimeout(()=>{timedOut=true;deadline.abort();},45000);timeout.unref?.();
      try {
        const response = await deps.fetch(path,{...options,signal:deadline.signal}); let result;
        try { result=await response.json(); } catch (_) { throw new Error('The response could not be read. Check Again before retrying a change.'); }
        if(!response.ok) throw new Error(result.error || result.message || Object.values(result.errors || {}).join(' ') || 'This action could not be completed.');
        return result;
      } catch(error) {if(timedOut)throw new Error('Request timed out. Check Again before retrying any change.');throw error;}
      finally {clearTimeout(timeout);signal?.removeEventListener('abort',cancel);}
    }
    function ticket() { if(readController)readController.abort();readController=new AbortController();return {id:++generation,signal:readController.signal}; }
    const current = t => active && t.id===generation && !t.signal.aborted;
    function choices(select,selected) {
      select.replaceChildren(); const empty=node('option','Choose a speaker');empty.value='';select.append(empty);
      (speakers.length?speakers:deps.getSpeakers()).forEach(s=>{const item=node('option',s.name);item.value=s.name;select.append(item);});
      select.value=selected || '';
    }
    const targetRecord = name => speakers.find(s=>s.name===name) || deps.getSpeakers().find(s=>s.name===name);
    function setBusy(value) {
      writing=value;el('music-review-confirm').disabled=value;el('music-target').disabled=value;el('music-slot').disabled=value;
      ['music-add-library','music-search-again','music-play','music-schedule','music-assign'].forEach(id=>{el(id).disabled=value;});
      if(!value) renderActions();
      el('music-review').setAttribute('aria-busy',String(value));
    }
    function renderLibraries() {
      const list=el('music-library-list');list.replaceChildren();
      const added=libraries.filter(item=>item.added);
      if(!added.length)list.append(node('p','No added libraries. Add Library asks your speakers what they can see.','preset-help'));
      added.forEach(item=>{
        const card=node('article','','music-library-card');card.append(node('h2',item.name));
        if(item.reconciliation_pending?.length)card.append(node('p','Removal propagation is still being checked. Use Check Again.','preset-help'));
        Object.values(item.observations || {}).forEach(obs=>card.append(node('p',`${obs.speaker}: ${stateLabel(obs.state)}${obs.reason?' · '+obs.reason:''}`,'preset-help')));
        const ready=Object.values(item.observations || {}).some(obs=>obs.state==='ready');
        card.append(button('Browse',()=>openLibrary(item),!ready),button('Check Again',()=>checkLibrary(item)));
        const menu=doc.createElement('details');menu.append(node('summary','More'));
        menu.append(button('Add Again',()=>startLibraryAction('add',item)),button('Remove from speaker',()=>startLibraryAction('remove',item)));
        card.append(menu);list.append(card);
      });
    }
    function scheduleImpactText(items) {
      const labels=(Array.isArray(items)?items:[]).map(item=>typeof item==='string'?item:`${item.name || 'Routine'}${item.speaker?' on '+item.speaker:''}`);
      return labels.length?labels.join('; '):'None known';
    }
    function buttonImpactText(items) {
      const labels=(Array.isArray(items)?items:[]).map(item=>`Button ${item.slot}: ${item.name || 'Unknown content'}${item.speaker?' on '+item.speaker:''}`);
      return labels.length?labels.join('; '):'None known';
    }
    function stateLabel(state) { return ({ready:'Ready',unavailable:'Added, Unavailable',not_registered:'Not registered',unknown:'Unknown — Check Again'})[state] || 'Unknown'; }
    async function refresh(discover=false) {
      if(!active || writing)return;const t=ticket();message(discover?'Searching through your speakers.':'Reading added libraries.');
      try {
        const result=await request('/api/music-libraries'+(discover?'/discover':''),discover?{...post({}),signal:t.signal}:{signal:t.signal});
        if(!current(t))return;libraries=result.libraries || [];speakers=result.speakers || deps.getSpeakers();renderLibraries();
        if(discover)renderDiscovery(result);
        message(result.errors?.length ? `Some speaker reads failed: ${result.errors.map(e=>e.speaker+': '+e.reason).join('; ')}. Search Again or check the speaker's music service and network.` : discover ? result.guidance || 'Choose a library and speaker. Discovery has not registered anything.' : 'Libraries are shared. Each action verifies access on its chosen speaker.');
      } catch(error) { if(current(t))message(`${error.message} ${discover?'Search Again and check the NAS music service and network.':'Check Again; retained libraries have not been deleted.'}`); }
    }
    function renderDiscovery(result) {
      el('music-discovery').hidden=false;const list=el('music-discovered');list.replaceChildren();
      const found=result.discovered ? libraries.filter(item=>result.discovered.includes(item.id)) : libraries;
      if(!found.length)list.append(node('p','No music server found. Search Again; check that its DLNA/music service is enabled and shares the speaker network.','preset-help'));
      found.forEach(item=>{
        const card=node('article','','music-library-card');card.append(node('strong',item.name));
        const visible=item.visible_to || item.speakers || [];
        card.append(node('p',visible.length?'Visible to: '+visible.map(s=>typeof s==='string'?s:s.name).join(', '):'Speaker visibility is shown in discovery observations.','preset-help'));
        card.append(button('Add Library',()=>startLibraryAction('add',item)));list.append(card);
      });
    }
    async function checkLibrary(item) {
      if(writing)return;const t=ticket();message('Checking availability.');
      try {const result=await request(`/api/music-libraries/${encodeURIComponent(item.id)}/check`,{...post({}),signal:t.signal});if(!current(t))return;
        if(result.library){libraries=libraries.map(old=>old.id===item.id?result.library:old);if(library?.id===item.id)library=result.library;}renderLibraries();
        if(action?.library?.id===item.id){action.library=result.library || item;action.checked=true;action.retryAllowed=result.retry_allowed===true; if(action.retryAllowed){action.stage='choose';el('music-review-confirm').textContent=action.kind==='add'?'Retry Add Library':'Review removal';} else if(action.kind==='add' && Object.values(result.library?.observations || {}).some(obs=>obs.speaker===action.speaker && ['ready','unavailable'].includes(obs.state))){hideReview();}}
        message(result.message || 'Availability reread. Missing registrations require explicit Add Again; review-paused schedules stay paused.');
      }catch(error){if(current(t))message(error.message);}
    }
    function startLibraryAction(kind,item) {
      if(writing)return;action={kind,library:item,stage:'choose'};showReview(`${kind==='add'?'Add Library':'Remove registration'}: ${item.name}`);
      el('music-review-text').textContent=kind==='add'?'Choose the speaker to register this library on. No playback or button changes.':'Choose a speaker to review known schedule/button impacts. Firmware may propagate removal. No music files are deleted.';
      el('music-review-confirm').textContent=kind==='add'?'Add Library':'Review removal';
    }
    function showReview(title) {
      el('music-review').hidden=false;el('music-review-title').textContent=title;
      choices(el('music-target'),action?.speaker || deps.getSpeaker());el('music-slots').hidden=true;el('music-volume-field').hidden=true;
      el('music-review-confirm').disabled=false;el('music-review').scrollIntoView?.({block:'nearest'});el('music-target').focus();
    }
    function hideReview() {action=null;el('music-review').hidden=true;renderActions();}
    async function openLibrary(item) {
      library=item;frames=[];el('music-browser').hidden=false;el('music-discovery').hidden=true;el('music-library-list').hidden=true;
      hideReview();await browse(null,false);
    }
    function selectedFrame(){return frames[frames.length-1];}
    function savePosition(){const frame=selectedFrame();if(frame)frame.scroll=el('music-body').scrollTop || 0;}
    async function browse(item,append=false) {
      if(!library || writing)return;
      savePosition();const prior=selectedFrame();
      const frame=append?prior:{item,items:[],next:null,scroll:0,speaker:prior?.speaker || null,preview:false};
      const t=ticket();message('Loading collection contents.');el('music-retry').hidden=true;
      try {
        const result=await request('/api/collections/browse',{...post({library_id:library.id,speaker:frame.speaker || undefined,container_id:item?.id,start:append?frame.next:1}),signal:t.signal});
        if(!current(t))return;
        if(!append)frames.push(frame);
        frame.speaker=result.speaker || frame.speaker;frame.preview=result.preview_unavailable===true;frame.previewError=result.preview_error;frame.items.push(...(result.items || []));frame.next=result.next_start;
        renderFrame(frame);if(!append)el('music-body').scrollTop=0;else el('music-body').scrollTop=frame.scroll;
        if(frame.previewError){el('music-retry').hidden=false;el('music-retry').onclick=()=>{if(selectedFrame()===frame)frames.pop();browse(item,false);};}
        message(frame.preview?(frame.previewError?`Preview unavailable: ${frame.previewError}. Retry or use supported collection actions.`:'Preview unavailable. Supported collection actions remain available.'):frame.items.length?'Tap a row to inspect. Playback order remains supplied by the music source.':'Empty collection.');
      }catch(error){if(current(t)){if(!append && item?.type==='playlist' && item.playable){frame.preview=true;frame.previewError=error.message;frames.push(frame);renderFrame(frame);message(`Preview unavailable: ${error.message}. Retry or use supported collection actions.`);}else message(`${error.message} Retry keeps your collection and loaded rows.`);el('music-retry').hidden=false;el('music-retry').onclick=()=>{if(frame.previewError && selectedFrame()===frame)frames.pop();return browse(item,append);};}}
    }
    function renderFrame(frame) {
      const list=el('music-items');list.replaceChildren();el('music-browser').hidden=false;
      el('music-path').textContent=[library.name,...frames.map(f=>f.item?.name).filter(Boolean)].join(' / ');
      el('music-collection-name').textContent=frame.item?.name || library.name;
      if(frame.preview)list.append(node('p','Preview unavailable','preset-help'));
      else if(!frame.items.length)list.append(node('p','Empty','preset-help'));
      frame.items.forEach(item=>{
        const label=(item.type==='playlist'?'♫ ':item.is_collection || item.is_dir?'▸ ':'♪ ')+item.name;
        const row=button(label,()=>inspect(item));row.className='music-row';list.append(row);
      });
      el('music-more').hidden=!frame.next;el('music-more').onclick=()=>browse(frame.item,true);
      el('music-back').textContent=frames.length>1?'Back':'Music Libraries';renderActions();
    }
    async function inspect(item) {
      if(item.is_collection || item.is_dir || item.type==='playlist') {
        if(item.preview_available===false){savePosition();const frame={item,items:[],next:null,scroll:0,speaker:selectedFrame()?.speaker,preview:true};frames.push(frame);renderFrame(frame);message('Preview unavailable. Supported collection actions remain available.');}
        else await browse(item);
      }else {message(`${item.name}. Track information only; individual track actions are deferred.`);}
    }
    function back() {
      savePosition();hideReview();
      if(frames.length>1){frames.pop();const frame=selectedFrame();renderFrame(frame);el('music-body').scrollTop=frame.scroll;}
      else {frames=[];library=null;el('music-browser').hidden=true;el('music-library-list').hidden=false;renderActions();}
    }
    function renderActions() {
      const item=selectedFrame()?.item,available=!!item && (item.is_collection || item.is_dir || item.type==='playlist');
      el('music-actions').hidden=!active || !available;el('music-body').classList.toggle('has-collection',active && available);
      el('music-actions-label').textContent=item?.name || '';
      el('music-play').disabled=writing || !item?.playable;el('music-schedule').disabled=writing || !item?.playable;el('music-assign').disabled=writing || !item?.playable || !item?.presetable;
      el('music-actions-help').textContent=!item?.playable?'This collection is not marked playable.':!item?.presetable?'Play and Schedule available. This collection cannot be assigned to a speaker button.':'';
    }
    function startCollectionAction(kind) {
      if(writing)return;const frame=selectedFrame();if(!frame?.item)return;
      savePosition();action={kind,item:frame.item,library,speaker:deps.getSpeaker(),stage:'choose'};
      showReview(`${kind==='play'?'Play':kind==='schedule'?'Schedule':'Assign'}: ${frame.item.name}`);
      el('music-review-text').textContent=`${library.name} / ${frame.item.name}. Choose a speaker; access will be verified before continuing.`;
      el('music-review-confirm').textContent='Verify access';
    }
    function invalidateAction(){if(!action || writing)return;action.checked=false;action.retryAllowed=false;action.speaker=el('music-target').value;action.stage='choose';action.resolved=null;action.plan=null;el('music-slots').hidden=true;el('music-volume-field').hidden=true;el('music-review-confirm').textContent=action.kind==='add'?'Add Library':action.kind==='remove'?'Review removal':'Verify access';}
    async function confirmAction() {
      if(!action || writing)return;const chosen=action,speaker=el('music-target').value;
      if(!speaker){message('Choose a speaker.');return;}chosen.speaker=speaker;
      const rec=targetRecord(speaker),speaker_id=rec?.device_id || rec?.speaker_id;
      if(!speaker_id && ['add','remove'].includes(chosen.kind)){message('Speaker identity is unavailable. Refresh Speakers before changing a registration.');return;}
      setBusy(true);const origin=generation;
      try {
        if(chosen.kind==='add') {
          if(chosen.unknown && !chosen.checked)throw new Error('Check Again before another registration attempt.');
          message('Adding. Checking availability.');
          const result=await request(`/api/music-libraries/${encodeURIComponent(chosen.library.id)}/add`,post({speaker,speaker_id,confirmed:true,...(chosen.checked?{retry:true}:{})}));
          if(!active || action!==chosen)return;
          message(result.message || stateLabel(result.state));
          if(result.library){libraries=libraries.filter(i=>i.id!==result.library.id);libraries.push(result.library);renderLibraries();}
          if(result.state==='unknown'){chosen.unknown=true;chosen.checked=false;el('music-review-confirm').textContent='Check Again';el('music-review-confirm').onclick=null;chosen.stage='check';}
          else if(result.state==='not_registered'){chosen.checked=true;chosen.retryAllowed=result.retry_allowed===true;el('music-review-confirm').textContent=result.retry_allowed?'Retry Add Library':'Check Again';chosen.stage=result.retry_allowed?'choose':'check';}
          else hideReview();
        }else if(chosen.kind==='remove') {
          if(chosen.stage==='choose') {
            const result=await request(`/api/music-libraries/${encodeURIComponent(chosen.library.id)}/removal-plan`,post({speaker,speaker_id}));
            if(!active || action!==chosen)return;chosen.plan=result;chosen.stage='confirm';
            el('music-review-text').textContent=`${chosen.library.name} on ${speaker}. ${result.warning || 'Removal may propagate. No music files are deleted.'} Schedules: ${scheduleImpactText(result.impacts)}. Buttons: ${buttonImpactText(result.buttons)}. ${result.unknown_impacts?.length?'Some speaker impacts are unknown. Check unavailable speakers before deciding.':''}`;
            el('music-review-confirm').textContent='Remove from speaker';
          }else if(chosen.stage==='check'){await checkLibrary(chosen.library);}
          else {
            const result=await request(`/api/music-libraries/${encodeURIComponent(chosen.library.id)}/remove`,post({plan_id:chosen.plan.plan_id,confirmed:true,...(chosen.checked && chosen.retryAllowed ? {retry:true} : {})}));
            if(!active || action!==chosen)return;message(result.message || stateLabel(result.state));
            if(result.state==='unknown'){chosen.stage='check';el('music-review-confirm').textContent='Check Again';}
            else {if(result.library){libraries=libraries.map(item=>item.id===result.library.id?result.library:item);renderLibraries();}hideReview();}
          }
        }else if(chosen.stage==='choose') {
          const result=await request('/api/collections/resolve',post({speaker,library_id:chosen.library.id,item_id:chosen.item.id}));
          if(!active || action!==chosen)return;chosen.resolved=result;
          if(chosen.kind==='schedule'){hideReview();deps.schedule(result.collection,speaker);return;}
          if(chosen.kind==='play') {
            chosen.stage='play';el('music-volume-field').hidden=false;
            el('music-review-text').textContent=`Play ${chosen.item.name} from ${chosen.library.name} on ${speaker}? This replaces current playback. Choose volume before Play.`;
            el('music-review-confirm').textContent='Play';
          }else {
            let presets=result.presets;
            if(!presets)presets=(await request(`/api/${encodeURIComponent(speaker)}/favorites`)).presets;
            if(!active || action!==chosen)return;const select=el('music-slot');select.replaceChildren();
            for(let slot=1;slot<=6;slot++){const preset=(presets || []).find(p=>p.slot===slot);const option=node('option',`Button ${slot}: ${preset?.name || 'Empty'}`);option.value=String(slot);select.append(option);}
            el('music-slots').hidden=false;chosen.stage='slot';el('music-review-confirm').textContent='Review assignment';
          }
        }else if(chosen.kind==='play') {
          const raw=el('music-volume').value,volume=Number(raw);if(raw==='' || !Number.isInteger(volume) || volume<0 || volume>100)throw new Error('Choose a volume from 0 through 100.');
          const result=await request(`/api/${encodeURIComponent(speaker)}/collections/play`,post({collection:chosen.resolved.collection,speaker_id:chosen.resolved.speaker_id,volume,confirmed:true}));
          session={speaker,speaker_id:chosen.resolved.speaker_id,operation:result.operation,name:chosen.item.name};hideReview();renderSession();schedulePoll();
        }else if(chosen.stage==='slot') {
          const result=await request(`/api/${encodeURIComponent(speaker)}/preset-plans`,post({item_id:chosen.resolved.browse_item_id,name:chosen.item.name,slot:Number(el('music-slot').value)}));
          if(!active || action!==chosen)return;chosen.plan=result;chosen.stage='assign';
          el('music-review-text').textContent=`${chosen.item.name} · ${chosen.library.name} · ${speaker} · Button ${result.slot}. Current: ${result.replaces || 'Empty'}. ${result.warning || ''} Affected schedules: ${scheduleImpactText(result.schedule_impacts || result.impacts || result.affected_schedules)}. Assignment does not start music.`;
          el('music-review-confirm').textContent=result.replaces && result.replaces!=='Empty'?`Replace Button ${result.slot}`:'Assign';
        }else {
          const result=await request(`/api/${encodeURIComponent(speaker)}/preset-plans/${encodeURIComponent(chosen.plan.plan_id)}/confirm`,post({confirmed:true}));
          if(!active || action!==chosen)return;message(result.state==='readback_matched'?`Button ${chosen.plan.slot} now contains ${chosen.item.name} on ${speaker}. Whole-map readback matched. No playback was started. Choose Play for a separate Play now action.`:result.message || 'Assignment outcome unknown. Check speaker readback before another write.');hideReview();
        }
      }catch(error){if(active && action===chosen){if(chosen.kind==='add' || (chosen.kind==='remove' && chosen.stage==='confirm')){chosen.unknown=true;chosen.checked=false;chosen.stage='check';el('music-review-confirm').textContent='Check Again';}else if(chosen.kind==='assign' && chosen.stage==='assign'){chosen.stage='choose';chosen.plan=null;el('music-review-confirm').textContent='Verify access';}message(`${error.message} Your selection is kept. Check readback before retrying any uncertain write; no automatic speaker switch is made.`);}}
      finally{setBusy(false);if(!active || origin!==generation)renderActions();}
    }
    function renderSession(){if(!session)return;el('music-session').hidden=false;const op=session.operation || {};el('music-session-status').textContent=op.state==='playing'?`Playing ${session.name} on ${session.speaker}. Audible sound is not verified.`:`${session.name} on ${session.speaker}: ${op.state || 'accepted'}${op.reason?' · '+op.reason:''}`;}
    function schedulePoll(){if(pollTimer)clearTimeout(pollTimer);if(active && session && !['failed','completed','canceled','skipped','replaced'].includes(session.operation?.state)){pollTimer=setTimeout(checkSession,1500);pollTimer.unref?.();}}
    async function checkSession(){if(!active || !session)return;const captured=session;try{const result=await request(`/api/${encodeURIComponent(captured.speaker)}/collections/status`);if(active && session===captured){if(result.operation?.operation_id===captured.operation?.operation_id)captured.operation=result.operation;else if(result.operation){captured.operation={...captured.operation,state:'replaced',reason:'Another session is current. Old Stop cannot stop it.'};}renderSession();schedulePoll();}}catch(error){if(active)message(error.message);}}
    async function stopSession(){if(!session || writing)return;const captured=session;setBusy(true);try{const result=await request(`/api/${encodeURIComponent(captured.speaker)}/collections/stop`,post({speaker_id:captured.speaker_id,operation_id:captured.operation.operation_id}));if(session===captured){captured.operation=result.operation;renderSession();schedulePoll();}}catch(error){message(`${error.message} Check playback before another request.`);}finally{setBusy(false);}}
    async function open(change=false){active=true;changingSchedule=change;deps.navigate('music');el('music-return-form').hidden=!change;el('music-title').focus();renderActions();if(!libraries.length)await refresh();else renderLibraries();}
    el('music-radio').addEventListener('click',()=>deps.radio());el('music-libraries').addEventListener('click',()=>{backToLibraries();refresh();});
    function backToLibraries(){frames=[];library=null;el('music-browser').hidden=true;el('music-library-list').hidden=false;renderActions();}
    el('music-add-library').addEventListener('click',()=>refresh(true));el('music-search-again').addEventListener('click',()=>refresh(true));
    el('music-back').addEventListener('click',back);el('music-play').addEventListener('click',()=>startCollectionAction('play'));el('music-schedule').addEventListener('click',()=>startCollectionAction('schedule'));el('music-assign').addEventListener('click',()=>startCollectionAction('assign'));
    el('music-review-confirm').addEventListener('click',()=>action?.stage==='check'?checkLibrary(action.library):confirmAction());
    el('music-review-cancel').addEventListener('click',()=>{hideReview();const frame=selectedFrame();if(frame)el('music-body').scrollTop=frame.scroll;});
    el('music-target').addEventListener('change',invalidateAction);el('music-slot').addEventListener('change',()=>{if(!writing && action?.kind==='assign'){action.stage='slot';action.plan=null;el('music-review-confirm').textContent='Review assignment';}});
    el('music-session-check').addEventListener('click',checkSession);el('music-session-stop').addEventListener('click',stopSession);
    el('music-return-form').addEventListener('click',()=>{changingSchedule=false;deps.cancelSchedule();});
    return {open,refresh,browse,inspect,back,startCollectionAction,confirmAction,checkSession,stopSession,libraryName(id){return libraries.find(item=>item.id===id)?.name || null;},
      onViewChange(name){active=name==='music';if(!active){savePosition();generation++;if(readController)readController.abort();if(pollTimer)clearTimeout(pollTimer);}renderActions();},
      state(){return {frames,libraries,action,session,changingSchedule};},stateLabel};
  }
  root.WispMusicUI={create};if(typeof module!=='undefined' && module.exports)module.exports=root.WispMusicUI;
})(typeof window!=='undefined'?window:globalThis);
