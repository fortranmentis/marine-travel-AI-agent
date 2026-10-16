export function transitSummary(leg){
  const sections=(leg.sections||[]).map(s=>`${{walk:'도보',bus:'버스',subway:'지하철'}[s.mode]||'이동'} ${(s.lines||[]).filter(Boolean).join('/')} ${s.minutes??'—'}분${s.start&&s.end?` (${s.start} → ${s.end})`:''}`).join(' → ');
  const metrics=[leg.transfers!=null?`환승 ${leg.transfers}회`:null,leg.walking_minutes!=null?`도보 합계 ${leg.walking_minutes}분`:null,leg.fare!=null?`화면 요금 ${Number(leg.fare).toLocaleString('ko-KR')}원`:null].filter(Boolean).join(' · ');
  const observed=leg.observed_at?new Date(leg.observed_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):null;
  return {sections,metrics,observed:observed?`${observed} 조회${leg.cached?' · 캐시 사용':''}`:null};
}
export function transitSourceUrl(value){
  try{const url=new URL(value);return url.protocol==='https:'&&url.hostname==='map.naver.com'&&url.pathname.startsWith('/p/directions/')?url.href:null;}catch{return null;}
}
