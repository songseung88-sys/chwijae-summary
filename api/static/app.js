const qs = (s) => document.querySelector(s);
const state = { data:null, articleVisible:10, rankingExpanded:{}, categoryFilter:null };
function uiCopy(key,fallback=""){
  const values=state.data?.site_config?.ui_copy;
  return values&&Object.prototype.hasOwnProperty.call(values,key)?values[key]:fallback;
}
function paintUiCopy(){
  const entries={
    "#dashboardTitle":"dashboard_title","#aboutLinkLabel":"about_link",
    "#dateLabel":"date_label","#categoryCriteria":"category_criteria",
    "#clearTopicFilter":"clear_category","#categoryDialogTitle":"category_dialog_title"
  };
  for(const [selector,key] of Object.entries(entries)){
    const el=qs(selector);if(el)el.textContent=uiCopy(key,el.textContent);
  }
  const heading=qs("#dashboardTitle");
  if(heading)document.title=heading.textContent||"취재를 종합하면";
  for(const selector of ["#closeCategoryDialog","#closeRankingDialog"]){
    const el=qs(selector);if(el)el.setAttribute("aria-label",uiCopy("dialog_close","팝업 닫기"));
  }
}


function esc(v=""){
  return String(v).replace(/[&<>"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[m]));
}
function fmtDateTime(v){
  if(!v) return "";
  const d = new Date(v);
  return new Intl.DateTimeFormat("ko-KR",{hour:"2-digit",minute:"2-digit",hour12:false}).format(d);
}
function renderCollectionHealth(collection){
  const el=qs("#collectionHealth");
  const stamp=collection?.finished_at;
  if(!stamp){
    el.textContent=uiCopy("collection_unknown","마지막 수집 시각: 확인되지 않음");
    return;
  }
  const dt=new Date(stamp);
  if(Number.isNaN(dt.getTime())){
    el.textContent=uiCopy("collection_unknown","마지막 수집 시각: 확인되지 않음");
    return;
  }
  const time=new Intl.DateTimeFormat("ko-KR",{
    timeZone:"Asia/Seoul",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false
  }).format(dt);
  el.textContent=`${uiCopy("collection_done","마지막 수집 완료: ")}${time}`;
}
function rowLabel(r){
  return r.publisher ? `${esc(r.name)} <span class="rank-affiliation">${esc(r.publisher)}</span>` : esc(r.name);
}
function renderRanking(el, rows, expanded=false, filterable=false){
  if(!rows?.length){el.innerHTML=`<div class="empty">${esc(uiCopy("empty_data","표시할 데이터가 없습니다."))}</div>`;return;}
  const visible = expanded ? rows : rows.slice(0,5);
  const max = rows[0].count || 1;
  el.innerHTML = visible.map((r,i)=>{
    const selected = filterable && state.categoryFilter===r.name;
    const tag = filterable ? "button" : "div";
    const attrs = filterable ? `type="button" class="rank-row rank-filter${selected?" selected":""}" data-category="${esc(r.name)}" aria-pressed="${selected}"` : 'class="rank-row"';
    return `<${tag} ${attrs}>
      <span class="rank-num">${String(i+1).padStart(2,"0")}</span>
      <span class="rank-name">${rowLabel(r)}</span>
      <span class="rank-count">${r.count}${esc(uiCopy("count_unit","건"))}</span>
      <span class="bar-track"><span class="bar" style="width:${Math.max(3,r.count/max*100)}%"></span></span>
    </${tag}>`;
  }).join("");
}
function topicSecondLevelRows(hierarchy){
  const rows=[];
  for(const group of hierarchy||[]){
    for(const node of group.secondaries||[]){
      rows.push({
        primary:group.primary,
        secondary:node.secondary,
        count:Number(node.count)||0,
      });
    }
  }
  return rows.sort((a,b)=>b.count-a.count||
    String(a.primary).localeCompare(String(b.primary),"ko")||
    String(a.secondary).localeCompare(String(b.secondary),"ko"));
}

function renderTopicOverview(d){
  const pieHost=qs("#topicPrimaryPie");
  const bars=qs("#topicSecondaryBars");
  const primary=d.category_primary_ranking||[];
  const total=primary.reduce((n,r)=>n+(Number(r.count)||0),0);
  if(!total){
    pieHost.innerHTML=`<div class="empty">${esc(uiCopy("empty_data","표시할 데이터가 없습니다."))}</div>`;
    bars.innerHTML=`<div class="empty">${esc(uiCopy("empty_data","표시할 데이터가 없습니다."))}</div>`;
    return;
  }
  // Color palette matches the restrained editorial-blue theme, also used by the detail dialog.
  pieHost.innerHTML=labeledPieSvg(primary,total,true);
  const secondaries=topicSecondLevelRows(d.category_hierarchy).slice(0,5);
  if(!secondaries.length){
    bars.innerHTML=`<div class="empty">${esc(uiCopy("empty_data","표시할 데이터가 없습니다."))}</div>`;
    return;
  }
  const max=secondaries[0].count||1;
  const byPrimary=topicColorMap(primary);
  bars.innerHTML=secondaries.map((r,i)=>{
    const selected=state.categoryFilter===r.secondary;
    const width=Math.min(100,Math.max(3,r.count/max*100));
    const pct=(r.count/total*100).toFixed(1);
    const fill=byPrimary.get(r.primary)||topicColorForCategory(r.primary);
    return `<button type="button" class="topic-bar-row rank-filter${selected?" selected":""}"
      data-category="${esc(r.secondary)}" aria-pressed="${selected}">
      <span class="topic-bar-rank">${i+1}</span>
      <span class="topic-bar-name">${esc(r.primary)} &rsaquo; ${esc(r.secondary)}</span>
      <span class="topic-bar-track"><span class="topic-bar-fill" style="width:${width}%;background:${fill}"></span></span>
      <strong class="topic-bar-count">${r.count}${esc(uiCopy("count_unit","건"))}</strong>
      <span class="topic-bar-percent">${pct}%</span>
    </button>`;
  }).join("");
}

function renderExpressionChart(rows){
  const host=qs("#secondaryRanking");
  const top=(rows||[]).slice(0,5);
  if(!top.length){
    host.innerHTML=`<div class="empty">${esc(uiCopy("empty_data","표시할 데이터가 없습니다."))}</div>`;
    return;
  }
  const max=Number(top[0].count)||1;
  host.innerHTML=top.map((r,i)=>{
    const count=Number(r.count)||0;
    const width=Math.min(100,Math.max(3,count/max*100));
    return `<div class="expression-row">
      <span class="expression-rank">${i+1}</span>
      <span class="expression-name">${esc(r.name)}</span>
      <span class="expression-track"><span class="expression-fill" style="width:${width}%"></span></span>
      <strong class="expression-count">${count}${esc(uiCopy("expression_unit","회"))}</strong>
    </div>`;
  }).join("");
}

function renderRankings(){
  const d=state.data;
  const cfg=d.site_config;
  const defs=[
    ["publisherRanking",d.publisher_ranking_week],
    ["reporterRanking",d.reporter_ranking_week],
  ];
  for(const [id,rows] of defs){
    renderRanking(qs("#"+id),rows,false,false);
    const btn=document.querySelector(`.rank-toggle[data-target="${id}"]`);
    if(!btn) continue;
    btn.style.display=(rows?.length||0)>0?"inline":"none";
    btn.textContent=cfg.ranking_view_all_text;
  }
  renderTopicOverview(d);
  renderExpressionChart(d.secondary_expressions);
  for(const [id,rows] of [
    ["categoryRanking",d.category_primary_ranking],
    ["secondaryRanking",d.secondary_expressions]
  ]){
    const btn=document.querySelector(`.rank-toggle[data-target="${id}"]`);
    if(!btn) continue;
    btn.style.display=(rows?.length||0)>0?"inline":"none";
    btn.textContent=cfg.ranking_view_all_text;
  }
}
function renderHistory(rows){
  const max = Math.max(1,...rows.map(x=>x.count));
  qs("#historyBars").innerHTML = rows.map(r=>`
    <div class="day">
      <div class="barbox"><div class="vbar" style="height:${Math.max(2,r.count/max*100)}%"></div></div>
      <div class="count">${r.count}</div>
      <div class="date">${r.date.slice(5)}</div>
    </div>`).join("");
}
function renderCards(d){
  const cfg=d.site_config;
  const pub = d.top_publisher ? `${esc(d.top_publisher.name)} <small>${d.top_publisher.count}${esc(uiCopy("count_unit","건"))}</small>` : "—";
  const rep = d.top_reporter_today
    ? `${esc(d.top_reporter_today.name)} <small>${esc(d.top_reporter_today.publisher)} · ${d.top_reporter_today.count}${esc(uiCopy("count_unit","건"))}</small>`
    : "—";
  qs("#summaryCards").innerHTML = `
    <div class="card target-phrase-summary"><div class="label">${esc(cfg.card_today_label)}</div><div class="value">${d.today_count}${esc(uiCopy("count_unit","건"))}</div><div class="sub">${d.date}${esc(uiCopy("card_today_asof"," 현재"))}</div><button type="button" class="text-link target-phrase-open" id="openTargetPhraseDialog" aria-haspopup="dialog" aria-controls="targetPhraseDialog">${esc(cfg.ranking_view_all_text||"자세히 보기")}</button></div>
    <div class="card"><div class="label">${esc(cfg.card_publisher_label)}</div><div class="value compact">${pub}</div><div class="sub">${esc(uiCopy("card_publisher_asof","오늘 기준"))}</div></div>
    <div class="card"><div class="label">${esc(cfg.card_reporter_label)}</div><div class="value compact">${rep}</div><div class="sub">${esc(uiCopy("card_reporter_asof","오늘 기준"))}</div></div>
    <div class="card"><div class="label">${esc(cfg.card_exclusive_label)}</div><div class="value">${(d.exclusive_ratio*100).toFixed(1)}%</div><div class="sub">${d.exclusive_count} / ${d.today_count}${esc(uiCopy("count_unit","건"))}</div></div>`;
}
function highlightTargetPhrases(element, value){
  // Use text nodes rather than injecting HTML from published article content.
  const text=String(value||"");
  const regex=/(취재를\s*종합하면|본지\s*취재\s*결과|취재에\s*따르면|취재(?:를\s*)?한\s*결과|본보\s*취재\s*결과|본지\s*확인\s*결과)/g;
  let cursor=0;
  for(const match of text.matchAll(regex)){
    if(match.index>cursor) element.appendChild(document.createTextNode(text.slice(cursor,match.index)));
    const mark=document.createElement("mark");
    mark.className="phrase-highlight";
    mark.textContent=match[0];
    element.appendChild(mark);
    cursor=match.index+match[0].length;
  }
  element.appendChild(document.createTextNode(text.slice(cursor)));
}

function articleNode(a,cfg){
  const node = qs("#articleTemplate").content.cloneNode(true);
  node.querySelector(".news-meta").textContent = [a.publisher,(a.reporters||[]).join(", "),fmtDateTime(a.published_at)].filter(Boolean).join(" · ");
  node.querySelector("h3").textContent = a.title || "";
  highlightTargetPhrases(node.querySelector(".context"), a.context_sentence || "");
  const details=node.querySelector(".paragraph-details");
  if(a.context_paragraph){
    node.querySelector("summary").textContent=cfg.paragraph_toggle_text;
    highlightTargetPhrases(node.querySelector(".paragraph"),a.context_paragraph);
  }else{details.remove();}
  const links=[];
  if(a.original_url) links.push(`<a target="_blank" rel="noopener noreferrer" href="${esc(a.original_url)}">${esc(cfg.original_link_text)}</a>`);
  if(a.naver_url) links.push(`<a target="_blank" rel="noopener noreferrer" href="${esc(a.naver_url)}">${esc(cfg.naver_link_text)}</a>`);
  node.querySelector(".links").innerHTML=links.join("");
  return node;
}
function renderArticles(){
  const d=state.data, cfg=d.site_config;
  const rows=state.categoryFilter?d.articles.filter(a=>a.category_secondary===state.categoryFilter):d.articles;
  qs("#articleCount").textContent = state.categoryFilter?`${rows.length}${uiCopy("count_unit","건")} / ${uiCopy("article_count_total","전체 ")}${d.articles.length}${uiCopy("count_unit","건")}`:`${rows.length}${uiCopy("count_unit","건")}`;
  qs("#clearTopicFilter").hidden=!state.categoryFilter;
  const host = qs("#articleList");
  if(!rows.length){
    host.innerHTML='<div class="empty">'+esc(state.categoryFilter?uiCopy("empty_topic","이 주제에 해당하는 기사가 없습니다."):uiCopy("empty_articles","해당 날짜에 수집된 문장이 없습니다."))+'</div>';
    qs("#loadMore").style.display="none";
    return;
  }
  host.innerHTML = "";
  for(const a of rows.slice(0,state.articleVisible)) host.appendChild(articleNode(a,cfg));
  const more=qs("#loadMore");
  more.textContent=cfg.articles_more_text;
  more.style.display=state.articleVisible<rows.length?"inline-flex":"none";
}
function applyCopy(d){
  const c=d.site_config;
  paintUiCopy();
  qs("#heroDescription").textContent=c.hero_description;
  qs("#usageGroupTitle").textContent=c.group_usage_title||"";
  qs("#analysisGroupTitle").textContent=c.group_analysis_title||"";
  qs("#publisherTitle").textContent=c.section_publisher_title;
  qs("#reporterTitle").textContent=c.section_reporter_title;
  qs("#categoryTitle").textContent=c.section_category_title;
  qs("#topicPrimaryCaption").textContent=c.topic_primary_caption??"";
  qs("#topicSecondaryCaption").textContent=c.topic_secondary_caption??"";
  qs("#secondaryTitle").textContent=c.section_secondary_title;
  qs("#historyTitle").textContent=c.section_history_title;
  qs("#articlesTitle").textContent=c.section_articles_title;
}
async function load(date){
  const res = await fetch(`/api/dashboard?date=${encodeURIComponent(date)}`);
  if(!res.ok) throw new Error(uiCopy("dashboard_load_error","데이터를 불러오지 못했습니다."));
  const d = await res.json();
  state.data=d; state.articleVisible=10; state.rankingExpanded={}; state.categoryFilter=null;
  applyCopy(d);
  renderCards(d);
  renderCollectionHealth(d.last_successful_collection);
  renderRankings();
  renderFirstPhrasePosition(d.first_phrase_position);
  renderHistory(d.daily_counts_14d);
  renderArticles();
  qs("#publisherWeekLabel").textContent = `${d.week_start}~${d.date}`;
  qs("#weekLabel").textContent = `${d.week_start}~${d.date}`;
}
document.addEventListener("DOMContentLoaded",()=>{
  const input=qs("#dateInput");
  const today=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
  input.value=today;
  load(today).catch(e=>{qs("#articleList").innerHTML=`<div class="empty">${esc(e.message)}</div>`;});
  input.addEventListener("change",()=>load(input.value));
  document.querySelectorAll(".rank-toggle").forEach(btn=>btn.addEventListener("click",()=>{
    const id=btn.dataset.target;
    if(id==="categoryRanking"){openCategoryDialog();return;}
    openRankingDialog(id);
  }));
  qs("#closeRankingDialog").addEventListener("click",()=>qs("#rankingDialog").close());
  qs("#rankingDialog").addEventListener("click",e=>{
    if(e.target===qs("#rankingDialog")) qs("#rankingDialog").close();
  });
  qs("#rankingDialogMore").addEventListener("click",showMoreRankingDialog);
  qs("#closeCategoryDialog").addEventListener("click",()=>qs("#categoryDialog").close());
  qs("#categoryDialog").addEventListener("click",e=>{
    if(e.target===qs("#categoryDialog")) qs("#categoryDialog").close();
  });
  qs("#summaryCards").addEventListener("click",event=>{
    if(event.target.closest("#openTargetPhraseDialog"))openTargetPhraseDialog();
  });
  qs("#loadMore").addEventListener("click",()=>{state.articleVisible+=10;renderArticles();});
  qs("#categoryRanking").addEventListener("click",e=>{
    const target=e.target.closest(".rank-filter");
    if(!target) return;
    const category=target.dataset.category;
    state.categoryFilter=state.categoryFilter===category?null:category;
    state.articleVisible=10;
    renderRankings();renderArticles();
    qs("#articlesTitle").scrollIntoView({behavior:"smooth",block:"start"});
  });
  qs("#clearTopicFilter").addEventListener("click",()=>{
    state.categoryFilter=null;state.articleVisible=10;renderRankings();renderArticles();
  });
});
