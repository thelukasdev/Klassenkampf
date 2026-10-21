(() => {
 'use strict';let pending=false;const $=id=>document.getElementById(id);
 async function refresh(){if(pending||document.hidden)return;pending=true;try{const r=await fetch('/auth/player/stats',{credentials:'same-origin',cache:'no-store'});if(!r.ok){$('personalStats').hidden=true;return;}const d=await r.json();$('statsPlayed').textContent=d.played;$('statsWins').textContent=d.wins;$('statsFavorite').textContent=d.favorite||'Noch offen';$('statsHint').textContent=d.played?d.losses+' Niederlagen · '+d.draws+' Unentschieden':'Deine nächsten Partien zählen hier.';$('personalStats').hidden=false;}catch{$('statsHint').textContent='Statistik momentan nicht erreichbar.';}finally{pending=false;}}
 refresh();setInterval(refresh,15000);document.addEventListener('visibilitychange',refresh);
})();
