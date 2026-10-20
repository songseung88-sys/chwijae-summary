const labels={
hero_description:"첫 화면 설명",
card_today_label:"카드 · 오늘 건수",
card_publisher_label:"카드 · 최다 언론사",
card_reporter_label:"카드 · 최다 기자",
card_exclusive_label:"카드 · 단독 비율",
section_publisher_title:"섹션 · 언론사 순위",
section_reporter_title:"섹션 · 기자 순위",
section_category_title:"섹션 · 원문 기사 분류",
section_secondary_title:"섹션 · 함께 쓰인 표현",
topic_primary_caption:"차트 제목 · 1차 기사 분류",
topic_secondary_caption:"차트 제목 · 2차 분류별 비중",
section_history_title:"섹션 · 최근 추이",
section_articles_title:"섹션 · 문장 목록",
group_usage_title:"그룹 제목 · 언론사·기자 순위",
group_analysis_title:"그룹 제목 · 주제·무주체형 표현",
ranking_view_all_text:"링크 · 자세히 보기",
ranking_collapse_text:"링크 · 접기",
paragraph_toggle_text:"링크 · 문단 보기",
original_link_text:"링크 · 원문",
naver_link_text:"링크 · 네이버",
articles_more_text:"버튼 · 더 보기",
about_body:"자세히 보기 · 본문 (줄바꿈 유지)"
};
let current={};
async function load(){
 const r=await fetch("/api/config"); current=await r.json();
 const form=document.querySelector("#configForm");
 form.innerHTML=Object.entries(labels).map(([k,label])=>{
   const value=String(current[k]||"")
     .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
   const rows=k==="about_body" ? 14 : (k==="hero_description" ? 4 : 2);
   return `
   <label class="admin-field"><span>${label}</span>
   <textarea name="${k}" rows="${rows}">${value}</textarea></label>`;
 }).join("");
}
async function save(){
 const status=document.querySelector("#status");
 status.textContent="저장 중…";
 const payload={};
 new FormData(document.querySelector("#configForm")).forEach((v,k)=>payload[k]=v);
 const r=await fetch("/api/admin/config",{method:"PUT",headers:{
   "Content-Type":"application/json",
   "X-Admin-Password":document.querySelector("#password").value
 },body:JSON.stringify(payload)});
 const body=await r.json().catch(()=>({}));
 if(!r.ok){status.textContent=body.detail||"저장 실패";return;}
 status.textContent="저장됨";
}
document.addEventListener("DOMContentLoaded",()=>{load();document.querySelector("#saveButton").addEventListener("click",save);});
