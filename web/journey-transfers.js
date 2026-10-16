import {el,button} from './ui.js?v=0.5.1';
import {transitSummary,transitSourceUrl} from './transit.js?v=0.5.1';

const stopKinds=new Set(['tourism','marine','locked','meal','cafe','port']);
const modes={car:'자차',walk:'도보',bus:'버스',subway:'지하철',transit:'대중교통',ferry:'여객선'};
const known=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0;

export function transfersFor(day,route){
  const stops=day.items.map((item,index)=>({item,index})).filter(({item})=>stopKinds.has(item.kind));
  const result=new Map();
  for(let n=1;n<stops.length;n++){
    const {item:from,index:start}=stops[n-1],{item:to,index:end}=stops[n];
    // Scheduled ferry blocks already describe this crossing; never add a road leg over it.
    if(day.items.slice(start+1,end).some(i=>i.kind==='ferry'))continue;
    const leg=route?.legs?.find(l=>l.from_slot===from.slot_id&&l.to_slot===to.slot_id);
    const available=leg?.status==='available'&&known(leg.duration_s);
    const sectionModes=[...new Set((leg?.sections||[]).map(s=>s.mode).filter(m=>modes[m]))];
    const mode=sectionModes.length?sectionModes.map(m=>modes[m]).join(' + '):modes[leg?.mode||day.transport]||'이동';
    const coordinates=[from.lat,from.lon,to.lat,to.lon].every(v=>typeof v==='number'&&Number.isFinite(v));
    result.set(to.slot_id,{from,to,leg,available,mode,coordinates,iconMode:leg?.mode||day.transport,
      duration:available?`약 ${Math.ceil(leg.duration_s/60)}분`:'시간 미확인',
      distance:available&&known(leg.distance_m)?(leg.distance_m<1000?`${Math.round(leg.distance_m)}m`:`${(leg.distance_m/1000).toFixed(1)}km`):null,
      warning:!available?(!coordinates?'장소 좌표가 없어 이동 경로를 확인하지 못했어요.':leg?.reason||'이동 경로를 확보하지 못했어요.'):leg.fits_schedule===false?'예상 이동시간이 일정의 이동 여유 시간보다 길어요.':null});
  }
  return result;
}

export function transferCard(transfer,date,onMap){
  const {from,to,leg,available,mode}=transfer;
  const row=el('div',undefined,'slot transfer-slot');
  row.dataset.fromSlot=from.slot_id;row.dataset.toSlot=to.slot_id;
  row.append(el('div','이동','time transfer-time'));
  const card=el('article',undefined,'transfer-card'+(transfer.warning?' needs-check':''));
  card.setAttribute('aria-label',`${from.title}에서 ${to.title}까지 이동`);
  const heading=el('div',undefined,'transfer-heading');
  const badge=el('span',mode,'transfer-mode');badge.prepend(modeIcon(transfer.iconMode));
  heading.append(badge,el('strong',transfer.duration,'transfer-duration'));
  if(transfer.distance)heading.append(el('span',transfer.distance,'transfer-distance'));
  card.append(heading,el('p',`${from.title} → ${to.title}`,'transfer-path'));
  card.append(el('p',`${from.end} 방문 종료 · 다음 방문 ${to.start}${known(leg?.available_minutes)?` · 이동 여유 ${leg.available_minutes}분`:''}`,'transfer-window'));
  if(transfer.warning)card.append(el('p',transfer.warning,'route-warning'));
  if(available&&leg?.mode==='transit')card.append(el('small','조회 시점 참고 경로 · 여행일 배차·막차 미확인'));
  const actions=el('div',undefined,'actions');
  if(transfer.coordinates)actions.append(button('지도에서 이동 구간 보기 ↗',()=>onMap(date,from.slot_id,to.slot_id)));
  const url=transitSourceUrl(leg?.source_url);
  if(url){const link=el('a','네이버 지도 상세 ↗');link.href=url;link.target='_blank';link.rel='noopener noreferrer';actions.append(link);}
  if(actions.childNodes.length)card.append(actions);
  if(available){
    const details=el('details',undefined,'transfer-details');details.append(el('summary','이동 방법·출처 보기'));
    const summary=transitSummary(leg);
    if(summary.sections)details.append(el('p',summary.sections));
    if(summary.metrics)details.append(el('p',summary.metrics));
    if(leg.note)details.append(el('p',leg.note));
    details.append(el('small',`${leg.source||'경로 출처 미확인'}${summary.observed?' · '+summary.observed:''}`));
    if(!leg.sections?.length)details.append(el('p',leg.mode==='car'?'도로 경로 기준 예상 운전시간 · 실시간 교통 미반영':leg.mode==='walk'?'도보 경로 기준 예상 시간':'상세 이동 방법은 원본 경로에서 확인하세요.'));
    card.append(details);
  }
  row.append(card);return row;
}

function modeIcon(mode){
  const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');
  icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('aria-hidden','true');
  const path=document.createElementNS(icon.namespaceURI,'path');
  path.setAttribute('d',mode==='walk'?'M13 4h.01M10 10l3-3 3 4 3 1M6 13l4-3 2 5-3 6M12 15l5 6':mode==='car'?'M5 10l2-5h10l2 5M4 10h16v8H4zM7 18v2m10-2v2M7 14h.01M17 14h.01':'M6 4h12v13H6zM8 8h8M8 12h.01M16 12h.01M8 17l-2 4m10-4 2 4');
  path.setAttribute('fill','none');path.setAttribute('stroke','currentColor');path.setAttribute('stroke-width','1.8');path.setAttribute('stroke-linecap','round');path.setAttribute('stroke-linejoin','round');icon.append(path);return icon;
}
