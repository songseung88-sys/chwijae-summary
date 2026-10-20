"use strict";
let bigkindsDraft=null,bigkindsSaved=null;
const bigkindsNumberFormatter=new Intl.NumberFormat("ko-KR");
function bigkindsEditorTotals(data){
  return data.years.map((_,i)=>Object.values(data.publishers).reduce((sum,arr)=>sum+arr[i],0));
}

function bigkindsYearModified(index){
  if(!bigkindsSaved||!bigkindsDraft)return false;
  return Object.keys(bigkindsDraft.publishers).some(
    name=>bigkindsDraft.publishers[name][index]!==bigkindsSaved.publishers[name][index]
  );
}
function updateBigkindsYearSave(index){
  const button=document.querySelector('[data-save-year="'+index+'"]');
  if(button)button.disabled=!bigkindsYearModified(index);
}
async function saveBigkindsYear(index){
  if(!bigkindsDraft||!bigkindsYearModified(index))return;
  const password=document.querySelector("#password").value;
  const label=document.querySelector('[data-year-feedback="'+index+'"]');
  const button=document.querySelector('[data-save-year="'+index+'"]');
  if(!password){label.textContent="관리자 비밀번호가 필요합니다.";return;}
  const inputs=[...document.querySelectorAll('#bigkindsEditorBody input[data-year-index="'+index+'"]')];
  if(inputs.some(input=>!input.checkValidity())){
    label.textContent="이 연도의 숫자를 확인해주세요.";return;
  }
  const names=Object.keys(bigkindsDraft.publishers);
  const values=Object.fromEntries(names.map(name=>[name,bigkindsDraft.publishers[name][index]]));
  button.disabled=true;
  label.textContent="저장 중…";
  try{
    // Read the last server version before merging just this one year's values.
    // Unsaved edits in the other nine years never reach the server.
    const latestResponse=await fetch("/api/bigkinds-history",{cache:"no-store"});
    if(!latestResponse.ok)throw Error("최신 기사 수를 불러오지 못했습니다.");
    const latest=await latestResponse.json();
    for(const name of names)latest.publishers[name][index]=values[name];
    latest.totals=latest.years.map((_,i)=>Object.values(latest.publishers)
      .reduce((sum,arr)=>sum+arr[i],0));
    const response=await fetch("/api/admin/bigkinds-history",{
      method:"PUT",
      headers:{"Content-Type":"application/json","X-Admin-Password":password},
      body:JSON.stringify(latest)
    });
    const result=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(result.detail||"해당 연도를 저장하지 못했습니다.");
    // Do not replace the draft. Its other years may contain unfinished edits.
    for(const name of names)bigkindsSaved.publishers[name][index]=values[name];
    label.textContent="저장 완료";
    document.querySelector("#bigkindsDataStatus").textContent=
      bigkindsDraft.years[index]+"년 저장 완료 · 다른 연도 수정 내용은 그대로 유지됩니다.";
  }catch(error){
    label.textContent=error.message;
  }finally{
    updateBigkindsYearSave(index);
  }
}

function renderBigkindsEditor(){
  const head=document.querySelector("#bigkindsEditorHead");
  const body=document.querySelector("#bigkindsEditorBody");
  const names=Object.keys(bigkindsDraft.publishers);
  head.innerHTML='<tr><th scope="col">연도</th>'+names.map(n=>'<th scope="col">'+n+'</th>').join("")+
    '<th scope="col">연간 합계 (자동)</th><th scope="col">개별 저장</th></tr>';
  const totals=bigkindsEditorTotals(bigkindsDraft);
  body.innerHTML=bigkindsDraft.years.map((year,i)=>'<tr><th scope="row">'+year+'</th>'+
    names.map(n=>'<td><input type="number" min="0" max="1000000" step="1" required '+
    'aria-label="'+year+'년 '+n+' 기사 수" data-year-index="'+i+'" data-publisher="'+n+
    '" value="'+bigkindsDraft.publishers[n][i]+'"></td>').join("")+
    '<td class="bigkinds-editor-total" data-total-index="'+i+'">'+bigkindsNumberFormatter.format(totals[i])+'</td>'+
    '<td><button type="button" class="bigkinds-year-save" data-save-year="'+i+'" '+(bigkindsYearModified(i)?'':'disabled')+'>이 연도 저장</button>'+
    '<span class="bigkinds-year-status" role="status" aria-live="polite" data-year-feedback="'+i+'"></span></td></tr>').join("");
  body.oninput=onBigkindsCellInput;
  body.onclick=event=>{
    const button=event.target.closest("button[data-save-year]");
    if(button)saveBigkindsYear(Number(button.dataset.saveYear));
  };
}
function onBigkindsCellInput(event){
  const el=event.target;
  if(!el.matches("input[data-publisher]"))return;
  const value=Number(el.value), i=Number(el.dataset.yearIndex), name=el.dataset.publisher;
  const status=document.querySelector("#bigkindsDataStatus");
  if(el.value===""||!Number.isSafeInteger(value)||value<0||value>1000000){
    el.setCustomValidity("0 이상 100만 이하의 정수를 입력하세요.");
    status.textContent="잘못된 값이 있습니다. 빈칸 없이 0 이상의 정수를 입력해주세요.";
    return;
  }
  el.setCustomValidity("");
  bigkindsDraft.publishers[name][i]=value;
  updateBigkindsYearSave(i);
  const annual=bigkindsEditorTotals(bigkindsDraft);
  document.querySelector('[data-total-index="'+i+'"]').textContent=bigkindsNumberFormatter.format(annual[i]);
  status.textContent="변경사항이 있습니다. 저장하면 두 그래프에 반영됩니다.";
}
async function loadBigkindsEditor(){
  const response=await fetch("/api/bigkinds-history",{cache:"no-store"});
  if(!response.ok)throw Error("기사 수 데이터를 불러오지 못했습니다.");
  bigkindsDraft=await response.json();
  bigkindsSaved=JSON.parse(JSON.stringify(bigkindsDraft));
  renderBigkindsEditor();
  document.querySelector("#bigkindsDataStatus").textContent="현재 저장된 데이터를 불러왔습니다.";
}
async function saveBigkindsEditor(){
  const status=document.querySelector("#bigkindsDataStatus");
  const pass=document.querySelector("#password").value;
  if(!pass){status.textContent="먼저 위에 관리자 비밀번호를 입력해주세요.";return;}
  if(!bigkindsDraft){status.textContent="먼저 현재 데이터를 불러오세요.";return;}
  const inputs=[...document.querySelectorAll("#bigkindsEditorBody input")];
  if(!inputs.every(el=>el.checkValidity())){
    status.textContent="기사 수는 0 이상 100만 이하의 정수여야 합니다.";
    inputs.find(el=>!el.checkValidity())?.focus();return;
  }
  bigkindsDraft.totals=bigkindsEditorTotals(bigkindsDraft);
  const button=document.querySelector("#saveBigkindsData");
  button.disabled=true;
  status.textContent="저장 중…";
  try{
    const response=await fetch("/api/admin/bigkinds-history",{
      method:"PUT",
      headers:{"Content-Type":"application/json","X-Admin-Password":pass},
      body:JSON.stringify(bigkindsDraft)
    });
    const result=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(result.detail||"저장 실패");
    bigkindsDraft=result.data;
    bigkindsSaved=JSON.parse(JSON.stringify(bigkindsDraft));
    renderBigkindsEditor();
    status.textContent="저장 완료 · 연간 합계와 언론사별 그래프에 반영됐습니다.";
  }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
}
document.addEventListener("DOMContentLoaded",()=>{
  document.querySelector("#loadBigkindsData").addEventListener("click",()=>{
    loadBigkindsEditor().catch(e=>document.querySelector("#bigkindsDataStatus").textContent=e.message);
  });
  document.querySelector("#saveBigkindsData").addEventListener("click",saveBigkindsEditor);
  loadBigkindsEditor().catch(e=>document.querySelector("#bigkindsDataStatus").textContent=e.message);
});
