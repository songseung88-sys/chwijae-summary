const assert=require("node:assert/strict");
const fs=require("node:fs");
const {toggleAboutFormatting:toggle}=require("../api/static/about-format.js");

const original="“취재를 종합하면”은";
const start=original.indexOf("종합하면");
const end=start+"종합하면".length;
let applied=toggle(original,start,end,"큰글씨");
assert(applied);
assert.equal(applied.applied,true);
assert.equal(applied.text,'“취재를 [큰글씨]종합하면[/큰글씨]”은');
assert.equal(applied.text.slice(applied.start,applied.end),"종합하면");
let removed=toggle(applied.text,applied.start,applied.end,"큰글씨");
assert(removed);
assert.equal(removed.applied,false);
assert.equal(removed.text,original);
assert.equal(removed.start,start);
assert.equal(removed.end,end);

// After toggling off, a third click can re-apply the same formatting.
assert.deepEqual(toggle(removed.text,removed.start,removed.end,"큰글씨"),applied);

// The same exact behavior works for bold and small style controls.
for(const tag of ["굵게","작은글씨"]){
  const a=toggle("편집할 글자",0,4,tag);
  assert.equal(a.applied,true);
  const b=toggle(a.text,a.start,a.end,tag);
  assert.equal(b.text,"편집할 글자");
  assert.equal(b.applied,false);
}

// The previous editor sometimes selected markers along with the phrase.
const preselected="[굵게]강조 문구[/굵게]";
const fullySelected=toggle(preselected,0,preselected.length,"굵게");
assert.equal(fullySelected.text,"강조 문구");
assert.equal(fullySelected.start,0);
assert.equal(fullySelected.end,5);

// Unformat only a subsection, preserving formatting on unselected words.
const part="[굵게]안녕하세요[/굵게]";
const partialStart=part.indexOf("하세");
const partial=toggle(part,partialStart,partialStart+2,"굵게");
assert.equal(partial.text,"[굵게]안녕[/굵게]하세[굵게]요[/굵게]");
assert.equal(partial.text.slice(partial.start,partial.end),"하세");

// Combining two *different* styles is supported without duplicate same-tag nesting.
const outer=toggle("문장",0,2,"큰글씨");
const both=toggle(outer.text,outer.start,outer.end,"굵게");
assert.equal(both.text,"[큰글씨][굵게]문장[/굵게][/큰글씨]");
const undoBold=toggle(both.text,both.start,both.end,"굵게");
assert.equal(undoBold.text,outer.text);

// Invalid selections cannot insert empty tags.
assert.equal(toggle("abc",1,1,"굵게"),null);
assert.equal(toggle("abc",0,3,"script"),null);

// Public feedback label must NOT rotate or inherit the 21px arrow style.
const css=fs.readFileSync("api/static/bigkinds-charts.css","utf8");
const about=fs.readFileSync("api/static/about.html","utf8");
const admin=fs.readFileSync("api/static/admin.html","utf8");
const editor=fs.readFileSync("api/static/about-layout-editor.js","utf8");
assert(css.includes('.feedback-section summary #feedbackSummaryLabel{font-size:14px'));
assert(css.includes('.feedback-section details[open] summary > span[aria-hidden="true"]{transform:rotate(180deg)}'));
assert(!css.includes('.feedback-section details[open] summary span{transform:rotate(180deg)}'));
assert(about.includes('/static/bigkinds-charts.css?v=6'));
assert(admin.includes('/static/about-format.js?v=1'));
assert(admin.includes('/static/about-layout-editor.js?v=3'));
assert(admin.indexOf("about-format.js")<admin.indexOf("about-layout-editor.js"));
assert(editor.includes('toggleAboutFormatting(field.value,start,end,tag)'));
assert(editor.includes('field.setSelectionRange(change.start,change.end)'));
assert(!editor.includes('field.setRangeText(prefix+chosen+suffix'));
console.log("Feedback stays upright, arrow rotates, format buttons toggle on/off with selection preserved.");
