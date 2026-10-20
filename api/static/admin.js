"use strict";
// Public fixed-copy editing: each field can save independently while the
// existing bottom "저장" button still submits all pending changes.
let copyFields=[],copyDraft={},copySaved={},copySaving=false;
function htmlEsc(v){return String(v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function copyChanged(key){return copyDraft[key]!==copySaved[key];}
function copyEntry(key){
  const field=document.getElementById("edit-copy-"+key);
  return field?.closest(".copy-editor-entry")||null;
}
function updateCopyEntryState(key){
  const entry=copyEntry(key);
  if(!entry)return;
  const changed=copyChanged(key);
  entry.classList.toggle("copy-editor-entry-modified",changed);
  const button=entry.querySelector("button[data-save-copy]");
  if(button){
    button.disabled=copySaving||!changed;
    button.textContent="이 항목 저장";
  }
  const note=entry.querySelector("[data-copy-feedback]");
  if(note&&!changed&&note.textContent==="수정됨 · 아직 저장하지 않았습니다.")note.textContent="";
}
function copyFieldEdited(key){
  updateCopyEntryState(key);
  const entry=copyEntry(key),note=entry?.querySelector("[data-copy-feedback]");
  if(note)note.textContent=copyChanged(key)?"수정됨 · 아직 저장하지 않았습니다.":"";
}
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
      textarea.addEventListener("input",()=>{
        copyDraft[field.key]=textarea.value;
        copyFieldEdited(field.key);
      });
      const buttons=document.createElement("div");
      buttons.className="copy-editor-inline-actions";
      const clear=document.createElement("button");
      clear.type="button";clear.textContent="문구 삭제";clear.addEventListener("click",()=>{
        textarea.value="";copyDraft[field.key]="";copyFieldEdited(field.key);
      });
      const restore=document.createElement("button");
      restore.type="button";restore.textContent="기본값";restore.addEventListener("click",()=>{
        textarea.value=field.default;copyDraft[field.key]=field.default;copyFieldEdited(field.key);
      });
      const saveButton=document.createElement("button");
      saveButton.type="button";
      saveButton.className="copy-item-save";
      saveButton.dataset.saveCopy=field.key;
      saveButton.textContent="이 항목 저장";
      saveButton.disabled=copySaving||!copyChanged(field.key);
      saveButton.addEventListener("click",()=>saveCopyField(field.key));
      const feedback=document.createElement("span");
      feedback.dataset.copyFeedback=field.key;
      feedback.className="copy-item-status";
      feedback.setAttribute("role","status");
      feedback.setAttribute("aria-live","polite");
      if(copyChanged(field.key))div.classList.add("copy-editor-entry-modified");
      buttons.append(clear,restore,saveButton);
      div.append(label,textarea,buttons,feedback);
      sec.appendChild(div);
    }
    frag.appendChild(sec);
  }
  if(!groups.size){root.textContent="일치하는 문구가 없습니다.";return;}
  root.replaceChildren(frag);
}
async function load(){
  if(copySaving)return;
  const [fieldsResponse,configResponse]=await Promise.all([
    fetch("/static/ui-copy-fields.json",{cache:"no-store"}),
    fetch("/api/config",{cache:"no-store"})
  ]);
  if(!fieldsResponse.ok||!configResponse.ok)throw Error("관리자 문구를 불러오지 못했습니다.");
  copyFields=await fieldsResponse.json();
  const cfg=await configResponse.json();
  copyDraft={};
  for(const field of copyFields)copyDraft[field.key]=cfg.ui_copy?.[field.key]??field.default;
  copySaved={...copyDraft};
  renderCopyEditor(document.querySelector("#copyFilter").value);
}
async function sendCopyUpdates(texts){
  const password=document.querySelector("#password").value;
  if(!password)throw Error("먼저 관리자 비밀번호를 입력해주세요.");
  const response=await fetch("/api/admin/ui-copy",{
    method:"PUT",headers:{"Content-Type":"application/json","X-Admin-Password":password},
    body:JSON.stringify({texts})
  });
  const obj=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(obj.detail||"문구를 저장하지 못했습니다.");
  return obj;
}
function setCopySaving(saving){
  copySaving=saving;
  const global=document.querySelector("#saveButton");
  if(global)global.disabled=saving;
  document.querySelectorAll("button[data-save-copy]").forEach(button=>{
    button.disabled=saving||!copyChanged(button.dataset.saveCopy);
  });
}
async function saveCopyField(key){
  if(copySaving||!copyChanged(key))return;
  const field=copyFields.find(item=>item.key===key);
  if(!field)return;
  const snapshot=copyDraft[key];
  const entry=copyEntry(key);
  const note=entry?.querySelector("[data-copy-feedback]");
  const status=document.querySelector("#status");
  setCopySaving(true);
  if(note)note.textContent="저장 중…";
  try{
    // The API supports partial updates. Send this field ONLY, leaving any
    // other in-progress edits untouched locally and on the server.
    await sendCopyUpdates({[key]:snapshot});
    copySaved[key]=snapshot;
    if(note){
      note.textContent=copyChanged(key)?"저장 완료 · 이후 수정한 내용은 아직 저장 전입니다.":"저장 완료";
    }
    status.textContent=field.label+" · 개별 저장 완료";
  }catch(e){
    if(note)note.textContent=e.message;
    status.textContent=field.label+" · "+e.message;
  }finally{
    setCopySaving(false);
    updateCopyEntryState(key);
  }
}
async function save(){
  if(copySaving)return;
  const status=document.querySelector("#status");
  const changed=Object.fromEntries(Object.keys(copyDraft)
    .filter(copyChanged).map(key=>[key,copyDraft[key]]));
  if(!Object.keys(changed).length){
    status.textContent="저장할 변경사항이 없습니다.";
    return;
  }
  status.textContent="저장 중…";
  setCopySaving(true);
  try{
    // Keep the existing global-save button, while writing only pending edits
    // so unrelated values and concurrent changes are not overwritten.
    await sendCopyUpdates(changed);
    Object.assign(copySaved,changed);
    status.textContent="전체 변경사항 저장 완료 · 공개 페이지를 새로고침하면 확인할 수 있습니다.";
    Object.keys(changed).forEach(updateCopyEntryState);
  }catch(e){
    status.textContent=e.message;
  }finally{
    setCopySaving(false);
  }
}
document.addEventListener("DOMContentLoaded",()=>{
  document.querySelector("#copyFilter").addEventListener("input",e=>renderCopyEditor(e.target.value));
  document.querySelector("#copyReload").addEventListener("click",()=>load().catch(e=>document.querySelector("#status").textContent=e.message));
  document.querySelector("#saveButton").addEventListener("click",save);
  load().catch(e=>document.querySelector("#status").textContent=e.message);
});
