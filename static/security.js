(() => {
 const $=id=>document.getElementById(id);let user=null;
 fetch('/api/player/me',{credentials:'same-origin',cache:'no-store'}).then(r=>r.json()).then(d=>{user=d.user;if(!user){location.replace('/login');return;}document.querySelectorAll('.report-link').forEach(a=>a.hidden=false);$('securitySubmit').disabled=false;$('deleteAccountSubmit').disabled=false;}).catch(()=>{$('securityError').textContent='Konto momentan nicht erreichbar.';$('securityError').hidden=false;});
 $('securityForm').onsubmit=async e=>{e.preventDefault();if(!user)return;$('securityError').hidden=true;if($('newPassword').value!==$('repeatPassword').value){$('securityError').textContent='Die Passwörter stimmen nicht überein.';$('securityError').hidden=false;return;}$('securitySubmit').disabled=true;try{const r=await fetch('/auth/player/change-password',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':user.csrf},body:JSON.stringify({current_password:$('currentPassword').value,password:$('newPassword').value})});const d=await r.json();if(!r.ok)throw Error(d.error||'Passwort konnte nicht geändert werden.');for(const id of ['currentPassword','newPassword','repeatPassword'])$(id).value='';$('securityForm').hidden=true;$('securitySuccess').hidden=false;$('deleteAccountSection').hidden=true;document.querySelectorAll('.report-link').forEach(a=>a.hidden=true);}catch(error){$('securityError').textContent=error.message;$('securityError').hidden=false;}finally{$('securitySubmit').disabled=false;}};
 $('deleteAccountForm').onsubmit=async event=>{
  event.preventDefault();if(!user)return;$('securityError').hidden=true;$('deleteAccountSubmit').disabled=true;
  try{
   const response=await fetch('/auth/player/delete-account',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':user.csrf},body:JSON.stringify({current_password:$('deletePassword').value,confirmation:$('deleteConfirmation').value})});
   const body=await response.json();if(!response.ok)throw Error(body.error||'Konto konnte nicht gelöscht werden.');
   $('deletePassword').value='';$('deleteConfirmation').value='';$('securityForm').hidden=true;$('deleteAccountSection').hidden=true;$('deleteSuccess').hidden=false;user=null;
   document.querySelectorAll('.report-link').forEach(a=>a.hidden=true);
  }catch(error){$('securityError').textContent=error.message;$('securityError').hidden=false;}finally{$('deleteAccountSubmit').disabled=false;}
 };
})();
