async function loadAbout(){
  const res=await fetch("/api/config",{cache:"no-store"});
  if(!res.ok)throw new Error("Could not load public site configuration");
  const cfg=await res.json();
  const content=document.querySelector("#aboutContent");
  content.textContent=typeof cfg.about_body==="string" ? cfg.about_body : "";
}
document.addEventListener("DOMContentLoaded",()=>{
  loadAbout().catch(()=>{
    document.querySelector("#aboutLoadError").hidden=false;
  });
});
