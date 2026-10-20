/* Administrator-only publisher display aliases. Raw article metadata is never edited. */
const publisherEditor={items:[],visible:50,loaded:false,scope:""};

function escapePublisherHtml(value=""){
  return String(value).replace(/[&<>"']/g,ch=>({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[ch]));
}

function changedPublisherItems(){
  return publisherEditor.items.filter(row=>row.draft.trim()!==row.display_name);
}

function renderPublisherNames(){
  const query=document.querySelector("#publisherSearch").value.trim().toLocaleLowerCase("ko");
  const filtered=publisherEditor.items.filter(row=>
    [row.source,row.display_name,row.default_name,row.draft].some(value=>
      String(value).toLocaleLowerCase("ko").includes(query)
    )
  );
  const rows=filtered.slice(0,publisherEditor.visible);
  const tbody=document.querySelector("#publisherRows");
  tbody.innerHTML=rows.map(row=>{
    const i=publisherEditor.items.indexOf(row);
    const changed=row.draft.trim()!==row.display_name;
    return '<tr class="'+(changed?"publisher-row-changed":"")+'">'+
      '<td class="publisher-source">'+escapePublisherHtml(row.source)+
        (row.is_custom?'<span class="publisher-custom-label">수정됨</span>':"")+'</td>'+
      '<td><input type="text" data-publisher-index="'+i+'" maxlength="80" aria-label="'+escapePublisherHtml(row.source)+'의 표시 이름" value="'+escapePublisherHtml(row.draft)+'"/></td>'+
      '<td><button class="publisher-row-save" data-save-publisher="'+i+'" type="button" '+(!changed?'disabled':'')+
        ' aria-label="'+escapePublisherHtml(row.source)+' 이름만 저장">이 항목 저장</button></td>'+
      '<td class="publisher-count">'+row.article_count+'건</td>'+
      '<td><button class="publisher-reset" data-reset-index="'+i+'" type="button" aria-label="'+escapePublisherHtml(row.source)+' 기본 이름으로 초기화">초기화</button></td>'+
      '</tr>';
  }).join("");
  document.querySelector("#publisherLoadMore").hidden=filtered.length<=publisherEditor.visible;
  const pending=changedPublisherItems().length;
  document.querySelector("#savePublishers").disabled=!publisherEditor.loaded||!pending;
  document.querySelector("#publisherEditorSummary").textContent=
    publisherEditor.items.length+'개 언론사 · 검색 결과 '+filtered.length+'개 · 수정 대기 '+pending+'개';
}

async function savePublisherRow(index){
  const row=publisherEditor.items[index];
  const status=document.querySelector("#publisherEditorStatus");
  if(!row||row.draft.trim()===row.display_name)return;
  const pass=document.querySelector("#password").value;
  if(!pass){status.textContent="관리자 비밀번호를 먼저 입력해주세요.";return;}
  const value=row.draft.trim();
  const rowButton=document.querySelector('[data-save-publisher="'+index+'"]');
  if(rowButton)rowButton.disabled=true;
  status.textContent=row.source+" · 개별 저장 중…";
  try{
    const res=await fetch("/api/admin/publishers",{
      method:"PUT",
      headers:{"Content-Type":"application/json","X-Admin-Password":pass},
      body:JSON.stringify({updates:[{source:row.source,display_name:value}]})
    });
    const result=await res.json().catch(()=>({}));
    if(!res.ok)throw Error(result.detail||"해당 언론사 저장에 실패했습니다.");
    // Only this one canonical value is updated. Other unfinished names remain
    // in their text fields and the local draft array.
    row.display_name=value||row.default_name;
    row.is_custom=!!value&&value!==row.default_name;
    status.textContent=row.source+" · 저장 완료 (다른 변경사항은 그대로 유지)";
  }catch(error){
    status.textContent=row.source+" · "+error.message;
  }finally{
    renderPublisherNames();
  }
}

async function loadPublisherNames(){
  const status=document.querySelector("#publisherEditorStatus");
  const password=document.querySelector("#password").value;
  if(!password){status.textContent="관리자 비밀번호를 먼저 입력해주세요.";return;}
  const button=document.querySelector("#loadPublishers");
  button.disabled=true;
  status.textContent="언론사 이름 목록을 불러오는 중…";
  try{
    const res=await fetch("/api/admin/publishers",{
      headers:{"X-Admin-Password":password},cache:"no-store"
    });
    const result=await res.json().catch(()=>({}));
    if(!res.ok)throw new Error(result.detail||"목록을 불러오지 못했습니다.");
    publisherEditor.items=(result.publishers||[]).map(row=>({
      ...row,draft:row.display_name
    }));
    publisherEditor.scope=result.scope||"";
    publisherEditor.visible=50;
    publisherEditor.loaded=true;
    document.querySelector("#publisherSearch").disabled=false;
    document.querySelector("#publisherSearch").value="";
    status.textContent="불러오기 완료. 이름을 수정한 다음 변경사항 저장을 눌러주세요.";
    renderPublisherNames();
  }catch(err){status.textContent=err.message;}
  finally{button.disabled=false;}
}

async function savePublisherNames(){
  const pending=changedPublisherItems();
  if(!pending.length)return;
  if(pending.length>200){
    document.querySelector("#publisherEditorStatus").textContent=
      "한 번에 200개까지 저장할 수 있습니다. 수정 항목을 나눠 저장해주세요.";
    return;
  }
  const btn=document.querySelector("#savePublishers");
  const status=document.querySelector("#publisherEditorStatus");
  btn.disabled=true;
  status.textContent=pending.length+"개 언론사 이름 저장 중…";
  try{
    const res=await fetch("/api/admin/publishers",{
      method:"PUT",
      headers:{
        "Content-Type":"application/json",
        "X-Admin-Password":document.querySelector("#password").value,
      },
      body:JSON.stringify({updates:pending.map(row=>({
        source:row.source,display_name:row.draft.trim()
      }))})
    });
    const result=await res.json().catch(()=>({}));
    if(!res.ok)throw new Error(result.detail||"저장에 실패했습니다.");
    // Reload canonical server state (including normalization and reset behavior).
    await loadPublisherNames();
    status.textContent=result.updated+"개 언론사 이름을 저장했습니다. 대시보드에 즉시 반영됩니다.";
  }catch(err){status.textContent=err.message;renderPublisherNames();}
  finally{btn.disabled=false;renderPublisherNames();}
}

document.addEventListener("DOMContentLoaded",()=>{
  document.querySelector("#loadPublishers").addEventListener("click",loadPublisherNames);
  document.querySelector("#savePublishers").addEventListener("click",savePublisherNames);
  document.querySelector("#publisherSearch").addEventListener("input",()=>{
    publisherEditor.visible=50;
    renderPublisherNames();
  });
  document.querySelector("#publisherLoadMore").addEventListener("click",()=>{
    publisherEditor.visible+=50;
    renderPublisherNames();
  });
  document.querySelector("#publisherRows").addEventListener("input",event=>{
    const index=event.target.dataset.publisherIndex;
    if(index===undefined||!publisherEditor.items[Number(index)])return;
    publisherEditor.items[Number(index)].draft=event.target.value;
    // Do not re-render inputs during typing: preserve focus and cursor position.
    const row=event.target.closest("tr");
    if(row)row.classList.toggle("publisher-row-changed",
      event.target.value.trim()!==publisherEditor.items[Number(index)].display_name);
    const rowSave=row?.querySelector("[data-save-publisher]");
    if(rowSave)rowSave.disabled=event.target.value.trim()===publisherEditor.items[Number(index)].display_name;
    const count=changedPublisherItems().length;
    document.querySelector("#savePublishers").disabled=!count;
    const q=document.querySelector("#publisherEditorSummary");
    q.textContent=publisherEditor.items.length+"개 언론사 · 수정 대기 "+count+"개";
  });
  document.querySelector("#publisherRows").addEventListener("click",event=>{
    const saveButton=event.target.closest("[data-save-publisher]");
    if(saveButton){
      savePublisherRow(Number(saveButton.dataset.savePublisher));
      return;
    }
    const button=event.target.closest("[data-reset-index]");
    if(!button)return;
    const row=publisherEditor.items[Number(button.dataset.resetIndex)];
    if(!row)return;
    row.draft=row.default_name;
    renderPublisherNames();
  });
});
