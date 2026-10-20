const topicColors=["#273c56","#438e9b","#b59b69","#6e829b","#8e796c","#789c85","#95778f","#a7a6a0","#5f6676"];

function openCategoryDialog(){
  const dialog=qs("#categoryDialog");
  const d=state.data;
  const rows=d.category_primary_ranking||[];
  const hierarchy=d.category_hierarchy||[];
  const root=qs("#categoryDialogContent");
  const total=rows.reduce((n,r)=>n+r.count,0);
  if(!total){
    root.innerHTML='<p class="empty">분류된 기사가 없습니다.</p>';
    dialog.showModal();
    return;
  }
  let offset=0;
  const slices=rows.map((r,i)=>{
    const start=offset;
    offset+=r.count/total*100;
    return topicColors[i%topicColors.length]+" "+start.toFixed(3)+"% "+offset.toFixed(3)+"%";
  });
  const aria=rows.map(r=>r.name+" "+r.count+"건").join(", ");
  const pie='<div class="topic-pie" role="img" aria-label="'+esc(aria)+'" style="background:conic-gradient('+slices.join(",")+')"><span class="topic-pie-center">1차 분류</span></div>';
  const legend=rows.map((r,i)=>'<li><span class="topic-legend-dot" style="background:'+topicColors[i%topicColors.length]+'"></span>'+
    '<span class="topic-legend-name">'+esc(r.name)+'</span><strong>'+r.count+'건</strong><small>'+(r.count/total*100).toFixed(1)+'%</small></li>').join("");
  const sections=hierarchy.map(group=>{
    const children=(group.secondaries||[]).map(node=>{
      const third=node.tertiaries||[];
      const sub=third.length?'<ul class="topic-tertiary-list">'+third.map(t=>
        '<li><span>'+esc(t.name)+'</span><span>'+t.count+'건</span></li>').join("")+'</ul>':"";
      return '<li><div class="topic-second-row"><span>'+esc(node.secondary)+'</span><strong>'+node.count+'건</strong></div>'+sub+'</li>';
    }).join("");
    return '<section class="topic-hierarchy-group"><h3>'+esc(group.primary)+' <small>'+group.count+'건</small></h3><ul>'+children+'</ul></section>';
  }).join("");
  root.innerHTML='<div class="topic-dialog-visual">'+pie+'<ul class="topic-legend">'+legend+'</ul></div>'+
    '<div class="topic-dialog-hierarchy"><h3>2차 · 3차 분류</h3><p class="topic-help">3차 분류가 없는 경우 2차 분류까지만 표시합니다.</p>'+sections+'</div>';
  dialog.showModal();
}
