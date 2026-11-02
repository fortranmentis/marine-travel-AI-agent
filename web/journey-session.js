import {el,button} from './ui.js?v=0.9.0';
const KEY='marine-journey-v09';
export function readTicket(storage){try{const v=JSON.parse(storage.getItem(KEY));return /^[a-f0-9]{32}$/.test(v?.id)&&/^[A-Za-z0-9_-]{40,100}$/.test(v?.token)?{id:v.id,token:v.token}:null;}catch{return null;}}
export function decisionOptions(data){return data?.journey?.status==='pending'?(data.decision?.options||[]).filter(s=>['keep','fewer','transit'].includes(s)):[];}
export function initializeJourney({stream,display,busy,status,isBusy}){
 let ticket=readTicket(sessionStorage),meta=null,timer=null,epoch=0;
 const panel=el('section',undefined,'journey-control note');panel.setAttribute('aria-label','저장된 여행 진행');
 document.querySelector('#status').after(panel);
 const labels={keep:'현재 제약으로 마무리',fewer:'방문 수 줄여 다시 검토',transit:'대중교통 허용 후 다시 검토'};
 function store(){try{if(ticket)sessionStorage.setItem(KEY,JSON.stringify(ticket));else sessionStorage.removeItem(KEY);}catch{status('이 브라우저에서는 진행 복구 정보를 보관할 수 없습니다.',true);}}
 function clearPoll(){clearTimeout(timer);timer=null;}
 function forget(){epoch++;clearPoll();ticket=null;meta=null;store();draw();restrictions();}
 function blocked(){return !!meta&&meta.status!=='completed';}
 function restrictions(){panel.querySelectorAll('button').forEach(b=>b.disabled=isBusy());document.querySelectorAll('[data-plan-mutation]').forEach(b=>b.disabled=isBusy()||blocked());}
 function draw(data){panel.replaceChildren();panel.hidden=!ticket;if(!ticket)return;
  panel.append(el('strong',({pending:'여행 조건 선택을 기다리고 있어요',running:'여행을 검토하고 있어요',completed:'여행 진행 저장됨',failed:'진행 중 문제가 발생했어요',interrupted:'서버 재시작으로 진행이 중단됐어요',expired:'일정 보관 시간이 지났어요'}[meta?.status]||'저장된 여행 진행이 있어요')));
  panel.append(el('p','최대 2시간 보관 · 선택은 저장된 여행 조건에 적용됩니다. 입력을 바꾸려면 새로 생성해 주세요.'));
  if(data?.attempts)panel.append(el('p',`재검토 ${Math.max(0,data.attempts-1)} / 2회`));
  for(const choice of decisionOptions(data))panel.append(button(labels[choice],()=>resume(choice),'secondary'));
  if(['failed','interrupted'].includes(meta?.status))panel.append(button('저장된 지점에서 다시 시도',()=>resume('retry'),'secondary'));
  panel.append(button('저장된 진행 불러오기',()=>restore(),'secondary'),button('이 브라우저의 복구 정보 지우기',forget,'secondary'));restrictions();
 }
 function remember(event){if(event.type!=='journey')return;epoch++;clearPoll();ticket={id:event.id,token:event.token};meta={status:'running'};store();draw();}
 function update(data){if(data?.journey){meta=data.journey;draw(data);}restrictions();}
 async function restore(){if(!ticket||isBusy())return;clearPoll();const serial=epoch;busy(true);
  try{const response=await fetch(`/api/journeys/${ticket.id}`,{headers:{'X-Journey-Token':ticket.token},cache:'no-store'});const data=await response.json();if(serial!==epoch)return;
   if(!response.ok){if([401,410].includes(response.status)){forget();status(data.detail||'저장된 진행이 만료됐습니다.',true);return;}throw Error(data.detail||'진행을 불러오지 못했습니다.');}
   meta=data.journey;if(data.result&&meta.status!=='running')display(data.result);draw(data.result);
   if(meta.status==='running'){status('저장된 작업이 진행 중입니다. 완료 상태를 확인하고 있어요.');if(!document.hidden)timer=setTimeout(()=>restore(),3000);}
  }catch(error){if(serial===epoch)status(error.message,true);}finally{busy(false);}
 }
 async function resume(choice){if(!ticket||!meta||isBusy())return;busy(true);clearPoll();
  try{const result=await stream(`/api/journeys/${ticket.id}/resume/stream`,{revision:meta.revision,choice},ticket.token);display(result);}
  catch(error){status(error.message,true);awaitError();}finally{busy(false);}
 }
 function awaitError(){if(ticket)timer=setTimeout(()=>restore(),1000);}
 function prepare(){epoch++;clearPoll();}
 document.addEventListener('visibilitychange',()=>{if(document.hidden)clearPoll();else if(ticket&&meta?.status==='running')restore();});
 window.addEventListener('pagehide',clearPoll);draw();
 return {remember,update,restore,blocked,restrictions,forget,prepare,hasTicket:()=>!!ticket};
}
