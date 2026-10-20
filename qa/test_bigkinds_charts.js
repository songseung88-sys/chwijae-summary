const fs=require("node:fs");
const assert=require("node:assert/strict");
const charts=require("../api/static/bigkinds-charts.js");
const data=require("../api/static/bigkinds-annual-2016-2025.json");
assert.equal(charts.validateBigkinds(data),true);
assert.equal(data.years.length,10);
assert.equal(Object.keys(data.publishers).length,10);
assert.deepEqual(data.years,[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025]);
assert.deepEqual(data.totals,[77,93,156,498,2684,3716,4015,3916,3463,4391]);
assert.equal(data.publishers["경향신문"][9],1302);
assert.equal(data.publishers["한겨레"][0],41);
assert.equal(data.publishers["한겨레"][8],203);
assert.equal(data.publishers["조선일보"][9],597);
assert.equal(data.publishers["한국일보"][9],694);
assert.equal(data.publishers["동아일보"][7],626);
const broken=JSON.parse(JSON.stringify(data));
broken.publishers["한겨레"][8]=204;
assert.throws(()=>charts.validateBigkinds(broken),/합계/);
const annual=charts.annualBigkindsSvg(data);
assert.equal((annual.match(/class="bigkinds-annual-bar/g)||[]).length,10);
assert.equal((annual.match(/data-year-index="/g)||[]).length,10);
assert.match(annual,/>2016</);
assert.match(annual,/>2025</);
assert.match(annual,/bigkinds-latest/);
assert.match(charts.bigkindsTipMarkup(data,"annual",9,new Set()),/4,391건/);

const selected=new Set(charts.BIGKINDS_DEFAULT_PUBLISHERS);
assert.deepEqual([...selected],["한겨레","경향신문","조선일보","한국일보"]);
const lines=charts.publisherBigkindsSvg(data,selected);
assert.equal((lines.match(/class="bigkinds-series-line"/g)||[]).length,4);
assert.equal((lines.match(/class="bigkinds-series-dot"/g)||[]).length,40);
assert.equal((lines.match(/data-year-index="/g)||[]).length,10);
for(const color of ["#285B91","#965E57","#47785F","#BA8540"]){
  assert(lines.includes('stroke="'+color+'"'));
}
const tip2025=charts.bigkindsTipMarkup(data,"publisher",9,selected);
assert.match(tip2025,/1,302건/);
assert.match(tip2025,/360건/);
assert.match(tip2025,/597건/);
assert.match(tip2025,/694건/);
assert.doesNotMatch(tip2025,/국민일보/);

selected.add("국민일보");
assert.equal((charts.publisherBigkindsSvg(data,selected).match(/class="bigkinds-series-line"/g)||[]).length,5);
selected.clear();
assert.match(charts.publisherBigkindsSvg(data,selected),/비교할 언론사를 선택해 주세요/);

/* On mobile, plot the entire decade instead of exposing a cropped first half. */
const compactAnnual=charts.annualBigkindsSvg(data,true);
const compactPublisher=charts.publisherBigkindsSvg(data,new Set(charts.BIGKINDS_DEFAULT_PUBLISHERS),true);
assert.match(compactAnnual,/viewBox="0 0 360 320"/);
assert.match(compactPublisher,/viewBox="0 0 360 320"/);
assert.match(compactAnnual,/bigkinds-svg-compact/);
assert.match(compactPublisher,/bigkinds-svg-compact/);
assert.equal((compactAnnual.match(/data-year-index="/g)||[]).length,10);
assert.equal((compactPublisher.match(/data-year-index="/g)||[]).length,10);
for(const year of [2016,2017,2018,2019,2020,2021,2022,2023,2024,2025]){
  assert(compactAnnual.includes('>'+year+'</text>'),"Visible full decade: "+year);
  assert(compactPublisher.includes('>'+year+'</text>'),"Visible publisher decade: "+year);
}
const compactSvgHitRects=[...compactAnnual.matchAll(/class="bigkinds-hit"[^>]*x="([\d.]+)"[^>]*width="([\d.]+)"/g)];
assert.equal(compactSvgHitRects.length,10);
for(const rect of compactSvgHitRects){
  assert(Number(rect[1])>=0);
  assert(Number(rect[1])+Number(rect[2])<=360);
}
assert.match(compactPublisher,/stroke="#285B91"/);
assert.match(compactPublisher,/stroke="#47785F"/);
assert.match(charts.publisherBigkindsSvg(data,new Set(),true),/viewBox="0 0 360 320"/);

const html=fs.readFileSync("api/static/about.html","utf8");
const css=fs.readFileSync("api/static/bigkinds-charts.css","utf8");
for(const token of ["bigkindsAnnualChart","bigkindsPublisherChart","bigkindsPublisherFilters",
  "bigkinds-charts.js","bigkinds-charts.css","aboutLayout"]){
  assert(html.includes(token),token);
}
for(const unwanted of ["bigkindsPeakYear","bigkindsResetPublishers","bigkinds-hint",
  "bigkinds-source","bigkinds-eyebrow","BIGKINDS · 2016","사용 빈도가 곧 취재의 질"]){
  assert(!html.includes(unwanted),"Remove highlighted copy: "+unwanted);
}
const chartCode=fs.readFileSync("api/static/bigkinds-charts.js","utf8");
assert(chartCode.includes('fetch("/api/bigkinds-history"'));
assert(!chartCode.includes("bigkindsPeakYear"));
const aboutCode=fs.readFileSync("api/static/about.js","utf8");
assert(aboutCode.includes("renderAboutLayout"));
assert(aboutCode.includes("renderAboutText(node,block.text,!leadSeen)")); // First section is safely rendered with text nodes.
assert(aboutCode.includes("node.textContent=text")); // Remaining content never treated as HTML.
assert(css.includes("bigkinds-tooltip"));
assert(css.includes("bigkinds-hit:focus-visible"));
assert(html.includes('id="aboutContent"'),"Keep legacy About content migration");
const adminHtml=fs.readFileSync("api/static/admin.html","utf8");
for(const id of ["aboutLayoutEditor","aboutLayoutRows","addAboutBlock","saveAboutLayout",
    "bigkindsDataEditor","bigkindsEditorBody","saveBigkindsData"]){
  assert(adminHtml.includes('id="'+id+'"'),id);
}
console.log("BigKinds annual totals, publisher comparison, 4 defaults, all 10 toggles and tooltips validated");
