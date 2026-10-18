import asyncio
import time
import unittest
from types import SimpleNamespace
import test_server as base
from game_sessions import GameSessions

class HostIdleTests(unittest.IsolatedAsyncioTestCase):
 websocket=base.ServerTests.websocket
 receive=base.ServerTests.receive
 until=base.ServerTests.until
 send=base.ServerTests.send
 async def asyncSetUp(self):
  await base.ServerTests.asyncSetUp(self)
  self.hub=GameSessions(self.app);self.app.session_hub=self.hub
  with self.app.web_admin.store.connect() as db:db.execute("INSERT INTO admins VALUES('player:test@example.org',NULL,'host',0)")
  self.a=self.hub.create('Player room');self.room=self.hub.get(self.a['id']);self.hub.hosts.attach(self.a['id'],'player:test@example.org')
  with self.app.web_admin.store.connect() as db:self.started=db.execute('SELECT created FROM host_rooms WHERE room_id=?',(self.a['id'],)).fetchone()[0]
 async def asyncTearDown(self):
  self.room.joined_connections.clear()
  await base.ServerTests.asyncTearDown(self)
 def connect(self):
  c=SimpleNamespace(alive=True,authed=True,writer=SimpleNamespace(is_closing=lambda:False))
  # Namespace is not hashable; a lightweight object is enough for online tracking.
  class C:pass
  conn=C();conn.alive=True;conn.authed=True;conn.writer=c.writer
  self.room.joined_connections.add(conn);return conn
 async def test_unused_closes_after_five_minutes_admin_rooms_stay(self):
  admin=self.hub.create('Admin room')
  await self.hub.hosts.sweep(self.started+299);self.assertTrue(self.room.room_active)
  await self.hub.hosts.sweep(self.started+300);self.assertFalse(self.room.room_active);self.assertTrue(self.hub.get(admin['id']).room_active)
 async def test_empty_grace_reconnect_and_closure(self):
  conn=self.connect();self.hub.hosts.observe(self.a['id'],self.started+10)
  await self.hub.hosts.sweep(self.started+1000);self.assertTrue(self.room.room_active)
  self.room.joined_connections.clear();self.hub.hosts.observe(self.a['id'],self.started+1001)
  await self.hub.hosts.sweep(self.started+1060);self.assertTrue(self.room.room_active)
  conn=self.connect();self.hub.hosts.observe(self.a['id'],self.started+1060)
  self.room.joined_connections.clear();self.hub.hosts.observe(self.a['id'],self.started+1100)
  await self.hub.hosts.sweep(self.started+1160);self.assertFalse(self.room.room_active)
 async def test_deadline_survives_policy_reload(self):
  self.connect();self.hub.hosts.observe(self.a['id'],self.started+1)
  self.room.joined_connections.clear();self.hub.hosts.observe(self.a['id'],self.started+2)
  from host_sessions import HostSessions
  self.hub.hosts=HostSessions(self.hub)
  await self.hub.hosts.sweep(self.started+62);self.assertFalse(self.room.room_active)
 async def test_existing_multiple_sessions_are_reduced_to_one(self):
  other=self.hub.create('Other');self.hub.hosts.attach(other['id'],'player:test@example.org')
  self.connect();await self.hub.hosts.sweep(self.started+10)
  self.assertTrue(self.room.room_active);self.assertFalse(self.hub.get(other['id']).room_active)

 async def test_real_connection_and_disconnect_update_deadline(self):
  reader,writer,_=await self.websocket();await self.until(reader,'welcome')
  await self.send(writer,{'t':'login','code':self.a['code']});await self.until(reader,'login_ok')
  with self.app.web_admin.store.connect() as db:
   row=db.execute('SELECT * FROM host_rooms WHERE room_id=?',(self.a['id'],)).fetchone()
  self.assertEqual(row['joined'],1);self.assertIsNone(row['empty_since'])
  writer.close();await writer.wait_closed();await asyncio.sleep(.1)
  with self.app.web_admin.store.connect() as db:row=db.execute('SELECT * FROM host_rooms WHERE room_id=?',(self.a['id'],)).fetchone()
  self.assertIsNotNone(row['empty_since'])
  await self.hub.hosts.sweep(row['empty_since']+60);self.assertFalse(self.room.room_active)
