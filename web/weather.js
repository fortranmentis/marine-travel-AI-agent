import {el,button} from './ui.js?v=0.5.0';

export function weatherKind(row) {
  const pty=String(row?.PTY??'');
  if(['1','4','5'].includes(pty))return 'rain';
  if(['2','6'].includes(pty))return 'sleet';
  if(['3','7'].includes(pty))return 'snow';
  if(pty!==''&&pty!=='0')return 'unknown';
  const sky=String(row?.SKY??'');
  return sky==='1'?'sun':sky==='3'?'partly':sky==='4'?'cloud':'unknown';
}
const labels={sun:'맑음',partly:'구름 많음',cloud:'흐림',rain:'비',sleet:'비 또는 눈',snow:'눈',unknown:'자료 없음'};
const paths={sun:'M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6L7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4',cloud:'M6 18a4 4 0 1 1 1-7.9 5 5 0 0 1 9.7 1.1A3.5 3.5 0 1 1 18 18H6',rain:'M6 15a4 4 0 1 1 1-7 5 5 0 0 1 9 1A3 3 0 1 1 18 15H6m2 3-1 3m6-3-1 3m6-3-1 3',snow:'M6 14a4 4 0 1 1 1-7 5 5 0 0 1 9 1A3 3 0 1 1 18 14H6m2 4v4m-2-2h4m6-2v4m-2-2h4',sleet:'M6 14a4 4 0 1 1 1-7 5 5 0 0 1 9 1A3 3 0 1 1 18 14H6m2 4-1 3m9-3v4m-2-2h4',unknown:'M9 8a3 3 0 1 1 5 2c-2 1-2 2-2 3m0 4v.1'};
export function weatherIcon(kind) {
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','weather-icon '+kind);svg.setAttribute('role','img');svg.setAttribute('aria-label',labels[kind]);
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',paths[kind]||paths.cloud);path.setAttribute('fill','none');path.setAttribute('stroke','currentColor');path.setAttribute('stroke-width','1.6');path.setAttribute('stroke-linecap','round');svg.append(path);
  if(kind==='sun'||kind==='partly'){const circle=document.createElementNS(svg.namespaceURI,'circle');circle.setAttribute('cx','12');circle.setAttribute('cy','12');circle.setAttribute('r','4');circle.setAttribute('fill','none');circle.setAttribute('stroke','currentColor');svg.append(circle);}
  return svg;
}
function number(v){if(v===null||v===undefined||v==='')return null;const n=Number(v);return Number.isFinite(n)&&n>-900?n:null;}
export function summarizeWeather(weather,start,end){
  const hourly=Object.entries(weather?.forecasts||{}).sort(([a],[b])=>a.localeCompare(b));
  const selected=hourly.filter(([time])=>time>=start.replace(':','')&&time<end.replace(':',''));
  const values=k=>selected.map(([,v])=>number(v[k])).filter(v=>v!==null);
  const temperatures=values('TMP'),pop=values('POP'),wind=values('WSD');
  const priority={unknown:0,sun:1,partly:2,cloud:3,rain:4,sleet:5,snow:6};
  const kind=selected.reduce((best,[,r])=>priority[weatherKind(r)]>priority[best]?weatherKind(r):best,'unknown');
  return {hourly,kind,temperature:temperatures.length?[Math.min(...temperatures),Math.max(...temperatures)]:null,pop:pop.length?Math.max(...pop):null,wind:wind.length?Math.max(...wind):null};
}
export function formatIssue(value){if(!value)return '발표 시각 미확인';const date=new Date(value);if(Number.isNaN(date.getTime()))return '발표 시각 미확인';return new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'long',day:'numeric',hour:'numeric',hour12:false}).format(date)+' 발표';}
export function weatherCard(weather,start,end){
  const summary=summarizeWeather(weather,start,end),box=el('section',undefined,'weather-card');box.setAttribute('aria-label','여행 시간대 날씨');
  const header=el('div',undefined,'weather-heading');header.append(el('strong','여행 시간대 날씨'),el('span','특보 미확인','weather-badge'));box.append(header);
  if(weather?.status!=='available'||!summary.hourly.length){box.append(el('p','해당 날짜 예보를 확보하지 못했어요.','forecast'));return box;}
  const strip=el('div',undefined,'weather-summary');const main=el('div',undefined,'weather-main');main.append(weatherIcon(summary.kind),el('strong',labels[summary.kind]));strip.append(main);
  for(const [label,value] of [['기온 범위',summary.temperature?summary.temperature.join(' ~ ')+'°C':'자료 없음'],['최대 강수확률',summary.pop===null?'자료 없음':summary.pop+'%'],['최대 바람',summary.wind===null?'자료 없음':summary.wind+'m/s']]){const item=el('div',undefined,'weather-stat');item.append(el('span',label),el('strong',value));strip.append(item);}box.append(strip);
  box.append(el('p',formatIssue(weather.issue_at)+' · 대표 지점: '+(weather.reference_place?.title||'조회 지점 미확인'),'forecast'));
  const details=el('details'),toggle=el('summary','시간별 예보 · 좌우로 넘겨 보기'),hours=el('div',undefined,'weather-hours');details.open=true;
  hours.tabIndex=0;hours.setAttribute('role','region');hours.setAttribute('aria-label','시간별 날씨 · 좌우 방향키로 이동');
  const controls=el('div',undefined,'weather-scroll-controls');
  const scroll=direction=>hours.scrollBy({left:direction*Math.max(150,hours.clientWidth*.7),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
  const left=button('← 이전',()=>scroll(-1)),right=button('다음 →',()=>scroll(1));
  left.setAttribute('aria-label','이전 시간대');right.setAttribute('aria-label','다음 시간대');controls.append(left,right);details.append(toggle,controls,hours);
  hours.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();scroll(e.key==='ArrowLeft'?-1:1);}});
  let dragging=null;
  hours.addEventListener('pointerdown',e=>{if(e.pointerType!=='mouse'||e.button!==0)return;dragging={x:e.clientX,left:hours.scrollLeft};hours.setPointerCapture(e.pointerId);hours.classList.add('dragging');});
  hours.addEventListener('pointermove',e=>{if(dragging)hours.scrollLeft=dragging.left+dragging.x-e.clientX;});
  const stop=()=>{dragging=null;hours.classList.remove('dragging');};hours.addEventListener('pointerup',stop);hours.addEventListener('pointercancel',stop);hours.addEventListener('lostpointercapture',stop);
  for(const [time,row] of summary.hourly){const h=el('div',undefined,'weather-hour');h.append(el('span',time.slice(0,2)+':'+time.slice(2)),weatherIcon(weatherKind(row)),el('strong',number(row.TMP)===null?'—':row.TMP+'°'),el('small',number(row.POP)===null?'강수 —':row.POP+'%'));hours.append(h);}box.append(details);return box;
}
