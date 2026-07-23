function openModal(){const m=document.getElementById('modal');m.classList.remove('hidden');m.classList.add('flex');}
function closeModal(){const m=document.getElementById('modal');m.classList.add('hidden');m.classList.remove('flex');}
function copyAnswer(id,btn){
  const el=document.getElementById(id); if(!el)return;
  const text=el.innerText;
  if(navigator.clipboard && window.isSecureContext){navigator.clipboard.writeText(text);}
  else{const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity=0;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');}catch(e){}document.body.removeChild(ta);}
  if(btn){const o=btn.innerText;btn.innerText='✓ 복사됨';setTimeout(()=>btn.innerText=o,1200);}
}
function afterSend(){const b=document.getElementById('msgbox');if(b){b.value='';b.style.height='auto';}scrollBottom();}
function scrollBottom(){const m=document.getElementById('messages');if(m)m.scrollTop=m.scrollHeight;}
document.addEventListener('htmx:afterSwap',scrollBottom);
document.addEventListener('input',e=>{if(e.target.id==='msgbox'){e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,160)+'px';}});
document.addEventListener('keydown',e=>{if(e.target.id==='msgbox'&&e.key==='Enter'&&!e.shiftKey){e.preventDefault();document.getElementById('chatform').requestSubmit();}});
document.addEventListener('paste',e=>{
  if(e.target.id!=='msgbox')return;
  const items=(e.clipboardData||{}).items||[];
  for(const it of items){if(it.type&&it.type.startsWith('image/')){
    const blob=it.getAsFile();const url=URL.createObjectURL(blob);
    const box=document.getElementById('pasted');
    box.innerHTML="<div class='inline-block relative mb-2'><img src='"+url+"' class='h-20 rounded border border-gray-200'><span class='absolute -top-2 -right-2 bg-gray-700 text-white rounded-full w-5 h-5 text-xs flex items-center justify-center cursor-pointer' onclick=\"document.getElementById('pasted').innerHTML=''\">×</span><div class='text-[10px] text-gray-400'>클립보드 이미지 (HTTP에서도 붙여넣기 됨)</div></div>";
  }}
});
window.addEventListener('load',scrollBottom);

// 헤더 패널(문서 범위 / 로그 첨부) 토글
function togglePanel(id){const el=document.getElementById(id);if(el)el.classList.toggle('hidden');}

// 개선기록 폼: 클립보드 이미지 붙여넣기 → 숨은 필드(base64) + 미리보기 (HTTP에서도 동작)
// 개선기록 모달이 열려 있으면 포커스 위치와 무관하게 Ctrl+V 이미지를 잡는다.
// (기존 버그: 클릭 영역이 일반 div라 paste 이벤트가 안 옴 → 모달 열림 기준으로 전역 캡처)
document.addEventListener('paste',e=>{
  const form=document.getElementById('fbform');
  const modal=document.getElementById('modal');
  if(!form||!modal||modal.classList.contains('hidden'))return;   // 개선기록 모달 열림일 때만
  if(e.target.id==='msgbox')return;                              // 채팅창은 자체 처리
  const items=(e.clipboardData||{}).items||[];
  for(const it of items){if(it.type&&it.type.startsWith('image/')){
    const blob=it.getAsFile();const fr=new FileReader();
    fr.onload=()=>{const h=document.getElementById('fbimg64');if(h)h.value=fr.result;
      const p=document.getElementById('fbimgprev');if(p)p.innerHTML="<img src='"+fr.result+"' class='max-w-xs rounded border border-gray-200'>";
      const z=document.getElementById('fbpaste');if(z)z.textContent='✅ 이미지가 첨부되었습니다 (다시 Ctrl+V로 교체 가능)';};
    fr.readAsDataURL(blob);e.preventDefault();return;
  }}
});
