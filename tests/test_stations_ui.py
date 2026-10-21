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
  constructor(tag='div') { this.tagName=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.attrs={}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children=children; }
  addEventListener(name,fn) { this.listeners[name]=fn; }
  setAttribute(name,value) { this.attrs[name]=value; }
  focus() { focused=this; }
}
const elements=new Map();
function el(id) { if(!elements.has(id))elements.set(id,new Element());return elements.get(id); }
const doc={getElementById:el,createElement:tag=>new Element(tag)};
const ok=body=>({ok:true,json:async()=>body});
let response=async()=>ok({stations:[]});
let current='Living Room';
const calls=[],assignments=[],plays=[],schedules=[];let favoriteCleared=0;
let view='hub';
const ui=api.create({document:doc,getSpeakers:()=>[{name:'Living Room'},{name:'Kitchen'}],getSpeaker:()=>current,
fetch:async(url,opts)=>{calls.push({url,opts});return response(url,opts);},
navigate:name=>{view=name;ui.onViewChange(name);},back:name=>{view=name;ui.onViewChange(name);},
schedule:(station,speaker)=>schedules.push({station,speaker}),clearFavorite:()=>favoriteCleared++,
assign:(station,speaker)=>assignments.push({station,speaker}),onPlay:(result,speaker)=>plays.push({result,speaker})});
const station={id:'jazz',name:'Jazz <img>',url:'https://radio.example/jazz'};
const action=label=>el('stations-list').children[0].children.find(child=>child.textContent===label);
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
action('Play…').listeners.click();
assert.equal(calls.length,1);assert.match(el('stations-confirm-text').textContent,/volume 5/);
assert.match(el('stations-confirm-text').textContent,/replace current audio/);
el('stations-speaker').value='Kitchen';el('stations-speaker').listeners.change();
await ui.confirm();assert.equal(calls.length,1);
action('Play…').listeners.click();
response=async()=>ok({state:'accepted',operation:{state:'accepted'}});
await ui.confirm();await ui.confirm();
assert.equal(calls.length,2);assert.equal(calls[1].url,'/api/Kitchen/stations/jazz/play');
assert.deepEqual(JSON.parse(calls[1].opts.body),{confirmed:true});
assert.match(el('stations-message').textContent,/not proof/);assert.equal(plays.length,1);
''')


def test_assign_only_opens_existing_preview_flow():
    checks('''
response=async()=>ok({stations:[station]});await ui.open();
action('Set to a preset…').listeners.click();
assert.deepEqual(assignments,[{station,speaker:'Living Room'}]);
assert.equal(calls.length,1);
''')


def test_no_speaker_does_not_prevent_library_management():
    checks('''
current=null;response=async()=>ok({stations:[station]});await ui.open();
assert.equal(el('stations-speaker').value,'');assert.equal(action('Play…').disabled,true);
assert.equal(action('Set to a preset…').disabled,true);assert.equal(action('Remove…').disabled,false);
action('Remove…').listeners.click();
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
response=async()=>ok({stations:[station]});await ui.open();action('Play…').listeners.click();
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
response=async()=>ok({stations:[station]});await ui.open();action('Play…').listeners.click();
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
action('Schedule…').listeners.click();
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
    assert 'station_id: window.wispStations' in html
    assert 'window.wispStations.loadSchedule(data ? data.station_id : null)' in html
    assert "favorite_id: window.wispPresets && !window.wispStations?.scheduleValue()" in html
    assert "preset:           window.wispStations?.scheduleValue() ||" in html
