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
    let stations = [], confirmation = null, writing = false;
    let scheduleGeneration = 0, scheduleController = null;
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
      const response = await deps.fetch(url, options);
      let body;
      try { body = await response.json(); } catch (_) { throw new Error('Wisp could not read the response.'); }
      if (!response.ok) throw new Error(body.error || body.message || 'The request could not be completed.');
      return body;
    }
    function clearConfirmation() { confirmation = null; el('stations-confirmation').hidden = true; }
    function setBusy() {
      el('stations-add').disabled = writing;
      el('stations-refresh').disabled = writing;
      el('stations-speaker').disabled = writing;
      el('stations-confirm').disabled = writing;
      el('stations-add-form').setAttribute('aria-busy', String(writing));
      render();
    }
    function render() {
      const list = el('stations-list'); list.replaceChildren();
      if (!stations.length) list.append(node('p', 'No saved stations yet. Add a direct stream below.', 'preset-help'));
      stations.forEach(station => {
        const card = node('article', '', 'station-card');
        card.append(node('h3', station.name), node('p', station.url, 'preset-help'));
        const speaker = el('stations-speaker').value;
        card.append(button('Play…', () => prompt('play', station), writing || !speaker));
        card.append(button('Set to a preset…', () => {
          if (writing || !el('stations-speaker').value) return;
          deps.assign({...station}, el('stations-speaker').value);
        }, writing || !speaker));
        card.append(button('Schedule…', () => {
          if (writing || !el('stations-speaker').value) return;
          deps.schedule({...station}, el('stations-speaker').value);
        }, writing || !speaker));
        card.append(button('Remove…', () => prompt('remove', station), writing));
        list.append(card);
      });
    }
    function prompt(kind, station) {
      if (writing || !active) return;
      const speaker = el('stations-speaker').value;
      if (kind === 'play' && !speaker) return;
      confirmation = {kind, station: {...station}, speaker};
      el('stations-confirm-text').textContent = kind === 'play'
        ? `Play “${station.name}” on ${speaker} at volume 5? This can replace current audio. A listening check is still needed; acceptance does not confirm sound.`
        : `Remove “${station.name}” from your station library? Existing presets, schedules and audio already playing stay intact. Station metadata is retained privately for existing playback and presets. You can add the stream again later.`;
      el('stations-confirm').textContent = kind === 'play' ? 'Play at volume 5' : 'Remove station';
      el('stations-confirmation').hidden = false;
      el('stations-confirm').focus();
    }
    async function refresh() {
      if (!active || writing) return;
      if (controller) controller.abort();
      controller = new AbortController(); const ticket = ++generation;
      clearConfirmation(); message('Loading stations…');
      try {
        const result = await request('/api/stations', {signal: controller.signal});
        if (!active || ticket !== generation) return;
        stations = result.stations || []; render(); message(result.seed_warning || `${stations.length} saved station${stations.length === 1 ? '' : 's'}. Saving is separate from assigning a speaker button.`);
        return true;
      } catch (error) { if (active && ticket === generation) message(error.message); }
    }
    function open(from = 'hub') {
      origin = from; deps.navigate('stations'); active = true;
      el('stations-back-label').textContent = from === 'speaker' ? (deps.getSpeaker() || 'Speaker') : 'Speakers';
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
      active = false; generation += 1; if (controller) controller.abort(); clearConfirmation();
    }
    async function add(event) {
      if (event) event.preventDefault();
      if (writing || !active) return;
      const name = el('station-name').value.trim(), url = el('station-url').value.trim();
      if (!name) { message('Give this station a name.'); el('station-name').focus(); return; }
      if (!validStream(url)) { message('Use a direct http or https stream without credentials, query parameters or a fragment.'); el('station-url').focus(); return; }
      const ticket = ++generation;
      if (controller) controller.abort();
      clearConfirmation(); writing = true; setBusy(); message('Saving station…');
      try {
        await request('/api/stations', post({name, url}));
        if (active && ticket === generation) { el('station-name').value = ''; el('station-url').value = ''; }
      } catch (error) {
        if (active && ticket === generation) message(`${error.message} Refresh the library before retrying; the station may have been saved.`);
        return;
      } finally {
        writing = false; setBusy();
        if (active && ticket !== generation) message('The earlier save finished. Refresh to check your station library before retrying.');
      }
      if (active && ticket === generation) {
        if (await refresh()) message('Station saved. No playback or preset was changed.');
      }
      else if (active) message('The earlier save finished. Refresh to check your station library.');
    }
    async function confirm() {
      if (!confirmation || writing || !active) return;
      const chosen = confirmation; clearConfirmation();
      const ticket = ++generation; if (controller) controller.abort();
      writing = true; setBusy();
      try {
        const path = chosen.kind === 'play'
          ? `/api/${encodeURIComponent(chosen.speaker)}/stations/${encodeURIComponent(chosen.station.id)}/play`
          : `/api/stations/${encodeURIComponent(chosen.station.id)}`;
        const options = post({confirmed: true}); if (chosen.kind === 'remove') options.method = 'DELETE';
        // Writes deliberately survive navigation and are never retried automatically.
        const result = await request(path, options);
        if (!active || ticket !== generation) return;
        if (chosen.kind === 'remove') {
          stations = stations.filter(station => station.id !== chosen.station.id); render();
          message('Station removed from the library. Existing presets, schedules and current audio stay intact.');
        } else {
          message('Quiet playback requested. Listen to confirm sound; acceptance is not proof of playback.');
          deps.onPlay(result, chosen.speaker);
        }
      } catch (error) {
        if (active && ticket === generation) message(`${error.message} ${chosen.kind === 'play' ? 'Playback may have started. Check the speaker before retrying.' : 'Removal may have completed. Refresh before retrying.'}`);
      } finally {
        writing = false; setBusy();
        if (active && ticket !== generation) message('The earlier request finished. Refresh and check the speaker before another change.');
      }
    }
    async function loadSchedule(initialId) {
      if (scheduleController) scheduleController.abort();
      scheduleController = new AbortController(); const ticket = ++scheduleGeneration;
      const select = el('f-station'); select.replaceChildren();
      const placeholder = () => { const option = node('option', 'Use a favorite, numbered preset or AUX'); option.value = ''; return option; };
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
        el('station-schedule-help').textContent = 'This station plays directly, without occupying a speaker button. Wisp must stay available.';
      } catch (_) {
        if (ticket === scheduleGeneration) el('station-schedule-help').textContent = 'Station library could not be checked. Any existing station binding is retained. Retry before changing it.';
      } finally { if (ticket === scheduleGeneration) select.disabled = false; }
    }
    el('btn-hub-stations').addEventListener('click', () => open('hub'));
    el('btn-speaker-stations').addEventListener('click', () => open('speaker'));
    el('btn-stations-back').addEventListener('click', () => { close(); deps.back(origin); });
    el('stations-refresh').addEventListener('click', refresh);
    el('stations-speaker').addEventListener('change', () => { clearConfirmation(); render(); });
    el('stations-add-form').addEventListener('submit', add);
    el('stations-confirm').addEventListener('click', confirm);
    el('stations-cancel').addEventListener('click', clearConfirmation);
    el('f-station').addEventListener('change', () => {
      if (el('f-station').value) deps.clearFavorite();
      if (deps.onStationSelected) deps.onStationSelected(!!el('f-station').value);
    });
    return {open, close, refresh, add, confirm, loadSchedule,
      scheduleValue() { return el('f-station').value || null; },
      clearScheduleChoice() { el('f-station').value = ''; if (deps.onStationSelected) deps.onStationSelected(false); },
      onViewChange(view) {
        if (view !== 'stations') close();
        if (view !== 'form') { scheduleGeneration += 1; if (scheduleController) scheduleController.abort(); }
      },
    };
  }
  root.WispStationUI = {create, validStream};
  if (typeof module !== 'undefined' && module.exports) module.exports = root.WispStationUI;
})(typeof window !== 'undefined' ? window : globalThis);
