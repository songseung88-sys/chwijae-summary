"use strict";
let feedbackSubmissionId=null;
const feedbackFormSelector="#feedbackForm";

function freshFeedbackId(){
  if(typeof crypto!=="undefined"&&typeof crypto.randomUUID==="function")return crypto.randomUUID();
  // Modern browsers provide randomUUID, but keep fallback for older supported browsers.
  const bytes=new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,b=>b.toString(16).padStart(2,"0")).join("");
  return hex.slice(0,8)+"-"+hex.slice(8,12)+"-"+hex.slice(12,16)+"-"+hex.slice(16,20)+"-"+hex.slice(20);
}
async function submitFeedback(event){
  event.preventDefault();
  const form=document.querySelector(feedbackFormSelector);
  const field=document.querySelector("#feedbackMessage");
  const status=document.querySelector("#feedbackStatus");
  const button=document.querySelector("#feedbackSubmit");
  const message=field.value.trim();
  if(message.length<2||message.length>3000){
    status.textContent="의견을 2자 이상 3,000자 이하로 입력해주세요.";
    field.focus();return;
  }
  if(!feedbackSubmissionId)feedbackSubmissionId=freshFeedbackId();
  button.disabled=true;
  status.textContent="전송 중…";
  try{
    const res=await fetch("/api/feedback",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        submission_id:feedbackSubmissionId,
        message,
        website:document.querySelector("#feedbackWebsite").value
      })
    });
    const result=await res.json().catch(()=>({}));
    if(!res.ok)throw Error(result.detail||"전송에 실패했습니다. 잠시 후 다시 시도해주세요.");
    status.textContent="의견이 전송됐습니다. 감사합니다.";
    field.value="";
    feedbackSubmissionId=null;
    button.textContent="전송 완료";
    button.disabled=true;
  }catch(error){
    status.textContent=error.message;
    // Keep the same submission ID and the entered message for safe retry.
    button.disabled=false;
  }
}
if(typeof document!=="undefined"){
  document.addEventListener("DOMContentLoaded",()=>{
    const form=document.querySelector(feedbackFormSelector);
    if(!form)return;
    const field=document.querySelector("#feedbackMessage");
    field.addEventListener("input",()=>{
      const button=document.querySelector("#feedbackSubmit");
      button.textContent="전송하기";
      button.disabled=false;
      document.querySelector("#feedbackStatus").textContent="";
      feedbackSubmissionId=null;
    });
    form.addEventListener("submit",submitFeedback);
  });
}
if(typeof module!=="undefined"&&module.exports)module.exports={freshFeedbackId};
