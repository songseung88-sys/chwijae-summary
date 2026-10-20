"use strict";
// One catalog powers every editable piece of fixed interface copy; article data
// and numeric statistics remain immutable through this editor.
let copyFields=[],copyDraft={};
function htmlEsc(v){return String(v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function renderCopyEditor(filter=""){
 const root=document.querySelector("#configForm");
 const q=filter.trim().toLocaleLowerCase("ko");
 const groups=new Map();
 for(const field of copyFields){
   if(q&&!([field.label,field.group,field.key,copyDraft[field.key]].join(" ").toLocaleLowerCase("ko").includes(q)))continue;
   if(!groups.has(field.group))groups.set(field.group,[]);
   groups.get(field.group).push(field);
 }
 const frag=document.createDocumentFragment();
 for(const [group,fields] of groups){
   const sec=document.createElement("section");
   sec.className="copy-editor-group";
   const title=document.createElement("h3");
   title.textContent=group;
   sec.appendChild(title);
   for(const field of fields){
     const div=document.createElement("div");
     div.className="copy-editor-entry";
     const label=document.createElement("label");
     label.htmlFor="edit-copy-"+field.key;
     label.textContent=field.label;
     const textarea=document.createElement("textarea");
     textarea.id="edit-copy-"+field.key;
     textarea.name=field.key;
     textarea.rows=String(copyDraft[field.key]||"").length>90?3:2;
     textarea.maxLength=800;
     textarea.value=copyDraft[field.key]??"";
     textarea.placeholder="빈칸으로 저장하면 공개 화면에서 이 문구를 숨깁니다.";
     textarea.addEventListener("input",()=>{copyDraft[field.key]=textarea.value;});
     const buttons=document.createElement("div");
     buttons.className="copy-editor-inline-actions";
     const clear=document.createElement("button");
     clear.type="button";clear.textContent="문구 삭제";clear.addEventListener("click",()=>{
       textarea.value="";copyDraft[field.key]="";
     });
     const restore=document.createElement("button");
     restore.type="button";restore.textContent="기본값";
     restore.addEventListener("click",()=>{
       textarea.value=field.default;copyDraft[field.key]=field.default;
     });
     buttons.append(clear,restore);
     div.append(label,textarea,buttons);
     sec.appendChild(div);
   }
   frag.appendChild(sec);
 }
 if(!groups.size){root.textContent="일치하는 문구가 없습니다.";return;}
 root.replaceChildren(frag);
}
async function load(){
 const [fieldsResponse,configResponse]=await Promise.all([
   fetch("/static/ui-copy-fields.json",{cache:"no-store"}),
   fetch("/api/config",{cache:"no-store"})
 ]);
 if(!fieldsResponse.ok||!configResponse.ok)throw Error("관리자 문구를 불러오지 못했습니다.");
 copyFields=await fieldsResponse.json();
 const cfg=await configResponse.json();
 copyDraft={};
 for(const field of copyFields)copyDraft[field.key]=cfg.ui_copy?.[field.key]??field.default;
 renderCopyEditor(document.querySelector("#copyFilter").value);
}
async function save(){
 const status=document.querySelector("#status");
 const password=document.querySelector("#password").value;
 if(!password){status.textContent="먼저 관리자 비밀번호를 입력해주세요.";return;}
 const button=document.querySelector("#saveButton");
 status.textContent="저장 중…";
 button.disabled=true;
 try{
   const response=await fetch("/api/admin/ui-copy",{
     method:"PUT",headers:{"Content-Type":"application/json","X-Admin-Password":password},
     body:JSON.stringify({texts:copyDraft})
   });
   const obj=await response.json().catch(()=>({}));
   if(!response.ok)throw Error(obj.detail||"문구를 저장하지 못했습니다.");
   copyDraft={...obj.texts};
   status.textContent="저장 완료 · 공개 페이지에서 새로고침하면 즉시 확인할 수 있습니다.";
 }catch(e){status.textContent=e.message;}finally{button.disabled=false;}
}
document.addEventListener("DOMContentLoaded",()=>{
 document.querySelector("#copyFilter").addEventListener("input",e=>renderCopyEditor(e.target.value));
 document.querySelector("#copyReload").addEventListener("click",()=>load().catch(e=>document.querySelector("#status").textContent=e.message));
 document.querySelector("#saveButton").addEventListener("click",save);
 load().catch(e=>document.querySelector("#status").textContent=e.message);
});
