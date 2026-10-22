/* Speaker-native preset management. A readback is not an audible playback test. */
(function (root) {
  'use strict';
  function createRequestGate() {
    let generation = 0;
    let controller = null;
    return {
      next() { if (controller) controller.abort(); controller = new AbortController(); return {generation: ++generation, signal: controller.signal}; },
      current(ticket) { return ticket.generation === generation && !ticket.signal.aborted; },
      cancel() { generation += 1; if (controller) controller.abort(); },
    };
  }
  function favoriteLabel(favorite) {
    const labels = {
      readback_matched: 'Speaker assignment confirmed. Listening not yet verified.',
      saved: 'Saved in Wisp only. Not assigned to a speaker button.',
      superseded: 'This button has a newer favorite. Update any older schedules.',
      programming: 'Programming requested. Outcome not yet known.',
      unknown: 'Assignment could not be confirmed. Check the speaker before retrying.',
      failed: 'Assignment failed.',
      mismatch: 'The speaker assignment has changed. Review it before scheduling.',
      unsupported: 'This source cannot be assigned with the current setup.',
    };
    return labels[favorite.state] || 'Assignment has not been verified.';
  }
  function create(deps) {
    const doc = deps.document;
    const el = id => doc.getElementById(id);
    const gate = createRequestGate();
    const scheduleGate = createRequestGate();
    const pendingWrites = new Set();
    const disabledBeforeBusy = new WeakMap();
    let speaker = null;
    let data = null;
    let source = null;
    let stack = [];
    let selected = null;
    let plan = null;
    let favorites = [];
    let scheduleSpeaker = null;
    const message = text => { el('presets-message').textContent = text; };
    function button(text, handler, disabled) {
      const node = doc.createElement('button'); node.type = 'button'; node.className = 'preset-action'; node.textContent = text;
      node.disabled = !!disabled; node.addEventListener('click', handler); return node;
    }
    function text(tag, value, className) {
      const node = doc.createElement(tag); node.textContent = value;
      if (className) node.className = className; return node;
    }
    function clear(node) { node.replaceChildren(); }
    const url = (name, suffix) => `/api/${encodeURIComponent(name)}${suffix}`;
    async function request(name, suffix, options = {}) {
      const response = await deps.fetch(url(name, suffix), options);
      let body;
      try { body = await response.json(); } catch (_) { throw new Error('Wisp could not read the response. Refresh before retrying.'); }
      if (!response.ok) throw new Error(body.error || body.message || 'The request could not be completed.');
      return body;
    }
    function post(body) { return {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}; }
    function busy(value) {
      el('presets-panel').setAttribute('aria-busy', String(value));
      el('presets-panel').querySelectorAll('button:not([data-preset-close]), input, select').forEach(node => {
        if (value) {
          if (!disabledBeforeBusy.has(node)) disabledBeforeBusy.set(node, node.disabled);
          node.disabled = true;
        } else if (disabledBeforeBusy.has(node)) {
          node.disabled = disabledBeforeBusy.get(node); disabledBeforeBusy.delete(node);
        }
      });
      if (!value) {
        el('preset-review').disabled = !selected || !selected.presetable;
        el('preset-confirm').disabled = !plan;
      }
    }
    function resetSelection() {
      selected = null; plan = null;
      el('preset-selection').hidden = true; el('preset-confirmation').hidden = true;
      el('preset-test-confirmation').hidden = true;
    }
    function close(restoreFocus = true) {
      gate.cancel(); speaker = null; source = null; stack = []; resetSelection();
      el('presets-panel').hidden = true;
      el('btn-manage-presets').setAttribute('aria-expanded', 'false');
      if (restoreFocus) el('btn-manage-presets').focus();
    }
    function renderFavorites() {
      const list = el('preset-favorites'); clear(list);
      if (!favorites.length) list.append(text('p', 'No saved favorites yet.', 'preset-help'));
      favorites.forEach(favorite => {
        const card = text('div', '', 'preset-favorite');
        card.append(text('strong', favorite.name));
        card.append(text('p', favorite.slot ? `Button ${favorite.slot} · ${favoriteLabel(favorite)}` : favoriteLabel(favorite), 'preset-help'));
        if (favorite.state === 'readback_matched') {
          card.append(button('Use in a schedule', () => {
            const chosen = {...favorite}; close(false); deps.openSchedule(chosen);
          }));
          card.append(button('Test quietly…', () => {
            el('preset-test-confirmation').hidden = false;
            el('preset-test-text').textContent = `Start “${favorite.name}” now at low volume? This can replace current audio. A listening check is still needed, including the physical button and next track.`;
            el('preset-test-confirm').dataset.favoriteId = favorite.id;
            el('preset-test-confirm').focus();
          }, pendingWrites.has(speaker)));
        }
        list.append(card);
      });
    }
    function renderSources() {
      const list = el('preset-sources'); clear(list);
      const sources = data.sources || [];
      if (!sources.length) list.append(text('p', 'No registered NAS music source was reported by this speaker. Wisp does not register or change your NAS service.', 'preset-help'));
      sources.forEach(item => list.append(button(item.name + (item.ready ? '' : ' · unavailable'), () => {
        source = item; stack = []; el('preset-browser').hidden = true; browse(null, 1);
      }, !item.ready)));
    }
    async function open(name) {
      close(false); speaker = name; el('presets-panel').hidden = false;
      el('speaker-settings').open = true;
      el('btn-manage-presets').setAttribute('aria-expanded', 'true');
      el('presets-title').textContent = `Presets · ${name}`;
      el('presets-title').focus();
      el('preset-browser').hidden = true;
      clear(el('preset-favorites')); clear(el('preset-sources'));
      message(pendingWrites.has(name) ? 'An earlier request may still be finishing. Refresh before making another change.' : 'Reading the speaker’s presets and music sources…');
      const ticket = gate.next(); busy(true);
      try {
        const result = await request(name, '/favorites', {signal: ticket.signal});
        if (!gate.current(ticket) || speaker !== name) return;
        data = result; favorites = result.favorites || [];
        renderFavorites(); renderSources();
        const slots = el('preset-slot'); clear(slots);
        for (let slot = 1; slot <= 6; slot += 1) {
          const preset = (data.presets || []).find(item => item.slot === slot);
          const option = doc.createElement('option'); option.value = String(slot);
          option.textContent = `Button ${slot}: ${preset && preset.name ? preset.name : 'Empty'}`; slots.append(option);
        }
        message('Choose a NAS folder or playlist. Existing buttons stay unchanged until you confirm.');
        return true;
      } catch (error) { if (gate.current(ticket)) message(error.message); }
      finally { if (gate.current(ticket)) { busy(false); if (pendingWrites.has(name)) busy(true); } }
    }
    async function browse(container, start, append = false, nextStack = stack) {
      if (!speaker || !source) return;
      const name = speaker; const ticket = gate.next(); resetSelection(); busy(true);
      message('Reading the collection…');
      try {
        const result = await request(name, '/library/browse', {...post({source_id: source.id, container_id: container ? container.id : undefined, start}), signal: ticket.signal});
        if (!gate.current(ticket) || speaker !== name) return;
        stack = nextStack;
        el('preset-browser').hidden = false;
        el('preset-browser-title').textContent = container ? container.name : source.name;
        const list = el('preset-items'); if (!append) clear(list);
        const items = result.items || [];
        if (!items.length && !append) list.append(text('p', 'No items in this collection.', 'preset-help'));
        items.forEach(item => {
          const row = text('div', '', 'preset-library-item');
          row.append(text('span', item.name));
          if (item.is_dir) row.append(button('Open', () => browse(item, 1, false, [...stack, item])));
          if (item.is_dir && item.playable && item.presetable) row.append(button('Choose', () => choose(item)));
          else if (!item.is_dir) row.append(text('span', 'Not preset-ready', 'preset-help'));
          list.append(row);
        });
        el('preset-up').disabled = !stack.length;
        el('preset-more').hidden = !result.next_start;
        el('preset-more').onclick = () => browse(container, result.next_start, true);
        message('Choose a playable collection to assign it to a button. Playback order is supplied by your music source.');
      } catch (error) { if (gate.current(ticket)) message(error.message); }
      finally { if (gate.current(ticket)) { busy(false); el('preset-up').disabled = !stack.length; } }
    }
    function choose(item) {
      selected = item; plan = null;
      el('preset-name').value = item.name;
      el('preset-selection').hidden = false; el('preset-confirmation').hidden = true;
      el('preset-review').disabled = !item.presetable;
      el('preset-name').focus();
    }
    async function review() {
      if (!selected || !speaker || pendingWrites.has(speaker)) return;
      if (!el('preset-name').value.trim()) { message('Give this favorite a name.'); el('preset-name').focus(); return; }
      const name = speaker; const item = selected; const ticket = gate.next(); busy(true);
      plan = null; el('preset-confirmation').hidden = true;
      try {
        const payload = {slot: Number(el('preset-slot').value), name: el('preset-name').value.trim()};
        payload.item_id = item.id;
        const result = await request(name, '/preset-plans', {...post(payload), signal: ticket.signal});
        if (!gate.current(ticket) || speaker !== name) return;
        plan = result;
        el('preset-confirmation').hidden = false;
        el('preset-confirm-text').textContent = `Assign “${result.name}” to button ${result.slot}? ${result.replaces ? `This replaces “${result.replaces}”. ` : ''}${result.warning || 'The speaker’s button assignment will change. This does not start playback.'}`;
        el('preset-confirm').focus(); message('Review this change before confirming.');
      } catch (error) { if (gate.current(ticket)) message(error.message); }
      finally { if (gate.current(ticket)) busy(false); }
    }
    async function confirm() {
      if (!plan || !speaker || pendingWrites.has(speaker)) return;
      const name = speaker; const chosen = plan; const ticket = gate.next();
      pendingWrites.add(name); plan = null; busy(true);
      message('Programming requested. Wait for readback before trying again.');
      try {
        // Deliberately do not abort a write when this panel closes. Its outcome is
        // uncertain until the next read; never retry it automatically.
        const result = await request(name, `/preset-plans/${encodeURIComponent(chosen.plan_id)}/confirm`, post({confirmed: true}));
        if (!gate.current(ticket) || speaker !== name) return;
        if (result.favorite) {
          favorites = favorites.filter(f => f.id !== result.favorite.id).map(f =>
            f.speaker_id === result.favorite.speaker_id && f.slot === result.favorite.slot ? {...f, state: 'superseded'} : f);
          favorites.push(result.favorite);
        }
        renderFavorites(); resetSelection();
        message(result.message || favoriteLabel({state: result.state}));
      } catch (error) {
        if (gate.current(ticket)) { resetSelection(); message(`${error.message} The speaker may have received the change. Refresh before retrying.`); }
      } finally {
        pendingWrites.delete(name);
        if (gate.current(ticket)) busy(false);
        else if (speaker === name) { busy(false); message('The earlier request finished. Refresh to check the speaker before another change.'); }
      }
    }
    async function test() {
      if (!speaker || pendingWrites.has(speaker)) return;
      const id = el('preset-test-confirm').dataset.favoriteId;
      if (!id) return;
      const name = speaker; const ticket = gate.next(); pendingWrites.add(name); busy(true);
      el('preset-test-confirmation').hidden = true;
      try {
        const result = await request(name, `/favorites/${encodeURIComponent(id)}/test`, post({confirmed: true}));
        if (!gate.current(ticket) || speaker !== name) return;
        message('Quiet test requested. Watch the playback status and listen; acceptance is not proof of sound.');
        deps.onTest(result, name);
      } catch (error) { if (gate.current(ticket)) message(`${error.message} Playback may have started. Check before retrying.`); }
      finally { pendingWrites.delete(name); if (gate.current(ticket)) busy(false); }
    }
    async function loadSchedule(name, initialId) {
      scheduleSpeaker = name; const ticket = scheduleGate.next(); const select = el('f-favorite');
      clear(select); select.append(Object.assign(doc.createElement('option'), {value: '', textContent: 'Choose a favorite…'}));
      if (initialId) select.append(Object.assign(doc.createElement('option'), {value: initialId, textContent: 'Saved favorite · checking assignment…'}));
      select.value = initialId || ''; select.disabled = true;
      try {
        const result = await request(name, '/favorites', {signal: ticket.signal});
        if (!scheduleGate.current(ticket) || scheduleSpeaker !== name) return;
        const chosenId = select.value;
        favorites = result.favorites || [];
        clear(select); select.append(Object.assign(doc.createElement('option'), {value: '', textContent: 'Choose a favorite…'}));
        favorites.filter(f => f.state === 'readback_matched').forEach(f => {
          select.append(Object.assign(doc.createElement('option'), {value: f.id, textContent: `${f.name} · button ${f.slot}`}));
        });
        if (chosenId && !favorites.some(f => f.id === chosenId && f.state === 'readback_matched')) {
          select.append(Object.assign(doc.createElement('option'), {value: chosenId, textContent: 'Saved favorite unavailable · review before saving'}));
        }
        select.value = chosenId;
        el('favorite-schedule-help').textContent = 'A saved favorite checks its button assignment before a scheduled start.';
      } catch (error) {
        if (scheduleGate.current(ticket)) el('favorite-schedule-help').textContent = 'Favorites could not be checked. An existing favorite remains attached; retry before changing it.';
      } finally { if (scheduleGate.current(ticket)) select.disabled = false; }
    }
    el('btn-manage-presets').addEventListener('click', () => open(deps.getSpeaker()));
    el('presets-close').addEventListener('click', () => close());
    el('presets-refresh').addEventListener('click', () => { if (speaker && !pendingWrites.has(speaker)) open(speaker); });
    el('preset-up').addEventListener('click', () => { const parentStack = stack.slice(0, -1); browse(parentStack[parentStack.length - 1] || null, 1, false, parentStack); });
    el('preset-review').addEventListener('click', review);
    el('preset-confirm').addEventListener('click', confirm);
    el('preset-cancel').addEventListener('click', () => { plan = null; el('preset-confirmation').hidden = true; el('preset-review').focus(); });
    el('preset-name').addEventListener('input', () => { plan = null; el('preset-confirmation').hidden = true; });
    el('preset-slot').addEventListener('change', () => { plan = null; el('preset-confirmation').hidden = true; });
    el('preset-test-confirm').addEventListener('click', test);
    el('preset-test-cancel').addEventListener('click', () => { el('preset-test-confirmation').hidden = true; });
    el('presets-panel').addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(); } });
    el('f-favorite').addEventListener('change', () => {
      const favorite = favorites.find(f => f.id === el('f-favorite').value && f.state === 'readback_matched');
      if (favorite) deps.setPreset(favorite.slot);
    });
    return {
      open, close, review, confirm, browse, choose, test, loadSchedule,
      onViewChange(view) { if (view !== 'speaker' || (speaker && speaker !== deps.getSpeaker())) close(false); if (view !== 'form') { scheduleGate.cancel(); scheduleSpeaker = null; } },
      scheduleValue() { return el('f-favorite').value || null; },
      clearScheduleChoice() { el('f-favorite').value = ''; },
      scheduleBinding() { return favorites.find(f => f.id === el('f-favorite').value) || null; },
    };
  }
  root.WispPresetUI = {create, createRequestGate, favoriteLabel};
  if (typeof module !== 'undefined' && module.exports) module.exports = root.WispPresetUI;
})(typeof window !== 'undefined' ? window : globalThis);
