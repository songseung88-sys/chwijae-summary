const qs = (s) => document.querySelector(s);

function esc(v=""){
  return String(v).replace(/[&<>"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[m]));
}
function fmtDateTime(v){
  if(!v) return "";
  const d = new Date(v);
  return new Intl.DateTimeFormat("ko-KR",{hour:"2-digit",minute:"2-digit",hour12:false}).format(d);
}
function renderRanking(el, rows){
  if(!rows?.length){el.innerHTML='<div class="empty">표시할 데이터가 없습니다.</div>';return;}
  const max = rows[0].count || 1;
  el.innerHTML = rows.map((r,i)=>`
    <div class="rank-row">
      <div class="rank-num">${String(i+1).padStart(2,"0")}</div>
      <div class="rank-name">${esc(r.name)}</div>
      <div class="rank-count">${r.count}건</div>
      <div class="bar-track"><div class="bar" style="width:${Math.max(3,r.count/max*100)}%"></div></div>
    </div>`).join("");
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
  const pub = d.top_publisher ? `${esc(d.top_publisher.name)} <small>${d.top_publisher.count}건</small>` : "—";
  const rep = d.top_reporter_week ? `${esc(d.top_reporter_week.name)} <small>${d.top_reporter_week.count}건</small>` : "—";
  qs("#summaryCards").innerHTML = `
    <div class="card"><div class="label">오늘의 취재 종합</div><div class="value">${d.today_count}건</div><div class="sub">${d.date} 현재</div></div>
    <div class="card"><div class="label">[단독] 동반 비율</div><div class="value">${(d.exclusive_ratio*100).toFixed(1)}%</div><div class="sub">${d.exclusive_count} / ${d.today_count}건</div></div>
    <div class="card"><div class="label">오늘의 최다 취재 종합 언론사</div><div class="value" style="font-size:22px">${pub}</div><div class="sub">오늘 기준</div></div>
    <div class="card"><div class="label">이번 주 가장 많이 취재 종합한 기자</div><div class="value" style="font-size:22px">${rep}</div><div class="sub">${d.week_start} 이후</div></div>`;
}
function renderArticles(rows){
  qs("#articleCount").textContent = `${rows.length}건`;
  const host = qs("#articleList");
  if(!rows.length){host.innerHTML='<div class="empty">해당 날짜에 수집된 기사가 없습니다.</div>';return;}
  host.innerHTML = "";
  for(const a of rows){
    const node = qs("#articleTemplate").content.cloneNode(true);
    node.querySelector(".news-meta").textContent = [a.publisher,(a.reporters||[]).join(", "),fmtDateTime(a.published_at)].filter(Boolean).join(" · ");
    node.querySelector("h3").textContent = a.title || "";
    node.querySelector(".context").textContent = a.context_sentence || "";
    const chips = [];
    if(a.is_exclusive) chips.push("[단독]");
    if(a.category_original) chips.push(a.category_original);
    if(a.phrase_count>1) chips.push(`표현 ${a.phrase_count}회`);
    for(const [k,v] of Object.entries(a.secondary_expressions||{})) chips.push(`${k} ${v}`);
    node.querySelector(".chips").innerHTML = chips.map(x=>`<span class="chip">${esc(x)}</span>`).join("");
    const details=node.querySelector("details");
    if(a.context_paragraph){node.querySelector(".paragraph").textContent=a.context_paragraph}else{details.remove();}
    const links=[];
    if(a.original_url) links.push(`<a target="_blank" rel="noopener noreferrer" href="${esc(a.original_url)}">원문 보기</a>`);
    if(a.naver_url) links.push(`<a target="_blank" rel="noopener noreferrer" href="${esc(a.naver_url)}">NAVER 전송본</a>`);
    node.querySelector(".links").innerHTML=links.join("");
    host.appendChild(node);
  }
}
async function load(date){
  const res = await fetch(`/api/dashboard?date=${encodeURIComponent(date)}`);
  if(!res.ok) throw new Error("데이터를 불러오지 못했습니다.");
  const d = await res.json();
  renderCards(d);
  renderRanking(qs("#publisherRanking"), d.publisher_ranking);
  renderRanking(qs("#reporterRanking"), d.reporter_ranking_week);
  renderRanking(qs("#categoryRanking"), d.category_ranking_original);
  renderRanking(qs("#secondaryRanking"), d.secondary_expressions);
  renderHistory(d.daily_counts_14d);
  renderArticles(d.articles);
  qs("#weekLabel").textContent = `${d.week_start}~${d.date}`;
  qs("#methodology").textContent = `수집 기준: NAVER 뉴스 검색 ${d.methodology.query} → 언론사 원문 본문 확인 · ${d.methodology.source_priority} · ${d.methodology.refresh} 갱신`;
}
document.addEventListener("DOMContentLoaded",()=>{
  const input=qs("#dateInput");
  const today=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
  input.value=today;
  load(today).catch(e=>{qs("#articleList").innerHTML=`<div class="empty">${esc(e.message)}</div>`;});
  input.addEventListener("change",()=>load(input.value));
});
