// Render a title-sized lead phrase inside the original first paragraph; never change stored admin text.
function renderAboutText(node,text,highlightLead){
  node.replaceChildren();
  // The existing introduction gets an attractive default, but administrators
  // can override the formatting at any point with the editor's selection tools.
  const markers={"큰글씨":"about-lead-phrase","작은글씨":"about-small-phrase","굵게":"about-bold-phrase"};
  const hasFormatting=/\[(?:큰글씨|작은글씨|굵게)\]/.test(text);
  if(highlightLead&&!hasFormatting){
    const match=/^(\s*)([“"‘']취재를 종합하면[”"’'])/.exec(text);
    if(match){
      if(match[1])node.appendChild(document.createTextNode(match[1]));
      const lead=document.createElement("span");
      lead.className="about-lead-phrase";
      lead.setAttribute("role","heading");
      lead.setAttribute("aria-level","1");
      lead.textContent=match[2]; // “은” stays in the normal-sized continuation.
      node.appendChild(lead);
      node.appendChild(document.createTextNode(text.slice(match[0].length)
        .replace(/^[ \t]*(?:\r?\n)[ \t]*/, " ")));
      return;
    }
  }
  if(!hasFormatting){node.textContent=text;return;}
  const root=node, stack=[{key:null,element:root}],token=/\[(\/?)(큰글씨|작은글씨|굵게)\]/g;
  let offset=0,match;
  while((match=token.exec(text))!==null){
    if(match.index>offset){
      stack[stack.length-1].element.appendChild(document.createTextNode(text.slice(offset,match.index)));
    }
    if(!match[1]&&stack.length<8){
      const span=document.createElement("span");
      span.className=markers[match[2]];
      if(match[2]==="큰글씨"){
        span.setAttribute("role","heading");
        span.setAttribute("aria-level","1");
      }
      stack[stack.length-1].element.appendChild(span);
      stack.push({key:match[2],element:span});
    }else if(match[1]&&stack.length>1&&stack[stack.length-1].key===match[2]){
      stack.pop();
    }else{
      stack[stack.length-1].element.appendChild(document.createTextNode(match[0]));
    }
    offset=token.lastIndex;
  }
  if(offset<text.length)stack[stack.length-1].element.appendChild(document.createTextNode(text.slice(offset)));
}

function renderAboutLayout(cfg){
  const host=document.querySelector("#aboutLayout");
  const legacy=document.querySelector("#aboutContent");
  const charts={
    annual:document.querySelector("#bigkindsAnnualSection"),
    publisher:document.querySelector("#bigkindsPublisherSection")
  };
  const t=(cfg.ui_copy||{});
  const put=(selector,key)=>{const el=document.querySelector(selector);if(el)el.textContent=key in t?t[key]:"";};
  document.title=(t.dashboard_title||"취재를 종합하면")+" | 자세히 보기";
  put("#aboutBackLabel","about_back");
  put("#bigkindsAnnualTitle","annual_chart_title");
  put("#annualChartCaption","annual_chart_caption");
  put("#bigkindsPublisherTitle","publisher_chart_title");
  put("#feedbackSummaryLabel","feedback_disclosure");
  put("#feedbackPromptLabel","feedback_label");
  put("#feedbackSubmit","feedback_submit");
  put("#aboutLoadError","about_load_error");
  const input=document.querySelector("#feedbackMessage");
  if(input)input.placeholder=t.feedback_placeholder??"";
  window.aboutPublicUiCopy=t;
  window.dispatchEvent(new Event("about-copy-ready"));
  const saved=Array.isArray(cfg.about_layout)?cfg.about_layout:[
    ...(cfg.about_body?[{type:"text",text:cfg.about_body}]:[]),
    {type:"chart",chart:"annual"},{type:"chart",chart:"publisher"}
  ];
  const fragment=document.createDocumentFragment();
  let legacyUsed=false;
  let leadSeen=false;
  for(const block of saved){
    if(block.type==="chart"&&charts[block.chart]){
      fragment.appendChild(charts[block.chart]);
    }else if(block.type==="text"&&typeof block.text==="string"&&block.text.trim()){
      const node=!legacyUsed?legacy:document.createElement("section");
      legacyUsed=true;
      node.className="about-text-block";
      renderAboutText(node,block.text,!leadSeen);
      leadSeen=true;
      node.hidden=false;
      fragment.appendChild(node);
    }
  }
  if(!legacyUsed){legacy.hidden=true;fragment.appendChild(legacy);}
  // Preserve both graphs even if configuration is malformed.
  for(const el of Object.values(charts))if(!fragment.contains(el))fragment.appendChild(el);
  host.replaceChildren(fragment);
}
async function loadAbout(){
  const res=await fetch("/api/config",{cache:"no-store"});
  if(!res.ok)throw new Error("Could not load public site configuration");
  renderAboutLayout(await res.json());
}
document.addEventListener("DOMContentLoaded",()=>{
  if(!document.querySelector("#aboutLayout"))return;
  loadAbout().catch(()=>{
    document.querySelector("#aboutLoadError").hidden=false;
  });
});
