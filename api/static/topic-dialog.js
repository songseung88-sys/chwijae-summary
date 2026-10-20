// Restrained editorial palette: distinct hues with similar visual weight.
const topicColors=["#285B91","#337180","#47785F","#886D3F","#70628D","#935D55","#4A6D8A","#4C7771","#775F76","#806B52"];

// Stable first-level category colors. These may not depend on rank, date or whether
// other categories (especially sports) appear in the selected day.
const topicCategoryColors={
  "사회":"#285B91",          // blue
  "경제산업":"#935D55",      // muted terracotta; formerly changed with sports/rank
  "경제":"#935D55",
  "정치":"#47785F",          // green
  "문화생활":"#886D3F",      // ochre
  "문화":"#886D3F",
  "국제":"#70628D",          // violet
  "스포츠":"#337180",        // teal
  "과학it":"#4A6D8A",
  "과학기술":"#4A6D8A",
  "기타":"#4C7771"
};
function topicColorForCategory(name){
  const key=String(name||"").replace(/[\s·ㆍ_-]/g,"").toLowerCase();
  if(Object.prototype.hasOwnProperty.call(topicCategoryColors,key)){
    return topicCategoryColors[key];
  }
  // Preserve a deterministic fallback for new labels, independent of sort order.
  let hash=0;
  for(const ch of key) hash=(hash*31+ch.codePointAt(0))>>>0;
  return topicColors[hash%topicColors.length];
}
function topicColorMap(rows){
  return new Map((rows||[]).map(row=>[row.name,topicColorForCategory(row.name)]));
}

function piePoint(cx,cy,r,angle){
  return [cx+r*Math.cos(angle), cy+r*Math.sin(angle)];
}
function svgCoord(number){
  return Number(number.toFixed(2));
}
function labeledPieSvg(rows,total,withPercent=false){
  const cx=230, cy=198, radius=123;
  const size=[460,396];
  let start=-Math.PI/2;
  const segments=[];
  const outer=[];
  const colors=topicColorMap(rows);
  rows.forEach((row,i)=>{
    const fraction=row.count/total;
    const end=start+Math.PI*2*fraction;
    const mid=(start+end)/2;
    const hue=colors.get(row.name)||topicColors[i%topicColors.length];
    const startPt=piePoint(cx,cy,radius,start),endPt=piePoint(cx,cy,radius,end);
    const path=(fraction>=.999999)
      ? '<circle cx="'+cx+'" cy="'+cy+'" r="'+radius+'" fill="'+hue+'"/>'
      : '<path d="M '+cx+' '+cy+' L '+svgCoord(startPt[0])+' '+svgCoord(startPt[1])+
        ' A '+radius+' '+radius+' 0 '+(fraction>.5?1:0)+' 1 '+svgCoord(endPt[0])+' '+svgCoord(endPt[1])+
        ' Z" fill="'+hue+'" stroke="#fff" stroke-width="2.5"/>';
    segments.push(path);
    const name=String(row.name||"미분류");
    // Wide slices can carry a readable label directly; small slices use leader lines.
    if(fraction>=.13 && name.length<=7){
      const p=piePoint(cx,cy,radius*.64,mid);
      const color="#fff";
      const label=withPercent
        ? '<tspan x="'+svgCoord(p[0])+'" dy="-7">'+esc(name)+'</tspan>'+
          '<tspan x="'+svgCoord(p[0])+'" dy="18">'+Math.round(fraction*100)+'%</tspan>'
        : esc(name);
      segments.push('<text x="'+svgCoord(p[0])+'" y="'+svgCoord(p[1])+
        '" text-anchor="middle" dominant-baseline="middle" fill="'+color+
        '" font-size="15" font-weight="700">'+label+'</text>');
    }else{
      const sign=Math.cos(mid)>=0?1:-1;
      const anchor=piePoint(cx,cy,radius+9,mid);
      outer.push({name,sign,anchor,
        percent:Math.round(fraction*100),
        bend:piePoint(cx,cy,radius+27,mid),
        y:cy+(radius+33)*Math.sin(mid)});
    }
    start=end;
  });
  // Collision handling independently on left and right for narrow mobile screens.
  const leaderLines=[];
  for(const sign of [-1,1]){
    const column=outer.filter(x=>x.sign===sign).sort((a,b)=>a.y-b.y);
    const ymin=22,ymax=size[1]-22,step=25;
    for(let i=0;i<column.length;i++){
      const minY=i===0?ymin:column[i-1].y+step;
      column[i].y=Math.max(minY,Math.min(ymax,column[i].y));
    }
    for(let i=column.length-1;i>=0;i--){
      const maxY=i===column.length-1?ymax:column[i+1].y-step;
      column[i].y=Math.min(column[i].y,maxY);
    }
    column.forEach(entry=>{
      const endX=sign>0?392:68;
      const textX=sign>0?398:62;
      const anchor=sign>0?"start":"end";
      leaderLines.push('<polyline points="'+svgCoord(entry.anchor[0])+','+svgCoord(entry.anchor[1])+' '+
        svgCoord(entry.bend[0])+','+svgCoord(entry.bend[1])+' '+endX+','+svgCoord(entry.y)+
        '" fill="none" stroke="#667085" stroke-width="1.35" stroke-linejoin="round"/>');
      leaderLines.push('<text x="'+textX+'" y="'+svgCoord(entry.y)+
        '" text-anchor="'+anchor+'" dominant-baseline="middle" font-size="13" font-weight="650" fill="#344054">'+
        esc(entry.name)+(withPercent?" "+entry.percent+"%":"")+'</text>');
    });
  }
  const description=esc(rows.map(r=>r.name+" "+r.count+"건").join(", "));
  return '<svg class="topic-pie-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+size.join(' ')+
    '" role="img" aria-label="'+description+'">'+segments.join("")+leaderLines.join("")+'</svg>';
}

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
  const pie=labeledPieSvg(rows,total);
  const colors=topicColorMap(rows);
  const legend=rows.map((r,i)=>'<li><span class="topic-legend-dot" style="background:'+(colors.get(r.name)||topicColors[i%topicColors.length])+'"></span>'+
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
