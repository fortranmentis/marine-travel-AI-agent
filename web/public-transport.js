import {el,button} from './ui.js?v=0.6.0';

export function minutesLabel(value){return typeof value==='number'&&Number.isFinite(value)&&value>=0?`${Math.ceil(value/60)}분`:'미확인';}
export function clockLabel(value){const s=String(value??'').padStart(4,'0');return value!=null&&value!==''&&/^(?:[01]\d|2[0-9])[0-5]\d$/.test(s)?s.slice(0,2)+':'+s.slice(2):'미확인';}
export function initializeTransport(form){
  const dialog=document.querySelector('#transport-dialog'),result=document.querySelector('#transport-results'),
    status=document.querySelector('#transport-status');let sequence=0;
  const observed=data=>data.observed_at?new Date(data.observed_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'미확인';
  async function get(path){const response=await fetch(path),data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'교통 조회에 실패했습니다.');return data;}
  function begin(message){const id=++sequence;result.replaceChildren();status.textContent=message;return id;}
  function unavailable(data){status.textContent=({not_configured:'교통 API 키가 서버에 설정되지 않았습니다.',unavailable:'제공기관 연결 또는 응답을 확인하지 못했습니다.',no_data:'현재 반환된 정보가 없습니다.',incomplete:'전체 자료를 확인하지 못했습니다.'})[data.status]||'조회 결과가 없습니다.';}
  function source(data){result.append(el('small',`조회 ${observed(data)}${data.cached?' · 캐시 사용':''}`));if(data.note)result.append(el('p',data.note,'note'));if(/^https:\/\/www\.data\.go\.kr\/data\/\d+\/openapi\.do$/.test(data.source_url||'')){const a=el('a','공공데이터포털 출처 ↗');a.href=data.source_url;a.target='_blank';a.rel='noopener noreferrer';result.append(a);}}
  async function route(city,id){const token=begin('노선·경유 정류소·현재 버스 위치를 조회하고 있어요…');try{
    const data=await get(`/api/transport/routes/${encodeURIComponent(id)}?`+new URLSearchParams({city}));if(token!==sequence)return;
    status.textContent='노선 참고 정보 · 여행일 출발시각 미확인';result.append(el('p',data.note,'note'));
    if(data.info.rows.length){const r=data.info.rows[0];result.append(el('h3',`${r.routeno}번 · ${r.startnodenm} → ${r.endnodenm}`),el('p',`기점 첫차 ${clockLabel(r.startvehicletime)} · 막차 ${clockLabel(r.endvehicletime)}`));
      const intervals=[['평일','intervaltime'],['토요일','intervalsattime'],['일요일','intervalsuntime']].filter(([,k])=>Number(r[k])>0).map(([label,k])=>`${label} ${r[k]}분`);result.append(el('p','배차: '+(intervals.join(' · ')||'미확인')));
    }else result.append(el('p','노선 기본정보 미확보'));
    result.append(el('h3','현재 버스 위치'),el('p',`조회 ${observed(data.positions)} · 위치 ${data.positions.rows.length}대`));
    if(!data.positions.rows.length)result.append(el('p',data.positions.status==='no_data'?'현재 위치 자료가 없습니다. 운행 중단을 뜻하지 않습니다.':'위치 정보를 확인하지 못했습니다.'));
    const live=el('ul');for(const r of data.positions.rows.slice(0,30))live.append(el('li',`${r.stop||'정류소 미확인'} 부근`));result.append(live);if(data.positions.rows.length>30)result.append(el('p','현재 위치는 30대까지 표시합니다.'));
    const details=el('details');details.append(el('summary',`경유 정류소 ${data.stops.rows.length}곳 · 노선 순서 참고`));
    const list=el('ol');for(const r of data.stops.rows)list.append(el('li',`${r.nodeord}. ${r.nodenm}`));details.append(list);result.append(details);
  }catch(e){if(token===sequence)status.textContent=e.message;}}
  async function stop(city,id,title){const token=begin('정류소의 현재 도착예정정보를 조회하고 있어요…');try{
    const data=await get(`/api/transport/stops/${encodeURIComponent(id)}?`+new URLSearchParams({city}));if(token!==sequence)return;
    result.append(el('h3',title));source(data);
    if(data.status!=='available'){unavailable(data);return;}status.textContent='현재 도착예정 버스 · 미래 일정에 적용하지 않습니다.';
    for(const r of data.rows){const card=el('article',undefined,'transport-choice');card.append(el('strong',`${r.route_name}번 · ${minutesLabel(r.seconds)} 후 예상`),el('p',`${r.remaining_stops??'—'}개 정류소 전 · ${r.vehicle_type||'차량 유형 미확인'}`),button('노선·현재 위치 보기',()=>route(city,r.route_id),'secondary'));result.append(card);}
  }catch(e){if(token===sequence)status.textContent=e.message;}}
  async function nearby(lat,lon,title='선택 좌표'){
    const token=begin(title+' 주변 정류소를 조회하고 있어요…');try{
      const data=await get('/api/transport/nearby?'+new URLSearchParams({lat,lon}));if(token!==sequence)return;source(data);
      if(data.status!=='available'||!data.rows.length){unavailable(data);return;}status.textContent=`${title} 주변 정류소 ${data.rows.length}곳${data.truncated?' · 가까운 12곳까지 표시':''}`;
      for(const r of data.rows){const card=el('article',undefined,'transport-choice');card.append(el('strong',r.title),el('p',`직선 ${r.distance_m}m${r.stop_number?' · 정류소번호 '+r.stop_number:''}`),button('현재 버스 도착정보',()=>stop(r.city_code,r.id,r.title),'secondary'));result.append(card);}
    }catch(e){if(token===sequence)status.textContent=e.message;}
  }
  async function subway(id,title){const token=begin('역별 요일 시간표와 출구 버스를 조회하고 있어요…');try{
    const date=document.querySelector('#transport-date').value,direction=document.querySelector('#transport-direction').value;
    const data=await get(`/api/transport/subway/${encodeURIComponent(id)}?`+new URLSearchParams({date,direction}));if(token!==sequence)return;
    result.append(el('h3',title),el('p',data.note,'note'),el('p',`${date} · ${direction==='U'?'상행':'하행'} · 조회 ${observed(data.times)}`));
    if(data.status!=='available'){unavailable(data);}else status.textContent='요일 유형의 참고 시간표 · 여행일 운행 미확정';
    const list=el('div',undefined,'transport-times');for(const r of data.times.rows)list.append(el('span',`${r.departure} ${r.destination}${r.service_day_offset?' (익일)':''}`));result.append(list);
    const exit=el('details');exit.append(el('summary',`출구 연계 버스 ${data.exits.rows.length}건`));for(const r of data.exits.rows)exit.append(el('p',`${r.exitNo}번 출구 · ${r.busRouteNo}번`));result.append(exit);
  }catch(e){if(token===sequence)status.textContent=e.message;}}
  document.querySelector('#transport-search').onsubmit=async event=>{event.preventDefault();const keyword=document.querySelector('#transport-keyword').value.trim();if(!keyword)return;const token=begin('지하철역을 찾고 있어요…');try{
    const data=await get('/api/transport/subway?'+new URLSearchParams({keyword}));if(token!==sequence)return;if(data.status!=='available'){unavailable(data);return;}
    status.textContent=`역 ${data.rows.length}곳 표시${data.truncated?' · 일부 결과':''}`;
    for(const r of data.rows)result.append(button(`${r.title} · ${r.line}`,()=>subway(r.id,`${r.title} · ${r.line}`),'transport-choice secondary'));
  }catch(e){if(token===sequence)status.textContent=e.message;}};
  document.querySelector('#transport-nearby').onsubmit=e=>{e.preventDefault();nearby(document.querySelector('#transport-lat').value,document.querySelector('#transport-lon').value);};
  document.querySelector('#transport-close').onclick=()=>dialog.close();dialog.addEventListener('close',()=>sequence++);
  for(const id of ['transport-date','transport-direction'])document.querySelector('#'+id).addEventListener('change',()=>begin('조건이 바뀌었습니다. 지하철역을 검색·선택해 다시 조회해 주세요.'));
  function open(){begin('관광지 주변 정류소 또는 지하철역을 조회해 주세요.');document.querySelector('#transport-date').value=form.elements.start_date.value;dialog.showModal();}
  document.querySelector('#transport-open').onclick=open;
  return {nearby(place){open();document.querySelector('#transport-lat').value=place.lat;document.querySelector('#transport-lon').value=place.lon;nearby(place.lat,place.lon,place.title);}};
}
