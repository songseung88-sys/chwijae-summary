// UI coverage: real denominators, paragraph structures, empty states and safe links.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const nodes=new Map();
const node=(selector)=>{
  if(!nodes.has(selector)) nodes.set(selector,{innerHTML:"",textContent:""});
  return nodes.get(selector);
};
const ctx={document:{querySelector:node,addEventListener(){}},URL,console};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync("api/static/app.js","utf8"),ctx);
vm.runInContext(fs.readFileSync("api/static/phrase-position.js","utf8"),ctx);
const state=vm.runInContext("state",ctx);
state.data={site_config:{ui_copy:{}}};
const rows={
  period_start:"2026-10-22",period_end:"2026-10-28",
  eligible_articles:12, analyzed_articles:10, unavailable_articles:2,
  mean_characters:87.5, median_characters:61,
  modal_paragraph:2, within_500_articles:8,
  paragraph_distribution:[
    {label:"1문단",count:3},{label:"2문단",count:5},
    {label:"3문단",count:1},{label:"4문단",count:0},
    {label:"5문단 이상",count:1},
  ],
  structure:[
    {label:"문단 첫머리",count:1},
    {label:"첫 문장 중간",count:7},
    {label:"후속 문장",count:2},
  ],
  examples:[
    {paragraph:2,character_offset:48,publisher:"기자신문",
      excerpt:"48자 앞 취재를 종합하면 기사입니다",
      url:"https://www.example.com/a"},
    {paragraph:1,character_offset:12,publisher:"<img src=x>",
      excerpt:"<script>alert('oops')</script> 취재를 종합하면",
      url:"javascript:alert(1)"},
  ],
};
vm.runInContext("renderFirstPhrasePosition("+JSON.stringify(rows)+")",ctx);
let html=node("#firstPhrasePosition").innerHTML;
assert(node("#positionTitle").textContent.includes("취재를 종합하면"));
assert.equal(node("#positionScope").textContent,
  "수집 기간 2026-10-22~2026-10-28 · '취재를 종합하면' 포함 기사 10건");
assert(!node("#positionScope").textContent.includes("10/12"));
assert(html.includes("87.5"));
assert(!html.includes("중앙값"));
assert(!html.includes("61<small>자"));
assert(html.includes("등장하는 문단"));
assert(!html.includes("처음 등장하는 문단"));
assert.equal((html.match(/<div><span>/g)||[]).length,2);
assert(html.includes("2문단"));
assert(html.includes("50%"));
assert(!html.includes("처음 500자 이내"));
assert(!html.includes("공백 포함, 정규화된 본문"));
assert(!html.includes("본문 확인 불가"));
assert.equal((html.match(/class="position-row"/g)||[]).length,8);
assert(html.includes("문단 첫머리"));
assert(html.includes("첫 문장 중간"));
assert(html.includes("후속 문장"));
assert(html.includes("실제 기사에서 확인하기"));
assert(html.includes("https://www.example.com/a"));
assert(!html.includes('href="javascript:'));
assert(!html.includes("<script>"));
assert(!html.includes("<img src=x>"));
assert(html.includes("&lt;script&gt;"));
assert(html.includes("&lt;img src=x&gt;"));


vm.runInContext('renderFirstPhrasePosition({period_start:"2026-10-22",period_end:"2026-10-28",eligible_articles:0,analyzed_articles:0})',ctx);
assert(node("#firstPhrasePosition").innerHTML.includes("분석할 수 있는 기사 본문이 없습니다"));
assert(!node("#firstPhrasePosition").innerHTML.includes("NaN"));
state.data.site_config.ui_copy.position_title="기록된 위치";
vm.runInContext("renderFirstPhrasePosition("+JSON.stringify(rows)+")",ctx);
assert.equal(node("#positionTitle").textContent,"기록된 위치");

const file=fs.readFileSync("api/static/index.html","utf8");
const css=fs.readFileSync("api/static/style.css","utf8");
assert(file.includes('id="firstPhrasePosition"'));
assert(file.includes('/static/phrase-position.js?v=2'));
assert(file.includes('/static/app.js?v=position-v1'));
assert(file.includes('/static/style.css?v=position-week-v2'));
assert(css.includes(".position-stats"));
assert(css.includes(".position-splits"));
console.log("First-phrase position metrics, 5+3 distribution, examples and empty/safe states validated.");
