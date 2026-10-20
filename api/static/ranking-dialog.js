function rankingCopy(key,fallback){return typeof uiCopy==="function"?uiCopy(key,fallback):fallback;}
/* Detail views reuse the existing dashboard ranking data: no extra API requests. */
const rankingDialogState={id:null, rows:[], visible:20};

function groupReportersByPublisher(rows){
  const byPublisher=new Map();
  for(const row of rows||[]){
    const publisher=String(row.publisher||rankingCopy("reporter_unknown","미확인"));
    if(!byPublisher.has(publisher)) byPublisher.set(publisher,[]);
    byPublisher.get(publisher).push(row);
  }
  return Array.from(byPublisher,([publisher,members])=>({
    publisher,
    members:members.sort((a,b)=>b.count-a.count||String(a.name).localeCompare(String(b.name),"ko")),
    total:members.reduce((sum,row)=>sum+row.count,0),
  })).sort((a,b)=>b.members.length-a.members.length||b.total-a.total||
    a.publisher.localeCompare(b.publisher,"ko"));
}

function rankingDialogRows(rows,first=0,overallMax=null){
  const max=overallMax||Math.max(1,...rows.map(row=>row.count||0));
  return rows.map((r,i)=>{
    const count=Math.max(0,Number(r.count)||0);
    const width=Math.max(3,Math.min(100,count/max*100));
    return '<div class="rank-row ranking-dialog-row">'+
      '<span class="rank-num">'+String(first+i+1).padStart(2,"0")+'</span>'+
      '<span class="rank-name">'+esc(r.name)+'</span>'+
      '<strong class="rank-count">'+count+esc(rankingCopy('count_unit','건'))+'</strong>'+
      '<span class="bar-track"><span class="bar" style="width:'+width+'%"></span></span>'+
      '</div>';
  }).join("");
}

function renderRankingDialog(){
  const view=rankingDialogState;
  const root=qs("#rankingDialogContent");
  const more=qs("#rankingDialogMore");
  const cfg=state.data.site_config;
  if(view.id==="reporterRanking"){
    const groups=groupReportersByPublisher(view.rows);
    root.innerHTML=groups.map(group=>
      '<section class="ranking-dialog-group"><div class="ranking-dialog-group-head">'+
      '<h3>'+esc(group.publisher)+'</h3><span>'+group.members.length+esc(rankingCopy('person_unit','명'))+'</span></div>'+
      '<div class="ranking ranking-dialog-list">'+rankingDialogRows(group.members,0)+
      '</div></section>'
    ).join("");
    more.hidden=true;
    more.style.display="none";
    return;
  }
  root.innerHTML='<div class="ranking ranking-dialog-list">'+
    rankingDialogRows(view.rows.slice(0,view.visible),0)+
    '</div>';
  const hasMore=view.visible<view.rows.length;
  more.hidden=!hasMore;
  more.style.display=hasMore?"inline-flex":"none";
  more.textContent=cfg.articles_more_text;
}

function openRankingDialog(id){
  const d=state.data;
  if(!d) return;
  const source={
    publisherRanking:{rows:d.publisher_ranking,title:d.site_config.section_publisher_title},
    reporterRanking:{rows:d.reporter_ranking_week,title:d.site_config.section_reporter_title},
    secondaryRanking:{rows:d.secondary_expressions,title:d.site_config.section_secondary_title},
  }[id];
  if(!source) return;
  rankingDialogState.id=id;
  rankingDialogState.rows=source.rows||[];
  rankingDialogState.visible=20;
  qs("#rankingDialogTitle").textContent=source.title||"";
  renderRankingDialog();
  qs("#rankingDialog").showModal();
}

function showMoreRankingDialog(){
  if(rankingDialogState.id==="reporterRanking") return;
  rankingDialogState.visible+=20;
  renderRankingDialog();
}
