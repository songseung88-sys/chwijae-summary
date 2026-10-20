// Node-only regression for the two redesigned analysis cards.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");

const nodes=new Map();
function node(selector){
  if(!nodes.has(selector)){
    nodes.set(selector,{
      innerHTML:"",textContent:"",hidden:false,style:{},attrs:{},
      showModal(){this.open=true},close(){this.open=false},
    });
  }
  return nodes.get(selector);
}
const doc={
  querySelector:node,
  addEventListener(){},
};
const context={document:doc,console};
vm.createContext(context);
vm.runInContext(fs.readFileSync("api/static/app.js","utf8"),context);
vm.runInContext(fs.readFileSync("api/static/topic-dialog.js","utf8"),context);
const state=vm.runInContext("state",context);
state.categoryFilter=null;
state.data={
  site_config:{
    ranking_view_all_text:"자세히 보기",
    section_category_title:"원문 기사 분류",
    section_secondary_title:"함께 쓰인 무주체형 표현",
  },
  publisher_ranking:[{name:"매체A",count:20}],
  reporter_ranking_week:[{name:"홍길동",count:8,publisher:"매체A"}],
  category_primary_ranking:[
    {name:"정치",count:8},{name:"사회",count:6},{name:"경제",count:4},{name:"문화",count:2},
  ],
  category_hierarchy:[
    {primary:"정치",count:8,secondaries:[
      {secondary:"국회·정당",count:5,tertiaries:[{name:"국정감사",count:3}]},
      {secondary:"선거",count:3,tertiaries:[]}]},
    {primary:"사회",count:6,secondaries:[{secondary:"사건·사고",count:6,tertiaries:[]}]},
    {primary:"경제",count:4,secondaries:[{secondary:"산업·기업",count:4,tertiaries:[]}]},
    {primary:"문화",count:2,secondaries:[{secondary:"도서",count:2,tertiaries:[]}]},
  ],
  secondary_expressions:[
    {name:"알려졌다",count:23},{name:"전해졌다",count:17},
    {name:"해석된다",count:8},{name:"지적이 나온다",count:4},
    {name:"법조계에 따르면",count:3},{name:"셈이다",count:1},
  ],
};
vm.runInContext("renderRankings()",context);
const colors=vm.runInContext("topicColors",context);
assert.equal(new Set(colors).size,colors.length);
assert(colors.includes("#285B91")); // Muted blue
assert(colors.includes("#47785F")); // Muted green
assert(colors.includes("#886D3F")); // Muted ochre
assert(colors.includes("#70628D")); // Muted violet
assert(colors.includes("#935D55")); // Muted terracotta
const svg=node("#topicPrimaryPie").innerHTML;
const topic=node("#topicSecondaryBars").innerHTML;
const expression=node("#secondaryRanking").innerHTML;
assert.match(svg,/class="topic-pie-svg"/);
assert.match(svg,/28?\%|40%/);
assert.match(svg,/정치/);
assert.match(svg,/사회/);
assert.equal((topic.match(/class="topic-bar-row/g)||[]).length,5);
assert(topic.indexOf("사회 &rsaquo; 사건·사고") < topic.indexOf("정치 &rsaquo; 국회·정당"));
assert.match(topic,/30\.0%/);
assert.match(topic,/data-category="국회·정당"/);
assert.equal((expression.match(/class="expression-row"/g)||[]).length,5);
assert.match(expression,/23회/);
assert.doesNotMatch(expression,/전언형|판단형|<legend|topic-legend/);
assert.equal(node('.rank-toggle[data-target="categoryRanking"]').textContent,"자세히 보기");
assert.equal(node('.rank-toggle[data-target="secondaryRanking"]').textContent,"자세히 보기");

state.categoryFilter="산업·기업";
vm.runInContext("renderRankings()",context);
assert.match(node("#topicSecondaryBars").innerHTML,/data-category="산업·기업" aria-pressed="true"/);
vm.runInContext("openCategoryDialog()",context);
const modal=node("#categoryDialog");
assert.equal(modal.open,true);
assert.match(node("#categoryDialogContent").innerHTML,/2차 · 3차 분류/);
assert.match(node("#categoryDialogContent").innerHTML,/국정감사/);

// The charts should degrade gracefully on dates without classified articles.
state.data.category_primary_ranking=[];
state.data.category_hierarchy=[];
state.data.secondary_expressions=[];
vm.runInContext("renderRankings()",context);
assert.match(node("#topicPrimaryPie").innerHTML,/표시할 데이터가 없습니다/);
assert.match(node("#topicSecondaryBars").innerHTML,/표시할 데이터가 없습니다/);
assert.match(node("#secondaryRanking").innerHTML,/표시할 데이터가 없습니다/);

const html=fs.readFileSync("api/static/index.html","utf8");
const css=fs.readFileSync("api/static/style.css","utf8");
const py=fs.readFileSync("api/main.py","utf8");
assert.match(html,/class="analysis-stack"/);
assert.match(html,/id="topicPrimaryPie"/);
assert.match(html,/id="topicSecondaryBars"/);
assert.match(html,/id="secondaryRanking"/);
assert.match(html,/class="grid two"/); // Unchanged publisher and reporter layout
assert.match(html,/id="historyBars"/);
assert.match(html,/id="articleList"/);
for(const label of ["topic_primary_caption","topic_secondary_caption"]){
  assert(py.includes('"'+label+'":'));
  assert(fs.readFileSync("api/static/admin.js","utf8").includes(label+':'));
}
assert(css.includes("@media(max-width:750px)")&&css.includes("@media(max-width:540px)"));
assert(css.includes(".analysis-group .analysis-stack"));
assert(css.includes(".expression-fill{background:linear-gradient(90deg,#72a9da,#367cbd)}"));
assert(css.includes(".expression-row:first-child .expression-fill{background:linear-gradient(90deg,#4b8fc9,#215f9f)}"));
console.log("Analysis charts, sorted 2nd-level topics, full 3rd-level detail, expression counts and no-type grouping validated");
