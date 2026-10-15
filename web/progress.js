import {$, el} from './ui.js';

const steps = [['input','조건 확인'],['data','예보·관광정보 조회'],['schedule','일정 구성·검증'],['enrich','지도·사진 준비'],['result','결과 완성']];
let started = 0, timer, lastMessage = '', running = false;
const completed = new Set();

export function openProgress() { if (!$('#progress-dialog').open) $('#progress-dialog').showModal(); }
export function beginProgress() {
  completed.clear(); running = true; started = performance.now();
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
  if (event.message) lastMessage=event.message;
  $('#progress-message').textContent=lastMessage;
  $('#progress-open').textContent=lastMessage+' · 진행 상태 보기';
  if(event.type==='stage' && ['completed','skipped'].includes(event.state)) completed.add(event.stage);
  document.querySelectorAll('#progress-steps li').forEach(li=>{
    li.classList.toggle('done',completed.has(li.dataset.stage));
    li.classList.toggle('active',li.dataset.stage===event.stage&&!completed.has(li.dataset.stage));
  });
  $('#progress-count').textContent=`${completed.size} / ${steps.length} 단계 완료`;
}
export function finishProgress(result, failed=false) {
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
