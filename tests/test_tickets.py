import json
import asyncio
import os
import secrets
import time
import unittest
from unittest.mock import patch
import test_player_accounts as base
from retention import cleanup,DAY


class TicketTests(unittest.IsolatedAsyncioTestCase):
    http=base.PlayerAccountTests.http
    body=base.PlayerAccountTests.body
    cookie=base.PlayerAccountTests.cookie
    preauth=base.PlayerAccountTests.preauth
    signup=base.PlayerAccountTests.signup
    admin_headers=base.PlayerAccountTests.admin_headers

    async def asyncSetUp(self):
        await base.PlayerAccountTests.asyncSetUp(self)
        self.reports=self.app.web_admin.reports
        self.notification=patch.object(self.reports,'send_notification');self.mailer=self.notification.start()
        self.player,*_=await self.signup()
        self.owner,_=self.admin_headers()
        r=await self.http('/auth/report/csrf',extra_headers=self.player)
        self.h={**self.player,'X-CSRF-Token':self.body(r)['csrf'],'Cookie':self.player['Cookie']+'; '+self.reports.COOKIE+'='+self.cookie(r,self.reports.COOKIE)}
        r=await self.http('/auth/report/submit',method='POST',extra_headers=self.h,data={'page':'/account','description':'Meine Partie startet leider nicht.'})
        self.ref=self.body(r)['reference']

    async def asyncTearDown(self):
        self.notification.stop();await base.PlayerAccountTests.asyncTearDown(self)

    def command(self,message='Bitte versuche es erneut.'):
        return {'action':'reply-report','value':self.ref,'message':message,'request_id':secrets.token_hex(16)}

    async def reply(self,command=None):
        r=await self.http('/api/admin/action',method='POST',extra_headers=self.owner,data=command or self.command())
        self.assertIn(b'200',r);return self.body(r)['result']

    async def test_admin_reply_mails_verified_owner_and_player_can_continue(self):
        result=await self.reply();self.assertEqual(result['mail_status'],'sent')
        self.assertEqual(self.mailer.call_args.args,('owner@example.org',self.ref,'Bitte versuche es erneut.'))
        d=self.body(await self.http('/auth/report/ticket/'+self.ref,extra_headers=self.h))
        self.assertEqual(d['messages'][0]['kind'],'admin');self.assertNotIn('mail_status',d['messages'][0]);self.assertIsNone(d['ticket']['owner'])
        r=await self.http('/auth/report/reply',method='POST',extra_headers=self.h,data={'reference':self.ref,'message':'Jetzt klappt es, danke!','request_id':secrets.token_hex(16)})
        self.assertIn(b'200',r);self.assertEqual(self.mailer.call_count,1)
        d=self.body(await self.http('/api/admin/report?reference='+self.ref,extra_headers=self.owner))
        self.assertEqual([m['kind'] for m in d['messages']],['admin','player'])
        self.assertEqual(d['ticket']['owner'],'player:owner@example.org')
        mine=self.body(await self.http('/auth/report/mine',extra_headers=self.h))
        self.assertEqual(mine['tickets'][0]['reference'],self.ref)

    async def test_ticket_isolation_roles_csrf_and_stale_login(self):
        other,*_=await self.signup('other@example.org');guide,_=self.admin_headers('guide')
        for h in (other,guide):
            self.assertIn(b'403',await self.http('/auth/report/ticket/'+self.ref,extra_headers=h))
        self.assertIn(b'401',await self.http('/auth/report/ticket/'+self.ref))
        self.assertIn(b'403',await self.http('/api/player/report?reference='+self.ref,extra_headers=other))
        self.assertIn(b'403',await self.http('/api/admin/report?reference='+self.ref,extra_headers=guide))
        for headers in (self.player,{**self.h,'Origin':'https://evil.example'}):
            self.assertIn(b'403',await self.http('/auth/report/reply',method='POST',extra_headers=headers,data={'reference':self.ref,'message':'bad','request_id':secrets.token_hex(16)}))
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=self.player,data=self.command()))
        self.assertIn(b'403',await self.http('/api/admin/action',method='POST',extra_headers=guide,data=self.command()))
        with self.auth.store.connect() as db:db.execute("DELETE FROM sessions WHERE email='player:owner@example.org'")
        self.assertIn(b'401',await self.http('/auth/report/ticket/'+self.ref,extra_headers=self.h))

    async def test_mail_failure_is_saved_and_retry_does_not_duplicate_messages(self):
        self.mailer.side_effect=OSError('smtp unavailable')
        command=self.command();result=await self.reply(command)
        self.assertEqual(result['mail_status'],'failed')
        await self.reply(command);self.assertEqual(self.mailer.call_count,1)
        self.mailer.side_effect=None
        retry={'action':'retry-report-email','value':self.ref,'message_id':result['message_id']}
        for _ in range(2):self.assertIn(b'200',await self.http('/api/admin/action',method='POST',extra_headers=self.owner,data=retry))
        self.assertEqual(self.mailer.call_count,2)
        with self.auth.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM report_messages').fetchone()[0],1)
        # A queued SMTP job must not be claimed twice, even past the stale-claim deadline.
        actor=self.auth.store.session(self.auth.store.new_session('owner@example.org'))
        self.auth.mail_slots=asyncio.Semaphore(0)
        command=self.command('Noch eine Antwort')
        task=asyncio.create_task(self.reports.reply(actor,self.ref,command['message'],command['request_id']))
        try:
            for _ in range(100):
                if self.reports.sending:break
                await asyncio.sleep(.01)
            mid=next(iter(self.reports.sending))
            with self.auth.store.connect() as db:db.execute('UPDATE report_messages SET mail_attempt=1 WHERE id=?',(mid,))
            self.assertEqual(await self.reports.notify(actor,self.ref,mid),'sending')
            self.auth.mail_slots.release();await task
            self.assertEqual(self.mailer.call_count,3)
        finally:
            if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)


    async def test_legacy_reports_have_no_invented_recipient_and_input_limits(self):
        with self.auth.store.connect() as db:db.execute('UPDATE issue_reports SET owner=NULL WHERE reference=?',(self.ref,))
        self.assertFalse(self.body(await self.http('/api/admin/report?reference='+self.ref,extra_headers=self.owner))['ticket']['replyable'])
        self.assertIn(b'400',await self.http('/api/admin/action',method='POST',extra_headers=self.owner,data=self.command()))
        self.mailer.assert_not_called()
        with self.auth.store.connect() as db:db.execute("UPDATE issue_reports SET owner='player:owner@example.org' WHERE reference=?",(self.ref,))
        for text in ('','x'*2001):
            self.assertIn(b'400',await self.http('/api/admin/action',method='POST',extra_headers=self.owner,data=self.command(text)))

    async def test_reply_reopens_and_retention_deletes_entire_history(self):
        actor=self.auth.store.session(self.auth.store.new_session('owner@example.org'))
        self.reports.resolve(actor,self.ref,True)
        await self.reply()
        with self.auth.store.connect() as db:
            row=db.execute('SELECT * FROM issue_reports WHERE reference=?',(self.ref,)).fetchone()
            self.assertFalse(row['resolved']);self.assertIsNone(row['resolved_at'])
            now=int(time.time());db.execute('UPDATE issue_reports SET created=?',(now-100*DAY,))
        cleanup(self.app,now)
        self.assertTrue(self.reports.ticket(actor,self.ref))
        cleanup(self.app,now+91*DAY)
        with self.auth.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM issue_reports').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM report_messages').fetchone()[0],0)

    async def test_account_deletion_removes_tickets_and_messages(self):
        await self.reply()
        r=await self.http('/api/admin/action',method='POST',extra_headers=self.owner,data={'action':'delete-player-account','value':'owner@example.org'})
        self.assertIn(b'200',r)
        with self.auth.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM issue_reports').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM report_messages').fetchone()[0],0)

    async def test_paginated_history_and_plain_text_mail_with_ticket_link(self):
        with self.auth.store.connect() as db:
            rid=db.execute('SELECT id FROM issue_reports WHERE reference=?',(self.ref,)).fetchone()[0]
            for n in range(105):db.execute("INSERT INTO report_messages(report_id,author,kind,body,created,request_id,mail_status) VALUES(?,'owner','admin',?,0,?,'sent')",(rid,str(n),str(n)))
        first=self.body(await self.http('/api/admin/report?reference='+self.ref,extra_headers=self.owner))
        second=self.body(await self.http('/api/admin/report?reference='+self.ref+'&before='+str(first['next']),extra_headers=self.owner))
        self.assertEqual(len(first['messages']),100);self.assertEqual(len(second['messages']),5)
        self.assertEqual(len({m['id'] for m in first['messages']+second['messages']}),105)
        self.notification.stop()
        try:
            with patch.dict(os.environ,{'SMTP_PORT':'465'}),patch('reports.smtplib.SMTP_SSL') as smtp:
                self.reports.send_notification('owner@example.org',self.ref,'Hallo <script>test</script>')
                msg=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
                self.assertEqual(msg['To'],'owner@example.org');self.assertIn('/tickets/'+self.ref,msg.get_content())
                self.assertEqual(msg.get_content_type(),'text/plain')
        finally:self.notification.start()
