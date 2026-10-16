import {initializeNational} from './national.js?v=0.4.4';
import {marineIndexCard,indexBadge} from './marine-index.js?v=0.4.4';
import {initializeTripForm} from './trip-form.js?v=0.4.4';
import {$,el,button,plainText} from './ui.js?v=0.4.4';
import {beginProgress,finishProgress,initializeProgress,readNDJSON,update as updateProgress} from './progress.js?v=0.4.4';
import {weatherCard} from './weather.js?v=0.4.4';
import {initializeMap,setMapPlan,showOnMap,showRouteSegment,highlightSlot} from './maps.js?v=0.4.4';
import {transfersFor,transferCard} from './journey-transfers.js?v=0.4.4';

const form=$('#trip-form');
const state={history:[],plan:null,locked:[],excluded:[],busy:false,alternative:null,lastRequest:null};
const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
form.elements.start_date.value=today;form.elements.start_date.min=today;
const tripForm=initializeTripForm(form);
const national=initializeNational(form);
api('/api/config').then(config=>{for(const island of config.islands||[]){const option=el('option',island.title);option.value=island.id;form.elements.island_id.append(option);}const option=form.elements.transport.querySelector('[value=transit]');option.textContent=config.mobility?.transit?'대중교통 + 도보 (지도 참고 경로)':'대중교통 + 도보 (조회 준비 필요)';option.title=config.mobility?.transit_reason||'조회 시점 참고 경로 · 여행일 시간표 미확인';}).catch(()=>{});
function status(text,error=false){$('#status').textContent=text;$('#status').className=error?'error':'';}
function busy(value){state.busy=value;document.querySelectorAll('button:not([data-always-enabled])').forEach(b=>b.disabled=value);}
function trip(){const f=new FormData(form);return {region:f.get('region'),start_date:f.get('start_date'),days:Number(f.get('days')),...tripForm.read(),activity:f.get('activity'),excluded_ids:state.excluded,locked:state.locked};}
async function api(path,body){const response=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'날짜·인원·고정 일정 등 입력 조건을 확인해 주세요.');return data;}
function edits(){const box=$('#edits');box.replaceChildren();if(state.locked.length||state.excluded.length){box.append(el('div',`고정 ${state.locked.length}개 · 제외 ${state.excluded.length}개`));box.append(button('다음 생성의 고정·제외 조건 초기화',()=>{state.locked=[];state.excluded=[];edits();status('다시 생성하면 초기화한 조건이 반영됩니다.');}));}}
function syncForm(plan){const previousDate=form.elements.start_date.value;national.selectRegion(plan.trip.region);state.locked=plan.trip.locked;state.excluded=plan.trip.excluded_ids;for(const key of ['region','start_date','days','adults','activity'])form.elements[key].value=plan.trip[key];tripForm.sync(plan.trip);if(previousDate!==plan.trip.start_date)national.refresh();edits();}
function photo(contentId){
  const value=state.plan?.media?.[contentId],figure=el('figure',undefined,'place-photo');
  const empty=()=>{figure.replaceChildren(el('div','사진 준비 중이거나 제공된 사진이 없어요.','photo-empty'));};
  if(value?.status!=='available'){empty();return figure;}
  const image=el('img');image.src=value.url;image.alt=value.title||'관광지 사진';image.loading='lazy';image.decoding='async';image.onerror=empty;
  figure.append(image);return figure;
}
function render(plan){
  state.plan=plan;$('#empty').hidden=true;$('#result-title').textContent=`${plan.trip.region} · ${plan.trip.days}일의 바다`;const box=$('#plan');box.replaceChildren();
  const notices=el('details',undefined,'notices');notices.append(el('summary','검토용 초안 · 운영·연령·현장 조건 확인 필요'));plan.notices.forEach(t=>notices.append(el('p',t)));box.append(notices);
  if(plan.travel_index)box.append(marineIndexCard(plan.travel_index,{overall:true}));
  $('#undo').hidden=!plan.can_undo;$('#messages').classList.toggle('outdated',!!plan.explanation_outdated);
  if(plan.explanation_outdated)box.append(el('p','방문을 교체했습니다. 아래 AI 설명은 변경 전 일정을 기준으로 합니다.','explanation-note'));
  for(const day of plan.days){
    const section=el('section',undefined,'day'),title=el('h3',day.date,'day-title');title.append(el('span',day.marine.status==='available'?'해양예보 조회됨':day.marine.status==='stale'?'해양자료 갱신 필요':day.marine.status==='not_requested'?'관광 중심':'해당 날짜·권역 해양예보 없음'));section.append(title,weatherCard(day.weather,day.day_start||plan.trip.day_start,day.day_end||plan.trip.day_end));
    if(day.travel_index)section.append(marineIndexCard(day.travel_index));
    if(day.search_reference)section.append(el('p',`관광 탐색 기준: ${day.search_reference.title}. 주변 후보를 찾기 위한 기준점이며 숙소·실제 출발지가 아닙니다.`,'search-reference'));
    section.append(el('p',`관광·체험 ${day.actual_visits??'—'} / 요청 ${day.requested_visits??'—'}곳`,'forecast'));
    for(const warning of day.warnings||[])section.append(el('p',warning,'route-warning'));
    const transfers=transfersFor(day,plan.routes?.[day.date]);
    for(const item of day.items){
      if(transfers.has(item.slot_id))section.append(transferCard(transfers.get(item.slot_id),day.date,showRouteSegment));
      const compact=['break','buffer'].includes(item.kind),slot=el('div',undefined,'slot'+(compact?' compact':''));slot.append(el('div',item.start+'\n'+item.end,'time'));
      const card=el('article',undefined,'card slot-card '+item.kind);card.dataset.slot=item.slot_id;const info=el('div',undefined,'card-content');info.append(el('h4',item.title));
      if(item.kind==='locked')info.append(el('span','시간 고정됨','lock-badge'));
      if(item.cuisine_label)info.append(el('span','TourAPI 분류: '+item.cuisine_label,'food-badge'));
      if(item.food_details?.menu)info.append(el('p','대표 메뉴: '+plainText(item.food_details.menu)));
      if(item.food_details?.hours)info.append(el('p','안내 영업시간: '+plainText(item.food_details.hours)));
      if(item.food_details?.rest_days)info.append(el('p','안내 휴무: '+plainText(item.food_details.rest_days)));
      if(item.vessel)info.append(el('p',item.vessel));
      if(item.reason)info.append(el('p',item.reason));if(item.address)info.append(el('p',item.address));
      if(item.forecast){const forecast=el('div',undefined,'activity-index');forecast.append(el('span','갯벌체험지수'),indexBadge(item.forecast.totalIndex),el('p',`체험 가능 시간 ${item.forecast.mdftExprnBgngTm} ~ ${item.forecast.mdftExprnEndTm}`));info.append(forecast);}
      if(item.checks)info.append(el('p','확인 필요: '+item.checks.join(' · '),'checks'));
      const actions=el('div',undefined,'actions');
      if(item.lat!=null&&item.lon!=null){
        actions.append(button('지도에서 보기 ↗',()=>showOnMap(day.date,item.slot_id)));
        card.tabIndex=0;
        card.addEventListener('mouseenter',()=>highlightSlot(item.slot_id,false));
        card.addEventListener('click',event=>{if(!event.target.closest('button,a'))showOnMap(day.date,item.slot_id);});
        card.addEventListener('keydown',event=>{if(event.target===card&&['Enter',' '].includes(event.key)){event.preventDefault();showOnMap(day.date,item.slot_id);}});
      }
      if(['tourism','marine'].includes(item.kind)||item.kind==='locked'&&item.original_kind){actions.append(button(item.kind==='locked'?'고정 해제':'시간 고정',()=>setLock(item)));}
      if(item.kind==='tourism')actions.append(button('다른 관광지로 바꾸기',()=>showAlternatives(day,item)));
      if(item.id&&item.kind!=='locked')actions.append(button('다음 일정에서 제외',()=>{if(!state.excluded.includes(item.id))state.excluded.push(item.id);edits();status('다음 생성에서 제외할 조건을 추가했습니다.');}));
      if(actions.childNodes.length)info.append(actions);card.append(info);
      if(!compact)card.append(photo(item.id));slot.append(card);section.append(slot);
    }
    for(const recommendation of day.food_recommendations||[]){if(!recommendation.candidates.length)continue;const details=el('details',undefined,'nearby-food');details.append(el('summary',`${recommendation.start} ${recommendation.kind==='cafe'?'주변 카페':'주변 식당'} 후보`));for(const candidate of recommendation.candidates){const row=el('div',undefined,'food-candidate');row.append(photo(candidate.id),el('p',candidate.title+' · '+candidate.cuisine_label+' · '+candidate.distance_km+'km (직선거리)'));details.append(row);}details.append(el('small','TourAPI 분류 기준 후보입니다. 실제 메뉴·영업시간·이동 경로·단체 수용 여부를 확인하세요.'));section.append(details);}
    box.append(section);
  }
  const credits=el('details',undefined,'photo-credits');credits.append(el('summary','사진 이용정보'));
  for(const value of Object.values(plan.media||{}).filter(v=>v.status==='available')){
    const row=el('p',value.title+' · '+value.source+' · ');
    const link=el('a',value.license==='Type3'?'공공누리 3유형':'공공누리 1유형');link.href=value.license_url;link.target='_blank';link.rel='noopener noreferrer';row.append(link);credits.append(row);
  }
  if(credits.childNodes.length>1)box.append(credits);
  box.append(el('p','자료 수집: '+plan.collected_at,'forecast'));$('#chat-panel').hidden=false;setMapPlan(plan);
}
async function setLock(item){if(state.busy)return;busy(true);try{const p=state.plan;const updated=await api(`/api/plans/${p.plan_id}/lock`,{revision:p.revision,slot_id:item.slot_id,locked:item.kind!=='locked'});syncForm(updated);render(updated);status(item.kind==='locked'?'고정을 해제했습니다.':'시간을 고정했습니다. 지도 좌표도 유지됩니다.');}catch(error){status(error.message,true);}finally{busy(false);}}
function showAlternatives(day,item){
  state.alternative={day:day.date,slot:item.slot_id};$('#alternative-target').textContent=`${item.title} · ${item.start}~${item.end}`;$('#alternative-status').textContent='';const list=$('#alternative-candidates');list.replaceChildren();
  const candidates=day.alternatives.filter(p=>!state.excluded.includes(p.id));
  if(!candidates.length)list.append(el('p','현재 선택할 수 있는 대체 후보가 없습니다.'));
  for(const candidate of candidates){const card=el('div',undefined,'alternative-card');card.append(photo(candidate.id));const b=button(candidate.title,()=>replace(candidate.id),'alternative-select');b.append(el('small',candidate.address||'주소 미확인'));card.append(b);list.append(card);}
  $('#alternatives-dialog').showModal();
}
async function replace(candidateId){if(state.busy)return;busy(true);$('#alternative-status').textContent='인접 도로 경로와 이동 여유 시간을 확인하고 있어요…';try{const p=state.plan;const result=await api(`/api/plans/${p.plan_id}/replace`,{revision:p.revision,slot_id:state.alternative.slot,candidate_id:candidateId});render(result);$('#alternatives-dialog').close();showOnMap(state.alternative.day,state.alternative.slot);status('선택한 방문만 교체했습니다. 지도·사진도 갱신했습니다.');}catch(error){$('#alternative-status').textContent=error.message;}finally{busy(false);}}
$('#alternatives-close').onclick=()=>$('#alternatives-dialog').close();
$('#undo').onclick=async()=>{if(state.busy)return;busy(true);try{const p=state.plan;render(await api(`/api/plans/${p.plan_id}/undo`,{revision:p.revision}));status('직전 교체를 되돌렸습니다.');}catch(error){status(error.message,true);}finally{busy(false);}};
async function aiRequest(request){
  state.lastRequest=request;beginProgress();
  try{const response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});const result=await readNDJSON(response,updateProgress);finishProgress(result);return result;}
  catch(error){finishProgress(null,true);throw error;}
}
function displayResult(data){if(data.plan){syncForm(data.plan);render(data.plan);}$('#messages').append(el('div',data.answer,'answer'));$('#chat-panel').hidden=false;$('#trace').textContent=data.trace.map(t=>`${t.tool}: ${t.status}`).join(' → ');status(data.status==='ok'?'초안을 만들었습니다. 미확인 항목을 확인해 주세요.':'AI 처리 상태: '+data.status+' · 데이터 기반 초안을 확인해 주세요.');}
async function generate(useAI){
  if(state.busy||!form.reportValidity())return;busy(true);status(useAI?'AI가 여행 자료를 확인하고 있습니다.':'데이터와 규칙으로 초안을 만드는 중입니다.');
  try{const input=trip();if(useAI){const message='입력한 동행·교통·식사·일별 시간 조건으로 선택한 권역의 바다여행 일정을 만들어 주세요.';const data=await aiRequest({message,trip:input});state.history=[{role:'user',content:message+' '+JSON.stringify(input)},{role:'assistant',content:data.answer}];$('#messages').replaceChildren();displayResult(data);}else{const plan=await api('/api/plan',input);syncForm(plan);render(plan);state.history=[];$('#messages').replaceChildren();$('#trace').textContent='Python 일정 엔진';status('규칙 기반 초안을 만들었습니다.');}}
  catch(error){status(error.message,true);}finally{busy(false);}
}
form.onsubmit=e=>{e.preventDefault();generate(true);};$('#rules').onclick=()=>generate(false);
initializeProgress(async()=>{if(state.busy||!state.lastRequest)return;busy(true);try{const data=await aiRequest(state.lastRequest);$('#messages').replaceChildren();displayResult(data);}catch(error){status(error.message,true);}finally{busy(false);}},()=>generate(false));
$('#chat-form').onsubmit=async e=>{
  e.preventDefault();if(state.busy)return;const message=$('#chat-input').value;busy(true);status('수정 요청을 검토하고 있습니다…');$('#messages').append(el('div',message,'user-message'));
  try{const context=state.plan?`현재 여행 조건: ${JSON.stringify({...state.plan.trip,locked:state.locked,excluded_ids:state.excluded})}\n요청: ${message}`:message;const data=await aiRequest({message:context,history:state.history.slice(-6),locked:state.locked,excluded_ids:state.excluded});displayResult(data);state.history.push({role:'user',content:message},{role:'assistant',content:data.answer});$('#chat-input').value='';}
  catch(error){status(error.message,true);}finally{busy(false);}
};
initializeMap();
api('/api/health').then(d=>{$('#health').textContent=d.catalog_ready?`${d.scope==='coastal'?'전국':'인천'} 관광 ${d.places.toLocaleString('ko-KR')}건 연결 · 바다예보 ${d.forecast_regions||0}권역\n수집: ${d.collected_at}`:'데이터 수집을 먼저 실행해 주세요.';$('#health-dot').style.color=d.catalog_ready?'#308a68':'#a47d39';}).catch(()=>{$('#health').textContent='서버 상태를 확인할 수 없습니다.';});
