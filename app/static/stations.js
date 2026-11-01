/* Saved stations are independent of speaker presets. Never autoplay on save. */
(function (root) {
  'use strict';
  function validStream(value) {
    try {
      const url = new URL(value);
      return ['http:', 'https:'].includes(url.protocol) && !!url.hostname && !url.username && !url.password && !url.search && !url.hash;
    } catch (_) { return false; }
  }
  function create(deps) {
    const doc = deps.document;
    const el = id => doc.getElementById(id);
    let generation = 0, controller = null, active = false, origin = 'hub';
    let stations = [], confirmation = null, writing = false, openMenu = null;
    let scheduleGeneration = 0, scheduleController = null;
    let testGeneration = 0, testController = null;
    let readinessGeneration = 0, readinessController = null;
    let draft = null, draftOperation = null, draftURL = null, draftStopped = false, draftBusy = false, draftPoll = null, radioSession = null, sessionPoll = null;
    const message = value => { el('stations-message').textContent = value; };
    function node(tag, value, className) {
      const item = doc.createElement(tag); item.textContent = value;
      if (className) item.className = className;
      return item;
    }
    function button(value, action, disabled) {
      const item = node('button', value, 'preset-action'); item.type = 'button'; item.disabled = !!disabled;
      item.addEventListener('click', action); return item;
    }
    function post(body) { return {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}; }
    async function request(url, options) {
      const deadline=new AbortController(),signal=options?.signal;
      const cancel=()=>deadline.abort();signal?.addEventListener('abort',cancel,{once:true});if(signal?.aborted)deadline.abort();
      let timedOut=false;const timeout=setTimeout(()=>{timedOut=true;deadline.abort();},45000);timeout.unref?.();
      try {
        const response = await deps.fetch(url, {...options,signal:deadline.signal});
        let body;
        try { body = await response.json(); } catch (_) { throw new Error('Wisp could not read the response.'); }
        if (!response.ok) throw new Error(body.error || body.message || 'The request could not be completed.');
        return body;
      } catch(error){if(timedOut)throw new Error('Request timed out. Check status before retrying a change.');throw error;}
      finally{clearTimeout(timeout);signal?.removeEventListener('abort',cancel);}
    }
    function clearConfirmation(restoreFocus = false) {
      testGeneration += 1; if (testController) testController.abort();
      el('stations-direct-risk').hidden = true; el('stations-accept-risk').checked = false;
      el('stations-listening-volume').hidden = true;
      const previous = confirmation; confirmation = null; el('stations-confirmation').hidden = true;
      if (restoreFocus && previous && previous.trigger && previous.trigger.isConnected) previous.trigger.focus();
    }
    function setBusy() {
      el('stations-add').disabled = writing || draftBusy || !draftStopped || !el('station-draft-audible').checked || draftURL!==el('station-url').value.trim();
      el('station-draft-test').disabled = writing || draftBusy;
      el('station-draft-stop').disabled = draftBusy;
      el('stations-refresh').disabled = writing;
      el('stations-speaker').disabled = writing;
      el('stations-confirm').disabled = writing || (confirmation?.kind === 'direct' && !el('stations-accept-risk').checked);
      if (confirmation?.kind === 'listen') el('stations-confirm').disabled = writing || listeningVolume() === null;
      el('stations-add-form').setAttribute('aria-busy', String(writing));
      render();
    }
    function closeMenu(restoreFocus = false) {
      if (!openMenu) return;
      const previous = openMenu; openMenu = null;
      previous.menu.hidden = true;
      previous.toggle.setAttribute('aria-expanded', 'false');
      if (restoreFocus) previous.toggle.focus();
    }
    function render() {
      // Refreshes and writes must not leave a detached menu or its focus behind.
      if (openMenu && openMenu.wrapper.contains(doc.activeElement)) el('stations-title').focus();
      closeMenu();
      const list = el('stations-list'); list.replaceChildren();
      if (!stations.length) list.append(node('p', 'No saved stations yet. Add a direct stream below.', 'preset-help'));
      stations.forEach((station, index) => {
        const card = node('article', '', 'station-card');
        card.append(node('h3', station.name), node('p', station.url, 'preset-help'));
        const speaker = el('stations-speaker').value;
        const actions = node('div', '', 'station-actions');
        actions.append(button('Play…', () => prompt('play', station), writing || !speaker));
        actions.append(button('Schedule…', () => {
          if (!active || writing || !el('stations-speaker').value) return;
          closeMenu();
          deps.schedule({...station}, el('stations-speaker').value);
        }, writing || !speaker));
        const wrapper = node('div', '', 'station-overflow');
        const menu = node('div', '', 'station-menu');
        menu.id = `station-menu-${index}`; menu.hidden = true;
        menu.setAttribute('role', 'menu');
        const toggle = button('⋯', () => {
          if (!active || writing) return;
          if (openMenu && openMenu.toggle === toggle) { closeMenu(true); return; }
          showMenu();
        }, writing);
        toggle.className += ' station-menu-toggle';
        toggle.id = `station-menu-toggle-${index}`;
        toggle.setAttribute('aria-label', `More actions for ${station.name}`);
        toggle.setAttribute('aria-haspopup', 'menu');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('aria-controls', menu.id);
        menu.setAttribute('aria-labelledby', toggle.id);
        function menuItem(label, action, disabled) {
          const item = button(label, () => {
            if (!active || writing || item.disabled || !openMenu || openMenu.toggle !== toggle) return;
            closeMenu(true); return action();
          }, disabled);
          item.setAttribute('role', 'menuitem'); item.tabIndex = -1;
          menu.append(item); return item;
        }
        const items = [
          menuItem('Test playback…', () => prompt('test', station), writing || !speaker),
          menuItem('Remove…', () => prompt('remove', station), writing),
        ];
        function showMenu(last = false) {
          closeMenu(); clearConfirmation();
          openMenu = {wrapper, menu, toggle}; menu.hidden = false;
          toggle.setAttribute('aria-expanded', 'true');
          const enabled = items.filter(item => !item.disabled);
          (last ? enabled[enabled.length - 1] : enabled[0]).focus();
        }
        toggle.addEventListener('keydown', event => {
          if (!active || writing || !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
          event.preventDefault(); showMenu(event.key === 'ArrowUp');
        });
        menu.addEventListener('keydown', event => {
          if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeMenu(true); return; }
          // Return to the trigger before native Tab navigation leaves the menu.
          if (event.key === 'Tab') { closeMenu(true); return; }
          if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          const enabled = items.filter(item => !item.disabled);
          const current = enabled.indexOf(doc.activeElement);
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? enabled.length - 1
            : (current + (event.key === 'ArrowDown' ? 1 : -1) + enabled.length) % enabled.length;
          enabled[next].focus();
        });
        wrapper.append(toggle, menu); actions.append(wrapper); card.append(actions); list.append(card);
      });
    }
    doc.addEventListener('pointerdown', event => {
      if (openMenu && !openMenu.wrapper.contains(event.target)) closeMenu(true);
    });
    doc.addEventListener('focusin', event => {
      if (openMenu && !openMenu.wrapper.contains(event.target)) closeMenu();
    });
    function listeningVolume() {
      const raw = el('stations-volume').value;
      const value = Number(raw);
      return raw !== '' && Number.isInteger(value) && value >= 0 && value <= 100 ? value : null;
    }
    async function listen(station) {
      if (!active || writing) return;
      const speaker = el('stations-speaker').value;
      if (!speaker) return;
      const trigger = doc.activeElement;
      clearConfirmation();
      const ticket = ++testGeneration;
      testController = new AbortController();
      const fresh = () => active && ticket === testGeneration && speaker === el('stations-speaker').value;
      message(`Checking ${speaker} for “${station.name}”…`);
      try {
        const options = await request(`/api/${encodeURIComponent(speaker)}/stations/${encodeURIComponent(station.id)}/listening-options`, {signal:testController.signal});
        if (!fresh()) return;
        if (options.available !== true || !options.speaker_id) {
          message(`${options.reason || 'Playback options could not be verified.'} No playback request was sent.`); return;
        }
        confirmation = {kind:'listen', station:{...station}, speaker, speaker_id:options.speaker_id, trigger};
        const volume = options.volume;
        el('stations-volume').value = Number.isInteger(volume) && volume >= 0 && volume <= 100 ? String(volume) : '';
        el('stations-volume-help').textContent = el('stations-volume').value === ''
          ? 'Current volume could not be read. Choose your listening volume.' : 'Current speaker volume. Adjust it before playing.';
        el('stations-confirm-text').textContent = `Play “${station.name}” on ${speaker}. ${options.requires_idle ? 'Stop current audio first. ' : 'This may replace current audio. '}${options.requires_wisp_running ? 'Keep Wisp running. ' : ''}Radio continues until stopped or the stream ends.`;
        el('stations-listening-volume').hidden = false;
        el('stations-confirm').textContent = 'Play radio';
        el('stations-confirm').disabled = listeningVolume() === null;
        el('stations-confirmation').hidden = false;
        message('Choose your listening volume, then Play radio.');
        el('stations-volume').focus();
      } catch (error) { if (fresh()) message(`${error.message} No playback request was sent.`); }
    }
    async function prompt(kind, station) {
      if (kind === 'play') return listen(station);
      if (writing || !active) return;
      const speaker = el('stations-speaker').value;
      if (kind === 'test' && !speaker) return;
      const trigger = doc.activeElement;
      clearConfirmation();
      let directInfo = null, readiness = null;
      if (kind === 'test') {
        const ticket = ++testGeneration;
        testController = new AbortController();
        const fresh = () => active && ticket === testGeneration && speaker === el('stations-speaker').value;
        message('Checking playback options. No audio has been started.');
        try {
          const overview = await request(`/api/${encodeURIComponent(speaker)}/stations/${encodeURIComponent(station.id)}/readiness`, {signal:testController.signal});
          if (!fresh()) return;
          readiness = overview;
          if (overview.available !== true) {
            // Only an explicitly unavailable native path may offer a different test.
            if (overview.available !== false) throw new Error('Playback options could not be confirmed. Refresh before testing.');
            directInfo = await request(`/api/${encodeURIComponent(speaker)}/stations/${encodeURIComponent(station.id)}/direct-test`, {signal:testController.signal});
            if (!fresh()) return;
            if (directInfo.available !== true || directInfo.experimental !== true || directInfo.quiet_start_guaranteed !== false || directInfo.duration_seconds !== 10 || directInfo.target_volume !== 5) {
              message(`${readiness.reason || 'This station cannot be tested with the current setup.'} No audio was started.`); return;
            }
            kind = 'direct';
          }
          if (kind === 'test') kind = 'quiet';
        } catch (error) { if (fresh()) message(`${error.message} No playback request was sent.`); return; }
      }
      confirmation = {kind, station: {...station}, speaker, trigger};
      el('stations-confirm-text').textContent = kind === 'direct'
        ? `Experimental test of “${station.name}” on ${speaker}. Audio may start at the speaker’s remembered volume before Wisp can lower it to 5. Keep physical Stop within reach. Wisp attempts to stop after 10 seconds; closing the app does not stop direct radio. Stop other controllers and schedules first. This does not enable speaker buttons or scheduled radio.`
        : kind === 'quiet'
        ? `Test “${station.name}” on ${speaker} at volume 5? ${readiness?.requires_idle ? 'Stop current audio first; playback requires an idle speaker. Wisp must remain running.' : 'This can replace current audio.'} Listen to check this station. Acceptance does not confirm sound.`
        : `Remove “${station.name}” from your station library? Existing presets, schedules and audio already playing stay intact. Station metadata is retained privately for existing playback and presets. You can add the stream again later.`;
      el('stations-confirm').textContent = kind === 'direct' ? 'Run experimental 10-second test' : kind === 'quiet' ? 'Test at volume 5' : 'Remove station';
      el('stations-direct-risk').hidden = kind !== 'direct';
      el('stations-confirm').disabled = kind === 'direct';
      el('stations-confirmation').hidden = false;
      message(kind === 'direct' ? 'Experimental option available; speaker support is checked when the test runs. No audio has been started.' : 'Review before confirming.');
      el(kind === 'direct' ? 'stations-accept-risk' : 'stations-confirm').focus();
    }
    async function refresh() {
      if (!active || writing) return;
      if (controller) controller.abort();
      controller = new AbortController(); const ticket = ++generation;
      if (openMenu && openMenu.wrapper.contains(doc.activeElement)) el('stations-title').focus();
      closeMenu(); clearConfirmation(); message('Loading stations…');
      try {
        const result = await request('/api/stations', {signal: controller.signal});
        if (!active || ticket !== generation) return;
        stations = result.stations || []; render(); message(result.seed_warning || `${stations.length} saved station${stations.length === 1 ? '' : 's'}. Saving is separate from playback and scheduling.`);
        return true;
      } catch (error) { if (active && ticket === generation) message(error.message); }
    }
    function open(from = 'hub') {
      origin = from; deps.navigate('stations'); active = true;
      el('stations-back-label').textContent = from === 'speaker' ? (deps.getSpeaker() || 'Speaker') : from === 'music' ? 'Music' : 'Speakers';
      const speakers = deps.getSpeakers(); const selected = deps.getSpeaker();
      const select = el('stations-speaker'); select.replaceChildren();
      const empty = node('option', 'Choose a speaker'); empty.value = ''; select.append(empty);
      speakers.forEach(speaker => { const option = node('option', speaker.name); option.value = speaker.name; select.append(option); });
      select.value = speakers.some(speaker => speaker.name === selected) ? selected : '';
      clearConfirmation(); setBusy(); el('stations-title').focus();
      if (writing) message('An earlier request is still finishing. Refresh after it finishes before making another change.');
      else return refresh();
    }
    function close() {
      closeMenu(); active = false; generation += 1; if (controller) controller.abort(); clearConfirmation();
      if (draftPoll) clearTimeout(draftPoll); if (sessionPoll) clearTimeout(sessionPoll);
    }
    async function add(event) {
      if (event) event.preventDefault();
      if (writing || !active) return;
      const name = el('station-name').value.trim(), url = el('station-url').value.trim();
      if (!name) { message('Give this station a name.'); el('station-name').focus(); return; }
      if (!validStream(url)) { message('Use a direct http or https stream without credentials, query parameters or a fragment.'); el('station-url').focus(); return; }
      if (!draft || draftURL !== url || !draftOperation || !draftStopped || !el('station-draft-audible').checked) { message('Test this URL, confirm hearing the intended station, and Stop before Save.'); return; }
      const ticket = ++generation;
      writing = true; setBusy(); message('Saving tested station.');
      try {
        await request(`/api/station-drafts/${encodeURIComponent(draft.id)}/save`, post({name,url,audible_confirmed:true,operation_id:draftOperation.operation_id}));
        if (active && ticket === generation) { el('station-name').value='';el('station-url').value='';resetDraft(); }
      } catch(error) { if(active && ticket===generation)message(`${error.message} Fields retained. Check the library before another save if the response was uncertain.`);return; }
      finally { writing=false;setBusy(); }
      if(active && ticket===generation && await refresh())message('Station saved. No playback or preset was changed.');
    }
    async function confirm() {
      if (!confirmation || writing || !active) return;
      if (confirmation.kind === 'direct' && !el('stations-accept-risk').checked) return;
      if (confirmation.kind === 'listen' && listeningVolume() === null) return;
      if (confirmation.kind === 'listen') confirmation.volume = listeningVolume();
      const chosen = confirmation; clearConfirmation();
      const ticket = ++generation; if (controller) controller.abort();
      writing = true; setBusy();
      try {
        const path = chosen.kind === 'direct'
          ? `/api/${encodeURIComponent(chosen.speaker)}/stations/${encodeURIComponent(chosen.station.id)}/direct-test`
          : chosen.kind === 'listen'
          ? `/api/${encodeURIComponent(chosen.speaker)}/stations/${encodeURIComponent(chosen.station.id)}/play`
          : chosen.kind === 'quiet'
          ? `/api/${encodeURIComponent(chosen.speaker)}/stations/${encodeURIComponent(chosen.station.id)}/test`
          : `/api/stations/${encodeURIComponent(chosen.station.id)}`;
        const options = post(chosen.kind === 'listen' ? {confirmed:true, volume:chosen.volume, speaker_id:chosen.speaker_id}
          : chosen.kind === 'direct' ? {confirmed: true, accept_startup_volume_risk: true} : {confirmed: true}); if (chosen.kind === 'remove') options.method = 'DELETE';
        // Writes deliberately survive navigation and are never retried automatically.
        const result = await request(path, options);
        if (!active || ticket !== generation) return;
        if (chosen.kind === 'remove') {
          stations = stations.filter(station => station.id !== chosen.station.id); render();
          message('Station removed from the library. Existing presets, schedules and current audio stay intact.');
        } else {
          message(chosen.kind === 'direct' ? 'Experimental test requested, not confirmed playing. Keep physical Stop within reach; closing this page does not stop radio.' : chosen.kind === 'listen' ? 'Radio requested. Waiting for speaker confirmation.' : 'Quiet playback requested. Listen to confirm sound; acceptance is not proof of playback.');
          radioSession={speaker:chosen.speaker,speaker_id:chosen.speaker_id || result.operation?.speaker_id,station:chosen.station,operation:result.operation,direct:chosen.kind==='direct'};
          renderSession();pollSessionSoon();
          if(deps.onPlay)deps.onPlay(result, chosen.speaker, {direct: chosen.kind === 'direct', listening:chosen.kind === 'listen'});
        }
      } catch (error) {
        if (active && ticket === generation) message(`${error.message} ${chosen.kind !== 'remove' ? 'Playback may have started. Check the speaker before retrying.' : 'Removal may have completed. Refresh before retrying.'}`);
      } finally {
        writing = false; setBusy();
        if (active && ticket !== generation) message('The earlier request finished. Refresh and check the speaker before another change.');
      }
    }
    async function checkScheduleReadiness() {
      if (readinessController) readinessController.abort();
      readinessController = new AbortController(); const ticket = ++readinessGeneration;
      const stationId = el('f-station').value, speaker = deps.getSpeaker();
      if (!stationId) { el('station-schedule-help').textContent = 'Choose a station. No speaker button is needed.'; return; }
      el('station-schedule-help').textContent = 'Checking this station’s setup…';
      try {
        const result = await request(`/api/${encodeURIComponent(speaker)}/stations/${encodeURIComponent(stationId)}/readiness`, {signal:readinessController.signal});
        if (ticket !== readinessGeneration || stationId !== el('f-station').value || speaker !== deps.getSpeaker()) return;
        el('station-schedule-help').textContent = result.available === true
          ? `Setup available. No speaker button is needed. ${result.requires_wisp_running ? 'Wisp must stay running and reachable by the speaker. ' : ''}Actual playback still needs verification.`
          : `Not ready: ${result.reason || 'The station’s setup could not be confirmed.'} Your selection is kept; an enabled schedule cannot be saved until setup is ready.`;
      } catch (_) {
        if (ticket === readinessGeneration) el('station-schedule-help').textContent = 'Could not check this station’s setup. Your selection is kept; saving will validate it again.';
      }
    }
    async function loadSchedule(initialId) {
      if (scheduleController) scheduleController.abort();
      scheduleController = new AbortController(); const ticket = ++scheduleGeneration;
      const select = el('f-station'); select.replaceChildren();
      const placeholder = () => { const option = node('option', 'Choose a station…'); option.value = ''; return option; };
      select.append(placeholder());
      if (initialId) { const option = node('option', 'Saved station · checking library…'); option.value = initialId; select.append(option); }
      select.value = initialId || ''; select.disabled = true;
      if (initialId) deps.clearFavorite();
      if (deps.onStationSelected) deps.onStationSelected(!!initialId);
      try {
        const result = await request('/api/stations', {signal: scheduleController.signal});
        if (ticket !== scheduleGeneration) return;
        const chosen = select.value; const available = result.stations || [];
        select.replaceChildren(placeholder());
        available.forEach(station => { const option = node('option', station.name); option.value = station.id; select.append(option); });
        if (chosen && !available.some(station => station.id === chosen)) {
          const option = node('option', 'Saved station removed from library · existing schedule binding retained'); option.value = chosen; select.append(option);
        }
        select.value = chosen;
        await checkScheduleReadiness();
      } catch (_) {
        if (ticket === scheduleGeneration) el('station-schedule-help').textContent = 'Station library could not be checked. Any existing station binding is retained. Retry before changing it.';
      } finally { if (ticket === scheduleGeneration) select.disabled = false; }
    }
    function resetDraft() {
      draft=null;draftURL=null;draftOperation=null;draftStopped=false;
      el('station-draft-audible').checked=false;el('station-draft-audible').disabled=true;
      el('station-draft-check').hidden=true;el('station-draft-stop').hidden=true;
      el('station-draft-status').textContent='Test before Save. Reported Playing is not proof of audible sound.';
      if(draftPoll)clearTimeout(draftPoll);setBusy();
    }
    function draftMessage(text){el('station-draft-status').textContent=text;}
    async function testDraft() {
      if(!active || writing || draftBusy)return;
      const name=el('station-name').value.trim(),url=el('station-url').value.trim(),speaker=el('stations-speaker').value;
      if(!name || !validStream(url)){draftMessage('Enter a name and valid direct stream URL.');return;}
      if(!speaker){draftMessage('Choose the test speaker above.');return;}
      if(draft && !draft.stopped_verified && !draft.retry_ready && !['untested','failed','canceled','skipped'].includes(draft.state)){draftMessage('Stop/check the previous test before another test.');return;}
      const originURL=url;draftBusy=true;setBusy();draftMessage(`Testing ${name} on ${speaker} at volume 5. This may replace current audio.`);
      try {
        const created=await request('/api/station-drafts',post({name,url}));
        draft=created.draft;draftURL=originURL;
        const target=deps.getSpeakers().find(item=>item.name===speaker);
        // Backend resolves/verifies identity authoritatively. Discovery may omit it;
        // read the existing discovery snapshot rather than infer an ID from the name.
        let speakerId=target?.device_id || target?.speaker_id;
        if(!speakerId){const observed=await request('/api/discover');const records=Array.isArray(observed)?observed:(observed.speakers || []);speakerId=records.find(item=>item.name===speaker)?.device_id;}
        if(!speakerId)throw new Error('Speaker identity unavailable. Refresh Speakers before testing.');
        draft.state='test_unknown';
        const result=await request(`/api/station-drafts/${encodeURIComponent(draft.id)}/test`,post({speaker,speaker_id:speakerId,confirmed:true}));
        draft={...draft,...result.draft,speaker,speaker_id:speakerId};draftOperation=result.operation;draftStopped=false;
        if(el('station-url').value.trim()!==originURL){draftMessage('URL changed while the test started. The previous URL may be playing; Stop this test before testing the edited URL.');}
        else draftMessage(`Test requested on ${speaker}. Waiting for matching playback; listen before confirming sound.`);
        el('station-draft-check').hidden=false;el('station-draft-stop').hidden=false;pollDraftSoon();
      } catch(error){draftMessage(`${error.message} Fields are retained. Playback may have started; Check test status before another request.`);if(draft){el('station-draft-check').hidden=false;el('station-draft-stop').hidden=false;}}
      finally{draftBusy=false;setBusy();}
    }
    function pollDraftSoon(){if(draftPoll)clearTimeout(draftPoll);if(active && draft && !draftStopped){draftPoll=setTimeout(checkDraft,1200);draftPoll.unref?.();}}
    async function checkDraft(){
      if(!active || !draft)return;const captured=draft;
      try {const result=await request(`/api/station-drafts/${encodeURIComponent(captured.id)}`);
        if(!active || draft!==captured)return;
        Object.assign(captured,result.draft || {});captured.state=result.draft?.state || captured.state;draftStopped=result.can_save===true;
        if(!draftOperation && captured.operation_id)draftOperation={operation_id:captured.operation_id};
        if(captured.observed_playing && draftURL===el('station-url').value.trim())el('station-draft-audible').disabled=false;
        const op=result.operation || {};const state=op.state || captured.state || 'unknown';
        if(state==='playing' && draftURL===el('station-url').value.trim())el('station-draft-audible').disabled=false;
        draftMessage(draftStopped?'Test stopped and confirmed. Confirm you heard the intended station, then Save.':`Test on ${captured.speaker}: ${state}${op.reason?' · '+op.reason:''}. ${state==='playing'?'Listen and confirm the intended sound, then Stop.':'Check before retrying; accepted work does not prove sound.'}`);
        el('station-draft-stop').hidden=draftStopped;setBusy();if(!draftStopped && !['failed','unknown','canceled','skipped'].includes(state))pollDraftSoon();
      }catch(error){if(draft===captured)draftMessage(`${error.message} Test outcome unknown. Check again; no automatic test retry.`);}
    }
    async function stopDraft(){
      if(!draft || !draftOperation || draftBusy)return;const captured=draft;draftBusy=true;setBusy();
      try{await request(`/api/station-drafts/${encodeURIComponent(captured.id)}/stop`,post({speaker_id:captured.speaker_id,operation_id:draftOperation.operation_id}));draftMessage('Stop accepted. Checking for confirmed stopped playback before Save.');await checkDraft();pollDraftSoon();}
      catch(error){draftMessage(`${error.message} Stop is unconfirmed; Save remains blocked. Check test status.`);}
      finally{draftBusy=false;setBusy();}
    }
    function renderSession(){if(!radioSession)return;const op=radioSession.operation || {};el('stations-session').hidden=false;el('stations-session-status').textContent=op.state==='playing'?`Playing ${radioSession.station.name} on ${radioSession.speaker}. Audibility not verified.`:`${radioSession.station.name} on ${radioSession.speaker}: ${op.state || 'accepted'}${op.reason?' · '+op.reason:''}`;el('stations-session-stop').disabled=radioSession.direct || !radioSession.speaker_id || !op.operation_id;}
    function pollSessionSoon(){if(sessionPoll)clearTimeout(sessionPoll);if(active && radioSession && !['completed','failed','canceled','skipped','replaced'].includes(radioSession.operation?.state)){sessionPoll=setTimeout(checkSession,1500);sessionPoll.unref?.();}}
    async function checkSession(){if(!active || !radioSession)return;const captured=radioSession;try{const result=await request(`/api/${encodeURIComponent(captured.speaker)}/operations`);if(!active || radioSession!==captured)return;const op=result.last_outcome || result.operation || result;if(op.operation_id===captured.operation?.operation_id)captured.operation=op;else if(op.operation_id)captured.operation={...captured.operation,state:'replaced',reason:'Another session is current; old Stop cannot stop it.'};renderSession();pollSessionSoon();}catch(error){if(active)message(`${error.message} Check playback before retrying.`);}}
    async function stopSession(){if(!radioSession || writing)return;const captured=radioSession;writing=true;setBusy();try{const result=await request(`/api/${encodeURIComponent(captured.speaker)}/stations/${encodeURIComponent(captured.station.id)}/stop`,post({speaker_id:captured.speaker_id,operation_id:captured.operation.operation_id}));captured.operation=result.operation;renderSession();pollSessionSoon();}catch(error){message(`${error.message} Stop unconfirmed; check current playback.`);}finally{writing=false;setBusy();}}
    el('station-draft-test').addEventListener('click',testDraft);
    el('station-draft-check').addEventListener('click',checkDraft);
    el('station-draft-stop').addEventListener('click',stopDraft);
    el('station-draft-audible').addEventListener('change',setBusy);
    el('station-url').addEventListener('input',()=>{el('station-draft-audible').checked=false;draftStopped=false;setBusy();draftMessage('URL changed. Save requires a test of this URL; Stop any previous test first.');});
    el('stations-session-check').addEventListener('click',checkSession);
    el('stations-session-stop').addEventListener('click',stopSession);

    el('btn-hub-stations').addEventListener('click', () => open('hub'));
    el('btn-speaker-stations').addEventListener('click', () => open('speaker'));
    el('btn-stations-back').addEventListener('click', () => { close(); deps.back(origin); });
    el('stations-refresh').addEventListener('click', refresh);
    el('stations-speaker').addEventListener('change', () => { clearConfirmation(); render(); });
    el('stations-add-form').addEventListener('submit', add);
    el('stations-confirm').addEventListener('click', confirm);
    el('stations-volume').addEventListener('input', () => {
      if (confirmation?.kind === 'listen') el('stations-confirm').disabled = writing || listeningVolume() === null;
    });
    el('stations-accept-risk').addEventListener('change', () => {
      el('stations-confirm').disabled = writing || (confirmation?.kind === 'direct' && !el('stations-accept-risk').checked);
    });
    el('stations-cancel').addEventListener('click', () => clearConfirmation(true));
    el('f-station').addEventListener('change', () => {
      if (el('f-station').value) deps.clearFavorite();
      if (deps.onStationSelected) deps.onStationSelected(!!el('f-station').value);
      return checkScheduleReadiness();
    });
    return {open, close, refresh, add, confirm, loadSchedule,testDraft,checkDraft,stopDraft,checkSession,stopSession,
      scheduleValue() { return el('f-station').value || null; },
      clearScheduleChoice() { el('f-station').value = ''; if (deps.onStationSelected) deps.onStationSelected(false); },
      onViewChange(view) {
        if (view !== 'stations') close();
        if (view !== 'form') { readinessGeneration += 1; if (readinessController) readinessController.abort(); scheduleGeneration += 1; if (scheduleController) scheduleController.abort(); }
      },
    };
  }
  root.WispStationUI = {create, validStream};
  if (typeof module !== 'undefined' && module.exports) module.exports = root.WispStationUI;
})(typeof window !== 'undefined' ? window : globalThis);
