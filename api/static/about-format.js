"use strict";
/* Toggle one selected inline style without generating nested duplicate tags. */
function toggleAboutFormatting(text,start,end,tag){
  if(typeof text!=="string"||!["큰글씨","작은글씨","굵게"].includes(tag)||
     !Number.isInteger(start)||!Number.isInteger(end)||start<0||end>text.length||start>=end){
    return null;
  }
  const opening="["+tag+"]",closing="[/"+tag+"]";
  const selected=text.slice(start,end);
  // Handle users who selected the entire previously formatted token.
  if(selected.startsWith(opening)&&selected.endsWith(closing)){
    const inner=selected.slice(opening.length,-closing.length);
    if(!inner)return null;
    return {text:text.slice(0,start)+inner+text.slice(end),
      start,end:start+inner.length,applied:false};
  }
  // Normal second click: textarea selection is kept on the unmarked words.
  if(start>=opening.length&&text.slice(start-opening.length,start)===opening&&
     text.slice(end,end+closing.length)===closing){
    const newStart=start-opening.length;
    return {text:text.slice(0,newStart)+selected+text.slice(end+closing.length),
      start:newStart,end:newStart+selected.length,applied:false};
  }
  // If only part of the already styled phrase is selected, split that one style
  // so the unselected words retain their formatting.
  const spans=[],stack=[],tokens=/\[(\/?)(큰글씨|작은글씨|굵게)\]/g;
  let token;
  while((token=tokens.exec(text))!==null){
    if(!token[1]){
      stack.push({tag:token[2],start:token.index,contentStart:tokens.lastIndex});
    }else if(stack.length&&stack[stack.length-1].tag===token[2]){
      const open=stack.pop();
      spans.push({...open,contentEnd:token.index,end:tokens.lastIndex});
    }else{
      // Avoid making an invalid markup structure worse.
      return null;
    }
  }
  const covering=spans.filter(s=>s.tag===tag&&start>=s.contentStart&&end<=s.contentEnd)
    .sort((a,b)=>(a.end-a.start)-(b.end-b.start))[0];
  if(covering){
    const left=text.slice(covering.contentStart,start);
    const right=text.slice(end,covering.contentEnd);
    // Do not split around another style's opening/closing tag.
    if(/\[(?:\/)?(?:큰글씨|작은글씨|굵게)\]/.test(left+right))return null;
    const before=left?opening+left+closing:"";
    const after=right?opening+right+closing:"";
    const content=before+selected+after;
    const newStart=covering.start+before.length;
    return {text:text.slice(0,covering.start)+content+text.slice(covering.end),
      start:newStart,end:newStart+selected.length,applied:false};
  }
  // A new application: leave only the actual words selected, not the tags.
  if(/\[(?:\/)?(?:큰글씨|작은글씨|굵게)\]/.test(selected))return null;
  return {text:text.slice(0,start)+opening+selected+closing+text.slice(end),
    start:start+opening.length,end:end+opening.length,applied:true};
}
if(typeof module!=="undefined"&&module.exports){
  module.exports={toggleAboutFormatting};
}
