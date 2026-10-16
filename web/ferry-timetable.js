import {el,button} from './ui.js?v=0.6.0';

export function dateClock(value){if(!value)return '미확인';const date=new Date(value);return Number.isNaN(date.getTime())?'미확인':new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(date);}
export function renderTimetable(data){
  const box=el('div',undefined,'api-timetable');box.append(el('p',data.note||data.reason||'반환 자료가 없습니다.','note'));
  box.append(el('p',`${data.date||''} · ${data.rows?.length||0}편 · 조회 ${dateClock(data.observed_at)} · 왕복 검증 미완료`));
  if(!data.rows?.length){box.append(el('p',data.status==='not_configured'?'API 키 설정이 필요합니다.':'조건에 맞는 시간표를 확보하지 못했습니다.'));return box;}
  const state={reported_normal:'출항 대조 일치 · 도착 미검증',not_operating:'비운항·통제',unmatched:'KOMSA 출항 대조 불일치',unknown:'운항상태 미확인',not_checked:'출항 대조 미실시'};
  for(const row of data.rows){const card=el('article',undefined,'transport-choice');card.append(el('strong',`${row.origin} → ${row.destination} · ${row.vessel}`),
    el('p',`출발 ${dateClock(row.departure)} → 도착 예정 ${dateClock(row.arrival)}`),el('p',state[row.operation_status]||'미확인',row.operation_status==='not_operating'?'error':'checks'));
    if(row.reason)card.append(el('p',row.reason));if(row.quality_flags?.length)card.append(el('p','여러 도착지의 예정시각이 같아 도착자료 재확인이 필요합니다.','error'));
    box.append(card);
  }
  const details=el('details');details.append(el('summary',`출항 대조를 통과한 참고 왕복 조합 ${data.pair_count||0}개 · 최대 8개 표시 · 자동 적용 안 함`));
  for(const pair of data.pairs||[])details.append(el('p',`${pair.outbound.vessel} ${dateClock(pair.outbound.departure)} 출발 / ${pair.returning.vessel} ${dateClock(pair.returning.departure)} 귀환 출발 · 체류 참고 ${pair.island_minutes}분 · 도착시각 독립 검증 필요`));box.append(details);
  return box;
}
export function initializeTimetable(form){
  const root=document.querySelector('#ferry-api-panel'),result=document.querySelector('#ferry-api-results'),status=document.querySelector('#ferry-api-status'),
    region=document.querySelector('#ferry-api-region'),date=document.querySelector('#ferry-api-date');let sequence=0;
  function inputs(){if([...region.options].some(o=>o.value===form.elements.region.value))region.value=form.elements.region.value;date.value=form.elements.start_date.value;}
  inputs();
  for(const input of [region,date])input.addEventListener('change',()=>{sequence++;result.replaceChildren();status.textContent='변경한 조건으로 시간표를 조회해 주세요.';});
  for(const name of ['region','start_date'])form.elements[name].addEventListener('change',()=>{sequence++;inputs();result.replaceChildren();status.textContent='변경한 조건으로 시간표를 조회해 주세요.';});
  document.querySelector('#ferry-api-load').onclick=async()=>{const token=++sequence;status.textContent='TAGO 시간표와 KOMSA 출항을 대조하고 있어요…';result.replaceChildren();try{
    const response=await fetch('/api/ferries/timetable?'+new URLSearchParams({region:region.value,date:date.value}));const data=await response.json();if(token!==sequence)return;
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'시간표 조회에 실패했습니다.');
    result.append(renderTimetable(data));status.textContent='API 조회 결과 · 예약·접근·도착시각 검증은 별도입니다.';
  }catch(e){if(token===sequence)status.textContent=e.message;}};
  return {show(name,day,data){if([...region.options].some(o=>o.value===name))region.value=name;date.value=day;root.open=true;sequence++;
    if(data){result.replaceChildren(renderTimetable(data));status.textContent='일정 생성 시 조회한 API 자료입니다.';}else document.querySelector('#ferry-api-load').click();root.scrollIntoView({behavior:'smooth',block:'start'});}};
}
