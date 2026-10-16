import {el,button} from './ui.js?v=0.5.0';

export function ferryState(row){
  return row.operation_status==='reported_normal'?'normal':row.operation_status==='not_operating'?'stopped':'unknown';
}
export function ferryRows(rows,route){return route?rows.filter(row=>row.licensed_route===route):rows;}
export function initializeFerries(form,config){
  const root=document.querySelector('#ferry-panel'),office=root.querySelector('[name=ferry_office]'),
        route=root.querySelector('[name=ferry_route]'),load=root.querySelector('[data-ferry-load]'),
        message=root.querySelector('[data-ferry-status]'),result=root.querySelector('[data-ferry-results]');
  office.replaceChildren(...(config.ferry_offices||[]).map(name=>{const option=el('option',name);option.value=name;return option;}));
  office.value='인천';let sequence=0,rows=[],limit=40,running=false;
  function clear(){sequence++;rows=[];result.replaceChildren();route.replaceChildren(el('option','전체 항로'));route.options[0].value='';route.disabled=true;message.textContent='오늘의 공식 운항정보를 조회해 주세요.';}
  function region(){const province=form.elements.province.value;office.value=({인천:'인천',부산:'부산',울산:'부산',강원:'강원',충남:'보령',전북:'전북',전남:'목포',경남:'통영',경북:'경북',제주:'제주'})[province]||'인천';clear();}
  office.addEventListener('change',clear);form.elements.region.addEventListener('change',region);
  route.addEventListener('change',()=>{limit=40;draw();});
  function draw(){
    result.replaceChildren();const filtered=ferryRows(rows,route.value);
    result.append(el('p',`${filtered.length}편 중 ${Math.min(limit,filtered.length)}편 표시 · 정원·잔여석·도착시각은 미확인`,'ferry-count'));
    if(!filtered.length){result.append(el('p','표시할 출항편이 없습니다.'));return;}
    const scroll=el('div',undefined,'ferry-table-scroll');scroll.tabIndex=0;scroll.setAttribute('aria-label','오늘 여객선 운항표 · 좌우 스크롤 가능');
    const table=el('table'),thead=el('thead'),header=el('tr');
    for(const title of ['출항','선박 · 운항항로','출항지 · 방향','운항구분','출항여부']){const cell=el('th',title);cell.scope='col';header.append(cell);}thead.append(header);table.append(thead);
    const body=el('tbody');for(const row of filtered.slice(0,limit)){
      const tr=el('tr');tr.append(el('td',row.departure));
      const ship=el('td');ship.append(el('strong',row.vessel),el('div',row.route));tr.append(ship);
      tr.append(el('td',row.origin+' · '+row.direction));const status=el('td');status.append(el('span',row.operation||'미확인','ferry-state '+ferryState(row)));if(row.reason)status.append(el('div',row.reason));tr.append(status,el('td',row.departure_status||'미확인'));body.append(tr);
    }table.append(body);scroll.append(table);result.append(scroll);
    if(filtered.length>limit)result.append(button('40편 더 보기',()=>{limit+=40;draw();},'secondary'));
  }
  load.onclick=async()=>{
    if(running)return;running=true;load.disabled=true;const request=++sequence;
    result.replaceChildren();route.disabled=true;message.textContent='공식 화면에서 오늘의 실제 출항편을 읽고 있어요…';
    try{
      const response=await fetch('/api/ferries/live?'+new URLSearchParams({office:office.value,date:config.today}));const data=await response.json();
      if(request!==sequence)return;
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'배편 조회에 실패했습니다.');
      if(data.status!=='available'){message.textContent=data.reason||'공식 배편 정보를 확인하지 못했습니다.';return;}
      rows=data.rows;limit=40;route.replaceChildren(el('option','전체 항로'));route.options[0].value='';
      for(const name of [...new Set(rows.map(r=>r.licensed_route))].sort()){const option=el('option',name);option.value=name;route.append(option);}route.disabled=false;
      message.textContent=`${data.date} · 공식 기준 ${new Date(data.as_of).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})}${data.cached?' · 캐시 사용':''} · 운항관리 지역 ${data.office}`;
      draw();
    }catch(error){if(request===sequence){message.textContent=error.message;result.replaceChildren();}}
    finally{running=false;load.disabled=false;}
  };
}
