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
test('daily dates cross month and year without local timezone drift',()=>{assert.deepEqual(datesFor('2026-12-31',3),['2026-12-31','2027-01-01','2027-01-02']);assert.deepEqual(datesFor('',2),[]);});
