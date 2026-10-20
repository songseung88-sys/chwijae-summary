const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");

const html=fs.readFileSync("api/static/about.html","utf8");
const css=fs.readFileSync("api/static/bigkinds-charts.css","utf8");
const script=fs.readFileSync("api/static/about.js","utf8");
assert(!html.includes("<h1>자세히 보기</h1>"),"Remove redundant visible title");
assert(!html.includes('id="bigkindsHistoryTitle"'));
assert(html.includes('src="/static/about.js?v=3"'),"Bust cached JS");
assert(html.includes('bigkinds-charts.css?v=4'),"Bust cached CSS");
assert(css.includes(".about-page .about-text-block .about-lead-phrase"));
assert(css.includes("font-size:30px"),"Match original About h1 size");
assert(css.includes("display:inline"),"Keep normal text on the same line");
assert(script.includes('renderAboutText(node,block.text,!leadSeen)'));

const document={
  addEventListener(){},
  createTextNode(text){return {type:"text",value:text}},
  createElement(tag){
    return {type:tag,attrs:{},textContent:"",setAttribute(k,v){this.attrs[k]=v}}
  }
};
const context=vm.createContext({document});
vm.runInContext(script,context);
function render(text,highlight=true){
  const node={
    children:[],textContent:"",
    replaceChildren(){this.children=[]},
    appendChild(c){this.children.push(c)}
  };
  context.renderAboutText(node,text,highlight);
  return node;
}
const first=render('“취재를 종합하면”은 언론의 서술 관행입니다. 다음 문장입니다.');
assert.equal(first.children.length,2);
assert.equal(first.children[0].textContent,'“취재를 종합하면”은');
assert.equal(first.children[0].className,"about-lead-phrase");
assert.deepEqual({...first.children[0].attrs},{role:"heading","aria-level":"1"});
assert.equal(first.children[1].value,' 언론의 서술 관행입니다. 다음 문장입니다.');
assert(!first.children.some(x=>x.type==="br"),"Do not force a line break");
const withWhitespace=render(' \n“취재를 종합하면”은\n다음 줄입니다.');
assert.equal(withWhitespace.children[0].value,' \n');
assert.equal(withWhitespace.children[1].textContent,'“취재를 종합하면”은');
assert.equal(withWhitespace.children[2].value,'\n다음 줄입니다.');
const apostrophe=render('‘취재를 종합하면’은 의견을 소개합니다.');
assert.equal(apostrophe.children[0].textContent,'‘취재를 종합하면’은');
const later=render('“취재를 종합하면”은 <img src=x onerror=alert(1)>',false);
assert.equal(later.children.length,0);
assert.equal(later.textContent,'“취재를 종합하면”은 <img src=x onerror=alert(1)>');
const missing=render('첫 문장이 다른 경우 그대로 표시합니다.');
assert.equal(missing.children.length,0);
assert.equal(missing.textContent,'첫 문장이 다른 경우 그대로 표시합니다.');
console.log("About lead text retained inline, accessible, source-preserving and safe");
