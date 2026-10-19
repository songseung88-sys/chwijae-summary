const qs = (s) => document.querySelector(s);
const state = { data:null, articleVisible:10, rankingExpanded:{} };

function esc(v=""){
  return String(v).replace(/[&<>"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[m]));
}
function fmtDateTime(v){
  if(!v) return "";
  const d = new Date(v);
  return new Intl.DateTimeFormat("ko-KR",{hour:"2-digit",minute:"2-digit",hour12:false}).format(d);
}
function rowLabel(r){
  return r.publisher ? `${esc(r.name)} <span class="rank-affiliation">${esc(r.publisher)}</span>` : esc(r.name);
}
function renderRanking(el, rows, expanded=false){
  if(!rows?.length){el.innerHTML='<div class="empty">표시할 데이터가 없습니다.</div>';return;}
  const visible = expanded ? rows : rows.slice(0,5);
  const max = rows[0].count || 1;
  el.innerHTML = visible.map((r,i)=>`
    <div class="rank-row">
      <div class="rank-num">${String(i+1).padStart(2,"0")}</div>
      <div class="rank-name">${rowLabel(r)}</div>
      <div class="rank-count">${r.count}건</div>
      <div class="bar-track"><div class="bar" style="width:${Math.max(3,r.count/max*100)}%"></div></div>
    </div>`).join("");
}
function renderRankings(){
  const d=state.data;
  const cfg=d.site_config;
  const defs=[
    ["publisherRanking",d.publisher_ranking],
    ["reporterRanking",d.reporter_ranking_week],
    ["categoryRanking",d.category_ranking_original],
    ["secondaryRanking",d.secondary_expressions],
  ];
  for(const [id,rows] of defs){
    renderRanking(qs("#"+id),rows,!!state.rankingExpanded[id]);
    const btn=document.querySelector(`.rank-toggle[data-target="${id}"]`);
    if(!btn) continue;
    btn.style.display=(rows?.length||0)>5?"inline":"none";
    btn.textContent=state.rankingExpanded[id]?cfg.ranking_collapse_text:cfg.ranking_view_all_text;
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
  const pub = d.top_publisher ? `${esc(d.top_publisher.name)} <small>${d.top_publisher.count}건</small>` : "—";
  const rep = d.top_reporter_week
    ? `${esc(d.top_reporter_week.name)} <small>${esc(d.top_reporter_week.publisher)} · ${d.top_reporter_week.count}건</small>`
    : "—";
  qs("#summaryCards").innerHTML = `
    <div class="card"><div class="label">${esc(cfg.card_today_label)}</div><div class="value">${d.today_count}건</div><div class="sub">${d.date} 현재</div></div>
    <div class="card"><div class="label">${esc(cfg.card_publisher_label)}</div><div class="value compact">${pub}</div><div class="sub">오늘 기준</div></div>
    <div class="card"><div class="label">${esc(cfg.card_reporter_label)}</div><div class="value compact">${rep}</div><div class="sub">${d.week_start} 이후</div></div>
    <div class="card"><div class="label">${esc(cfg.card_exclusive_label)}</div><div class="value">${(d.exclusive_ratio*100).toFixed(1)}%</div><div class="sub">${d.exclusive_count} / ${d.today_count}건</div></div>`;
}
function articleNode(a,cfg){
  const node = qs("#articleTemplate").content.cloneNode(true);
  node.querySelector(".news-meta").textContent = [a.publisher,(a.reporters||[]).join(", "),fmtDateTime(a.published_at)].filter(Boolean).join(" · ");
  node.querySelector("h3").textContent = a.title || "";
  node.querySelector(".context").textContent = a.context_sentence || "";
  const chips = [];
  if(a.is_exclusive) chips.push("[단독]");
  if(a.category_original && a.category_original!=="미분류") chips.push(a.category_original);
  if(a.phrase_count>1) chips.push(`표현 ${a.phrase_count}회`);
  for(const [k,v] of Object.entries(a.secondary_expressions||{})) chips.push(`${k} ${v}`);
  node.querySelector(".chips").innerHTML = chips.map(x=>`<span class="chip">${esc(x)}</span>`).join("");
  const details=node.querySelector("details");
  if(a.context_paragraph){
    node.querySelector("summary").textContent=cfg.paragraph_toggle_text;
    node.querySelector(".paragraph").textContent=a.context_paragraph;
  }else{details.remove();}
  const links=[];
  if(a.original_url) links.push(`<a target="_blank" rel="noopener noreferrer" href="${esc(a.original_url)}">${esc(cfg.original_link_text)}</a>`);
  if(a.naver_url) links.push(`<a target="_blank" rel="noopener noreferrer" href="${esc(a.naver_url)}">${esc(cfg.naver_link_text)}</a>`);
  node.querySelector(".links").innerHTML=links.join("");
  return node;
}
function renderArticles(){
  const d=state.data, rows=d.articles, cfg=d.site_config;
  qs("#articleCount").textContent = `${rows.length}건`;
  const host = qs("#articleList");
  if(!rows.length){
    host.innerHTML='<div class="empty">해당 날짜에 수집된 문장이 없습니다.</div>';
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
  qs("#heroDescription").textContent=c.hero_description;
  qs("#publisherTitle").textContent=c.section_publisher_title;
  qs("#reporterTitle").textContent=c.section_reporter_title;
  qs("#categoryTitle").textContent=c.section_category_title;
  qs("#secondaryTitle").textContent=c.section_secondary_title;
  qs("#historyTitle").textContent=c.section_history_title;
  qs("#articlesTitle").textContent=c.section_articles_title;
}
async function load(date){
  const res = await fetch(`/api/dashboard?date=${encodeURIComponent(date)}`);
  if(!res.ok) throw new Error("데이터를 불러오지 못했습니다.");
  const d = await res.json();
  state.data=d; state.articleVisible=10; state.rankingExpanded={};
  applyCopy(d);
  renderCards(d);
  renderRankings();
  renderHistory(d.daily_counts_14d);
  renderArticles();
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
    state.rankingExpanded[id]=!state.rankingExpanded[id];
    renderRankings();
  }));
  qs("#loadMore").addEventListener("click",()=>{state.articleVisible+=10;renderArticles();});
});
