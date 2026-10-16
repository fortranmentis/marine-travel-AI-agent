import {el} from './ui.js?v=0.4.3';

export function datesFor(start, days) {
  const date=new Date(start+'T00:00:00Z');
  if(Number.isNaN(date.getTime()))return [];
  return Array.from({length:days},(_,i)=>new Date(date.getTime()+i*86400000).toISOString().slice(0,10));
}
export function initializeTripForm(form){
  const children=document.querySelector('#child-ages'),days=document.querySelector('#daily-times');
  function ages(values){
    const previous=values||[...children.querySelectorAll('input')].map(n=>n.value);
    children.replaceChildren();
    for(let i=0;i<Number(form.elements.child_count.value);i++){
      const label=el('label',`자녀 ${i+1} 나이`),input=el('input');input.type='number';input.min='0';input.max='17';input.required=true;input.value=previous[i]??'6';input.name='child_age';label.append(input);children.append(label);
    }
  }
  function times(values){
    const previous=values||[...days.querySelectorAll('[data-date]')].map(row=>({date:row.dataset.date,start:row.querySelector('[data-start]').value,end:row.querySelector('[data-end]').value}));
    days.replaceChildren();
    datesFor(form.elements.start_date.value,Number(form.elements.days.value)).forEach((date,i)=>{
      const row=el('div',undefined,'daily-time-row');row.dataset.date=date;row.append(el('strong',`${i+1}일차 · ${date.slice(5)}`));
      const pair=el('div',undefined,'pair');const saved=previous.find(t=>t.date===date);
      for(const [key,text,fallback] of [['start','하루 시작','09:00'],['end','하루 마침','18:00']]){
        const label=el('label',text),input=el('input');input.type='time';input.required=true;input.dataset[key]='';input.value=saved?.[key]||fallback;label.append(input);pair.append(label);
      }row.append(pair);days.append(row);
    });
  }
  form.elements.child_count.addEventListener('change',()=>ages());
  for(const name of ['start_date','days'])form.elements[name].addEventListener('change',()=>times());
  form.elements.party_type.addEventListener('change',()=>{
    const defaults={solo:[1,0],couple:[2,0],family:[2,1],group:[6,0]}[form.elements.party_type.value];
    form.elements.adults.value=defaults[0];form.elements.child_count.value=defaults[1];ages();
  });
  ages();times();
  return {
    read(){const data=new FormData(form);return {party_type:data.get('party_type'),transport:data.get('transport'),
      adults:Number(data.get('adults')),child_count:Number(data.get('child_count')),
      child_ages:[...children.querySelectorAll('input')].map(n=>Number(n.value)),
      visits_per_day:Number(data.get('visits_per_day')),cafes:data.get('cafes')==='on',cuisines:data.getAll('cuisine'),
      island_id:data.get('island_id')||null,
      daily_times:[...days.querySelectorAll('[data-date]')].map(row=>({date:row.dataset.date,start:row.querySelector('[data-start]').value,end:row.querySelector('[data-end]').value}))};},
    sync(trip){for(const name of ['party_type','transport','child_count','visits_per_day'])form.elements[name].value=trip[name]??({party_type:'family',transport:'car',child_count:trip.child_ages.length,visits_per_day:2}[name]);form.elements.cafes.checked=trip.cafes??true;form.elements.island_id.value=trip.island_id||'';for(const n of form.querySelectorAll('[name=cuisine]'))n.checked=(trip.cuisines||[]).includes(n.value);ages(trip.child_ages);times(trip.daily_times?.length?trip.daily_times:datesFor(trip.start_date,trip.days).map(date=>({date,start:trip.day_start,end:trip.day_end})));}
  };
}
