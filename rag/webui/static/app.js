function openModal(){const m=document.getElementById('modal');m.classList.remove('hidden');m.classList.add('flex');}
function closeModal(){const m=document.getElementById('modal');m.classList.add('hidden');m.classList.remove('flex');}
function copyAnswer(id,btn){
  const el=document.getElementById(id); if(!el)return;
  const text=el.innerText;
  if(navigator.clipboard && window.isSecureContext){navigator.clipboard.writeText(text);}
  else{const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity=0;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');}catch(e){}document.body.removeChild(ta);}
  if(btn){const o=btn.innerText;btn.innerText='✓ 복사됨';setTimeout(()=>btn.innerText=o,1200);}
}
function afterSend(ev){
  // 성공(2xx)일 때만 입력창 비움 — 취소/실패 시 질문 텍스트 보존(다시 보내기 편하게)
  if(ev && ev.detail && ev.detail.successful){
    const b=document.getElementById('msgbox');if(b){b.value='';b.style.height='auto';}
  }
  scrollBottom();
}
function scrollBottom(){const m=document.getElementById('messages');if(m)m.scrollTop=m.scrollHeight;}
document.addEventListener('htmx:afterSwap',scrollBottom);
document.addEventListener('input',e=>{if(e.target.id==='msgbox'){e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,160)+'px';}});
document.addEventListener('keydown',e=>{
  if(e.target.id==='msgbox'&&e.key==='Enter'&&!e.shiftKey){
    e.preventDefault();
    if(isBusy())return;                    // 생성 중엔 Enter 재전송 금지
    document.getElementById('chatform').requestSubmit();
  }
});

// ---- 작업 중 화면 차단 오버레이 + 생성 취소 --------------------------------
// 오래 걸리는 요청 경로 → 표시 문구(그 외 짧은 요청은 오버레이 없음)
const BUSY_PATHS={
  '/chat':{msg:'답변 생성 중… (검색 → 리랭킹 → 생성)',cancel:true},
  '/log/upload':{msg:'명세 후보 검색 중…'},
  '/log/attach':{msg:'명세에서 규격 도출 → 로그 파싱 중…'},
  '/admin/upload':{msg:'문서 저장 + 인덱싱 중… 완료까지 잠시 기다려주세요'},
  '/admin/reindex':{msg:'인덱싱 중… 완료까지 잠시 기다려주세요'},
};
function isBusy(){const b=document.getElementById('busy');return b&&!b.classList.contains('hidden');}
function busyShow(msg,cancelable){
  const b=document.getElementById('busy');if(!b)return;
  document.getElementById('busy-msg').textContent=msg||'처리 중…';
  document.getElementById('busy-cancel').classList.toggle('hidden',!cancelable);
  b.classList.remove('hidden');b.classList.add('flex');
}
function busyHide(){
  const b=document.getElementById('busy');if(!b)return;
  b.classList.add('hidden');b.classList.remove('flex');
}
document.addEventListener('htmx:beforeRequest',e=>{
  const p=(e.detail.pathInfo&&(e.detail.pathInfo.requestPath||e.detail.pathInfo.path))||'';
  const path=p.split('?')[0];
  const cfg=BUSY_PATHS[path];
  if(cfg)busyShow(cfg.msg,!!cfg.cancel);
});
document.addEventListener('htmx:afterRequest',busyHide);
document.addEventListener('htmx:sendError',busyHide);
document.addEventListener('htmx:responseError',busyHide);
function cancelGen(){
  // 1) 서버에 취소 표시(진행 중 결과 폐기·대화 미저장) 2) 클라이언트 요청 중단 3) 오버레이 해제
  try{fetch('/chat/cancel',{method:'POST'});}catch(e){}
  const f=document.getElementById('chatform');
  if(f&&window.htmx)htmx.trigger(f,'htmx:abort');
  busyHide();
}
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
