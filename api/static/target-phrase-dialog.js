/* Unique-article breakdown of the headline: the same article may match
   several expressions, but only one contributes to today's total. */
function targetDetailCopy(key,fallback){
  return typeof uiCopy==="function"?uiCopy(key,fallback):fallback;
}
function targetSafeLink(value){
  const raw=String(value||"");
  return /^https:\/\/[a-z0-9.-]+(?:[:/]|$)/i.test(raw)?raw:"";
}
function targetPhraseDetailMarkup(data){
  const articles=Array.isArray(data?.articles)?data.articles:[];
  const groups=(Array.isArray(data?.target_phrase_breakdown)?data.target_phrase_breakdown:[])
    .filter(group=>Number(group?.article_count)>0)
    .sort((a,b)=>
      Number(b.article_count)-Number(a.article_count) ||
      (Number(b.occurrence_count)||0)-(Number(a.occurrence_count)||0)
    );
  const countUnit=targetDetailCopy("count_unit","건");
  const unique=Number(data?.today_count)||0;
  const rows=groups.map(group=>{
    const name=String(group.name||"");
    const matched=articles.filter(a=>Number(a?.target_phrase_counts?.[name])>0);
    const cnt=Number(group.article_count)||0;
    const mentions=Number(group.occurrence_count)||0;
    const items=matched.map(a=>{
      const title=esc(a.title||targetDetailCopy("target_detail_untitled","제목 없음"));
      const link=targetSafeLink(a.original_url)||targetSafeLink(a.naver_url);
      const heading=link?'<a href="'+esc(link)+'" target="_blank" rel="noopener noreferrer">'+title+'</a>':title;
      const publisher=a.publisher?'<span class="target-detail-publisher">'+esc(a.publisher)+'</span>':"";
      return '<li>'+heading+publisher+'</li>';
    }).join("");
    return '<details class="target-detail-group">'+
      '<summary><span class="target-detail-name">'+esc(name)+'</span>'+
      '<strong>'+cnt+esc(countUnit)+'</strong>'+
      '<small>'+mentions+esc(targetDetailCopy("target_detail_mentions","회 사용"))+'</small></summary>'+
      '<div class="target-detail-body">'+
      (matched.length?'<ul>'+items+'</ul>':
        '<p>'+esc(targetDetailCopy("target_detail_empty","해당 날짜에 확인된 기사가 없습니다."))+'</p>')+
      '</div></details>';
  }).join("");
  return '<div class="target-detail-metrics"><strong>'+unique+esc(countUnit)+'</strong>'+
    '</div>'+
    '<p class="target-detail-intro">'+esc(targetDetailCopy("target_detail_intro","표현별 기사 수를 누르면 실제 기사와 언론사를 확인할 수 있습니다."))+'</p>'+
    '<div class="target-detail-list">'+rows+'</div>';
}
function openTargetPhraseDialog(){
  const d=state.data;
  if(!d)return;
  const dialog=qs("#targetPhraseDialog");
  if(!dialog)return;
  qs("#targetPhraseDialogTitle").textContent=
    targetDetailCopy("target_detail_title","오늘의 취재 근거 표현");
  qs("#targetPhraseDialogContent").innerHTML=targetPhraseDetailMarkup(d);
  dialog.showModal();
}
document.addEventListener("DOMContentLoaded",()=>{
  const d=qs("#targetPhraseDialog");
  if(!d)return;
  qs("#closeTargetPhraseDialog").addEventListener("click",()=>d.close());
  d.addEventListener("click",event=>{if(event.target===d)d.close();});
});
