"""Private JSON pipe worker: one process per playing session, one engine per match."""
import json
import sys
import games

def main():
    if sys.platform != 'win32':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (96*1024*1024,96*1024*1024))
    engines={}
    for line in sys.stdin:
        try:
            obj=json.loads(line); key=str(obj['id']); op=obj['op']
            if op=='create':
                if len(engines)>=16: raise ValueError('Worker capacity')
                engines[key]=games.create(obj['gid'],obj['n']); result={}
            elif op=='drop':
                engines.pop(key,None); result={}
            else:
                g=engines[key]
                for cmd in obj.get('commands',[]):
                    if cmd[0]=='input': g.set_input(cmd[1],cmd[2])
                    elif cmd[0]=='remove': g.remove_player(cmd[1])
                for _ in range(obj.get('ticks',1)): g.tick()
                result={'result':g.result,'snapshots':{str(i):g.snapshot(view=i) for i in range(1,g.n+1)} if g.per_view else {'0':g.snapshot()}}
            print(json.dumps({'ok':True,**result},separators=(',',':')),flush=True)
        except Exception:
            print(json.dumps({'ok':False}),flush=True)
if __name__=='__main__': main()
