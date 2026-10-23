"""Offline behavior checks for the existing UI; no browser or speaker is contacted."""

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "templates" / "index.html"
NODE = shutil.which("node")


def run_ui_checks(checks):
    if NODE is None:
        pytest.skip("Node is unavailable; UI source assertions still run")
    source = re.findall(r"<script>(.*?)</script>", TEMPLATE.read_text(), re.S)[-1]
    harness = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
const timers = new Map();
let nextTimer = 0;
function element(id) {
  if (!elements.has(id)) {
    const classes = new Set();
    elements.set(id, {
      id, textContent: '', innerHTML: '', hidden: false, disabled: false,
      dataset: {}, style: {}, listeners: {},
      classList: {
        add: name => classes.add(name), remove: name => classes.delete(name),
        contains: name => classes.has(name),
        toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
      },
      addEventListener(name, handler) { this.listeners[name] = handler; },
    });
  }
  return elements.get(id);
}
const context = vm.createContext({
  assert, element, timers, console, AbortController,
  document: {
    readyState: 'loading', getElementById: element,
    querySelectorAll: () => [], addEventListener: () => {},
  },
  window: {addEventListener: () => {}}, navigator: {},
  setTimeout: (fn, delay) => { const id = ++nextTimer; timers.set(id, {fn, delay}); return id; },
  clearTimeout: id => timers.delete(id),
  fetch: async () => { throw new Error('Unexpected network access'); },
});
"""
    script = harness + f"\nvm.runInContext({json.dumps(source)}, context);\n"
    script += f"vm.runInContext({json.dumps('(async () => {' + checks + '})()')}, context).catch(error => {{ console.error(error); process.exitCode = 1; }});"
    result = subprocess.run([NODE, "-"], input=script, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_outcome_controls_are_accessible_and_warn_about_audio_replacement():
    source = TEMPLATE.read_text()
    assert 'id="detail-operation" role="status" aria-live="polite"' in source
    assert 'id="btn-cancel-operation" hidden aria-describedby="cancel-operation-help"' in source
    assert "Run Now can replace current audio" in source
    assert "Audio already playing may continue" in source
    assert 'id="toast" role="status" aria-live="polite"' in source
    assert "content_identity" not in source


def test_outcome_labels_and_timezone_are_honest():
    run_ui_checks(r"""
      assert.match(operationSummary({state: 'accepted'}), /waiting to start/);
      assert.match(operationSummary({state: 'starting'}), /not yet confirmed/);
      assert.match(operationSummary({state: 'unknown'}), /could not be confirmed/);
      assert.match(operationSummary({state: 'playing'}), /audibility not verified/);
      assert.match(operationSummary({state: 'completed'}), /Completed/);
      assert.match(operationSummary({state: 'failed'}), /Failed/);
      assert.match(operationSummary({state: 'skipped'}), /Skipped/);
      assert.match(operationSummary({state: 'canceled'}), /Cancelled/);
      assert.equal(operationIsActive({state: 'starting', terminal: false}), true);
      assert.equal(operationIsActive({state: 'playing', terminal: true}), false);
      assert.match(nextRunSummary({next_run: '2026-10-22T06:15:00+02:00', timezone: 'Europe/Paris'}), /Europe\/Paris/);
      assert.match(nextRunSummary({paused: true, timezone: 'Europe/Paris'}), /^Paused/);
      assert.match(nextRunSummary({next_run: '2026-10-22T06:15:00+02:00', timezone: 'Unsupported/Zone'}), /06:15:00\+02:00/);
      renderOperation({state: 'starting', terminal: false});
      assert.equal(element('btn-cancel-operation').hidden, false);
      renderOperation({state: 'canceled', terminal: true});
      assert.equal(element('btn-cancel-operation').hidden, true);
    """)


def test_recovery_messages_are_honest_and_pending_listening_can_stop():
    run_ui_checks(r"""
      assert.match(operationSummary({state:'recovery_pending',recovery_state:'pending'}),
                   /Recovery pending.*not confirmed/);
      assert.match(operationSummary({state:'recovering',recovery_state:'recovering'}),
                   /Attempting.*not confirmed/);
      assert.match(operationSummary({state:'playing',recovery_state:'recovered'}),
                   /reported recovered.*audibility not verified/);
      assert.match(operationSummary({state:'unknown',recovery_state:'declined'}),
                   /Recovery declined.*will not retry/);
      assert.match(operationSummary({state:'unknown',recovery_state:'failed'}),
                   /Recovery failed.*will not retry/);
      assert.match(operationSummary({state:'unknown',reason:'radio_recovery_worker_unavailable',recovery_state:'failed'}),
                   /worker unavailable/);
      assert.match(operationSummary({state:'completed',reason:'radio_recovery_canceled_no_speaker_command',recovery_state:'canceled'}),
                   /No speaker command was sent/);
      const pending={operation_id:'one',station_id:'station',speaker_id:'ABC',
                     listening_session:true,state:'recovery_pending',terminal:false};
      renderOperation(pending);
      assert.equal(element('btn-stop-radio').hidden,false);
    """)


def test_listening_stop_captures_owner_and_never_uses_power():
    run_ui_checks(r"""
      currentSpeaker='Room';refreshPlayback=()=>{};
      latestOperation={operation_id:'one',station_id:'station',speaker_id:'ABC',listening_session:true,state:'playing',terminal:true};
      renderOperation(latestOperation);
      assert.equal(element('btn-stop-radio').hidden,false);
      const calls=[];let finish;
      fetch=async(url,opts)=>{calls.push({url,opts});return new Promise(resolve=>finish=resolve);};
      const first=element('btn-stop-radio').listeners.click();
      await element('btn-stop-radio').listeners.click();
      assert.equal(calls.length,1);
      assert.equal(calls[0].url,'/api/Room/stations/station/stop');
      assert.deepEqual(JSON.parse(calls[0].opts.body),{speaker_id:'ABC',operation_id:'one'});
      assert.doesNotMatch(calls[0].url,/power|test/);
      currentSpeaker='Other';latestOperation={operation_id:'newer',state:'playing'};
      finish({ok:true,json:async()=>({operation:{operation_id:'stop-one',state:'accepted'}})});
      await first;assert.equal(latestOperation.operation_id,'newer');
      renderOperation({state:'playing',listening_session:false});
      assert.equal(element('btn-stop-radio').hidden,true);
    """)


def test_buffering_is_not_classified_as_playing_and_failure_is_not_standby():
    run_ui_checks(r"""
      element('hub-greeting').textContent = 'Good morning';
      fetch = async () => ({ok: true, json: async () => ({status: 'Buffering', source: 'Radio', volume: 10})});
      await fetchSpeakerStatus('Living Room');
      assert.equal(speakerStatuses['Living Room'], 'buffering');
      assert.equal(element('card-Living Room').classList.contains('playing'), false);
      assert.match(element('status-Living Room').textContent, /^Buffering/);
      fetch = async () => ({ok: false, json: async () => ({error: 'Offline'})});
      await fetchSpeakerStatus('Living Room');
      assert.equal(speakerStatuses['Living Room'], 'unavailable');
      assert.equal(element('status-Living Room').textContent, 'Unavailable');
    """)


def test_repeated_run_now_is_deduplicated_and_acceptance_is_not_success():
    run_ui_checks(r"""
      currentSpeaker = 'Living Room';
      moreTargetSchedule = 'Morning';
      let resolveRequest;
      const calls = [];
      fetch = url => { calls.push(url); return new Promise(resolve => { resolveRequest = resolve; }); };
      refreshPlayback = async () => {};
      const first = element('sheet-btn-trigger').listeners.click();
      await element('sheet-btn-trigger').listeners.click();
      assert.equal(calls.length, 1);
      assert.equal(element('sheet-btn-trigger').disabled, true);
      resolveRequest({ok: true, json: async () => ({operation: {state: 'accepted', schedule_name: 'Morning', terminal: false}})});
      await first;
      assert.match(element('toast').textContent, /not yet confirmed/);
      assert.match(element('detail-operation').textContent, /waiting to start/);
      assert.equal(element('sheet-btn-trigger').disabled, true);
      await element('sheet-btn-trigger').listeners.click();
      assert.equal(calls.length, 1);
    """)


def test_failed_run_and_power_requests_do_not_show_success():
    run_ui_checks(r"""
      currentSpeaker = 'Living Room';
      moreTargetSchedule = 'Morning';
      fetch = async () => ({ok: false, json: async () => ({error: 'Command delivery unconfirmed'})});
      refreshPlayback = async () => {};
      await element('sheet-btn-trigger').listeners.click();
      assert.equal(element('toast').textContent, 'Command delivery unconfirmed');
      assert.equal(element('sheet-btn-trigger').disabled, false);
      assert.equal(latestOperation, null);
      await element('btn-power-speaker').listeners.click();
      assert.equal(element('toast').textContent, 'Command delivery unconfirmed');
      discoveredSpeakers = [{name: 'Living Room'}];
      speakerStatuses['Living Room'] = 'playing';
      await element('sheet-btn-confirm-all-off').listeners.click();
      assert.match(element('toast').textContent, /1 power command\(s\) unconfirmed/);
      assert.equal(speakerStatuses['Living Room'], 'playing');
    """)


def test_cancel_does_not_send_power_and_explains_audio_may_continue():
    run_ui_checks(r"""
      currentSpeaker = 'Living Room';
      latestOperation = {state: 'starting', terminal: false};
      const urls = [];
      fetch = async url => {
        urls.push(url);
        return {ok: true, json: async () => ({last_outcome: {state: 'canceled', terminal: true}})};
      };
      refreshPlayback = async () => {};
      await element('btn-cancel-operation').listeners.click();
      assert.equal(urls.length, 1);
      assert.equal(urls[0], '/api/Living%20Room/cancel');
      assert.match(element('toast').textContent, /audio may continue/);
      assert.equal(element('btn-cancel-operation').hidden, true);
    """)


def test_late_operation_response_cannot_overwrite_new_speaker_or_restart_poll():
    run_ui_checks(r"""
      currentSpeaker = 'Living Room';
      activeView = 'speaker';
      const pending = [];
      fetch = () => new Promise(resolve => pending.push(resolve));
      const update = refreshPlayback('Living Room');
      currentSpeaker = 'Kitchen';
      latestOperation = {state: 'canceled', terminal: true, schedule_name: 'Kitchen run'};
      element('detail-operation').textContent = 'Kitchen run';
      pending[0]({ok: true, json: async () => ({last_outcome: {state: 'playing'}})});
      pending[1]({ok: true, json: async () => ({schedules: []})});
      await update;
      assert.equal(element('detail-operation').textContent, 'Kitchen run');
      assert.equal(latestOperation.schedule_name, 'Kitchen run');
      assert.equal(timers.size, 0);
    """)


def test_back_navigation_stops_playback_poll_and_discards_inflight_response():
    run_ui_checks(r"""
      currentSpeaker = 'Living Room';
      activeView = 'speaker';
      const pending = [];
      fetch = () => new Promise(resolve => pending.push(resolve));
      const update = refreshPlayback('Living Room');
      showView('hub');
      pending[0]({ok: true, json: async () => ({last_outcome: {state: 'playing'}})});
      pending[1]({ok: true, json: async () => ({schedules: []})});
      await update;
      assert.equal(latestOperation, null);
      assert.equal(timers.size, 0);
      assert.equal(activeView, 'hub');
    """)


def test_source_choice_shows_only_relevant_fields_and_preserves_drafts():
    run_ui_checks(r"""
      element('f-name').value = 'Morning';
      element('f-station').value = 'radio-id';
      element('f-favorite').value = 'favorite-id';
      selectedPreset = 4;
      setPlayKind('radio');
      assert.equal(element('schedule-radio').hidden, false);
      for (const kind of ['favorite', 'preset', 'aux']) assert.equal(element(`schedule-${kind}`).hidden, true);
      assert.deepEqual(scheduleSource(), {station_id:'radio-id', favorite_id:null, preset:null, source:null});
      setPlayKind('favorite');
      assert.deepEqual(scheduleSource(), {station_id:null, favorite_id:'favorite-id', preset:null, source:null});
      setPlayKind('preset');
      assert.deepEqual(scheduleSource(), {station_id:null, favorite_id:null, preset:4, source:null});
      setPlayKind('aux');
      assert.deepEqual(scheduleSource(), {station_id:null, favorite_id:null, preset:null, source:'AUX'});
      setPlayKind('radio');
      assert.equal(scheduleSource().station_id, 'radio-id');
      assert.equal(element('f-favorite').value, 'favorite-id');
    """)


def test_empty_source_does_not_fall_back_to_hidden_button_one():
    run_ui_checks(r"""
      element('f-name').value = 'Morning';
      selectedPreset = 1;
      element('f-station').value = '';
      element('f-favorite').value = '';
      for (const kind of ['', 'radio', 'favorite']) {
        setPlayKind(kind);
        assert.equal(hasScheduleSource(), false);
        assert.equal(element('btn-save').disabled, true);
        await element('btn-save').listeners.click(); // no fetch permitted by harness
      }
    """)


def test_open_schedule_selects_legacy_source_and_new_draft_resets():
    run_ui_checks(r"""
      document.querySelector = () => element('quick');
      window.wispPresets = {loadSchedule: (speaker, id) => {element('f-favorite').value=id || '';}, onViewChange:()=>{}};
      window.wispStations = {loadSchedule: id => {element('f-station').value=id || '';}, onViewChange:()=>{}};
      const existing={name:'Morning',on_time:'06:00',off_time:'07:00',days:[],volume:5,preset:3};
      for (const [extra, kind] of [[{station_id:'s'},'radio'],[{favorite_id:'f'},'favorite'],[{source:'AUX'},'aux'],[{},'preset']]) {
        openForm({...existing,...extra});
        assert.equal(element('f-play-kind').value,kind);
      }
      currentSpeaker='Another speaker';
      openForm();
      assert.equal(element('f-play-kind').value,'');
      assert.equal(element('f-favorite').value,'');
      assert.equal(element('f-station').value,'');
      assert.equal(hasScheduleSource(),false);
    """)


def test_nas_scope_and_source_controls_are_truthful():
    text = TEMPLATE.read_text()
    assert 'Music connected to this speaker' in text
    assert 'not a scan of every NAS on your network' in text
    assert 'for="f-play-kind">What to play' in text
    for kind in ('radio', 'favorite', 'preset', 'aux'):
        assert f'id="schedule-{kind}" hidden' in text
    assert 'data-preset="AUX"' not in text


def test_save_submits_only_the_selected_source_with_explicit_clear_fields():
    run_ui_checks(r"""
      element('f-name').value='Morning';
      element('f-on').value='06:00'; element('f-off').value='07:00';
      element('f-volume').value='5'; element('f-station').value='station-a';
      element('f-favorite').value='favorite-a';
      document.querySelectorAll=selector=>selector==='.day-chip.active' ? [{dataset:{day:'monday'}}] : [];
      window.wispPresets={scheduleBinding:()=>({speaker_id:'favorite-speaker'}),onViewChange:()=>{}};
      currentSpeaker='Kitchen'; selectedPreset=4;
      const submitted=[];
      fetch=async(url, options)=>{submitted.push({url, data:JSON.parse(options.body)});return {ok:true};};
      for (const kind of ['radio','favorite','preset','aux']) {
        setPlayKind(kind);
        assert.equal(element('btn-save').disabled,false);
        const source=scheduleSource();
        await element('btn-save').listeners.click();
        const saved=submitted.at(-1);
        assert.equal(saved.url,'/api/Kitchen/schedules');
        for (const key of ['station_id','favorite_id','preset','source']) assert.equal(saved.data[key],source[key]);
        assert.equal(saved.data.speaker_id,kind==='favorite'?'favorite-speaker':undefined);
      }
      assert.equal(submitted.length,4);
    """)


def test_supporting_setup_is_collapsed_below_devices_and_schedules():
    text = TEMPLATE.read_text()
    assert '<details class="support-settings" id="hub-settings">' in text
    assert '<details class="support-settings" id="speaker-settings">' in text
    assert text.index('id="speaker-list"') < text.index('id="hub-settings"') < text.index('id="btn-hub-stations"')
    assert text.index('id="schedule-list"') < text.index('id="btn-add-schedule"') < text.index('id="speaker-settings"') < text.index('id="btn-manage-presets"')
    assert 'speaker-settings\').addEventListener' not in text
    assert 'hub-settings\').addEventListener' not in text


def test_speaker_button_selection_is_exposed_to_assistive_technology():
    run_ui_checks(r"""
      const buttons=[1,2,3].map(number=>({dataset:{preset:String(number)},classList:{toggle(){}},setAttribute(name,value){this[name]=value;}}));
      document.querySelectorAll=()=>buttons;
      setSelectedPreset(2);
      assert.deepEqual(buttons.map(button=>button['aria-pressed']),['false','true','false']);
    """)
    assert 'id="f-favorite" aria-describedby="favorite-schedule-help"' in TEMPLATE.read_text()


def test_direct_radio_stop_warning_survives_outcome_refresh_and_status_failure():
    run_ui_checks(r"""
      currentSpeaker='Living Room'; activeView='speaker';
      for (const state of ['canceled','unknown','completed']) {
        const outcome={state,terminal:true,reason:'different_reason',physical_stop_may_be_needed:true};
        fetch=async url=>({ok:true,json:async()=>url.endsWith('/operations') ? {last_outcome:outcome} : {schedules:[]}});
        await refreshPlayback('Living Room');
        assert.equal(element('detail-physical-stop').hidden,false);
        assert.match(element('detail-operation').textContent,/Physical Stop may be needed/);
        assert.match(operationSummary(outcome),/closing Wisp does not stop/);
      }
      fetch=async()=>({ok:false}); await refreshPlayback('Living Room');
      assert.equal(element('detail-physical-stop').hidden,false);
      renderOperation(null); // new device starts without another device's stale warning
      assert.equal(element('detail-physical-stop').hidden,true);
      fetch=async url=>({ok:true,json:async()=>url.endsWith('/operations') ? {last_outcome:{state:'canceled',terminal:true,physical_stop_may_be_needed:true}} : {schedules:[]}});
      await refreshPlayback('Living Room'); // reopening retrieves persistent server outcome
      assert.equal(element('detail-physical-stop').hidden,false);
      renderOperation({state:'completed',physical_stop_may_be_needed:false});
      assert.equal(element('detail-physical-stop').hidden,true);
    """)
    text = TEMPLATE.read_text()
    assert 'id="detail-physical-stop" role="alert" hidden' in text
    assert 'Use the speaker’s physical Stop button and check its volume.' in text


def test_schedule_save_surfaces_station_setup_error_without_losing_draft():
    run_ui_checks(r"""
      element('f-name').value='Morning'; element('f-on').value='06:00'; element('f-off').value='07:00';
      element('f-volume').value='5'; element('f-station').value='ici';
      document.querySelectorAll=selector=>selector==='.day-chip.active' ? [{dataset:{day:'monday'}}] : [];
      setPlayKind('radio');
      fetch=async()=>({ok:false,status:400,json:async()=>({errors:{station_id:'Enable the Linux HLS adapter in Settings.'}})});
      await element('btn-save').listeners.click();
      assert.equal(element('toast').textContent,'Enable the Linux HLS adapter in Settings.');
      assert.equal(element('f-station').value,'ici');
      assert.equal(element('schedule-preset').hidden,true);
    """)


def test_hub_refresh_uses_bounded_rediscovery_and_rejects_departed_view():
    run_ui_checks("""
let seen=[];
fetchWithTimeout=async(url,ms)=>{seen.push({url,ms}); return {ok:true,json:async()=>url.includes('discover')?[]:{}};};
await element('btn-refresh').listeners.click();
assert.equal(seen[0].url,'/api/discover?refresh=true');
assert.equal(seen[0].ms,20000);
let release;
fetchWithTimeout=async(url)=>url.includes('discover') ? new Promise(resolve=>release=resolve) : {ok:true,json:async()=>({})};
const pending=loadHub(true);
showView('stations');
release({ok:true,json:async()=>[{name:'Old speaker'}]});
await pending;
assert.equal(discoveredSpeakers.length,0);
assert.equal(activeView,'stations');
""")
