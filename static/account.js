(() => {
  const $=id=>document.getElementById(id);let csrf='',register=location.hash==='#register',busy=false;
  function mode(value){register=value;$('forgotPassword').hidden=value;$('chooseLogin').classList.toggle('active',!value);$('chooseRegister').classList.toggle('active',value);$('accountSubmit').textContent=value?'Konto erstellen':'Anmelden';$('accountPassword').autocomplete=value?'new-password':'current-password';$('passwordHelp').hidden=!value;$('accountError').hidden=true;}
  async function post(route,data){const r=await fetch('/auth/player/'+route,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});const result=await r.json();if(!r.ok)throw Error(result.error||'Anfrage fehlgeschlagen.');return result;}
  function fail(error){$('accountError').textContent=error.message;$('accountError').hidden=false;}
  $('chooseLogin').onclick=()=>mode(false);$('chooseRegister').onclick=()=>mode(true);$('restartLogin').onclick=()=>location.reload();
  $('accountForm').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;$('accountSubmit').disabled=true;$('accountError').hidden=true;
    try{await post(register?'register':'login',{email:$('accountEmail').value,password:$('accountPassword').value});$('accountPassword').value='';$('accountTabs').hidden=true;$('accountForm').hidden=true;$('emailStep').hidden=false;$('forgotPassword').hidden=true;$('codeRecipient').textContent='Code gesendet an '+$('accountEmail').value;$('emailCode').focus();}catch(error){fail(error);}finally{busy=false;$('accountSubmit').disabled=false;}
  };
  $('codeForm').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;$('codeSubmit').disabled=true;$('accountError').hidden=true;
    try{await post('verify',{code:$('emailCode').value});location.replace('/account');}catch(error){fail(error);}finally{busy=false;$('codeSubmit').disabled=false;}
  };
  $('forgotPassword').onclick=()=>{for(const id of ['accountTabs','accountForm','forgotPassword'])$(id).hidden=true;$('resetStep').hidden=false;$('resetBack').hidden=false;$('resetEmail').value=$('accountEmail').value;$('accountError').hidden=true;$('resetEmail').focus();};
  $('resetBack').onclick=()=>location.replace('/login');
  async function resetSubmit(e,button,action){e.preventDefault();if(busy)return;busy=true;$(button).disabled=true;$('accountError').hidden=true;try{await action();}catch(error){fail(error);}finally{busy=false;$(button).disabled=false;}}
  $('resetRequestForm').onsubmit=e=>resetSubmit(e,'resetRequestSubmit',async()=>{await post('reset-request',{email:$('resetEmail').value});$('resetStep').hidden=true;$('resetConfirm').hidden=false;$('resetCode').focus();});
  $('resetConfirmForm').onsubmit=e=>resetSubmit(e,'resetConfirmSubmit',async()=>{if($('resetPassword').value!==$('resetPasswordAgain').value)throw Error('Die Passwörter stimmen nicht überein.');await post('reset-confirm',{code:$('resetCode').value,password:$('resetPassword').value});$('resetPassword').value='';$('resetPasswordAgain').value='';$('resetConfirm').hidden=true;$('resetSuccess').hidden=false;});
  mode(register);
  fetch('/auth/player/csrf',{credentials:'same-origin'}).then(r=>{if(!r.ok)throw Error('Anmeldung nicht erreichbar.');return r.json();}).then(data=>{csrf=data.csrf;if(!data.ready){$('accountSubmit').disabled=true;fail(Error('E-Mail-Anmeldung momentan nicht verfügbar.'));}}).catch(fail);
})();
