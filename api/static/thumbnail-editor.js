/* Upload and activate a social-share image, using the existing admin password. */
const thumbnailApi="/api/admin/thumbnail";
const originalShareImage="/static/og-thumbnail-wide.jpg";
let localPreviewUrl=null;

function setThumbnailStatus(message){
  document.querySelector("#thumbnailStatus").textContent=message;
}
function setThumbnailMetaStatus(message){
  document.querySelector("#thumbnailMetaStatus").textContent=message;
}
function thumbnailMetaFields(){
  return {
    title:document.querySelector("#thumbnailMetaTitle").value.trim(),
    description:document.querySelector("#thumbnailMetaDescription").value.trim()
  };
}
function thumbnailPassword(){
  const password=document.querySelector("#password").value;
  if(!password){
    setThumbnailStatus("관리자 비밀번호를 먼저 입력해주세요.");
    return null;
  }
  return password;
}
function setPreview(src){
  const img=document.querySelector("#thumbnailPreview");
  img.src=src;
}
function releaseLocalPreview(){
  if(localPreviewUrl){
    URL.revokeObjectURL(localPreviewUrl);
    localPreviewUrl=null;
  }
}
async function thumbnailRequest(method,body){
  const password=thumbnailPassword();
  if(password===null)return null;
  const options={method,headers:{"X-Admin-Password":password},cache:"no-store"};
  if(body!==undefined){
    options.headers["Content-Type"]="application/json";
    options.body=JSON.stringify(body);
  }
  const res=await fetch(thumbnailApi,options);
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw Error(data.detail||"썸네일 설정에 실패했습니다.");
  return data;
}
async function loadCurrentThumbnail(){
  const button=document.querySelector("#thumbnailLoad");
  button.disabled=true;
  try{
    const result=await thumbnailRequest("GET");
    if(!result)return;
    releaseLocalPreview();
    setPreview(result.url);
    document.querySelector("#thumbnailMetaTitle").value=result.title||"취재를 종합하면";
    document.querySelector("#thumbnailMetaDescription").value=result.description||"";
    setThumbnailMetaStatus("현재 공유 제목과 설명을 불러왔습니다.");
    setThumbnailStatus(result.version
      ?"현재 적용 중인 썸네일을 불러왔습니다."
      :"기본 썸네일을 사용 중입니다.");
    document.querySelector("#thumbnailFile").value="";
    document.querySelector("#thumbnailSave").disabled=true;
  }catch(error){setThumbnailStatus(error.message);}
  finally{button.disabled=false;}
}
async function thumbnailRequestMetadata(payload){
  const password=thumbnailPassword();
  if(password===null)return null;
  const res=await fetch("/api/admin/thumbnail/metadata",{
    method:"PUT",cache:"no-store",
    headers:{"X-Admin-Password":password,"Content-Type":"application/json"},
    body:JSON.stringify(payload)
  });
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw Error(data.detail||"공유 문구 저장에 실패했습니다.");
  return data;
}
async function saveThumbnailMetadata(){
  if(!thumbnailPassword())return;
  const payload=thumbnailMetaFields();
  if(!payload.title||!payload.description){
    setThumbnailMetaStatus("공유 제목과 설명을 모두 입력해주세요.");
    return;
  }
  if(payload.title.length>100||payload.description.length>300){
    setThumbnailMetaStatus("제목은 100자, 설명은 300자를 넘을 수 없습니다.");
    return;
  }
  const button=document.querySelector("#thumbnailMetaSave");
  button.disabled=true;
  setThumbnailMetaStatus("공유 제목·설명을 저장하는 중…");
  try{
    const result=await thumbnailRequestMetadata(payload);
    if(!result)return;
    setThumbnailMetaStatus("공유 제목과 설명이 적용됐습니다. 카카오톡에서 캐시 갱신이 필요할 수 있습니다.");
  }catch(error){setThumbnailMetaStatus(error.message);}
  finally{button.disabled=false;}
}
function encodeImage(file){
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onerror=()=>reject(Error("이미지 파일을 읽을 수 없습니다."));
    reader.onload=()=>{
      const value=String(reader.result||"");
      const separator=value.indexOf(",");
      if(separator<0)reject(Error("이미지 인코딩에 실패했습니다."));
      else resolve(value.slice(separator+1));
    };
    reader.readAsDataURL(file);
  });
}
async function saveThumbnail(){
  const file=document.querySelector("#thumbnailFile").files?.[0];
  if(!file){setThumbnailStatus("새 이미지를 선택해주세요.");return;}
  if(file.size>5*1024*1024){setThumbnailStatus("5MB 이하의 이미지를 선택해주세요.");return;}
  if(!["image/jpeg","image/png","image/webp"].includes(file.type)){
    setThumbnailStatus("JPG, PNG, WEBP 파일만 지원합니다.");return;
  }
  if(!thumbnailPassword())return;
  const button=document.querySelector("#thumbnailSave");
  button.disabled=true;
  setThumbnailStatus("이미지를 변환하고 공유 썸네일을 변경하는 중…");
  try{
    const image_base64=await encodeImage(file);
    const result=await thumbnailRequest("PUT",{image_base64});
    if(!result)return;
    releaseLocalPreview();
    setPreview(result.url);
    document.querySelector("#thumbnailFile").value="";
    setThumbnailStatus("썸네일이 적용됐습니다. 1200×630 JPG "+
      Math.round(result.size_bytes/1024)+"KB · 이전 카카오톡 미리보기는 캐시 갱신이 필요할 수 있습니다.");
  }catch(error){
    setThumbnailStatus(error.message);
    button.disabled=false;
  }
}
async function resetThumbnail(){
  if(!thumbnailPassword())return;
  if(!confirm("관리자가 올린 이미지를 해제하고 기본 썸네일로 되돌릴까요?"))return;
  const button=document.querySelector("#thumbnailReset");
  button.disabled=true;
  try{
    const result=await thumbnailRequest("DELETE");
    if(!result)return;
    releaseLocalPreview();
    setPreview(result.url||originalShareImage);
    document.querySelector("#thumbnailFile").value="";
    document.querySelector("#thumbnailSave").disabled=true;
    setThumbnailStatus("기본 가로형 썸네일로 되돌렸습니다.");
  }catch(error){setThumbnailStatus(error.message);}
  finally{button.disabled=false;}
}
document.addEventListener("DOMContentLoaded",()=>{
  document.querySelector("#thumbnailLoad").addEventListener("click",loadCurrentThumbnail);
  document.querySelector("#thumbnailMetaSave").addEventListener("click",saveThumbnailMetadata);
  document.querySelector("#thumbnailSave").addEventListener("click",saveThumbnail);
  document.querySelector("#thumbnailReset").addEventListener("click",resetThumbnail);
  document.querySelector("#thumbnailFile").addEventListener("change",event=>{
    releaseLocalPreview();
    const file=event.target.files?.[0];
    const button=document.querySelector("#thumbnailSave");
    button.disabled=!file;
    if(!file)return;
    if(file.size>5*1024*1024){
      button.disabled=true;
      setThumbnailStatus("파일이 5MB를 초과합니다.");
      return;
    }
    localPreviewUrl=URL.createObjectURL(file);
    setPreview(localPreviewUrl);
    setThumbnailStatus("미리보기입니다. '썸네일 업로드·적용'을 눌러야 공개 페이지에 반영됩니다.");
  });
});
