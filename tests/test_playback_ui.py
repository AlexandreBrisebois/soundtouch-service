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
