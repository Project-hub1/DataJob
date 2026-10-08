const toastEl=document.getElementById('toast');
function toast(message){if(!toastEl)return;toastEl.textContent=message;toastEl.classList.add('show');clearTimeout(window.__toastTimer);window.__toastTimer=setTimeout(()=>toastEl.classList.remove('show'),2400)}

// Candidate Naukri-style profile menu
(()=>{
  const trigger=document.getElementById('profileMenuTrigger');
  const panel=document.getElementById('profileMenuPanel');
  if(!trigger||!panel)return;
  const close=()=>{panel.classList.remove('open');trigger.setAttribute('aria-expanded','false');panel.setAttribute('aria-hidden','true')};
  trigger.addEventListener('click',e=>{e.stopPropagation();const open=panel.classList.toggle('open');trigger.setAttribute('aria-expanded',String(open));panel.setAttribute('aria-hidden',String(!open))});
  panel.addEventListener('click',e=>e.stopPropagation());
  document.addEventListener('click',close);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
})();

document.addEventListener('click',async(e)=>{
  const menu=e.target.closest('#mobileMenu');
  if(menu){const nav=document.getElementById('navLinks');const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',open);return;}
  const close=e.target.closest('.flash-close');if(close){close.closest('.flash')?.remove();return;}
  const toggle=e.target.closest('.filter-toggle');if(toggle){document.querySelector('.filter-body')?.classList.toggle('open');return;}
  const btn=e.target.closest('.save-btn');if(!btn)return;
  const id=btn.dataset.jobId;btn.disabled=true;
  try{const r=await fetch(`/jobs/${id}/save`,{method:'POST',headers:{'X-CSRFToken':document.querySelector('meta[name="csrf-token"]')?.content||'','Accept':'application/json'}});const d=await r.json();if(r.status===401){window.location.href=`/login?next=${encodeURIComponent(location.pathname+location.search)}`;return}if(d.ok){btn.classList.toggle('saved',d.saved);btn.setAttribute('aria-pressed',String(d.saved));btn.textContent=d.saved?(btn.classList.contains('big')?'Saved':'Saved'):(btn.classList.contains('big')?'Save job':'Save');toast(d.saved?'Job saved':'Job removed from saved jobs')}else toast(d.message||'Unable to save job.')}catch(err){toast('Network error. Please try again.')}finally{btn.disabled=false;}
});

document.addEventListener('submit',(e)=>{const form=e.target;if(form.matches('.js-confirm')){const msg=form.dataset.confirm||'Are you sure?';if(!window.confirm(msg))e.preventDefault();}});
window.copyJobLink=async()=>{try{await navigator.clipboard.writeText(location.href);toast('Job link copied')}catch{toast('Copy failed — copy the URL from your browser')}};

// Phase 2: compact candidate activity center
(()=>{
  const trigger=document.getElementById('activityTrigger');
  const panel=document.getElementById('activityPanel');
  if(!trigger||!panel)return;
  const close=()=>{panel.classList.remove('open');trigger.setAttribute('aria-expanded','false');panel.setAttribute('aria-hidden','true')};
  trigger.addEventListener('click',e=>{e.stopPropagation();const open=panel.classList.toggle('open');trigger.setAttribute('aria-expanded',String(open));panel.setAttribute('aria-hidden',String(!open))});
  panel.addEventListener('click',e=>e.stopPropagation());
  document.addEventListener('click',close);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
})();

// Accessible show/hide password control used across authentication forms.
document.addEventListener('click',(e)=>{
  const toggle=e.target.closest('[data-password-toggle]');
  if(!toggle)return;
  const input=document.getElementById(toggle.dataset.passwordToggle);
  if(!input)return;
  const showing=input.type==='password';
  input.type=showing?'text':'password';
  toggle.textContent=showing?'Hide':'Show';
  toggle.setAttribute('aria-label',showing?'Hide password':'Show password');
  toggle.setAttribute('aria-pressed',String(showing));
});

window.submitReport=async function(event,form){
  event.preventDefault();
  const submit=form.querySelector('button[type="submit"]') || form.querySelector('.btn:not(.ghost)');
  if(submit){submit.disabled=true;submit.textContent='Submitting…';}
  try{
    const response=await fetch(form.action,{
      method:'POST',
      body:new FormData(form),
      headers:{'Accept':'application/json','X-Requested-With':'XMLHttpRequest'}
    });
    const data=await response.json().catch(()=>({ok:false,message:'Unexpected server response.'}));
    if(response.ok && data.ok){
      form.closest('dialog')?.close();
      form.reset();
      toast(data.message||'Report submitted.');
    }else{
      toast(data.message||'Unable to submit the report.');
    }
  }catch(error){
    toast('Network error. Please try again.');
  }finally{
    if(submit){submit.disabled=false;submit.textContent='Submit report';}
  }
};
