// BigKinds annual survey visualizations, 2016–2025. No external chart library.
"use strict";

const BIGKINDS_DEFAULT_PUBLISHERS=["한겨레","경향신문","조선일보","한국일보"];
const BIGKINDS_COLORS={
  "한겨레":"#285B91",
  "경향신문":"#965E57",
  "조선일보":"#47785F",
  "한국일보":"#BA8540",
  "국민일보":"#6D6090",
  "동아일보":"#35818D",
  "문화일보":"#AE738E",
  "서울신문":"#787F47",
  "세계일보":"#667D9E",
  "중앙일보":"#966B5D"
};
const BIGKINDS_PLOT={width:940,height:380,left:65,right:23,top:25,bottom:53};
const bigkindsFormat=new Intl.NumberFormat("ko-KR");
const bigkindsNumber=value=>bigkindsFormat.format(value);
const bigkindsEscape=value=>String(value).replace(/&/g,"&amp;").replace(/</g,"&lt;")
  .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const bigkindsYMax=(values,step)=>Math.max(step,Math.ceil(Math.max(...values,0)/step)*step);

function validateBigkinds(data){
  if(!data||!Array.isArray(data.years)||!Array.isArray(data.totals)||
     !data.publishers||typeof data.publishers!=="object")throw Error("빅카인즈 자료 형식 오류");
  if(data.years.length!==10||data.totals.length!==10)throw Error("연도별 자료 누락");
  const names=Object.keys(data.publishers);
  if(names.length!==10)throw Error("언론사별 자료 누락");
  for(let i=0;i<10;i++){
    if(data.years[i]!==2016+i||!Number.isSafeInteger(data.totals[i])||data.totals[i]<0){
      throw Error("연도·합계 자료 오류");
    }
    let sum=0;
    for(const name of names){
      const values=data.publishers[name];
      if(!Array.isArray(values)||values.length!==10||!Number.isSafeInteger(values[i])||values[i]<0){
        throw Error("언론사별 기사 수 오류");
      }
      sum+=values[i];
    }
    if(sum!==data.totals[i])throw Error("빅카인즈 원표의 연도별 합계가 일치하지 않습니다: "+data.years[i]);
  }
  return true;
}

function bigkindsLayout(){
  const p=BIGKINDS_PLOT;
  const innerWidth=p.width-p.left-p.right;
  const bottom=p.height-p.bottom;
  return {p,innerWidth,bottom,innerHeight:bottom-p.top,step:innerWidth/10};
}
function bigkindsX(index){
  const l=bigkindsLayout();
  return l.p.left+(index+.5)*l.step;
}
function bigkindsY(value,ymax){
  const l=bigkindsLayout();
  return l.bottom-(value/ymax)*l.innerHeight;
}
function bigkindsAxis(data,ymax,ticks){
  const l=bigkindsLayout();
  let markup="";
  for(let n=0;n<=ticks;n++){
    const val=ymax*n/ticks;
    const y=bigkindsY(val,ymax);
    markup+='<line class="bigkinds-gridline" x1="'+l.p.left+'" y1="'+y+
      '" x2="'+(l.p.width-l.p.right)+'" y2="'+y+'"/>'+
      '<text class="bigkinds-axis-label" text-anchor="end" x="'+(l.p.left-11)+
      '" y="'+(y+4)+'">'+bigkindsNumber(val)+'</text>';
  }
  data.years.forEach((year,i)=>{
    markup+='<text class="bigkinds-axis-label bigkinds-axis-year" text-anchor="middle" x="'+
      bigkindsX(i)+'" y="'+(l.bottom+28)+'">'+year+'</text>';
  });
  return markup;
}
function bigkindsHoverGuides(){
  const l=bigkindsLayout();
  let lines="",hits="";
  for(let i=0;i<10;i++){
    const x=bigkindsX(i);
    lines+='<line class="bigkinds-guide" data-guide="'+i+'" x1="'+x+
      '" x2="'+x+'" y1="'+l.p.top+'" y2="'+l.bottom+'" />';
    hits+='<rect class="bigkinds-hit" data-year-index="'+i+'" tabindex="0" '+
      'x="'+(x-l.step/2)+'" y="'+l.p.top+'" width="'+l.step+'" height="'+l.innerHeight+
      '" fill="transparent" />';
  }
  return {lines,hits};
}
function annualBigkindsSvg(data){
  const l=bigkindsLayout();
  const max=bigkindsYMax(data.totals,1000);
  const guides=bigkindsHoverGuides();
  const bars=data.totals.map((count,i)=>{
    const y=bigkindsY(count,max);
    const h=Math.max(l.bottom-y,2);
    const x=bigkindsX(i)-l.step*.29;
    return '<rect class="bigkinds-annual-bar'+(i===9?' bigkinds-latest':'')+
      '" x="'+x+'" y="'+(l.bottom-h)+'" width="'+(l.step*.58)+
      '" height="'+h+'" rx="3"/>';
  }).join("");
  return '<svg class="bigkinds-svg" viewBox="0 0 940 380" role="img" '+
    'aria-label="빅카인즈 취재를 종합하면 연도별 기사 수, 2016년부터 2025년까지. '+
    '연도에 마우스를 올리거나 Tab 키로 자세한 수치를 확인할 수 있습니다.">'+
    bigkindsAxis(data,max,max/1000)+bars+guides.lines+guides.hits+'</svg>';
}
function orderedBigkindsPublishers(data){
  const all=Object.keys(data.publishers);
  return BIGKINDS_DEFAULT_PUBLISHERS.filter(name=>all.includes(name))
    .concat(all.filter(name=>!BIGKINDS_DEFAULT_PUBLISHERS.includes(name)));
}
function publisherBigkindsSvg(data,selected){
  const names=orderedBigkindsPublishers(data).filter(name=>selected.has(name));
  const values=names.flatMap(name=>data.publishers[name]);
  const ymax=bigkindsYMax(values,values.length&&Math.max(...values)>1000?300:200);
  const l=bigkindsLayout();
  const guides=bigkindsHoverGuides();
  const axis=bigkindsAxis(data,ymax,5);
  if(!names.length){
    return '<svg class="bigkinds-svg" viewBox="0 0 940 380" role="img" aria-label="선택된 언론사가 없습니다.">'+
      axis+'<text x="470" y="165" class="bigkinds-empty" text-anchor="middle">비교할 언론사를 선택해 주세요</text></svg>';
  }
  const lines=names.map(name=>{
    const values=data.publishers[name];
    const color=BIGKINDS_COLORS[name]||"#344E6B";
    const d=values.map((n,i)=>(i?"L":"M")+bigkindsX(i)+" "+bigkindsY(n,ymax)).join(" ");
    const points=values.map((n,i)=>'<circle class="bigkinds-series-dot" cx="'+bigkindsX(i)+
      '" cy="'+bigkindsY(n,ymax)+'" r="3.7" fill="'+color+'"/>').join("");
    return '<path class="bigkinds-series-line" stroke="'+color+'" d="'+d+'"/>'+points;
  }).join("");
  return '<svg class="bigkinds-svg" viewBox="0 0 940 380" role="img" '+
    'aria-label="선택한 언론사별 취재를 종합하면 연간 기사 수. 연도에 마우스를 올리거나 Tab 키로 정확한 수치를 확인할 수 있습니다.">'+
    axis+lines+guides.lines+guides.hits+'</svg>';
}

function bigkindsTipMarkup(data,type,index,selected){
  const year=data.years[index];
  if(type==="annual"){
    return '<div class="bigkinds-tip-year">'+year+'년 · 전체</div>'+
      '<strong class="bigkinds-tip-total">'+bigkindsNumber(data.totals[index])+'건</strong>';
  }
  const rows=orderedBigkindsPublishers(data).filter(n=>selected.has(n));
  return '<div class="bigkinds-tip-year">'+year+'년 · 언론사별</div>'+
    '<ul class="bigkinds-tip-list">'+rows.map(name=>'<li><span><i style="background:'+
      (BIGKINDS_COLORS[name]||"#344E6B")+'"></i>'+bigkindsEscape(name)+'</span>'+
      '<strong>'+bigkindsNumber(data.publishers[name][index])+'건</strong></li>').join("")+'</ul>';
}

function wireBigkindsTooltip(shell,data,type,selected){
  const svg=shell.querySelector("svg");
  const tip=shell.querySelector(".bigkinds-tooltip");
  if(!svg||!tip)return;
  function hide(){
    tip.hidden=true;
    svg.querySelectorAll(".bigkinds-guide").forEach(el=>el.classList.remove("is-active"));
  }
  function show(element,event){
    if(!element||!element.hasAttribute("data-year-index"))return;
    const index=Number(element.getAttribute("data-year-index"));
    tip.innerHTML=bigkindsTipMarkup(data,type,index,selected);
    tip.hidden=false;
    svg.querySelectorAll(".bigkinds-guide").forEach(el=>
      el.classList.toggle("is-active",el.getAttribute("data-guide")===String(index)));
    const rect=shell.getBoundingClientRect();
    let x,y;
    if(event&&Number.isFinite(event.clientX)&&Number.isFinite(event.clientY)){
      x=event.clientX-rect.left+15;
      y=event.clientY-rect.top-12;
    }else{
      const box=element.getBoundingClientRect();
      x=box.left+box.width/2-rect.left+12;
      y=box.top+18-rect.top;
    }
    tip.style.left=Math.max(5,Math.min(x,rect.width-tip.offsetWidth-5))+"px";
    tip.style.top=Math.max(5,Math.min(y,rect.height-tip.offsetHeight-5))+"px";
  }
  svg.addEventListener("pointermove",event=>show(event.target.closest(".bigkinds-hit"),event));
  svg.addEventListener("pointerleave",hide);
  svg.addEventListener("focusin",event=>show(event.target.closest(".bigkinds-hit"),null));
  svg.addEventListener("focusout",hide);
  svg.addEventListener("click",event=>show(event.target.closest(".bigkinds-hit"),event));
}

function renderBigkindsLegend(data,selected,render){
  const host=document.querySelector("#bigkindsPublisherFilters");
  host.innerHTML=orderedBigkindsPublishers(data).map(name=>{
    const active=selected.has(name);
    return '<button type="button" class="bigkinds-publisher-toggle'+(active?' is-selected':'')+
      '" aria-pressed="'+active+'" data-publisher="'+bigkindsEscape(name)+'" '+
      'style="--series-color:'+(BIGKINDS_COLORS[name]||"#344E6B")+'">'+
      '<span class="bigkinds-toggle-indicator" aria-hidden="true"></span>'+bigkindsEscape(name)+'</button>';
  }).join("");
  host.querySelectorAll("button[data-publisher]").forEach(button=>{
    button.addEventListener("click",()=>{
      const name=button.getAttribute("data-publisher");
      if(selected.has(name))selected.delete(name);
      else selected.add(name);
      render();
    });
  });
}
async function loadBigkindsCharts(){
  const response=await fetch("/static/bigkinds-annual-2016-2025.json",{cache:"no-store"});
  if(!response.ok)throw Error("빅카인즈 자료 불러오기 실패");
  const data=await response.json();
  validateBigkinds(data);
  const selected=new Set(BIGKINDS_DEFAULT_PUBLISHERS);
  const annualHost=document.querySelector("#bigkindsAnnualChart");
  const publisherHost=document.querySelector("#bigkindsPublisherChart");
  annualHost.innerHTML=annualBigkindsSvg(data)+'<div class="bigkinds-tooltip" hidden></div>';
  wireBigkindsTooltip(annualHost,data,"annual",selected);
  function renderPublishers(){
    publisherHost.innerHTML=publisherBigkindsSvg(data,selected)+'<div class="bigkinds-tooltip" hidden></div>';
    wireBigkindsTooltip(publisherHost,data,"publisher",selected);
    renderBigkindsLegend(data,selected,renderPublishers);
    document.querySelector("#bigkindsSelectedCount").textContent=selected.size+" / 10개 언론사 선택";
  }
  renderPublishers();
  document.querySelector("#bigkindsResetPublishers").addEventListener("click",()=>{
    selected.clear();
    BIGKINDS_DEFAULT_PUBLISHERS.forEach(name=>selected.add(name));
    renderPublishers();
  });
  document.querySelector("#bigkindsPeakYear").textContent="2025년 "+bigkindsNumber(data.totals[9])+"건";
}
if(typeof document!=="undefined"){
  document.addEventListener("DOMContentLoaded",()=>{
    if(!document.querySelector("#bigkindsAnnualChart"))return;
    loadBigkindsCharts().catch(error=>{
      console.error("BigKinds annual chart:",error);
      for(const id of ["#bigkindsAnnualChart","#bigkindsPublisherChart"]){
        document.querySelector(id).textContent="그래프 데이터를 불러오지 못했습니다.";
      }
    });
  });
}
if(typeof module!=="undefined"&&module.exports){
  module.exports={BIGKINDS_DEFAULT_PUBLISHERS,BIGKINDS_COLORS,
    validateBigkinds,orderedBigkindsPublishers,annualBigkindsSvg,
    publisherBigkindsSvg,bigkindsTipMarkup,bigkindsYMax};
}
