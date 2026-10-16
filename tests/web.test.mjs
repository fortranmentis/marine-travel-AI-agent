import test from 'node:test';
import assert from 'node:assert/strict';
import {weatherKind,summarizeWeather,formatIssue} from '../web/weather.js';
import {readNDJSON} from '../web/progress.js';

test('precipitation overrides sky and missing values stay missing',()=>{
 assert.equal(weatherKind({PTY:'1',SKY:'1'}),'rain');
 assert.equal(weatherKind({PTY:'2',SKY:'4'}),'sleet');
 assert.equal(weatherKind({PTY:'3'}),'snow');
 assert.equal(weatherKind({SKY:'4'}),'cloud');
 assert.equal(weatherKind({}),'unknown');
 const summary=summarizeWeather({forecasts:{'0900':{TMP:'0',POP:'0'},'1000':{},'2300':{TMP:'-10',POP:'80'}}},'09:00','18:00');
 assert.deepEqual(summary.temperature,[0,0]);assert.equal(summary.pop,0);assert.equal(summary.wind,null);
 const missing=summarizeWeather({forecasts:{'0900':{TMP:'-999',WSD:'-999'}}},'09:00','18:00');
 assert.equal(missing.temperature,null);assert.equal(missing.wind,null);
});
test('issue time is Korean local time',()=>{
 assert.match(formatIssue('2026-10-15T05:00:00Z'),/14/);
 assert.equal(formatIssue('bad'),'발표 시각 미확인');
});
test('NDJSON parser handles split Korean bytes and emits stages before result',async()=>{
 const text='{"type":"stage","stage":"data","message":"예보 조회"}\n{"type":"result","result":{"status":"ok"}}\n';
 const bytes=new TextEncoder().encode(text),seen=[];
 const body=new ReadableStream({start(controller){for(let i=0;i<bytes.length;i+=7)controller.enqueue(bytes.slice(i,i+7));controller.close();}});
 const result=await readNDJSON(new Response(body),e=>seen.push(e.type));
 assert.equal(result.status,'ok');assert.deepEqual(seen,['stage','result']);
});
test('truncated streams fail explicitly',async()=>{
 await assert.rejects(()=>readNDJSON(new Response('{"type":"stage"}\n'),()=>{}),/결과를 받지/);
});

import {datesFor} from '../web/trip-form.js';
import {transitSummary,transitSourceUrl} from '../web/transit.js';
import {transfersFor} from '../web/journey-transfers.js';
import {ferryState,ferryRows} from '../web/ferries.js';
test('ferry display keeps unknown operations distinct and filters exact route names',()=>{
 const rows=[{licensed_route:'인천-덕적',operation_status:'reported_normal'},{licensed_route:'인천-백령',operation_status:'not_operating'},{licensed_route:'인천-덕적',operation_status:'unknown'}];
 assert.equal(ferryState(rows[0]),'normal');assert.equal(ferryState(rows[1]),'stopped');assert.equal(ferryState(rows[2]),'unknown');
 assert.equal(ferryRows(rows,'인천-덕적').length,2);assert.equal(ferryRows(rows,'덕적').length,0);assert.equal(ferryRows(rows,'').length,3);
});

const stops=()=>[{slot_id:'beach',kind:'tourism',title:'함덕해수욕장',start:'10:00',end:'11:30',lat:33.54,lon:126.66},{slot_id:'meal',kind:'meal',title:'훈남횟집',start:'12:00',end:'12:45',lat:33.54,lon:126.665},{slot_id:'cafe',kind:'cafe',title:'카페',start:'13:15',end:'13:45',lat:33.54,lon:126.67}];
test('transfer cards follow slot IDs across tourism, meal and cafe, not route array order',()=>{
 const day={transport:'car',items:stops()};const route={legs:[{from_slot:'meal',to_slot:'cafe',mode:'walk',status:'available',duration_s:240,distance_m:300},{from_slot:'beach',to_slot:'meal',mode:'car',status:'available',duration_s:361,distance_m:1500,available_minutes:30,fits_schedule:true}]};
 const entries=transfersFor(day,route);assert.deepEqual([...entries.keys()],['meal','cafe']);assert.equal(entries.get('meal').mode,'자차');assert.equal(entries.get('meal').duration,'약 7분');assert.equal(entries.get('meal').distance,'1.5km');assert.equal(entries.get('cafe').mode,'도보');
});
test('unknown and failed transfers never invent zero minutes or a distance',()=>{
 const day={transport:'transit',items:stops()};const route={legs:[{from_slot:'beach',to_slot:'meal',status:'unavailable',reason:'경로 미확보'}]};
 for(const item of transfersFor(day,route).values()){assert.equal(item.available,false);assert.equal(item.duration,'시간 미확인');assert.equal(item.distance,null);assert.ok(item.warning);}
 day.items[1].lat=null;assert.match(transfersFor(day,route).get('meal').warning,/좌표/);
});
test('mixed transit sections, missing distance and insufficient gaps remain distinct',()=>{
 const day={transport:'transit',items:stops()};const route={legs:[{from_slot:'beach',to_slot:'meal',status:'available',mode:'transit',duration_s:2400,distance_m:null,fits_schedule:false,sections:[{mode:'walk'},{mode:'bus'},{mode:'subway'},{mode:'walk'}]}]};
 const item=transfersFor(day,route).get('meal');assert.equal(item.mode,'도보 + 버스 + 지하철');assert.equal(item.distance,null);assert.match(item.warning,/여유 시간/);
});
test('breaks are not destinations and a scheduled ferry never gets a ground transfer over it',()=>{
 const day={transport:'walk',items:stops()};day.items.splice(1,0,{slot_id:'rest',kind:'break',start:'11:30',end:'11:45'});
 assert.deepEqual([...transfersFor(day,{}).keys()],['meal','cafe']);
 day.items.splice(1,0,{slot_id:'boat',kind:'ferry',start:'11:30',end:'11:45'});assert.deepEqual([...transfersFor(day,{}).keys()],['cafe']);
});
test('transit display preserves missing values and links only to the source map',()=>{
 const summary=transitSummary({sections:[{mode:'bus',lines:['2'],minutes:5,start:'인천역',end:'GS칼텍스'}],fare:1500,transfers:0,walking_minutes:7,observed_at:'2026-10-16T00:51:00Z'});
 assert.match(summary.sections,/인천역 → GS칼텍스/);assert.match(summary.metrics,/1,500원/);assert.match(summary.metrics,/환승 0회/);
 assert.match(summary.observed,/9:51/);assert.equal(transitSummary({}).metrics,'');
 assert.equal(transitSourceUrl('javascript:alert(1)'),null);assert.equal(transitSourceUrl('https://evil.example/p/directions/x'),null);
 assert.equal(transitSourceUrl('https://map.naver.com/p/directions/a/b/-/transit'),'https://map.naver.com/p/directions/a/b/-/transit');
});
test('daily dates cross month and year without local timezone drift',()=>{assert.deepEqual(datesFor('2026-12-31',3),['2026-12-31','2027-01-01','2027-01-02']);assert.deepEqual(datesFor('',2),[]);});
