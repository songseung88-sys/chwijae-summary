/* First occurrence of the literal core expression; no new article fetches. */
function safePositionLink(value){
  try{
    const url=new URL(String(value||""));
    return /^https?:$/.test(url.protocol)?url.href:"";
  }catch(_error){return "";}
}
function positionPercent(value,total){
  return total?Math.round(Number(value||0)*1000/total)/10:0;
}
function renderFirstPhrasePosition(data){
  const root=qs("#firstPhrasePosition");
  const title=qs("#positionTitle");
  const caption=qs("#positionScope");
  if(!root || !title || !caption)return;
  title.textContent=uiCopy("position_title","'취재를 종합하면'은 기사 어디에 등장할까?");
  const n=Number(data?.analyzed_articles)||0;
  caption.textContent=uiCopy("position_period_prefix","수집 기간")+" "+
    String(data?.period_start||"")+"~"+String(data?.period_end||"")+" · "+
    uiCopy("position_article_label","'취재를 종합하면' 포함 기사")+" "+n+uiCopy("count_unit","건");
  if(!n){
    root.innerHTML='<p class="empty">'+esc(uiCopy("position_empty","위치를 분석할 수 있는 기사 본문이 없습니다."))+'</p>';
    return;
  }
  const num=(v)=>Number(v).toLocaleString("ko-KR",{maximumFractionDigits:1});
  const bars=(items)=>items.map(item=>{
    const count=Number(item.count)||0;
    const percent=positionPercent(count,n);
    return '<div class="position-row">'+
      '<span class="position-row-label">'+esc(item.label)+'</span>'+
      '<div class="position-track"><span class="position-fill" style="width:'+percent+'%"></span></div>'+
      '<span class="position-row-value">'+count+'건 · '+num(percent)+'%</span>'+
    '</div>';
  }).join("");
  const best=data.modal_paragraph ? data.modal_paragraph+'문단' : "—";
  const mean=num(data.mean_characters);
  const samples=(data.examples||[]).slice(0,5).map(ex=>{
    const url=safePositionLink(ex.url);
    const name=esc(ex.publisher||"");
    const text=esc(ex.excerpt||"");
    return '<li><span class="position-example-meta">'+
      esc(String(ex.paragraph||""))+'문단 · 본문 시작 '+esc(String(ex.character_offset||0))+'자 지점 · '+name+
      '</span><div class="position-example-text">'+
      (url?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+text+'</a>':text)+
      '</div></li>';
  }).join("");
  root.innerHTML=
    '<div class="position-stats">'+
      '<div><span>'+esc(uiCopy("position_avg","평균 첫 등장"))+'</span><strong>'+mean+'<small>자</small></strong></div>'+
      '<div><span>'+esc(uiCopy("position_modal","가장 많이 등장하는 문단"))+'</span><strong>'+esc(best)+'</strong></div>'+
    '</div>'+
    '<div class="position-splits">'+
      '<div><h3>등장하는 문단</h3><div class="position-bars">'+bars(data.paragraph_distribution||[])+'</div></div>'+
      '<div><h3>문단 안에서의 등장 구조</h3><div class="position-bars">'+bars(data.structure||[])+'</div></div>'+
    '</div>'+

    (samples?'<details class="position-examples"><summary>'+
      esc(uiCopy("position_samples","실제 기사에서 확인하기"))+
      '</summary><ul>'+samples+'</ul></details>':"");
}
