(() => {
  const nav=document.getElementById('accountNav');if(!nav)return;
  fetch('/api/player/me',{credentials:'same-origin',cache:'no-store'}).then(r=>r.json()).then(data=>{
    if(!data.user)return;nav.replaceChildren();const account=document.createElement('a');account.href='/account';account.textContent='Meine Sitzungen';nav.append(account);
    const logout=document.createElement('a');logout.href='/';logout.textContent='Abmelden';logout.onclick=async e=>{e.preventDefault();const r=await fetch('/auth/player/logout',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':data.user.csrf},body:'{}'});if(r.ok)location.reload();};nav.append(logout);
  }).catch(()=>{});
})();
