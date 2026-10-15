import {el,button} from './ui.js?v=0.4.2';
let map, markerLayer, routeLayer, selectedDate, activePlan, config;
const markerBySlot=new Map();
export async function initializeMap(){try{config=await(await fetch('/api/config')).json();}catch{config={tile_url:'https://tile.openstreetmap.org/{z}/{x}/{y}.png'};}}
export function setMapPlan(plan){activePlan=plan;selectedDate=plan.days.some(d=>d.date===selectedDate)?selectedDate:plan.days[0].date;renderMap();}
export function highlightSlot(id,pan=true){
  document.querySelectorAll('.slot-card').forEach(n=>n.classList.toggle('selected',n.dataset.slot===id));
  markerBySlot.forEach((marker,key)=>marker.getElement()?.classList.toggle('selected-marker',key===id));
  const marker=markerBySlot.get(id);if(pan&&marker){map.panTo(marker.getLatLng());marker.openTooltip();}
}
export function showOnMap(date,id){selectedDate=date;renderMap();highlightSlot(id);document.querySelector('#route-map').scrollIntoView({behavior:'smooth',block:'center'});}
function renderMap(){
  const panel=document.querySelector('#map-panel');panel.hidden=false;
  const tabs=document.querySelector('#map-days');tabs.replaceChildren(...activePlan.days.map((day,index)=>{const b=button(`${index+1}일차 · ${day.date.slice(5)}`,()=>{selectedDate=day.date;renderMap();},'map-tab');b.setAttribute('aria-pressed',day.date===selectedDate);return b;}));
  const route=activePlan.routes?.[selectedDate];const info=document.querySelector('#route-info');info.replaceChildren();
  if(!window.L){info.textContent='지도를 불러오지 못했어요. 일정은 계속 확인할 수 있습니다.';return;}
  if(!map){map=L.map('route-map',{scrollWheelZoom:false}).setView([37.46,126.45],11);L.tileLayer(config?.tile_url||'https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);markerLayer=L.layerGroup().addTo(map);routeLayer=L.layerGroup().addTo(map);}
  markerLayer.clearLayers();routeLayer.clearLayers();markerBySlot.clear();
  if(!route?.waypoints?.length){info.textContent='좌표가 있는 방문이 없어 경로를 표시할 수 없습니다.';return;}
  const bounds=[];
  for(const p of route.waypoints){const point=[p.lat,p.lon];bounds.push(point);const icon=L.divIcon({className:'route-pin',html:String(p.number),iconSize:[28,28],iconAnchor:[14,14]});const marker=L.marker(point,{icon,keyboard:true,title:p.title}).addTo(markerLayer);marker.bindTooltip(document.createTextNode(p.title));marker.on('click',()=>{highlightSlot(p.slot_id,false);document.querySelector(`[data-slot="${p.slot_id}"]`)?.scrollIntoView({behavior:'smooth',block:'center'});});markerBySlot.set(p.slot_id,marker);}
  for(const leg of route.legs){if(leg.status==='available'&&leg.geometry)L.geoJSON(leg.geometry,{style:{color:leg.fits_schedule?'#157b80':'#b77835',weight:4,opacity:.8}}).addTo(routeLayer);}
  const label=route.legs.length?`${(route.total_distance_m/1000).toFixed(1)}km · 예상 ${{car:'운전',walk:'도보',transit:'대중교통+도보'}[route.mode]||'이동'} ${Math.ceil(route.total_duration_s/60)}분${route.complete?'':' (확보된 구간 합계)'}`:'방문 장소 한 곳 · 계산할 이동 구간 없음';info.append(el('strong',label),el('p','구간별 교통수단 기준 · 실시간 교통·미래 출발시각 미반영 · 선형이 확보된 구간만 표시'));
  const sources=el('p');for(const [title,url] of [['OSRM','https://project-osrm.org/'],['FOSSGIS 도보 경로','https://routing.openstreetmap.de/about.html'],['지도 수정','https://www.openstreetmap.org/fixthemap']]){const link=el('a',title);link.href=url;link.target='_blank';link.rel='noopener noreferrer';sources.append(link,document.createTextNode(' · '));}info.append(sources);
  for(const leg of route.legs){if(leg.sections?.length){const text=leg.sections.map(s=>`${{walk:'도보',bus:'버스',subway:'지하철'}[s.mode]||'이동'} ${(s.lines||[]).filter(Boolean).join('/')} ${s.minutes??'—'}분`).join(' → ');info.append(el('p',text));}if(leg.note)info.append(el('p',leg.note));if(leg.status!=='available'||!leg.fits_schedule){const a=route.waypoints.find(p=>p.slot_id===leg.from_slot),b=route.waypoints.find(p=>p.slot_id===leg.to_slot);info.append(el('p',`${a?.title} → ${b?.title}: ${leg.status!=='available'?leg.reason:'기존 일정의 이동 여유 시간 부족'}`,'route-warning'));}}
  requestAnimationFrame(()=>{map.invalidateSize();map.fitBounds(bounds,{padding:[30,30],maxZoom:14});});
}
