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
    assert 'id="btn-speaker-stations"' in text
    assert '<h3>External playback</h3>' in text
    assert 'Connected services' not in text
    assert 'favorite_id: favorite || null' in text
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


def test_preset_panel_has_no_radio_assignment_controls():
    html = (ROOT / 'app/templates/index.html').read_text()
    script = (ROOT / 'app/static/presets.js').read_text()
    assert 'preset-radio-form' not in html
    assert 'preset-radio-url' not in html
    assert 'radio_url' not in script
    assert 'station_id' not in script


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


def test_explicit_preset_open_reveals_settings_before_confirmation():
    checks('''
el('speaker-settings').open=false;
await ui.open('Living Room');
assert.equal(el('speaker-settings').open,true);
assert.equal(el('presets-panel').hidden,false);
assert.equal(calls.length,1);
''')


def test_native_slots_are_visible_without_wisp_favorites_and_refresh_rediscovers():
    checks("""
getResponse=async url=>ok(url.includes('/discover') ? [] : {favorites:[], sources:[{id:'nas',name:'Family NAS',ready:true}], services:[{name:'Alexa',ready:true},{name:'Amazon Music',ready:true}], external_playback:[{name:'Spotify Connect',ready:true,guidance:'Start playback from the Spotify app.'}], presets:[{slot:1,name:'Existing playlist'}]});
await ui.open('Living Room');
assert.equal(el('preset-selection').hidden,true);
assert.equal(el('preset-native-slots').children[0].textContent,'Button 1: Existing playlist');
assert.equal(el('preset-external-playback').children[0].textContent,'Spotify Connect · Speaker-reported ready — Start playback from the Spotify app.');
assert.equal(el('preset-external-playback').children[0].tagName,'p');
assert(!el('preset-external-playback').children.some(item=>/Alexa|Amazon Music/.test(item.textContent)));
assert.equal(el('preset-sources').children[0].textContent,'Family NAS');
assert.equal(el('preset-favorites').children[0].textContent,'No saved favorites yet.');
await el('presets-refresh').listeners.click(); await flush();
assert.equal(calls[calls.length-2].url,'/api/discover?refresh=true');
assert.equal(calls[calls.length-1].url,'/api/Living%20Room/favorites');
assert(calls.every(c=>!c.opts.method || c.opts.method==='GET'));
""")


def test_refresh_discovery_failure_is_visible_and_does_not_read_old_speaker():
    checks("""
getResponse=async()=>ok({favorites:[],sources:[],presets:[{slot:1,name:'Old'}]});
await ui.open('Living Room');
getResponse=async()=>({ok:false});
await ui.open('Living Room',true);
assert.match(el('presets-message').textContent,/discovery failed/);
assert.equal(el('preset-native-slots').children.length,0);
assert.equal(el('presets-refresh').disabled,false);
assert.equal(calls[calls.length-1].url,'/api/discover?refresh=true');
""")


def test_speaker_switch_rejects_native_slots_and_external_playback_from_old_request():
    checks("""
let pending=[];
getResponse=()=>new Promise(resolve=>pending.push(resolve));
const old=ui.open('Living Room');
current='Kitchen'; const next=ui.open(current);
pending[1](ok({favorites:[],sources:[],external_playback:[{name:'Spotify Connect',ready:false,guidance:'Start playback from the Spotify app.'}],presets:[{slot:1,name:'Kitchen preset'}]})); await next;
pending[0](ok({favorites:[],sources:[],external_playback:[{name:'Spotify Connect',ready:true,guidance:'Start playback from the Spotify app.'}],presets:[{slot:1,name:'Old preset'}]})); await old;
assert.equal(el('preset-native-slots').children[0].textContent,'Button 1: Kitchen preset');
assert.equal(el('preset-external-playback').children[0].textContent,'Spotify Connect · Speaker-reported unavailable — Start playback from the Spotify app.');
""")


def test_speaker_read_deadline_reports_timeout_and_reenables_refresh():
    checks("""
const originalTimer=global.setTimeout;
let expire;
global.setTimeout=(fn,ms)=>{assert.equal(ms,45000); expire=fn; return 1;};
getResponse=async(url,opts)=>new Promise((resolve,reject)=>opts.signal.addEventListener('abort',()=>reject(new Error('aborted'))));
const pending=ui.open('Living Room',true);
expire(); await pending;
global.setTimeout=originalTimer;
assert.match(el('presets-message').textContent,/timed out/);
assert.equal(el('presets-refresh').disabled,false);
""")


def test_switch_during_rediscovery_does_not_fetch_previous_speaker():
    checks("""
let finish;
getResponse=async url=>url.includes('discover') ? new Promise(resolve=>finish=resolve) : ok({favorites:[],sources:[],presets:[]});
const old=ui.open('Living Room',true);
current='Kitchen'; await ui.open(current);
finish(ok([])); await old;
assert(!calls.some(call=>call.url==='/api/Living%20Room/favorites'));
assert.equal(el('presets-title').textContent,'Presets · Kitchen');
""")
