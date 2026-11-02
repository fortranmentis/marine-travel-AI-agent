import test from 'node:test';
import assert from 'node:assert/strict';
import {connectLive,readSSE,LiveHTTPError} from '../web/live-events.js';
import {graphModel,putEvent} from '../web/execution-graph.js';
import {restoreRuns,updateRun,updateStep,trimRuns} from '../web/live-model.js';

const tick = () => new Promise(resolve => setImmediate(resolve));
function runtime() {
 const listeners=new Set(), timers=new Map(), calls=[];
 const page={hidden:false,addEventListener(_n,f){listeners.add(f);},removeEventListener(_n,f){listeners.delete(f);}};
 let next=0;
 return {page,timers,calls,
  options:{document:page,setTimeout(f,ms){const id=++next;timers.set(id,{f,ms});return id;},clearTimeout(id){timers.delete(id);}},
  visibility(hidden){page.hidden=hidden;for(const f of [...listeners])f();},
  async runTimer(){const [id,t]=timers.entries().next().value;timers.delete(id);t.f();await tick();},
  fetch(_url,options){return new Promise(resolve=>calls.push({resolve,signal:options.signal,headers:options.headers}));},
 };
}
function liveResponse(signal) {
 return new Response(new ReadableStream({start(c){signal.addEventListener('abort',()=>c.error(new DOMException('aborted','AbortError')),{once:true});c.enqueue(new TextEncoder().encode('event: snapshot\ndata: {"runs":[]}\n\n'));}}));
}

test('late step starts cannot regress completed graph nodes',()=>{
 const m=graphModel({id:'run'});
 putEvent(m,{run_id:'run',step_id:'s',stage:'data',state:'started',at:'2026-11-02T00:00:00Z'});
 putEvent(m,{run_id:'run',step_id:'s',stage:'data',state:'completed',at:'2026-11-02T00:00:02Z',duration_seconds:2});
 putEvent(m,{run_id:'run',step_id:'s',stage:'data',state:'started',at:'2026-11-02T00:00:00Z'});
 assert.equal(m.steps.get('s').state,'completed');assert.equal(m.steps.get('s').duration_s,2);
 assert.equal(m.steps.get('s').started_at,'2026-11-02T00:00:00Z');
});
test('reconnect follows active AI instead of a newer completed request',()=>{
 const cache=new Map([['done',{id:'done',kind:'ai_plan',status:'success',steps:[]}]]);
 const active='old-running';
 const selected=restoreRuns(cache,[{id:active,kind:'ai_plan',status:'running',started_at:'2026-11-01',steps:[]},{id:'done',kind:'ai_plan',status:'success',started_at:'2026-11-02',steps:[]}],'done',true);
 assert.equal(selected,active);
 updateRun(cache,{id:'done',status:'running',steps:[]},selected);assert.equal(cache.get('done').status,'success');
});
test('manual history selection survives snapshots and cache bounds favor active work',()=>{
 const selected={id:'selected',kind:'ai_plan',status:'success',steps:[]};const cache=new Map([[selected.id,selected]]);
 assert.equal(restoreRuns(cache,[],selected.id,false),selected.id);
 for(let i=0;i<60;i++)cache.set('done'+i,{id:'done'+i,status:'success',started_at:String(i).padStart(2,'0'),steps:[]});
 cache.set('running',{id:'running',status:'running',started_at:'00',steps:[]});trimRuns(cache,selected.id);
 assert.equal(cache.size,40);assert.ok(cache.has('running')&&cache.has(selected.id));
 updateStep(cache,'running',{id:'step',state:'completed',duration_s:3},selected.id);
 updateStep(cache,'running',{id:'step',state:'started'},selected.id);
 assert.equal(cache.get('running').steps[0].state,'completed');
});
test('rapid visibility changes keep one current connection and ignore stale data',async()=>{
 const env=runtime(),events=[];const stop=connectLive(()=> 'TOKEN',e=>events.push(e),()=>{},{...env.options,fetch:env.fetch});
 assert.equal(env.calls.length,1);
 env.visibility(false);assert.equal(env.calls.length,1);
 env.visibility(true);assert.ok(env.calls[0].signal.aborted);
 env.visibility(false);assert.equal(env.calls.length,2);
 env.calls[0].resolve(liveResponse(env.calls[0].signal));await tick();assert.equal(events.length,0);
 env.calls[1].resolve(liveResponse(env.calls[1].signal));await tick();assert.equal(events.length,1);
 assert.equal(env.calls[1].headers.Authorization,'Bearer TOKEN');
 stop();await tick();assert.ok(env.calls[1].signal.aborted);assert.equal(env.timers.size,0);
});
test('logout before a delayed response cannot restore events or schedule retry',async()=>{
 const env=runtime(),events=[];const stop=connectLive(()=> 'TOKEN',e=>events.push(e),()=>{},{...env.options,fetch:env.fetch});
 stop();env.calls[0].resolve(new Response('event: snapshot\ndata: {"runs":[]}\n\n'));await tick();
 assert.equal(events.length,0);assert.equal(env.timers.size,0);
});
test('401 HTML responses stop retries and ask for authentication again',async()=>{
 const env=runtime();let unauthorized=0;
 connectLive(()=> 'BAD',()=>{},()=>{},{...env.options,fetch:env.fetch,onUnauthorized(){unauthorized++;}});
 env.calls[0].resolve(new Response('<html>Unauthorized</html>',{status:401,headers:{'Content-Type':'text/html'}}));await tick();
 assert.equal(unauthorized,1);assert.equal(env.timers.size,0);
 env.visibility(true);env.visibility(false);assert.equal(env.calls.length,1);
});
test('temporary failures back off and only one timer survives',async()=>{
 const env=runtime();const stop=connectLive(()=> 'TOKEN',()=>{},()=>{},{...env.options,fetch:env.fetch});
 env.calls[0].resolve(new Response('{}',{status:503}));await tick();assert.equal(env.timers.size,1);
 assert.equal([...env.timers.values()][0].ms,1000);await env.runTimer();
 env.calls[1].resolve(new Response('{}',{status:503}));await tick();assert.equal([...env.timers.values()][0].ms,2000);
 stop();assert.equal(env.timers.size,0);
});
test('aborting while a reader waits cannot dispatch its buffered event',async()=>{
 let source;const abort=new AbortController(),seen=[];
 const response=new Response(new ReadableStream({start(c){source=c;}}));
 const reading=readSSE(response,e=>seen.push(e),abort.signal);abort.abort();source.enqueue(new TextEncoder().encode('event: update\ndata: {"state":"started"}\n\n'));
 await reading;assert.equal(seen.length,0);
});
