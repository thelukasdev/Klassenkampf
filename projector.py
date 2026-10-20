"""Explicit, revocable room projection; public payloads never contain hidden player views."""
import secrets


class Projector:
    def __init__(self,room):
        self.room=room;self.token=None;self.mode='ranking';self.match_id=None;self.revision=0

    def select(self,value):
        if not getattr(self.room,'room_active',True):raise ValueError('Sitzung bereits beendet.')
        if value=='off':
            self.token=None;self.match_id=None;self.mode='ranking'
            return 'Beamer-Übertragung beendet.'
        if value=='ranking':mode='ranking';match_id=None
        elif isinstance(value,str) and value.startswith('match:') and value[6:].isdigit():
            match_id=int(value[6:]);match=self.room.matches.get(match_id)
            if not match or match.finished:raise ValueError('Diese Partie läuft nicht mehr.')
            if match.game.per_view:raise ValueError('Spiele mit verdeckten Informationen können nicht übertragen werden.')
            mode='match'
        else:raise ValueError('Bitte Rangliste oder eine laufende Partie auswählen.')
        self.mode=mode;self.match_id=match_id;self.revision+=1
        if not self.token:self.token=secrets.token_urlsafe(48)
        return 'Beamer zeigt die Rangliste.' if mode=='ranking' else 'Live-Spiel wird auf dem Beamer übertragen.'

    def overview(self):
        return {'enabled':bool(self.token),'selection':'match:'+str(self.match_id) if self.mode=='match' else 'ranking',
                'url':'/beamer#'+self.token if self.token else None}

    def payload(self):
        if not self.token or not getattr(self.room,'room_active',True):return None
        players=sorted((p for p in self.room.players.values() if p.key not in self.room.banned),key=lambda p:(-p.credits,p.nick.casefold()))
        result={'session':getattr(self.room,'room_name','Klassenkampf'),'mode':'ranking','state':'ranking','revision':self.revision,
                'ranking':[{'name':p.nick,'credits':p.credits} for p in players[:20]],
                'online':sum(p.online for p in self.room.players.values()),'matches':len(self.room.matches)}
        if self.mode=='match':
            match=self.room.matches.get(self.match_id)
            if match and not match.finished and not match.game.per_view:
                frame=match.last_frame
                # Defense in depth: only the shared view may cross the projection boundary.
                public_frame={'t':frame['t'],'views':{'0':frame['views']['0']}} if frame and '0' in frame.get('views',{}) else None
                result.update(mode='match',state='paused' if match.is_paused else 'live',game=match.gid,name=match.name,
                    players=[p.nick for p in match.players],frame=public_frame,
                    reconnecting=[p.nick for p in match.disconnected])
            else:result['state']='finished'
        return result


def find(server,token):
    if not isinstance(token,str) or len(token)!=64:return None
    rooms=list(server.session_hub.rooms.values()) if server.session_hub else [server]
    return next((r.projector for r in rooms if r.projector.token and secrets.compare_digest(token.encode(),r.projector.token.encode())),None)
