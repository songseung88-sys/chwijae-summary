"use strict";
let aboutDraft=[];
const aboutLabels={annual:"연간 기사 수 그래프",publisher:"언론사별 사용 추이 그래프"};
function aboutEscape(text){
  return String(text).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function renderAboutEditor(){
  const host=document.querySelector("#aboutLayoutRows");
  host.innerHTML=aboutDraft.map((b,i)=>{
    const chart=b.type==="chart";
    return '<div class="about-editor-block" data-block="'+i+'">'+
      '<div class="about-editor-block-heading"><strong>'+(chart?'그래프 · '+aboutLabels[b.chart]:'소개글 블록 '+(i+1))+
      '</strong><div class="about-editor-block-buttons">'+
      '<button type="button" data-action="up" data-index="'+i+'" '+(i===0?'disabled':'')+' aria-label="위로 이동">↑</button>'+
      '<button type="button" data-action="down" data-index="'+i+'" '+(i===aboutDraft.length-1?'disabled':'')+' aria-label="아래로 이동">↓</button>'+
      (chart?'':'<button type="button" data-action="delete" data-index="'+i+'" aria-label="이 소개글 삭제">삭제</button>')+
      '</div></div>'+
      (chart?'<p class="about-editor-chart-info">이 그래프는 공개 페이지에서 자동으로 표시됩니다.</p>':
        '<label class="admin-field"><span>본문 (줄바꿈 유지)</span><textarea data-about-text="'+i+'" rows="6" maxlength="30000" placeholder="이 위치에 소개글을 입력하세요.">'+aboutEscape(b.text||"")+'</textarea></label>'+
        '<div class="about-format-toolbar" role="group" aria-label="선택한 글자 서식">'+
        '<button type="button" data-format="큰글씨" data-index="'+i+'">큰 글씨</button>'+
        '<button type="button" data-format="작은글씨" data-index="'+i+'">작은 글씨</button>'+
        '<button type="button" data-format="굵게" data-index="'+i+'">굵게</button>'+
        '<span>글자 선택 → 적용 · 같은 버튼 다시 누르면 해제</span></div>'+
        '<div class="about-editor-preview" data-about-preview="'+i+'" aria-label="본문 미리보기"></div>')+
      '</div>';
  }).join("");
  host.querySelectorAll("textarea[data-about-text]").forEach(t=>{
    const idx=Number(t.dataset.aboutText);
    const preview=host.querySelector('[data-about-preview="'+idx+'"]');
    function update(){
      aboutDraft[idx].text=t.value;
      const first=aboutDraft.findIndex(block=>block.type==="text"&&block.text.trim());
      renderAboutText(preview,t.value,idx===first);
    }
    t.addEventListener("input",update);
    update();
  });
  host.querySelectorAll("button[data-format]").forEach(button=>button.addEventListener("click",()=>{
    const idx=Number(button.dataset.index);
    const field=host.querySelector('textarea[data-about-text="'+idx+'"]');
    const start=field.selectionStart,end=field.selectionEnd;
    if(start===end){field.focus();return;}
    const tag=button.dataset.format;
    const change=toggleAboutFormatting(field.value,start,end,tag);
    if(!change){
      document.querySelector("#aboutLayoutStatus").textContent=
        "서식을 적용하거나 해제할 글자 범위를 다시 선택해주세요.";
      field.focus();
      return;
    }
    field.value=change.text;
    field.focus();
    field.setSelectionRange(change.start,change.end);
    field.dispatchEvent(new Event("input",{bubbles:true}));
    document.querySelector("#aboutLayoutStatus").textContent=
      change.applied?"선택한 글자에 서식을 적용했습니다.":"선택한 글자의 서식을 해제했습니다.";
  }));
  host.querySelectorAll("button[data-action]").forEach(button=>button.addEventListener("click",()=>{
    const i=Number(button.dataset.index), action=button.dataset.action;
    if(action==="delete"){aboutDraft.splice(i,1);}
    else{
      const j=i+(action==="up"?-1:1);
      if(j<0||j>=aboutDraft.length)return;
      [aboutDraft[i],aboutDraft[j]]=[aboutDraft[j],aboutDraft[i]];
    }
    renderAboutEditor();
  }));
}
async function fetchAboutLayout(){
  const status=document.querySelector("#aboutLayoutStatus");
  const response=await fetch("/api/config",{cache:"no-store"});
  if(!response.ok)throw Error("소개글을 불러오지 못했습니다.");
  const cfg=await response.json();
  aboutDraft=Array.isArray(cfg.about_layout)?cfg.about_layout.map(b=>({...b})):
    [...(cfg.about_body?[{type:"text",text:cfg.about_body}]:[]),
      {type:"chart",chart:"annual"},{type:"chart",chart:"publisher"}];
  renderAboutEditor();
  status.textContent="현재 공개된 배치를 불러왔습니다.";
}
async function saveAboutEditor(){
  const status=document.querySelector("#aboutLayoutStatus");
  status.textContent="저장 중…";
  const password=document.querySelector("#password").value;
  if(!password){status.textContent="먼저 위에 관리자 비밀번호를 입력해주세요.";return;}
  const button=document.querySelector("#saveAboutLayout");
  button.disabled=true;
  try{
    const response=await fetch("/api/admin/about-layout",{
      method:"PUT",headers:{"Content-Type":"application/json","X-Admin-Password":password},
      body:JSON.stringify({blocks:aboutDraft})
    });
    const result=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(result.detail||"저장에 실패했습니다.");
    status.textContent="저장 완료 · 새로 연 공개 페이지에 반영됩니다.";
  }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
}
document.addEventListener("DOMContentLoaded",()=>{
  document.querySelector("#loadAboutLayout").addEventListener("click",()=>
    fetchAboutLayout().catch(e=>document.querySelector("#aboutLayoutStatus").textContent=e.message));
  document.querySelector("#addAboutBlock").addEventListener("click",()=>{
    if(aboutDraft.filter(b=>b.type==="text").length>=20){
      document.querySelector("#aboutLayoutStatus").textContent="소개글은 최대 20개입니다.";return;
    }
    // Add a text block after the last selected content block.
    aboutDraft.push({type:"text",text:""});
    renderAboutEditor();
    const last=document.querySelector("#aboutLayoutRows textarea[data-about-text]:last-child");
    if(last)last.focus();
  });
  document.querySelector("#saveAboutLayout").addEventListener("click",saveAboutEditor);
  fetchAboutLayout().catch(e=>document.querySelector("#aboutLayoutStatus").textContent=e.message);
});
