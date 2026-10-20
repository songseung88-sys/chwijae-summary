const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
function context(path,elements,fetchImpl){
  const document={
    addEventListener(){},
    querySelector(selector){return elements[selector]||null},
    querySelectorAll(){return []},
    getElementById(){return null}
  };
  const ctx=vm.createContext({document,fetch:fetchImpl,console});
  vm.runInContext(fs.readFileSync(path,"utf8"),ctx);
  return ctx;
}
async function test(){
  const requests=[];
  const elements={
    "#status":{textContent:""},"#password":{value:"secret"},"#saveButton":{disabled:false}
  };
  const ctx=context("api/static/admin.js",elements,async (url,options)=>{
    requests.push({url,data:JSON.parse(options.body)});
    return {ok:true,json:async()=>({ok:true})};
  });
  vm.runInContext('copyFields=[{key:"one",label:"제목"},{key:"two",label:"설명"}];copyDraft={one:"수정1",two:"수정2"};copySaved={one:"원본1",two:"원본2"};',ctx);
  await vm.runInContext('saveCopyField("one")',ctx);
  assert.equal(requests.length,1);
  assert.deepEqual(requests[0].data,{texts:{one:"수정1"}});
  assert.equal(vm.runInContext('copyDraft.two',ctx),"수정2");
  assert.equal(vm.runInContext('copySaved.two',ctx),"원본2");
  await vm.runInContext('save()',ctx);
  assert.deepEqual(requests[1].data,{texts:{two:"수정2"}});
  await vm.runInContext('save()',ctx);
  assert.equal(requests.length,2);

  const publisherElements={
    "#publisherEditorStatus":{textContent:""},
    "#password":{value:"secret"},
    "#publisherSearch":{value:""},
    "#publisherRows":{innerHTML:""},
    "#publisherLoadMore":{hidden:false},
    "#savePublishers":{disabled:false},
    "#publisherEditorSummary":{textContent:""}
  };
  let publisherPayload;
  const publisher=context("api/static/publisher-editor.js",publisherElements,async(url,options)=>{
    publisherPayload=JSON.parse(options.body);
    return {ok:true,json:async()=>({updated:1})};
  });
  vm.runInContext('publisherEditor.loaded=true;publisherEditor.items=[{source:"A",default_name:"A",display_name:"A",draft:"A1",article_count:2,is_custom:false},{source:"B",default_name:"B",display_name:"B",draft:"B1",article_count:4,is_custom:false}];',publisher);
  await vm.runInContext('savePublisherRow(0)',publisher);
  assert.deepEqual(publisherPayload,{updates:[{source:"A",display_name:"A1"}]});
  assert.equal(vm.runInContext('publisherEditor.items[1].draft',publisher),"B1");
  assert.equal(vm.runInContext('publisherEditor.items[1].display_name',publisher),"B");

  const aboutElements={
    "#aboutLayoutStatus":{textContent:""},
    "#password":{value:"secret"},
    '[data-save-about-status="0"]':{textContent:""},
    '[data-save-about="0"]':{disabled:false}
  };
  let aboutPayload;
  const about=context("api/static/about-layout-editor.js",aboutElements,async(url,options)=>{
    assert.equal(url,"/api/admin/about-block");
    aboutPayload=JSON.parse(options.body);
    return {ok:true,json:async()=>({ok:true})};
  });
  vm.runInContext('aboutDraft=[{type:"text",text:"수정 문단",_savedIndex:1,_savedText:"기존 문단"},{type:"text",text:"미저장 다른 문단",_savedIndex:2,_savedText:"다른 원본"}];',about);
  await vm.runInContext('saveOneAboutBlock(0)',about);
  assert.deepEqual(aboutPayload,{index:1,expected_text:"기존 문단",text:"수정 문단"});
  assert.equal(vm.runInContext('aboutDraft[1]._savedText',about),"다른 원본");

  const yearElements={
    "#password":{value:"secret"},
    "#bigkindsDataStatus":{textContent:""},
    '[data-save-year="1"]':{disabled:false},
    '[data-year-feedback="1"]':{textContent:""}
  };
  let yearPayload;
  const baseline={years:[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025],
     publishers:{A:[1,1,1,1,1,1,1,1,1,1],B:[2,2,2,2,2,2,2,2,2,2]}};
  const big=context("api/static/bigkinds-data-editor.js",yearElements,async(url,options)=>{
    if(url==="/api/bigkinds-history")return {ok:true,json:async()=>JSON.parse(JSON.stringify(baseline))};
    assert.equal(url,"/api/admin/bigkinds-history");
    yearPayload=JSON.parse(options.body);
    return {ok:true,json:async()=>({ok:true,data:yearPayload})};
  });
  big.document.querySelectorAll=()=>[{checkValidity:()=>true}];
  vm.runInContext("bigkindsDraft="+JSON.stringify(baseline)+";bigkindsSaved="+JSON.stringify(baseline)+";bigkindsDraft.publishers.A[1]=12;bigkindsDraft.publishers.A[2]=99;",big);
  await vm.runInContext("saveBigkindsYear(1)",big);
  assert.equal(yearPayload.publishers.A[1],12);
  assert.equal(yearPayload.publishers.A[2],1);
  assert.equal(yearPayload.totals[1],14);
  assert.equal(vm.runInContext("bigkindsDraft.publishers.A[2]",big),99);
  assert.equal(vm.runInContext("bigkindsSaved.publishers.A[2]",big),1);

  const html=fs.readFileSync("api/static/admin.html","utf8");
  for(const id of ["saveButton","saveAboutLayout","saveBigkindsData","savePublishers"]){
    assert(html.includes('id="'+id+'"'),"Retain the original: "+id);
  }
  assert(fs.readFileSync("api/main.py","utf8").includes('@app.patch("/api/admin/about-block")'));
  console.log("Individual saves work without submitting other drafts; original save buttons remain.");
}
test().catch(e=>{console.error(e);process.exitCode=1});
