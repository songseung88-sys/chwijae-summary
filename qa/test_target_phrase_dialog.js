const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const files={
  html:fs.readFileSync("api/static/index.html","utf8"),
  app:fs.readFileSync("api/static/app.js","utf8"),
  dialog:fs.readFileSync("api/static/target-phrase-dialog.js","utf8"),
  css:fs.readFileSync("api/static/style.css","utf8"),
};
const elements={};
const doc={
  addEventListener(){},
  querySelector(s){return elements[s]||null;}
};
const ctx=vm.createContext({
  document:doc,
  qs:s=>elements[s]||null,
  esc:s=>String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;"),
  uiCopy:(k,fallback)=>fallback,
  state:{data:null}
});
vm.runInContext(files.dialog,ctx);
const rows=[
 {id:"1",title:"기존 두 표현을 쓴 기사",publisher:"경향신문",
  original_url:"https://example.com/a",target_phrase_counts:{"취재를 종합하면":1,"본지 취재 결과":1}},
 {id:"2",title:"취재한 결과만 쓴 기사",publisher:"한겨레",
  original_url:"https://example.com/b",target_phrase_counts:{"취재한 결과":2}},
 {id:"3",title:"<script>alert(1)</script>",publisher:"한국일보",
  original_url:"javascript:alert(1)",target_phrase_counts:{"본지 확인 결과":1}}
];
const d={
 today_count:3,legacy_today_count:1,
 target_phrase_breakdown:[
  {name:"취재를 종합하면",article_count:1,occurrence_count:1},
  {name:"본지 취재 결과",article_count:1,occurrence_count:1},
  {name:"취재에 따르면",article_count:0,occurrence_count:0},
  {name:"취재한 결과",article_count:1,occurrence_count:2},
  {name:"본보 취재 결과",article_count:0,occurrence_count:0},
  {name:"본지 확인 결과",article_count:1,occurrence_count:1},
 ],
 articles:rows,
 methodology:{target_phrase_note:"이전 기간 소급 검색 없음"}
};
const html=vm.runInContext("targetPhraseDetailMarkup("+JSON.stringify(d)+")",ctx);
assert.equal((html.match(/class="target-detail-group"/g)||[]).length,4);
// Equal article counts: expressions used more times rank ahead; other ties keep source order.
const names=Array.from(html.matchAll(/<span class="target-detail-name">([^<]+)<\/span>/g),m=>m[1]);
assert.deepEqual(names,[
  "취재한 결과","취재를 종합하면","본지 취재 결과","본지 확인 결과"
]);
// Article count is the primary sort key, even when a smaller group has more mentions.
const sorted={...d,target_phrase_breakdown:[
  {name:"1건·10회",article_count:1,occurrence_count:10},
  {name:"3건·3회",article_count:3,occurrence_count:3},
  {name:"2건·5회",article_count:2,occurrence_count:5},
  {name:"0건",article_count:0,occurrence_count:0},
  {name:"2건·2회",article_count:2,occurrence_count:2},
]};
const sortedHtml=vm.runInContext("targetPhraseDetailMarkup("+JSON.stringify(sorted)+")",ctx);
const sortedNames=Array.from(sortedHtml.matchAll(/<span class="target-detail-name">([^<]+)<\/span>/g),m=>m[1]);
assert.deepEqual(sortedNames,["3건·3회","2건·5회","2건·2회","1건·10회"]);
assert(!html.includes("전체 대상 기사 · 중복 제거"));
assert(html.includes("3건"));
assert(html.includes("취재를 종합하면"));
assert(!html.includes("본보 취재 결과"));
assert(!html.includes("취재에 따르면"));
assert(html.includes("https://example.com/a"));
assert(html.includes("2회 사용"));
assert(!html.includes("이전 기간 소급 검색 없음"));
assert(!html.includes("한 기사가 두 표현 이상을 쓰면"));
assert(html.includes("&lt;script&gt;alert(1)&lt;/script&gt;"));
assert(!html.includes("<script>"));
assert(!html.includes('href="javascript:'));
assert(!html.includes("여섯 표현 합계 4건"));
assert(files.app.includes('id="openTargetPhraseDialog"'));
assert(!files.app.includes('card_additional_prefix'));
assert(files.app.includes("openTargetPhraseDialog()"));
assert(files.html.includes('id="targetPhraseDialog"'));
assert(files.html.includes('/static/target-phrase-dialog.js?v=3'));
assert(files.css.includes(".target-phrase-dialog"));
const zeroData={...d,target_phrase_breakdown:d.target_phrase_breakdown.map(g=>({...g,article_count:0,occurrence_count:0}))};
const zeroHtml=vm.runInContext("targetPhraseDetailMarkup("+JSON.stringify(zeroData)+")",ctx);
assert.equal((zeroHtml.match(/class="target-detail-group"/g)||[]).length,0);
console.log("Target phrase detail: descending article counts, occurrence tie-break, positive-only rows, safe links and mobile dialog verified.");
