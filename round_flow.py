"""Room-local readiness, consensual rematches and four-player post-game votes."""
import math
import random
import secrets
import time
import games


class RoundFlow:
    def __init__(self,room):self.room=room;self.offers={};self.members={}

    @property
    def waiting(self):return self.room.rules['waiting_room'] and not self.room.rules['waiting_released']

    def summary(self):
        players=[p for p in self.room.players.values() if p.online]
        ready=sum(p.ready for p in players)
        return {'waiting':self.waiting,'online':len(players),'ready':ready,'can_release':self.waiting and len(players)>=2 and ready==len(players)}

    def release(self):
        if not self.summary()['can_release']:raise ValueError('Mindestens zwei Spieler müssen verbunden und alle bereit sein.')
        self.room.rules['waiting_released']=True;self.room.save()
        return 'Sitzung zum Spielen freigegeben.'

    def remove(self,oid):
        offer=self.offers.pop(oid,None)
        if offer:
            for p in offer['players']:
                if self.members.get(p.pid)==oid:self.members.pop(p.pid,None)
        return bool(offer)

    def drop(self,player):return self.remove(self.members.get(player.pid))

    def cancel_all(self):
        self.offers.clear();self.members.clear()

    def prune(self):
        changed=False
        for oid,offer in list(self.offers.items()):
            if offer['deadline']<=time.monotonic() or not getattr(self.room,'room_active',True) or any(not p.online or p.busy or p.key in self.room.banned for p in offer['players']) or any(g not in self.room.rules['enabled'] for g in offer['choices']):
                changed=self.remove(oid) or changed
        return changed

    def completed(self,match):
        players=list(match.players)
        if getattr(match,'followup_blocked',False) or self.waiting or not getattr(self.room,'room_active',True) or match.end_reason not in ('normal','leave'):return
        if any(getattr(p,'skip_offer_for',None)==match.id for p in players):return
        if len(players)<2 or len(players)>4 or any(not p.online or p.busy or p.key in self.room.banned for p in players):return
        if len(players)==4:
            if match.end_reason!='normal' or match.left:return
            choices=[g for g in self.room.rules['enabled'] if games.GAMES[g].max_players>=4]
            kind='vote'
        else:choices=[match.gid] if match.gid in self.room.rules['enabled'] else [];kind='rematch'
        if not choices:return
        for p in players:self.drop(p)
        oid=secrets.token_urlsafe(18)
        self.offers[oid]={'id':oid,'kind':kind,'players':players,'choices':choices,'votes':{},'deadline':time.monotonic()+(30 if kind=='vote' else 60)}
        for p in players:self.members[p.pid]=oid

    def view(self,player):
        self.prune();offer=self.offers.get(self.members.get(player.pid))
        result=self.summary();result['you_ready']=player.ready
        result['offer']=None
        if offer:
            result['offer']={'id':offer['id'],'kind':offer['kind'],'players':[p.nick for p in offer['players']],
                'total':len(offer['players']),'accepted':len(offer['votes']),'selected':offer['votes'].get(player.pid),
                'seconds':max(0,math.ceil(offer['deadline']-time.monotonic())),
                'choices':[{'id':g,'name':games.GAMES[g].name,'votes':sum(v==g for v in offer['votes'].values())} for g in offer['choices']]}
        return result

    async def handle(self,player,obj):
        self.prune();action=obj.get('t')
        if action=='ready':
            if not self.waiting or type(obj.get('ready')) is not bool:raise ValueError('Kein offener Warteraum oder ungültiger Bereitstatus.')
            if player.ready==obj['ready']:return
            player.ready=obj['ready']
        elif action=='round_leave':
            if player.match and player.match.finished:player.skip_offer_for=player.match.id
            self.drop(player)
        elif action=='round_vote':
            offer=self.offers.get(self.members.get(player.pid))
            if not offer or obj.get('id')!=offer['id']:raise ValueError('Diese Runde ist nicht mehr verfügbar.')
            if self.waiting or self.room.rules['paused']:raise ValueError('Die Sitzung ist noch nicht freigegeben oder pausiert.')
            gid=obj.get('game')
            if gid not in offer['choices'] or gid not in self.room.rules['enabled']:raise ValueError('Dieses Spiel steht nicht zur Wahl.')
            if offer['votes'].get(player.pid)==gid:return
            offer['votes'][player.pid]=gid
            if len(offer['votes'])==len(offer['players']):
                counts={g:sum(v==g for v in offer['votes'].values()) for g in offer['choices']}
                best=max(counts.values());chosen=random.choice([g for g,n in counts.items() if n==best])
                # Reserve all participants atomically before starting; no awaits until state is consumed.
                try:self.room.start_match(chosen,offer['players'])
                except ValueError:
                    offer['votes'].pop(player.pid,None)
                    await self.room.push_lobby()
                    raise
        await self.room.push_lobby()
