import {el,button} from './ui.js?v=0.4.2';
import {indexBadge} from './marine-index.js?v=0.4.2';

const legacy=['영종·용유','강화','송도·도심'];
export function initializeNational(form){
  let data=null,sequence=0;
  const province=form.elements.province,region=form.elements.region,date=document.querySelector('#outlook-date');
  const topProvince=document.querySelector('#outlook-province');
  date.value=form.elements.start_date.value;date.min=form.elements.start_date.min;
  const note=document.querySelector('#national-status'),cards=document.querySelector('#national-cards');
  function activities(){
    const local=legacy.includes(region.value);
    for(const option of form.elements.activity.options)if(['mudflat','beach'].includes(option.value))option.disabled=!local;
    if(!local&&['mudflat','beach'].includes(form.elements.activity.value))form.elements.activity.value='seatrip';
  }
  function populate(preferred=region.value){
    if(!data)return;
    topProvince.value=province.value;
    const rows=data.regions.filter(r=>province.value==='all'||r.province===province.value);
    region.replaceChildren();
    for(const r of rows){const option=el('option',r.title+(r.planning_enabled?'':' · 예보만 제공'));option.value=r.id;option.disabled=!r.planning_enabled;region.append(option);}
    if(['all','인천'].includes(province.value))for(const name of legacy){const option=el('option',name+' · 인천 세부 권역');option.value=name;region.append(option);}
    if([...region.options].some(o=>o.value===preferred&&!o.disabled))region.value=preferred;
    else {const first=[...region.options].find(o=>!o.disabled);if(first)region.value=first.value;}
    activities();
  }
  function selectRegion(name){
    const row=data?.regions.find(r=>r.id===name);
    if(row){province.value=row.province;populate(name);}
    else if(legacy.includes(name)){province.value='인천';populate(name);region.value=name;}
    render();
  }
  function render(){
    if(!data)return;
    const rows=data.regions.filter(r=>province.value==='all'||r.province===province.value);
    cards.replaceChildren();
    for(const row of rows){
      const article=el('article',undefined,'national-region-card');
      const head=el('div',undefined,'national-region-title');head.append(el('span',row.province),el('h3',row.title));article.append(head,indexBadge(row.outlook.grade,row.outlook.status));
      const periods=el('div',undefined,'national-periods');
      if(row.outlook.temporal_resolution==='daily')periods.append(el('span','일 단위 예보 · 오전·오후 구분 없음'));
      else for(const period of ['오전','오후']){const evidence=row.outlook.rows.find(r=>r.predcNoonSeCd===period);periods.append(el('span',period+' · '+(row.outlook.status==='stale'?'갱신 필요':evidence?.totalIndex||'자료 없음')));}article.append(periods);
      if(row.planning_enabled){article.append(button('이 권역으로 일정 만들기',()=>{selectRegion(row.id);form.scrollIntoView({behavior:'smooth',block:'start'});},'national-select'));}
      else article.append(el('p',row.reason,'national-disabled'));
      cards.append(article);
    }
    document.querySelector('#national-count').textContent=`${data.regions.length}개 예보 권역 · ${data.regions.filter(r=>r.planning_enabled).length}개 권역 일정 지원`;
  }
  async function load(){
    const request=++sequence;date.value=form.elements.start_date.value;
    data=null;
    note.textContent='전국 바다여행지수를 조회하고 있어요.';
    cards.replaceChildren();
    try{
      const response=await fetch('/api/regions?date='+encodeURIComponent(date.value));
      if(!response.ok)throw new Error();
      const value=await response.json();if(request!==sequence)return;
      data=value;
      const selected=province.value;province.replaceChildren(new Option('전국 해안 권역','all'));
      for(const name of [...new Set(data.regions.map(r=>r.province))])province.append(new Option(name,name));
      province.value=[...province.options].some(o=>o.value===selected)?selected:'all';
      topProvince.replaceChildren(...[...province.options].map(o=>new Option(o.textContent,o.value)));
      populate();render();
      note.textContent=`${data.date} · 09~18시 비교 (일 예보는 하루 등급) · 수집 ${new Date(data.collected_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})}`;
      document.querySelector('#forecast-range').textContent=data.forecast_dates.length?`현재 제공 날짜: ${data.forecast_dates[0]} ~ ${data.forecast_dates.at(-1)} · 날짜·오전/오후별 결측이 있을 수 있어요.`:'현재 제공된 예보 날짜가 없습니다.';
    }catch{if(request!==sequence)return;data=null;cards.replaceChildren();document.querySelector('#forecast-range').textContent='';note.textContent='전국 예보를 불러오지 못했습니다. 데이터 수집·연결 상태를 확인해 주세요.';}
  }
  province.addEventListener('change',()=>{populate();render();});
  topProvince.addEventListener('change',()=>{province.value=topProvince.value;populate();render();});
  region.addEventListener('change',activities);
  form.elements.start_date.addEventListener('change',load);
  date.addEventListener('change',()=>{form.elements.start_date.value=date.value;form.elements.start_date.dispatchEvent(new Event('change',{bubbles:true}));});
  load();
  return {selectRegion,refresh:load};
}
