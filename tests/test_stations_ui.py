"""Offline station page tests. No speaker or radio endpoint is contacted."""
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
const assert=require('node:assert/strict');
const api=require('./app/static/stations.js');
let focused=null;
class Element {
  constructor(tag='div') { this.tagName=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.attrs={};this.isConnected=true; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children=children; }
  addEventListener(name,fn) { this.listeners[name]=fn; }
  setAttribute(name,value) { this.attrs[name]=value; }
  contains(item) { return this===item || this.children.some(child=>child.contains(item)); }
  focus() { focused=this; }
}
const elements=new Map();
function el(id) { if(!elements.has(id))elements.set(id,new Element());return elements.get(id); }
const docListeners={};
const doc={getElementById:el,createElement:tag=>new Element(tag),get activeElement(){return focused;},addEventListener:(name,fn)=>{docListeners[name]=fn;}};
const ok=body=>({ok:true,json:async()=>body});
let response=async()=>ok({stations:[]});
let current='Living Room';
const calls=[],capabilityReads=[],assignments=[],plays=[],schedules=[];
let capabilities=async()=>ok({available:true,mode:'native',requires_wisp_running:true});let favoriteCleared=0;
let view='hub';
const ui=api.create({document:doc,getSpeakers:()=>[{name:'Living Room'},{name:'Kitchen'}],getSpeaker:()=>current,
fetch:async(url,opts)=>{if(url.endsWith('/readiness') || (url.endsWith('/direct-test') && !opts.method)){capabilityReads.push({url,opts});return capabilities(url,opts);} calls.push({url,opts});return response(url,opts);},
navigate:name=>{view=name;ui.onViewChange(name);},back:name=>{view=name;ui.onViewChange(name);},
schedule:(station,speaker)=>schedules.push({station,speaker}),clearFavorite:()=>favoriteCleared++,
assign:(station,speaker)=>assignments.push({station,speaker}),onPlay:(result,speaker,options)=>plays.push({result,speaker,options})});
const station={id:'jazz',name:'Jazz <img>',url:'https://radio.example/jazz'};
const descendants=item=>[item,...item.children.flatMap(descendants)];
const action=(label,index=0)=>descendants(el('stations-list').children[index]).find(child=>child.textContent===label);
const clickAction=label=>{if(label!=='Schedule…')action('⋯').listeners.click();return action(label).listeners.click();};
const key=(element,key)=>element.listeners.keydown({key,preventDefault(){},stopPropagation(){}});
'''
    script = harness + '\n(async()=>{\n' + body + '\n})().catch(e=>{console.error(e);process.exitCode=1;});'
    result = subprocess.run([NODE, '-'], input=script, cwd=ROOT, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_stations_page_accessible_separate_view():
    html = (ROOT / 'app/templates/index.html').read_text()
    assert 'id="view-stations" class="view"' in html
    assert 'id="stations-message" role="status" aria-live="polite"' in html
    assert 'id="stations-title" tabindex="-1"' in html
    assert 'id="btn-hub-stations"' in html
    assert 'id="btn-speaker-stations"' in html
    assert '/app-static/stations.js' in html
    assert 'if (!ready || activeView' in html
    assert 'innerHTML' not in (ROOT / 'app/static/stations.js').read_text()


def test_library_exceeds_six_and_names_render_as_text():
    checks('''
response=async()=>ok({stations:Array.from({length:12},(_,i)=>({...station,id:String(i)}))});
await ui.open();
assert.equal(el('stations-list').children.length,12);
assert.equal(el('stations-list').children[0].children[0].textContent,'Jazz <img>');
assert.equal(calls.length,1);
''')


def test_add_is_library_only_and_rejects_invalid_urls():
    checks('''
await ui.open();
el('station-name').value='Jazz';el('station-url').value='https://user:secret@example.com/live';
await ui.add(); assert.equal(calls.length,1);
el('station-url').value='https://radio.example/live';
response=async(url,opts)=>opts.method==='POST'?ok({station}):ok({stations:[station]});
await ui.add();
const writes=calls.filter(call=>call.opts.method==='POST');
assert.equal(writes.length,1);assert.equal(writes[0].url,'/api/stations');
assert.deepEqual(JSON.parse(writes[0].opts.body),{name:'Jazz',url:'https://radio.example/live'});
assert.match(el('stations-message').textContent,/No playback or preset/);
''')


def test_play_requires_confirmation_and_is_bound_to_speaker():
    checks('''
response=async()=>ok({stations:[station]});await ui.open('speaker');
await clickAction('Test playback…');
assert.equal(calls.length,1);assert.match(el('stations-confirm-text').textContent,/volume 5/);
assert.match(el('stations-confirm-text').textContent,/replace current audio/);
el('stations-speaker').value='Kitchen';el('stations-speaker').listeners.change();
await ui.confirm();assert.equal(calls.length,1);
await clickAction('Test playback…');
response=async()=>ok({state:'accepted',operation:{state:'accepted'}});
await ui.confirm();await ui.confirm();
assert.equal(calls.length,2);assert.equal(calls[1].url,'/api/Kitchen/stations/jazz/play');
assert.deepEqual(JSON.parse(calls[1].opts.body),{confirmed:true});
assert.match(el('stations-message').textContent,/not proof/);assert.equal(plays.length,1);
''')


def test_assign_only_opens_existing_preview_flow():
    checks('''
response=async()=>ok({stations:[station]});await ui.open();
await clickAction('Assign to speaker button…');
assert.deepEqual(assignments,[{station,speaker:'Living Room'}]);
assert.equal(calls.length,1);
''')


def test_no_speaker_does_not_prevent_library_management():
    checks('''
current=null;response=async()=>ok({stations:[station]});await ui.open();
assert.equal(el('stations-speaker').value,'');assert.equal(action('Test playback…').disabled,true);
assert.equal(action('Assign to speaker button…').disabled,true);assert.equal(action('Remove…').disabled,false);
await clickAction('Remove…');
assert.match(el('stations-confirm-text').textContent,/stay intact/);
assert.match(el('stations-confirm-text').textContent,/retained privately/);
response=async()=>ok({removed:true});await ui.confirm();
assert.equal(calls[1].opts.method,'DELETE');assert.equal(calls[1].url,'/api/stations/jazz');
assert.match(el('stations-message').textContent,/current audio stay intact/);
''')


def test_stale_read_cannot_replace_new_open_or_reopen_page():
    checks('''
const pending=[];response=()=>new Promise(resolve=>pending.push(resolve));
const first=ui.open();ui.close();const second=ui.open();
pending[1](ok({stations:[station]}));await second;
pending[0](ok({stations:[]}));await first;
assert.equal(el('stations-list').children[0].children[0].textContent,station.name);
assert.equal(calls[0].opts.signal.aborted,true);
''')


def test_duplicate_write_suppressed_and_navigation_never_aborts_write():
    checks('''
response=async()=>ok({stations:[station]});await ui.open();await clickAction('Test playback…');
let finish;response=()=>new Promise(resolve=>finish=resolve);
const write=ui.confirm();await ui.confirm();ui.close();
assert.equal(calls.length,2);assert.equal(calls[1].opts.signal,undefined);
await ui.open();assert.equal(el('stations-refresh').disabled,true);
finish(ok({state:'accepted'}));await write;
assert.equal(el('stations-refresh').disabled,false);assert.equal(plays.length,0);
assert.match(el('stations-message').textContent,/earlier request finished/);
''')


def test_network_failure_does_not_retry_or_claim_playback():
    checks('''
response=async()=>ok({stations:[station]});await ui.open();await clickAction('Test playback…');
response=async()=>{throw new Error('Disconnected');};await ui.confirm();await ui.confirm();
assert.equal(calls.length,2);assert.equal(plays.length,0);
assert.match(el('stations-message').textContent,/may have started/);
''')


def test_invalid_streams_never_transmitted():
    checks('''
for(const url of ['javascript:alert(1)','https://u:p@example.com/live','https://example.com/?token=secret','https://example.com/#fragment','not a url'])assert.equal(api.validStream(url),false);
assert.equal(api.validStream('https://radio.example/live.mp3'),true);
''')


def test_station_can_open_schedule_without_preset_assignment():
    checks('''
response=async()=>ok({stations:[station]});await ui.open();
await clickAction('Schedule…');
assert.deepEqual(schedules,[{station,speaker:'Living Room'}]);
assert.equal(assignments.length,0);assert.equal(calls.length,1);
''')


def test_station_schedule_retains_removed_binding_and_failed_load():
    checks('''
response=async()=>ok({stations:[]});await ui.loadSchedule('removed');
assert.equal(ui.scheduleValue(),'removed');
assert.match(el('f-station').children[1].textContent,/binding retained/);
assert.equal(favoriteCleared,1);
response=async()=>{throw new Error('Offline');};await ui.loadSchedule('saved');
assert.equal(ui.scheduleValue(),'saved');
assert.match(el('station-schedule-help').textContent,/binding is retained/);
ui.clearScheduleChoice();assert.equal(ui.scheduleValue(),null);
''')


def test_station_schedule_ignores_stale_reads_and_clears_favorite():
    checks('''
const pending=[];response=()=>new Promise(resolve=>pending.push(resolve));
const first=ui.loadSchedule('old');const second=ui.loadSchedule('new');
pending[1](ok({stations:[{...station,id:'new'}]}));await second;
pending[0](ok({stations:[{...station,id:'old'}]}));await first;
assert.equal(ui.scheduleValue(),'new');assert.equal(el('f-station').children.length,2);
el('f-station').listeners.change();assert.equal(favoriteCleared,3);
''')


def test_template_serializes_station_binding_without_preset_requirement():
    html = (ROOT / 'app/templates/index.html').read_text()
    assert 'id="f-station"' in html
    assert '...scheduleSource(),' in html
    assert 'window.wispStations.loadSchedule(data ? data.station_id : null)' in html
    assert "favorite_id: favorite || null" in html
    assert "preset: kind === 'preset'" in html


def test_starters_are_seed_data_not_an_import_button():
    html = (ROOT / 'app/templates/index.html').read_text()
    script = (ROOT / 'app/static/stations.js').read_text()
    assert 'stations-starter' not in html
    assert '/api/stations/starter' not in script


def test_seed_warning_does_not_hide_existing_station_actions():
    checks("""
response=async()=>ok({stations:[station],seed_warning:'Station storage is full. Seed not applied.'});
await ui.open();
assert.match(el('stations-message').textContent,/Seed not applied/);
assert.equal(el('stations-list').children.length,1);
assert.equal(action('Remove…').disabled,false);
""")


def test_menu_keyboard_dismissal_and_one_open_at_a_time():
    checks("""
response=async()=>ok({stations:[station,{...station,id:'second',name:'Second'}]});await ui.open();
const toggle=action('⋯'),menu=action('Remove…').attrs.role;
assert.equal(toggle.attrs['aria-haspopup'],'menu');assert.match(toggle.attrs['aria-label'],/Jazz <img>/);
assert.equal(menu,'menuitem');assert.equal(toggle.attrs['aria-expanded'],'false');
key(toggle,'ArrowDown');assert.equal(focused,action('Test playback…'));
const panel=action('Test playback…').attrs.role && action('⋯').attrs['aria-controls'];assert.equal(panel,'station-menu-0');
const menuNode=descendants(el('stations-list').children[0]).find(x=>x.attrs.role==='menu');
key(menuNode,'ArrowDown');assert.equal(focused,action('Assign to speaker button…'));
key(menuNode,'End');assert.equal(focused,action('Remove…'));
key(menuNode,'ArrowDown');assert.equal(focused,action('Test playback…'));
key(menuNode,'Escape');assert.equal(focused,toggle);assert.equal(menuNode.hidden,true);
key(toggle,'ArrowUp');assert.equal(focused,action('Remove…'));
key(menuNode,'Tab');assert.equal(focused,toggle);assert.equal(menuNode.hidden,true);
toggle.listeners.click();action('⋯',1).listeners.click();assert.equal(menuNode.hidden,true);
assert.equal(action('⋯',1).attrs['aria-expanded'],'true');
docListeners.pointerdown({target:el('stations-title')});assert.equal(action('⋯',1).attrs['aria-expanded'],'false');
toggle.listeners.click();docListeners.focusin({target:el('station-name')});assert.equal(menuNode.hidden,true);
toggle.listeners.click();ui.close();assert.equal(menuNode.hidden,true);assert.equal(calls.length,1);
""")


def test_disabled_menu_items_are_skipped_and_refresh_closes_menu():
    checks("""
current=null;response=async()=>ok({stations:[station]});await ui.open();
key(action('⋯'),'ArrowDown');assert.equal(focused,action('Remove…'));
await ui.refresh();assert.equal(action('⋯').attrs['aria-expanded'],'false');
assert.equal(el('stations-confirmation').hidden,true);
action('⋯').listeners.click();el('stations-speaker').value='Kitchen';el('stations-speaker').listeners.change();
assert.equal(action('⋯').attrs['aria-expanded'],'false');
await clickAction('Test playback…');assert.match(el('stations-confirm-text').textContent,/Kitchen/);
assert.equal(action('⋯').attrs['aria-expanded'],'false');assert.equal(focused,el('stations-confirm'));
el('stations-cancel').listeners.click();assert.equal(focused,action('⋯'));assert.equal(el('stations-confirmation').hidden,true);
""")


def test_direct_test_requires_separate_risk_consent_and_never_claims_quiet():
    checks('''
response=async()=>ok({stations:[station]}); await ui.open();
capabilities=async url=>ok(url.endsWith('/readiness') ? {available:false,reason:'Configure WISP_BASE_URL in Settings'} : {available:true,experimental:true,quiet_start_guaranteed:false,duration_seconds:10,target_volume:5});
await clickAction('Test playback…');
assert.equal(capabilityReads.length,2); assert.equal(calls.length,1);
assert.equal(el('stations-direct-risk').hidden,false);
assert.equal(el('stations-accept-risk').checked,false);
assert.equal(el('stations-confirm').disabled,true);
assert.match(el('stations-confirm-text').textContent,/remembered volume/);
assert.match(el('stations-confirm-text').textContent,/closing the app does not stop/);
assert.doesNotMatch(el('stations-confirm').textContent,/quiet|Play at volume 5/i);
await ui.confirm(); assert.equal(calls.length,1);
el('stations-accept-risk').checked=true; el('stations-accept-risk').listeners.change();
assert.equal(el('stations-confirm').disabled,false);
response=async()=>ok({state:'accepted',operation:{state:'accepted'}});
await ui.confirm(); await ui.confirm();
assert.equal(calls.length,2);
assert.equal(calls[1].url,'/api/Living%20Room/stations/jazz/direct-test');
assert.deepEqual(JSON.parse(calls[1].opts.body),{confirmed:true,accept_startup_volume_risk:true});
assert.equal(calls[1].opts.signal,undefined);
assert.match(el('stations-message').textContent,/not confirmed playing/);
assert.equal(plays[0].options.direct,true);
assert.doesNotMatch(el('stations-message').textContent,/Quiet/);
''')


def test_direct_consent_resets_when_speaker_changes_and_cannot_authorize_another_test():
    checks('''
response=async()=>ok({stations:[station]}); await ui.open();
capabilities=async url=>ok(url.endsWith('/readiness') ? {available:false,reason:'Configure WISP_BASE_URL in Settings'} : {available:true,experimental:true,quiet_start_guaranteed:false,duration_seconds:10,target_volume:5});
await clickAction('Test playback…');
el('stations-accept-risk').checked=true;
el('stations-speaker').value='Kitchen'; el('stations-speaker').listeners.change();
await ui.confirm(); assert.equal(calls.length,1);
await clickAction('Test playback…');
assert.equal(el('stations-accept-risk').checked,false);
assert.equal(el('stations-confirm').disabled,true);
assert.match(el('stations-confirm-text').textContent,/Kitchen/);
''')


def test_native_readiness_uses_existing_quiet_path_without_experimental_request():
    checks('''
response=async()=>ok({stations:[station]}); await ui.open();
await clickAction('Test playback…');
assert.equal(capabilityReads.length,1);
assert.equal(el('stations-direct-risk').hidden,true);
assert.equal(el('stations-confirm').disabled,false);
response=async()=>ok({state:'accepted'}); await ui.confirm();
assert.equal(calls[1].url,'/api/Living%20Room/stations/jazz/play');
assert.deepEqual(JSON.parse(calls[1].opts.body),{confirmed:true});
''')


def test_unknown_capability_or_unsupported_station_never_falls_back_or_writes():
    checks('''
response=async()=>ok({stations:[station]}); await ui.open();
for (const responseBody of [{}, {available:false}, {available:true,experimental:true,quiet_start_guaranteed:false,duration_seconds:60,target_volume:5}, {available:true,experimental:true,quiet_start_guaranteed:true}]) {
 capabilities=async url=>ok(url.endsWith('/readiness') ? {available:false,reason:'Configure WISP_BASE_URL in Settings'} : responseBody);
 await clickAction('Test playback…'); await ui.confirm();
 assert.equal(el('stations-confirmation').hidden,true); assert.equal(calls.length,1);
}
capabilities=async()=>ok({radio:{available:true}}); // old server cannot authorize new fallback
await clickAction('Test playback…'); await ui.confirm();
assert.equal(calls.length,1);
assert.match(el('stations-message').textContent,/No playback request was sent/);
''')


def test_stale_capability_read_cannot_confirm_for_new_speaker_or_after_navigation():
    checks('''
response=async()=>ok({stations:[station]}); await ui.open();
let finish; capabilities=()=>new Promise(resolve=>finish=resolve);
const pending=clickAction('Test playback…');
el('stations-speaker').value='Kitchen'; el('stations-speaker').listeners.change();
finish(ok({available:true,mode:'native'})); await pending;
assert.equal(el('stations-confirmation').hidden,true);
assert.equal(capabilityReads[0].opts.signal.aborted,true);
const next=clickAction('Test playback…'); ui.close();
finish(ok({available:true,mode:'native'})); await next;
assert.equal(el('stations-confirmation').hidden,true); await ui.confirm();
assert.equal(calls.length,1);
''')


def test_ready_relay_uses_normal_play_without_direct_volume_risk():
    checks(r'''
response=async()=>ok({stations:[station]}); await ui.open();
capabilities=async()=>ok({available:true,mode:'relay',requires_idle:true,requires_wisp_running:true,volume_gated:true,hardware_verified:false});
await clickAction('Test playback…');
assert.equal(capabilityReads.length,1);
assert.match(capabilityReads[0].url,/stations\/jazz\/readiness$/);
assert.equal(el('stations-direct-risk').hidden,true);
assert.match(el('stations-confirm-text').textContent,/requires an idle speaker/);
assert.match(el('stations-confirm-text').textContent,/Wisp must remain running/);
response=async()=>ok({state:'accepted'}); await ui.confirm();
assert.match(calls[1].url,/\/play$/);
assert.deepEqual(JSON.parse(calls[1].opts.body),{confirmed:true});
''')


def test_schedule_readiness_shows_backend_reason_and_keeps_choice():
    checks('''
response=async()=>ok({stations:[station]});
capabilities=async()=>ok({available:false,mode:'unavailable',reason:'Configure WISP_BASE_URL with an HTTP address reachable by the speaker.'});
await ui.loadSchedule(station.id);
assert.equal(el('f-station').value,station.id);
assert.match(el('station-schedule-help').textContent,/Configure WISP_BASE_URL/);
assert.match(el('station-schedule-help').textContent,/selection is kept/);
capabilities=async()=>ok({available:true,mode:'relay',requires_wisp_running:true,hardware_verified:false});
await el('f-station').listeners.change();
assert.match(el('station-schedule-help').textContent,/Wisp must stay running/);
assert.match(el('station-schedule-help').textContent,/playback still needs verification/);
assert.equal(el('f-station').value,station.id);
''')


def test_stale_schedule_readiness_never_replaces_new_selection_or_navigation():
    checks('''
response=async()=>ok({stations:[station]});
await ui.loadSchedule(station.id);
let finish; capabilities=()=>new Promise(resolve=>finish=resolve);
const old=el('f-station').listeners.change();
el('f-station').value=''; await el('f-station').listeners.change();
finish(ok({available:false,reason:'OLD'})); await old;
assert.doesNotMatch(el('station-schedule-help').textContent,/OLD/);
el('f-station').value=station.id;
const next=el('f-station').listeners.change(); ui.onViewChange('speaker');
finish(ok({available:false,reason:'STALE'})); await next;
assert.doesNotMatch(el('station-schedule-help').textContent,/STALE/);
''')
