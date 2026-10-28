// Ranking layout: daily top cards and week-to-date ranking panels and dialogs.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const nodes = new Map();
function node(key) {
  if (!nodes.has(key)) nodes.set(key, {
    innerHTML:"", textContent:"", style:{}, hidden:false,
    showModal(){this.open=true}, close(){this.open=false}
  });
  return nodes.get(key);
}
const context={document:{querySelector:node,addEventListener(){}},console};
vm.createContext(context);
vm.runInContext(fs.readFileSync("api/static/app.js","utf8"),context);
vm.runInContext(fs.readFileSync("api/static/ranking-dialog.js","utf8"),context);
const state=vm.runInContext("state",context);
state.data={
  date:"2026-10-28",week_start:"2026-10-26",
  today_count:3,exclusive_ratio:0,exclusive_count:0,
  site_config:{
    card_today_label:"오늘의 '취재 종합'",
    card_publisher_label:"오늘 가장 많이 '취재를 종합'한 언론사",
    card_reporter_label:"오늘 가장 많이 '취재를 종합'한 기자",
    card_exclusive_label:"[단독] 비율",
    ranking_view_all_text:"자세히 보기",articles_more_text:"더 보기",
    section_publisher_title:"이번 주 가장 많이 '취재를 종합'한 언론사",
    section_reporter_title:"이번 주 가장 많이 '취재를 종합'한 기자",
  },
  top_publisher:{name:"오늘언론",count:2},
  top_reporter_today:{name:"오늘기자",publisher:"오늘언론",count:2},
  top_reporter_week:{name:"주간기자",publisher:"주간언론",count:9},
  publisher_ranking:[{name:"오늘언론",count:2}],
  publisher_ranking_week:[
    {name:"주간언론",count:12},{name:"주간언론2",count:9},
    {name:"주간언론3",count:7},{name:"주간언론4",count:6},
    {name:"주간언론5",count:5},{name:"주간언론6",count:3},
  ],
  reporter_ranking_week:[
    {name:"주간기자",count:9,publisher:"주간언론"},
    {name:"기자2",count:7,publisher:"주간언론"},
    {name:"기자3",count:6,publisher:"주간언론"},
    {name:"기자4",count:5,publisher:"주간언론"},
    {name:"기자5",count:4,publisher:"주간언론"},
    {name:"기자6",count:3,publisher:"주간언론"},
  ],
  category_primary_ranking:[], category_hierarchy:[], secondary_expressions:[],
};
vm.runInContext("renderCards(state.data)",context);
const cards=node("#summaryCards").innerHTML;
assert(cards.includes("오늘언론"));
assert(cards.includes("오늘기자"));
assert(!cards.includes("주간기자"));
assert(!cards.includes("주간언론"));
assert(cards.includes("오늘 기준"));
assert(!cards.includes(" 이후"));
assert(!cards.includes("1위"));

vm.runInContext("renderRankings()",context);
const publisher=node("#publisherRanking").innerHTML;
const reporter=node("#reporterRanking").innerHTML;
assert.equal((publisher.match(/class="rank-row"/g)||[]).length,5);
assert.equal((reporter.match(/class="rank-row"/g)||[]).length,5);
assert(publisher.includes("주간언론"));
assert(!publisher.includes("오늘언론"));
assert(!publisher.includes("주간언론6"));
assert(reporter.includes("주간기자"));
assert(!reporter.includes("기자6"));
vm.runInContext('openRankingDialog("publisherRanking")',context);
assert(node("#rankingDialog").open);
assert(node("#rankingDialogTitle").textContent.includes("이번 주"));
assert(node("#rankingDialogContent").innerHTML.includes("주간언론6"));

// Unsorted source data must become one global weekly reporter ranking,
// with affiliation printed on each row and the same 20-at-a-time paging.
state.data.reporter_ranking_week=Array.from({length:45},(_,i)=>({
  name:"기자"+String(i+1).padStart(2,"0"),
  publisher:i%2?"신문B":"신문A",
  count:45-i,
})).reverse();
vm.runInContext('openRankingDialog("reporterRanking")',context);
let ranked=node("#rankingDialogContent").innerHTML;
assert(!ranked.includes("ranking-dialog-group"));
assert.equal((ranked.match(/ranking-dialog-row/g)||[]).length,20);
assert(ranked.includes('class="rank-name">기자01'));
assert(ranked.includes('class="rank-name">기자20'));
assert(!ranked.includes('class="rank-name">기자21'));
assert(ranked.includes('rank-affiliation">신문A'));
assert(ranked.includes('rank-affiliation">신문B'));
assert(ranked.indexOf('class="rank-name">기자01') < ranked.indexOf('class="rank-name">기자20'));
assert.equal(node("#rankingDialogMore").hidden,false);
vm.runInContext("showMoreRankingDialog()",context);
ranked=node("#rankingDialogContent").innerHTML;
assert.equal((ranked.match(/ranking-dialog-row/g)||[]).length,40);
assert(ranked.includes('class="rank-name">기자40'));
assert(!ranked.includes('class="rank-name">기자41'));
vm.runInContext("showMoreRankingDialog()",context);
ranked=node("#rankingDialogContent").innerHTML;
assert.equal((ranked.match(/ranking-dialog-row/g)||[]).length,45);
assert(ranked.includes('class="rank-name">기자45'));
assert.equal(node("#rankingDialogMore").hidden,true);
state.data.reporter_ranking_week=[
 {name:"<script>",publisher:"<img>",count:2},
 {name:"동명이인",publisher:"신문A",count:1},
 {name:"동명이인",publisher:"신문B",count:1}
];
vm.runInContext('openRankingDialog("reporterRanking")',context);
ranked=node("#rankingDialogContent").innerHTML;
assert(!ranked.includes("<script>"));
assert(!ranked.includes("<img>"));
assert(ranked.includes("&lt;script&gt;"));
assert(ranked.includes("&lt;img&gt;"));
assert.equal((ranked.match(/ranking-dialog-row/g)||[]).length,3);
assert(ranked.includes("신문A")&&ranked.includes("신문B"));

const html=fs.readFileSync("api/static/index.html","utf8");
assert(html.includes('id="publisherWeekLabel"'));
assert(html.includes('id="weekLabel"'));
assert(html.includes('/static/app.js?v=target-phrase-v2-weekly-rank-v1'));
assert(html.includes('/static/ranking-dialog.js?v=flat-weekly-v2'));
const app=fs.readFileSync("api/static/app.js","utf8");
assert(app.includes('qs("#publisherWeekLabel").textContent'));
assert(app.includes('qs("#weekLabel").textContent'));
console.log("Daily winner cards, week-to-date top-five leaderboards, weekly detail dialog and date labels verified.");
