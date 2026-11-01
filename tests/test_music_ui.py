"""Offline Music/draft-radio interaction checks; every request is a fixture."""
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')

HARNESS = r'''
const assert=require('node:assert/strict');
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.checked=false;this.scrollTop=0;this.dataset={};this.attrs={};this.isConnected=true;const classes=new Set();this.classList={add:n=>classes.add(n),remove:n=>classes.delete(n),contains:n=>classes.has(n),toggle:(n,on)=>on?classes.add(n):classes.delete(n)};}
 append(...c){this.children.push(...c);}replaceChildren(...c){this.children=c;}addEventListener(n,f){this.listeners[n]=f;}setAttribute(n,v){this.attrs[n]=v;}focus(){focused=this;}scrollIntoView(){}contains(item){return this===item||this.children.some(c=>c.contains?.(item));}
}
let focused=null;const elements=new Map();const el=id=>{if(!elements.has(id)){const item=new Element();item.id=id;elements.set(id,item);}return elements.get(id);};
const doc={getElementById:el,createElement:tag=>new Element(tag),addEventListener(){},get activeElement(){return focused;}};
const ok=body=>({ok:true,json:async()=>body});let respond=async()=>ok({libraries:[],speakers:[],stations:[]});const calls=[];let view='hub',scheduled=null;
const devices=[{name:'Living Room',device_id:'ABC'},{name:'Kitchen',device_id:'DEF'}];
const fetch=async(path,options={})=>{calls.push({path,options});return respond(path,options);};
const lib={id:'nas',name:'Shared NAS',added:true,observations:{ABC:{speaker:'Living Room',state:'ready',source_id:'source'}}};
const folder={id:'folder',name:'Morning',type:'dir',is_dir:true,is_collection:true,playable:true,presetable:true,preview_available:true};
const collection={version:1,library_id:'nas',speaker_id:'DEF',content:{name:'Morning',type:'dir',source:'STORED_MUSIC',sourceAccount:'nas/0',location:'native'},ancestors:[]};
'''

def check(module, body):
    assert NODE, 'Node is required for these isolated UI checks'
    setup = ("const api=require('./app/static/music.js');const ui=api.create({document:doc,fetch,getSpeakers:()=>devices,getSpeaker:()=> 'Kitchen',navigate:n=>{view=n;ui.onViewChange(n);},radio:()=>{view='stations';},schedule:(value,speaker)=>{scheduled={value,speaker};},cancelSchedule:()=>{view='form';}});" if module == 'music' else "const api=require('./app/static/stations.js');const ui=api.create({document:doc,fetch,getSpeakers:()=>devices,getSpeaker:()=> 'Living Room',navigate:n=>{view=n;ui.onViewChange(n);},back:n=>{view=n;},clearFavorite(){},schedule(){},onPlay(){}});")
    script = HARNESS + setup + '\n(async()=>{\n' + body + '\n})().catch(e=>{console.error(e);process.exitCode=1;});'
    result = subprocess.run([NODE, '-'], input=script, text=True, encoding='utf-8', cwd=ROOT, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_browse_back_restores_loaded_pages_scroll_and_never_plays():
    check('music', r'''
respond=async(path,opts)=>{if(path==='/api/music-libraries')return ok({libraries:[lib],speakers:devices});const data=JSON.parse(opts.body);return ok({speaker:'Living Room',items:data.container_id?[{...folder,id:'child',name:'Child'}]:data.start===2?[{...folder,id:'second'}]:[folder],next_start:!data.container_id&&data.start===1?2:null});};
await ui.open();el('music-library-list').children[0].children.find(e=>e.textContent==='Browse').listeners.click();await new Promise(r=>setImmediate(r));
el('music-body').scrollTop=220;await el('music-more').onclick();assert.equal(el('music-items').children.length,2);assert.equal(el('music-body').scrollTop,220);
el('music-body').scrollTop=305;await ui.inspect(folder);ui.back();assert.equal(el('music-items').children.length,2);assert.equal(el('music-body').scrollTop,305);assert.equal(calls.filter(c=>/play|preset-plans/.test(c.path)).length,0);
''')


def test_playlist_preview_unavailable_and_tracks_inspect_only():
    check('music', r'''
respond=async(path)=>ok(path==='/api/music-libraries'?{libraries:[lib],speakers:devices}:{speaker:'Living Room',items:[folder]});await ui.open();await el('music-library-list').children[0].children.find(e=>e.textContent==='Browse').listeners.click();
await ui.inspect({...folder,id:'list',type:'playlist',is_dir:false,presetable:false,preview_available:false});assert.equal(el('music-items').children[0].textContent,'Preview unavailable');assert.equal(el('music-play').disabled,false);assert.equal(el('music-schedule').disabled,false);assert.equal(el('music-assign').disabled,true);assert.match(el('music-actions-help').textContent,/cannot be assigned/);
const count=calls.length;await ui.inspect({id:'track',type:'track',name:'Song'});assert.equal(calls.length,count);assert.match(el('music-message').textContent,/Track information only/);
''')


def test_schedule_resolves_chosen_target_and_does_not_play_or_assign():
    check('music', r'''
respond=async(path)=>ok(path==='/api/music-libraries'?{libraries:[lib],speakers:devices}:path.endsWith('/resolve')?{collection,speaker_id:'DEF',browse_item_id:'target-token'}:{speaker:'Living Room',items:[folder]});await ui.open();await el('music-library-list').children[0].children.find(e=>e.textContent==='Browse').listeners.click();await ui.inspect(folder);ui.startCollectionAction('schedule');el('music-target').value='Kitchen';await ui.confirmAction();assert.deepEqual(scheduled,{value:collection,speaker:'Kitchen'});assert.equal(JSON.parse(calls.find(c=>c.path.endsWith('/resolve')).options.body).speaker,'Kitchen');assert.equal(calls.filter(c=>/\/play$|preset-plans/.test(c.path)).length,0);
''')


def test_assignment_reviews_existing_six_slots_and_explicit_replacement():
    check('music', r'''
respond=async(path)=>ok(path==='/api/music-libraries'?{libraries:[lib],speakers:devices}:path.endsWith('/resolve')?{collection,speaker_id:'DEF',browse_item_id:'target',presets:[{slot:2,name:'Old collection'}]}:path.endsWith('/preset-plans')?{plan_id:'p',slot:2,replaces:'Old collection',impacts:['Wakeup'],warning:'Review pauses'}:path.endsWith('/confirm')?{state:'readback_matched'}:{speaker:'Living Room',items:[folder]});await ui.open();await el('music-library-list').children[0].children.find(e=>e.textContent==='Browse').listeners.click();await ui.inspect(folder);ui.startCollectionAction('assign');el('music-target').value='Kitchen';await ui.confirmAction();assert.equal(el('music-slot').children.length,6);assert.equal(el('music-slot').children[1].textContent,'Button 2: Old collection');el('music-slot').value='2';await ui.confirmAction();assert.equal(el('music-review-confirm').textContent,'Replace Button 2');assert.match(el('music-review-text').textContent,/Old collection.*Wakeup/);await ui.confirmAction();assert.equal(calls.filter(c=>c.path.endsWith('/confirm')).length,1);assert.equal(calls.filter(c=>c.path.endsWith('/play')).length,0);
''')


def test_lost_library_add_ack_requires_readback_before_another_write():
    check('music', r'''
respond=async(path)=>{if(path.endsWith('/add'))throw new Error('Response lost');if(path.endsWith('/check'))return ok({library:lib,retry_allowed:false});return ok({libraries:[lib],speakers:devices});};await ui.open();const card=el('music-library-list').children[0];card.children.find(c=>c.tagName==='details').children.find(c=>c.textContent==='Add Again').listeners.click();el('music-target').value='Kitchen';await ui.confirmAction();assert.equal(el('music-review-confirm').textContent,'Check Again');await el('music-review-confirm').listeners.click();assert.equal(calls.filter(c=>c.path.endsWith('/add')).length,1);assert.equal(calls.filter(c=>c.path.endsWith('/check')).length,1);
''')


def test_radio_draft_requires_reported_playing_audible_confirmation_and_stopped():
    check('stations', r'''
let stopped=false;respond=async(path,opts)=>{if(path==='/api/stations')return ok({stations:[]});if(path==='/api/station-drafts')return ok({draft:{id:'draft',name:'Jazz',url:'https://radio.example/live'}});if(path.endsWith('/test'))return ok({draft:{id:'draft'},operation:{operation_id:'original',state:'accepted'}});if(path.endsWith('/stop')){stopped=true;return ok({operation:{operation_id:'stop'}});}if(path.endsWith('/save'))return ok({station:{id:'saved'}});return ok({draft:{id:'draft',speaker:'Living Room',speaker_id:'ABC',operation_id:'original',observed_playing:true,stopped_verified:stopped},operation:{operation_id:stopped?'stop':'original',state:stopped?'completed':'playing'},can_save:stopped});};
await ui.open();el('station-name').value='Jazz';el('station-url').value='https://radio.example/live';await ui.add();assert.equal(calls.filter(c=>c.path.endsWith('/save')).length,0);await ui.testDraft();await ui.checkDraft();assert.equal(el('station-draft-audible').disabled,false);el('station-draft-audible').checked=true;el('station-draft-audible').listeners.change();assert.equal(el('stations-add').disabled,true);await ui.stopDraft();assert.equal(el('stations-add').disabled,false);await ui.add();const save=calls.find(c=>c.path.endsWith('/save'));assert.equal(JSON.parse(save.options.body).operation_id,'original');assert.equal(JSON.parse(save.options.body).audible_confirmed,true);assert.equal(calls.filter(c=>c.path.endsWith('/test')).length,1);ui.close();
''')


def test_lost_radio_test_result_can_recover_exact_original_stop_identity():
    check('stations', r'''
respond=async(path)=>{if(path==='/api/stations')return ok({stations:[]});if(path==='/api/station-drafts')return ok({draft:{id:'draft'}});if(path.endsWith('/test'))throw new Error('Lost response');if(path.endsWith('/stop'))return ok({operation:{operation_id:'stop'}});return ok({draft:{id:'draft',speaker:'Living Room',speaker_id:'ABC',operation_id:'original',observed_playing:true},operation:{operation_id:'original',state:'playing'},can_save:false});};await ui.open();el('station-name').value='Jazz';el('station-url').value='https://radio.example/live';await ui.testDraft();await ui.checkDraft();await ui.stopDraft();const stop=calls.find(c=>c.path.endsWith('/stop'));assert.deepEqual(JSON.parse(stop.options.body),{speaker_id:'ABC',operation_id:'original'});assert.equal(el('station-name').value,'Jazz');assert.equal(el('station-url').value,'https://radio.example/live');assert.equal(el('stations-add').disabled,true);ui.close();
''')


def test_phone_navigation_and_collection_source_are_additive():
    html=(ROOT/'app/templates/index.html').read_text(encoding='utf-8')
    css=(ROOT/'app/static/styles.css').read_text(encoding='utf-8')
    assert 'id="dock-speakers"' in html and 'id="dock-music"' in html
    assert 'id="btn-refresh" type="button">Refresh Speakers' in html
    assert "collection:null, station_id: station || null, favorite_id: favorite || null" in html
    assert "source_kind:'collection'" in html
    assert 'Change music</button>' in html
    assert 'fade_in_duration ?? 300' in html and 'fade_out_duration ?? 60' in html
    assert 'padding-bottom: calc(var(--collection-actions-height) + 36px)' in css
    assert 'bottom: var(--dock-height)' in css
    assert 'innerHTML' not in (ROOT/'app/static/music.js').read_text(encoding='utf-8')
    source=re.findall(r'<script>(.*?)</script>',html,re.S)[-1]
    result=subprocess.run([NODE,'--check'],input=source,text=True,encoding='utf-8',capture_output=True,timeout=10)
    assert result.returncode == 0,result.stderr


def test_unknown_radio_test_blocks_retry_until_read_only_check_proves_safe():
    check('stations', r"""
let safe=false;respond=async(path)=>{if(path==='/api/stations')return ok({stations:[]});if(path==='/api/station-drafts')return ok({draft:{id:'draft',state:'untested'}});if(path.endsWith('/test'))throw new Error('Lost response');return ok({draft:{id:'draft',speaker:'Living Room',speaker_id:'ABC',operation_id:'original',state:safe?'test_unavailable':'unknown',retry_ready:safe},operation:{operation_id:'original',state:'unknown'},can_save:false});};await ui.open();el('station-name').value='Jazz';el('station-url').value='https://radio.example/live';await ui.testDraft();await ui.testDraft();assert.equal(calls.filter(c=>c.path.endsWith('/test')).length,1);safe=true;await ui.checkDraft();await ui.testDraft();assert.equal(calls.filter(c=>c.path.endsWith('/test')).length,2);assert.equal(el('stations-add').disabled,true);ui.close();
""")


def test_failed_playlist_preview_retains_actions_and_retry_without_playing():
    check('music', r"""
const playlist={...folder,id:'playlist',type:'playlist',is_dir:false};respond=async(path,opts)=>{if(path==='/api/music-libraries')return ok({libraries:[lib],speakers:devices});const data=JSON.parse(opts.body);if(data.container_id==='playlist')throw new Error('Contents read failed');return ok({speaker:'Living Room',items:[playlist]});};await ui.open();await el('music-library-list').children[0].children.find(e=>e.textContent==='Browse').listeners.click();await ui.inspect(playlist);assert.equal(el('music-items').children[0].textContent,'Preview unavailable');assert.equal(el('music-retry').hidden,false);assert.equal(el('music-play').disabled,false);assert.equal(el('music-schedule').disabled,false);assert.match(el('music-message').textContent,/Contents read failed/);assert.equal(calls.filter(c=>c.path.endsWith('/play')).length,0);
""")


def test_existing_collection_speaker_change_preserves_origin_and_revalidates():
    import importlib.util
    spec=importlib.util.spec_from_file_location('existing_playback_ui',ROOT/'tests/test_playback_ui.py')
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.run_ui_checks(r"""
      document.querySelector=()=>element('quick');
      const day={dataset:{day:'monday'},classList:{toggle(){},add(){},remove(){}}};
      document.querySelectorAll=selector=>selector==='.day-chip.active'||selector==='.day-chip'?[day]:[];
      discoveredSpeakers=[{name:'Living Room',device_id:'ABC'},{name:'Kitchen',device_id:'DEF'}];
      currentSpeaker='Living Room';
      const original={version:1,library_id:'opaque-library-id',speaker_id:'ABC',content:{name:'Morning collection',source:'STORED_MUSIC',sourceAccount:'nas/0',location:'old-token',type:'dir'},ancestors:[]};
      const existing={name:'Wakeup',speaker_id:'ABC',collection:original,on_time:'06:00',off_time:'07:00',days:['monday'],volume:8,fade_in_duration:0,fade_out_duration:0,paused:false};
      const reads=[],writes=[];
      fetch=async(path,options={})=>{if(path==='/api/collections/resolve'){const request=JSON.parse(options.body);reads.push(request);return {ok:true,json:async()=>({collection:{...request.collection,speaker_id:request.speaker==='Kitchen'?'DEF':'ABC',content:{...request.collection.content,location:request.speaker==='Kitchen'?'target-native-token':'old-token'}}})};}if(path.endsWith('/schedules')&&options.method==='POST'){writes.push({path,payload:JSON.parse(options.body)});return {ok:true};}return {ok:true,json:async()=>({last_outcome:null,schedules:[]})};};
      window.wispMusic={onViewChange(){},libraryName(){return 'Shared Music';},open(){showView('music');}};
      openForm(existing);await checkCollectionChoice();
      assert.equal(editingOrigin.speaker,'Living Room');assert.equal(editingOrigin.collection.content.location,'old-token');
      element('f-collection-speaker').value='Kitchen';
      const targetCheck=checkCollectionChoice();assert.equal(element('btn-save').disabled,true);await targetCheck;
      assert.equal(currentSpeaker,'Kitchen');assert.equal(collectionChoice.speaker_id,'DEF');assert.equal(editingOrigin.speaker,'Living Room');assert.equal(existing.collection.speaker_id,'ABC');
      assert.equal(reads.at(-1).speaker,'Kitchen');assert.equal(element('f-name').value,'Wakeup');assert.equal(fadeIn,0);assert.equal(fadeOut,0);
      element('collection-change-music').listeners.click();assert.equal(activeView,'music');showView('form');changingMusic=false;
      assert.equal(editingOrigin.speaker,'Living Room');assert.equal(collectionChoice.content.location,'target-native-token');assert.equal(element('f-name').value,'Wakeup');
      await element('btn-save').listeners.click();assert.equal(writes.length,1);
      const saved=writes[0];assert.equal(saved.path,'/api/Kitchen/schedules');assert.equal(saved.payload.previous_speaker,'Living Room');assert.equal(saved.payload.previous_speaker_id,'ABC');assert.equal(saved.payload.previous_name,'Wakeup');assert.deepEqual(saved.payload.previous_collection,original);assert.equal(saved.payload.collection.speaker_id,'DEF');assert.equal(saved.payload.collection.content.location,'target-native-token');assert.equal(saved.payload.fade_in_duration,0);assert.equal(saved.payload.fade_out_duration,0);
      let returned;openSpeaker=name=>{returned=name;};element('btn-back-speaker').listeners.click();assert.equal(returned,'Living Room');
      assert.equal(element('collection-schedule-name').textContent.includes('opaque-library-id'),false);
    """)


def test_remove_retry_requires_conclusive_check_and_fresh_review_confirmation():
    check('music', r"""
let removals=0,reviews=0;respond=async(path,options)=>{if(path==='/api/music-libraries')return ok({libraries:[lib],speakers:devices});if(path.endsWith('/removal-plan'))return ok({plan_id:'plan-'+(++reviews),library:lib,warning:'May propagate',impacts:[],buttons:[]});if(path.endsWith('/remove')){removals++;return ok(removals===1?{library:lib,state:'unknown',retry_allowed:false,message:'Unknown; Check Again'}:{library:{...lib,added:false},state:'not_registered',retry_allowed:false});}if(path.endsWith('/check'))return ok({library:lib,state:'ready',retry_allowed:true,message:'Prior removal did not apply'});return ok({});};
await ui.open();const card=el('music-library-list').children[0];card.children.find(c=>c.tagName==='details').children.find(c=>c.textContent==='Remove from speaker').listeners.click();el('music-target').value='Kitchen';await ui.confirmAction();await ui.confirmAction();assert.equal(removals,1);assert.equal(el('music-review-confirm').textContent,'Check Again');await el('music-review-confirm').listeners.click();assert.equal(removals,1);assert.equal(el('music-review-confirm').textContent,'Review removal');await ui.confirmAction();assert.equal(reviews,2);await ui.confirmAction();assert.equal(removals,2);const writes=calls.filter(c=>c.path.endsWith('/remove'));assert.equal(JSON.parse(writes[0].options.body).retry,undefined);assert.equal(JSON.parse(writes[1].options.body).retry,true);assert.equal(JSON.parse(writes[1].options.body).plan_id,'plan-2');
""")


def test_change_music_to_radio_preserves_existing_draft_and_source_origin():
    import importlib.util
    spec=importlib.util.spec_from_file_location('existing_playback_ui',ROOT/'tests/test_playback_ui.py')
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.run_ui_checks(r"""
      document.querySelector=()=>element('quick');
      const day={dataset:{day:'tuesday'},classList:{toggle(){},add(){},remove(){}}};
      document.querySelectorAll=selector=>selector==='.day-chip.active'||selector==='.day-chip'?[day]:[];
      currentSpeaker='Living Room';discoveredSpeakers=[{name:'Living Room'},{name:'Kitchen'}];
      const original={version:1,library_id:'nas',speaker_id:'ABC',content:{name:'Morning',source:'STORED_MUSIC',sourceAccount:'nas/0',location:'original',type:'dir'},ancestors:[]};
      const existing={name:'Wakeup',speaker_id:'ABC',collection:original,on_time:'06:00',off_time:'07:00',days:['monday'],volume:8,fade_in_duration:0,fade_out_duration:0,paused:true,review_token:'original-review'};
      window.wispStations={loadSchedule:id=>{element('f-station').value=id||'';},onViewChange(){}};
      const writes=[];fetch=async(path,options={})=>{if(path==='/api/collections/resolve')return {ok:true,json:async()=>({collection:original})};if(options.method==='POST'&&path.endsWith('/schedules')){writes.push({path,payload:JSON.parse(options.body)});return {ok:true};}return {ok:true,json:async()=>({last_outcome:null,schedules:[]})};};
      openForm(existing);await checkCollectionChoice();element('f-name').value='Quiet edited routine';element('f-on').value='08:10';element('f-off').value='09:20';element('f-volume').value='17';fadeIn=3;fadeOut=4;
      changingMusic=true;showView('music');openSpeaker=()=>{throw new Error('Changing music must not start a new speaker/form flow');};
      scheduleStation({id:'jazz',name:'Jazz'},'Kitchen');
      assert.equal(activeView,'form');assert.equal(editingSchedule,existing);assert.equal(editingOrigin.speaker,'Living Room');assert.equal(currentSpeaker,'Kitchen');assert.equal(element('f-play-kind').value,'radio');assert.equal(element('f-station').value,'jazz');assert.equal(element('f-name').value,'Quiet edited routine');assert.equal(element('f-on').value,'08:10');assert.equal(element('f-off').value,'09:20');assert.equal(element('f-volume').value,'17');assert.equal(fadeIn,3);assert.equal(fadeOut,4);assert.equal(changingMusic,false);
      await element('btn-save').listeners.click();assert.equal(writes.length,1);const saved=writes[0];assert.equal(saved.path,'/api/Kitchen/schedules');assert.equal(saved.payload.previous_name,'Wakeup');assert.equal(saved.payload.previous_speaker,'Living Room');assert.equal(saved.payload.previous_speaker_id,'ABC');assert.deepEqual(saved.payload.previous_collection,original);assert.equal(saved.payload.collection,null);assert.equal(saved.payload.station_id,'jazz');assert.equal(saved.payload.speaker_id,undefined);assert.equal(saved.payload.name,'Quiet edited routine');assert.deepEqual(saved.payload.days,['tuesday']);assert.equal(saved.payload.volume,17);assert.equal(saved.payload.fade_in_duration,180);assert.equal(saved.payload.fade_out_duration,240);assert.equal(saved.payload.paused,true);assert.equal(saved.payload.review_token,'original-review');
    """)
