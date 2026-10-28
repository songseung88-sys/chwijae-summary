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
assert(files.html.includes('/static/target-phrase-dialog.js?v=2'));
assert(files.css.includes(".target-phrase-dialog"));
const zeroData={...d,target_phrase_breakdown:d.target_phrase_breakdown.map(g=>({...g,article_count:0,occurrence_count:0}))};
const zeroHtml=vm.runInContext("targetPhraseDetailMarkup("+JSON.stringify(zeroData)+")",ctx);
assert.equal((zeroHtml.match(/class="target-detail-group"/g)||[]).length,0);
console.log("Target phrase detail: positive-only groups, concise notes, safe links, overlapping article counts and mobile dialog verified.");
