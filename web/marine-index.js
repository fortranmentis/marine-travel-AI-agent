import {el} from './ui.js?v=0.5.0';

const grades=['매우좋음','좋음','보통','나쁨','매우나쁨'];
const tones=['excellent','good','moderate','poor','very-poor'];
const paths={excellent:'m3 12 4 4 8-9m-4 9 8-9',good:'m5 12 4 4L19 6',moderate:'M5 9h14M5 15h14',poor:'m12 3 10 18H2L12 3Zm0 6v5m0 3v.1','very-poor':'m8 3-5 5v8l5 5h8l5-5V8l-5-5H8Zm1 6 6 6m0-6-6 6',unknown:'M9 8a3 3 0 1 1 5 2c-2 1-2 2-2 3m0 4v.1'};

export function indexPresentation(grade,status='available'){
  const position=grades.indexOf(String(grade||'').replaceAll(' ',''));
  const known=position>=0&&status==='available';
  return {tone:known?tones[position]:'unknown',label:known?grades[position]:status==='stale'?'자료 갱신 필요':'자료 부족',position:known?position:-1};
}

function icon(tone){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',paths[tone]);path.setAttribute('fill','none');path.setAttribute('stroke','currentColor');path.setAttribute('stroke-width','1.8');path.setAttribute('stroke-linecap','round');path.setAttribute('stroke-linejoin','round');svg.append(path);return svg;
}

export function indexBadge(grade,status='available'){
  const value=indexPresentation(grade,status),badge=el('span',undefined,'marine-grade grade-'+value.tone);
  badge.append(icon(value.tone),el('strong',value.label));return badge;
}

export function marineIndexCard(index,{overall=false}={}){
  const value=indexPresentation(index.grade,index.status),card=el('section',undefined,'travel-index marine-index-card grade-'+value.tone+(overall?' overall-index':''));
  card.setAttribute('aria-label',index.label||'생활해양예보지수');
  const header=el('div',undefined,'marine-index-heading'),symbol=el('span','≈','marine-wave');symbol.setAttribute('aria-hidden','true');
  const title=el('div');title.append(el('span','생활해양예보지수','marine-index-eyebrow'),el('h4',index.label||'바다여행지수'));header.append(symbol,title);card.append(header,indexBadge(index.grade,index.status));
  const scale=el('ol',undefined,'marine-index-scale');scale.setAttribute('aria-label','공식 지수 5단계');
  grades.forEach((grade,i)=>{const step=el('li',undefined,'scale-'+tones[i]);step.append(icon(tones[i]),el('span',grade));if(i===value.position){step.classList.add('active');step.setAttribute('aria-current','step');step.setAttribute('aria-label',grade+' · 현재 등급');}scale.append(step);});card.append(scale);
  if(overall)card.append(el('p',`${index.covered_days}/${index.total_days}일 자료 확보`,'index-coverage'));
  else card.append(el('p',(index.area?index.area+' 권역 · ':'')+(index.aggregation||''),'index-coverage'));
  if(value.position<0)card.append(el('p','확인된 예보가 부족해 등급을 표시하지 않았어요.','index-missing'));
  if(index.note)card.append(el('p',index.note,'index-note'));
  if(index.source){const link=el('a','국립해양조사원 자료 ↗');link.href=index.source;link.target='_blank';link.rel='noopener noreferrer';card.append(link);}
  return card;
}
