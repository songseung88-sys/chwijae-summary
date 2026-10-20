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
const html=fs.readFileSync("api/static/about.html","utf8");
const css=fs.readFileSync("api/static/bigkinds-charts.css","utf8");
for(const token of ["bigkindsAnnualChart","bigkindsPublisherChart","bigkindsPublisherFilters",
  "bigkindsResetPublishers","bigkindsSelectedCount","bigkinds-charts.js","bigkinds-charts.css",
  "빅카인즈","2016","2025"]){
  assert(html.includes(token),token);
}
assert(css.includes("bigkinds-tooltip"));
assert(css.includes("bigkinds-hit:focus-visible"));
assert(html.includes('id="aboutContent"'),"Keep admin-editable About content");
console.log("BigKinds annual totals, publisher comparison, 4 defaults, all 10 toggles and tooltips validated");
