// Render a title-sized lead phrase inside the original first paragraph; never change stored admin text.
function renderAboutText(node,text,highlightLead){
  node.replaceChildren();
  const lead=/^(\s*)([“"‘']취재를 종합하면[”"’']은)/.exec(text);
  if(highlightLead&&lead){
    if(lead[1])node.appendChild(document.createTextNode(lead[1]));
    const title=document.createElement("span");
    title.className="about-lead-phrase";
    title.textContent=lead[2];
    node.appendChild(title);
    node.appendChild(document.createTextNode(text.slice(lead[0].length)));
  }else{
    node.textContent=text;
  }
}

function renderAboutLayout(cfg){
  const host=document.querySelector("#aboutLayout");
  const legacy=document.querySelector("#aboutContent");
  const charts={
    annual:document.querySelector("#bigkindsAnnualSection"),
    publisher:document.querySelector("#bigkindsPublisherSection")
  };
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
  loadAbout().catch(()=>{
    document.querySelector("#aboutLoadError").hidden=false;
  });
});
