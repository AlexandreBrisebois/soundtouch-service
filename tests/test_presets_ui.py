"""Fixture-only UI contract checks. No browser, NAS or speaker is contacted."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')


def checks(body):
    if NODE is None:
        pytest.skip('Node unavailable')
    harness = r'''
const assert = require('node:assert/strict');
const api = require('./app/static/presets.js');
class Element {
  constructor(tag='div') { this.tagName=tag; this.children=[]; this.listeners={}; this.dataset={}; this.hidden=false; this.disabled=false; this.value=''; this.textContent=''; this.attrs={}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=nodes; }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  setAttribute(name,value) { this.attrs[name]=value; }
  focus() { focused=this; }
  querySelectorAll() { return [...elements.values()].filter(e => e.id !== 'presets-close' && /^(button|input|select)$/.test(e.tagName)); }
}
let focused=null;
const elements=new Map();
function el(id) { if (!elements.has(id)) { const node=new Element(id.includes('name') ? 'input' : id.includes('slot') || id==='f-favorite' ? 'select' : 'button'); node.id=id; elements.set(id,node); } return elements.get(id); }
const doc={getElementById:el, createElement:tag=>new Element(tag)};
const calls=[];
let getResponse=async()=>({favorites:[],sources:[],presets:[],radio:{reason:'Not configured'}});
let current='Living Room';
let selectedPreset=null;
let scheduled=null;
let tests=[];
const ui=api.create({document:doc,getSpeaker:()=>current,fetch:async(url,opts)=>{calls.push({url,opts});return getResponse(url,opts);},setPreset:value=>selectedPreset=value,openSchedule:f=>scheduled=f,onTest:r=>tests.push(r)});
const ok=body=>({ok:true,json:async()=>body});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
'''
    script = harness + '\n(async()=>{\n' + body + '\n})().catch(e=>{console.error(e);process.exitCode=1;});'
    result = subprocess.run([NODE, '-'], input=script, cwd=ROOT, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_preset_markup_is_accessible_and_assets_are_linked():
    text = (ROOT / 'app/templates/index.html').read_text()
    assert 'aria-controls="presets-panel"' in text
    assert 'id="presets-message" role="status" aria-live="polite"' in text
    assert 'id="presets-title" tabindex="-1"' in text
    assert '/app-static/presets.js' in text
    assert '/app-static/presets.css' in text
    assert 'favorite_id: window.wispPresets' in text
    assert 'innerHTML' not in (ROOT / 'app/static/presets.js').read_text()


def test_labels_do_not_claim_success_from_save_or_programming():
    checks('''
assert.match(api.favoriteLabel({state:'saved'}), /Wisp only/);
assert.match(api.favoriteLabel({state:'programming'}), /not yet known/);
assert.match(api.favoriteLabel({state:'readback_matched'}), /Listening not yet verified/);
assert.match(api.favoriteLabel({state:'unknown'}), /before retrying/);
''')


def test_close_aborts_reads_and_stale_open_cannot_reopen_panel():
    checks('''
let complete;
getResponse=()=>new Promise(resolve=>complete=resolve);
const pending=ui.open('Living Room');
ui.close();
assert.equal(calls[0].opts.signal.aborted,true);
complete(ok({favorites:[{id:'old',name:'Old',state:'readback_matched'}],sources:[]}));
await pending;
assert.equal(el('presets-panel').hidden,true);
assert.equal(el('preset-favorites').children.length,0);
assert.equal(focused,el('btn-manage-presets'));
''')


def test_switching_speakers_ignores_previous_results():
    checks('''
const pending=[];
getResponse=()=>new Promise(resolve=>pending.push(resolve));
const first=ui.open('Living Room');
current='Kitchen';
const second=ui.open('Kitchen');
pending[1](ok({favorites:[],sources:[{id:'new',name:'Kitchen NAS',ready:true}]}));
await second;
pending[0](ok({favorites:[],sources:[{id:'old',name:'Old NAS',ready:true}]}));
await first;
assert.equal(el('preset-sources').children[0].textContent,'Kitchen NAS');
assert.equal(el('presets-title').textContent,'Presets · Kitchen');
''')


def test_duplicate_confirmation_sends_one_write_and_never_plays_audio():
    checks('''
getResponse=async()=>ok({favorites:[],sources:[],presets:[]});
await ui.open('Living Room');
ui.choose({id:'folder',name:'Morning',presetable:true,playable:true});
el('preset-slot').value='2';
getResponse=async()=>ok({plan_id:'plan',name:'Morning',slot:2,replaces:'Old music'});
await ui.review();
assert.match(el('preset-confirm-text').textContent,/replaces “Old music”/);
let complete;
getResponse=()=>new Promise(resolve=>complete=resolve);
const first=ui.confirm();
await ui.confirm();
assert.equal(calls.filter(c=>c.url.endsWith('/confirm')).length,1);
assert.equal(calls.filter(c=>c.url.endsWith('/test')).length,0);
complete(ok({state:'readback_matched',favorite:{id:'f',name:'Morning',slot:2,state:'readback_matched'}}));
await first;
assert.match(el('presets-message').textContent,/Listening not yet verified/);
assert.equal(el('preset-confirmation').hidden,true);
''')


def test_closed_write_is_not_retried_and_refresh_remains_possible():
    checks('''
getResponse=async()=>ok({favorites:[],sources:[],presets:[]});
await ui.open('Living Room'); ui.choose({id:'i',name:'Music',presetable:true}); el('preset-slot').value='1';
getResponse=async()=>ok({plan_id:'p',name:'Music',slot:1}); await ui.review();
let complete;
getResponse=()=>new Promise(resolve=>complete=resolve);
const mutation=ui.confirm();
ui.close();
getResponse=async()=>ok({favorites:[],sources:[],presets:[]}); await ui.open('Living Room');
complete(ok({state:'unknown',message:'Uncertain'})); await mutation;
assert.equal(calls.filter(c=>c.url.endsWith('/confirm')).length,1);
assert.equal(el('presets-refresh').disabled,false);
assert.match(el('presets-message').textContent,/Refresh to check/);
''')


def test_failed_write_warns_about_uncertainty_instead_of_retrying():
    checks('''
getResponse=async()=>ok({favorites:[],sources:[],presets:[]});
await ui.open('Living Room'); ui.choose({id:'i',name:'Music',presetable:true}); el('preset-slot').value='1';
getResponse=async()=>ok({plan_id:'p',name:'Music',slot:1}); await ui.review();
getResponse=async()=>{throw new Error('Network interrupted');}; await ui.confirm();
assert.match(el('presets-message').textContent,/may have received/);
await ui.confirm();
assert.equal(calls.filter(c=>c.url.endsWith('/confirm')).length,1);
''')


def test_existing_schedule_binding_survives_failed_favorites_load():
    checks('''
getResponse=async()=>{throw new Error('offline');};
await ui.loadSchedule('Living Room','existing-id');
assert.equal(ui.scheduleValue(),'existing-id');
assert.match(el('favorite-schedule-help').textContent,/remains attached/);
ui.clearScheduleChoice(); assert.equal(ui.scheduleValue(),null);
''')


def test_schedule_load_cannot_overwrite_newer_speaker_choice():
    checks('''
const pending=[];getResponse=()=>new Promise(resolve=>pending.push(resolve));
const first=ui.loadSchedule('Living Room','old');
const second=ui.loadSchedule('Kitchen','new');
pending[1](ok({favorites:[{id:'new',name:'Kitchen',slot:2,state:'readback_matched'}]}));await second;
pending[0](ok({favorites:[{id:'old',name:'Old',slot:1,state:'readback_matched'}]}));await first;
assert.equal(ui.scheduleValue(),'new');
assert.equal(ui.scheduleBinding().name,'Kitchen');
''')


def test_radio_form_requires_capability_and_rejects_credential_urls():
    checks('''
getResponse=async()=>ok({favorites:[],sources:[],radio:{available:false,reason:'Source missing'}});
await ui.open('Living Room'); assert.equal(el('preset-radio-form').hidden,true);
getResponse=async()=>ok({favorites:[],sources:[],radio:{available:true}});
await ui.open('Living Room'); assert.equal(el('preset-radio-form').hidden,false);
el('preset-radio-url').value='https://user:secret@example.com/radio';
el('preset-radio-choose').listeners.click();
assert.equal(el('preset-selection').hidden,true);
assert.match(el('presets-message').textContent,/without credentials/);
assert.equal(calls.length,2);
''')


def test_radio_uses_same_explicit_preview_without_stream_fetch():
    checks('''
getResponse=async()=>ok({favorites:[],sources:[],radio:{available:true}});
await ui.open('Living Room');
el('preset-radio-url').value='https://radio.example/live.mp3';
el('preset-radio-choose').listeners.click();
el('preset-name').value='Calm radio';el('preset-slot').value='3';
getResponse=async()=>ok({plan_id:'radio',name:'Calm radio',slot:3,replaces:'NAS playlist'});
await ui.review();
assert.equal(calls.length,2);
assert.equal(calls[1].url,'/api/Living%20Room/preset-plans');
const payload=JSON.parse(calls[1].opts.body);
assert.equal(payload.radio_url,'https://radio.example/live.mp3');
assert.equal(payload.item_id,undefined);
assert.match(el('preset-confirm-text').textContent,/replaces “NAS playlist”/);
assert.equal(calls.filter(c=>c.url.endsWith('/confirm')).length,0);
''')


def test_replacement_invalidates_old_favorite_card_immediately():
    checks('''
getResponse=async()=>ok({favorites:[{id:'old',name:'Old',speaker_id:'ABC',slot:2,state:'readback_matched'}],sources:[],presets:[]});
await ui.open('Living Room');
ui.choose({id:'folder',name:'Morning',presetable:true,playable:true,is_dir:true});
el('preset-slot').value='2';
getResponse=async()=>ok({plan_id:'plan',name:'Morning',slot:2,replaces:'Old'});
await ui.review();
getResponse=async()=>ok({state:'readback_matched',favorite:{id:'new',name:'Morning',speaker_id:'ABC',slot:2,state:'readback_matched'}});
await ui.confirm();
const old=el('preset-favorites').children[0];
assert.match(old.children[1].textContent,/newer favorite/);
assert.equal(old.children.filter(x=>x.tagName==='button').length,0);
''')


def test_tracks_cannot_be_chosen_as_folder_presets():
    checks('''
getResponse=async()=>ok({favorites:[],sources:[{id:'nas',name:'Music',ready:true}],presets:[]});
await ui.open('Living Room');
getResponse=async()=>ok({items:[{id:'track',name:'Song',playable:true,presetable:true,is_dir:false}],total:1});
el('preset-sources').children[0].listeners.click(); await flush();
assert.equal(el('preset-items').children[0].children.filter(x=>x.textContent==='Choose').length,0);
''')
