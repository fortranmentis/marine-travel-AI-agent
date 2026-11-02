import {createGraph} from './execution-graph.js?v=0.8.0';
import {$, el} from './ui.js?v=0.8.0';

const steps = [['input','조건 확인'],['data','예보·관광정보 조회'],['schedule','일정 구성·검증'],['enrich','지도·사진 준비'],['result','결과 완성']];
let started = 0, timer, lastMessage = '', running = false;
const completed = new Set();
const toolRows=new Map();
const stageTimes=new Map();
let summary=null,liveGraph=null,resultGraph=null;
function progressGraph(){return liveGraph||(liveGraph=createGraph(document.querySelector("#progress-graph")));}
export function executionSummary(data){if(!data)return;summary=data;const graphTarget=document.querySelector("#result-graph");if(graphTarget){graphTarget.hidden=false;resultGraph??=createGraph(graphTarget);resultGraph.snapshot(data);requestAnimationFrame(()=>resultGraph.resize());}const target=document.querySelector("#execution-summary");if(!target)return;target.hidden=false;target.replaceChildren(el("h3","이번 요청의 실행 흐름"),el("p",`${{success:"완료",warning:"일부 자료 확인 필요",failed:"실패",interrupted:"중단"}[data.status]||data.status} · ${data.duration_s}초`));const list=el("ol");for(const s of data.steps||[]){const row=el("li",`${s.tool||s.provider||steps.find(([k])=>k===s.stage)?.[1]||s.stage} · ${{completed:"완료",started:"실행 중",failed:"실패",warning:"일부 미확보",skipped:"생략"}[s.state]||s.state} · ${s.duration_s??"—"}초`);list.append(row);}const details=el("details");details.append(el("summary","실제 단계·도구 호출 보기"),list);target.append(details);}

export function openProgress() { if (!$('#progress-dialog').open) $('#progress-dialog').showModal();requestAnimationFrame(()=>liveGraph?.resize()); }
export function beginProgress() {
  progressGraph().reset({kind:"ai_plan"});
  completed.clear();toolRows.clear();stageTimes.clear();document.querySelector("#progress-tools")?.replaceChildren(); running = true; started = performance.now();
  $('#progress-steps').replaceChildren(...steps.map(([id,label]) => {const li=el('li',label);li.dataset.stage=id;return li;}));
  $('#progress-recovery').hidden = true;
  $('#progress-track').classList.add('running');
  $('#progress-open').hidden = false;
  update({type:'stage',stage:'input',state:'started',message:'입력한 여행 조건을 확인하고 있어요.'});
  clearInterval(timer); timer=setInterval(tick,1000); tick(); openProgress();
}
function tick() { $('#progress-elapsed').textContent=`${Math.floor((performance.now()-started)/1000)}초 경과`; }
export function update(event) {
  if (event.type === 'heartbeat') return;
  if(event.step_id)progressGraph().event(event);
  if(event.type==='tool'&&event.step_id){let row=toolRows.get(event.step_id);if(!row){row=el('li');toolRows.set(event.step_id,row);document.querySelector('#progress-tools')?.append(row);}row.textContent=`${event.tool} · ${event.state==='started'?'실행 중':event.state==='completed'?'완료':'실패'}${event.duration_seconds!=null?' · '+event.duration_seconds+'초':''}`;}
  if(event.type==='stage'&&event.duration_seconds!=null)stageTimes.set(event.stage,event.duration_seconds);
  if (event.message) lastMessage=event.message;
  $('#progress-message').textContent=lastMessage;
  $('#progress-open').textContent=lastMessage+' · 진행 상태 보기';
  if(event.type==='stage' && ['completed','skipped'].includes(event.state)) completed.add(event.stage);
  document.querySelectorAll('#progress-steps li').forEach(li=>{
    const timing=stageTimes.get(li.dataset.stage);li.textContent=(steps.find(([k])=>k===li.dataset.stage)?.[1]||li.dataset.stage)+(timing!=null?' · '+timing+'초':'');
    li.classList.toggle('done',completed.has(li.dataset.stage));
    li.classList.toggle('active',li.dataset.stage===event.stage&&!completed.has(li.dataset.stage));
  });
  $('#progress-count').textContent=`${completed.size} / ${steps.length} 단계 완료`;
}
export function finishProgress(result, failed=false) {
  if(result?.execution){progressGraph().snapshot(result.execution);executionSummary(result.execution);}else if(failed)liveGraph?.finish('failed');
  running=false; clearInterval(timer);tick();$('#progress-track').classList.remove('running');
  if(failed){$('#progress-message').textContent='요청을 완료하지 못했어요. 다시 시도하거나 데이터 기반 초안을 만들어 보세요.';$('#progress-open').textContent='요청을 완료하지 못했어요 · 재시도 방법 보기';$('#progress-recovery').hidden=false;}
  else {$('#progress-dialog').close();$('#progress-open').hidden=true;}
}
export function initializeProgress(retry, rules) {
  $('#progress-close').onclick=()=>$('#progress-dialog').close();
  $('#progress-open').onclick=openProgress;
  $('#progress-retry').onclick=retry;
  $('#progress-rules').onclick=()=>{$('#progress-dialog').close();rules();};
  $('#progress-dialog').addEventListener('cancel',()=>{});
}

export async function readNDJSON(response, onEvent) {
  if(!response.ok){const obj=await response.json();throw new Error(typeof obj.detail==='string'?obj.detail:'입력 조건을 확인해 주세요.');}
  const reader=response.body.getReader(), decoder=new TextDecoder();let pending='',result;
  const consume=line=>{if(!line.trim())return;const event=JSON.parse(line);onEvent(event);if(event.type==='error')throw new Error(event.message);if(event.type==='result')result=event.result;};
  try {while(true){const {value,done}=await reader.read();pending+=decoder.decode(value,{stream:!done});let end;
    while((end=pending.indexOf('\n'))>=0){const line=pending.slice(0,end);pending=pending.slice(end+1);consume(line);}
    if(done){if(pending.trim())consume(pending);break;}}
  } finally {reader.releaseLock();}
  if(!result)throw new Error('연결이 종료되어 결과를 받지 못했습니다. 다시 시도해 주세요.');
  return result;
}
