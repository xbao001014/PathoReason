import asyncio
import json
import socket
import sqlite3
import pytest
from pathoreason.native_refresh import maintenance_directories,refresh_idle_instances


class Runtime:
    def __init__(self, skill, *, busy=None, permission=None, stale=False, connected=True):
        self.skill=skill;self.busy=busy;self.permission=permission;self.stale=stale;self.connected=connected;self.disposed=[]
    async def call(self, method, path, directory):
        if path=='/session/status':return {'session':{'type':'busy'}} if directory==self.busy else {}
        if path=='/permission':return [{}] if directory==self.permission else []
        if path=='/instance/dispose':self.disposed.append(directory);return True
        if path=='/skill':return [{'name':'example','location':str(self.skill),'content':'old' if self.stale else 'new instructions'}]
        if path=='/mcp':return {'pathoreason_dialogue':{'status':'connected' if self.connected else 'failed'}}


@pytest.mark.parametrize('block',['busy','permission'])
def test_checks_all_instances_before_disposal(tmp_path,block):
    runtime=Runtime(tmp_path/'SKILL.md',**{block:'second'})
    with pytest.raises(RuntimeError,match='busy|pending'):
        asyncio.run(refresh_idle_instances(runtime,['first','second'],{},lambda r:None))
    assert not runtime.disposed


@pytest.mark.parametrize('stale,connected',[(False,True),(True,True),(False,False)])
def test_refresh_verifies_actual_content_and_keeps_partial_receipt(tmp_path,stale,connected):
    skill=tmp_path/'SKILL.md';skill.write_text('---\nname: example\n---\nnew instructions\n')
    runtime=Runtime(skill,stale=stale,connected=connected);receipts=[]
    operation=refresh_idle_instances(runtime,['first'],{'example':skill},receipts.append)
    if stale or not connected:
        with pytest.raises(RuntimeError,match='mismatch|disconnected'):asyncio.run(operation)
        assert receipts==[{'directory':'first','disposed':True,'verified':False}]
    else:
        result=asyncio.run(operation);assert result[0]['verified'];assert len(receipts)==2
    assert runtime.disposed==['first']


def test_refuses_live_application_before_reading_database(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen()
        with pytest.raises(RuntimeError,match='requires_app_offline'):
            maintenance_directories(tmp_path,listener.getsockname()[1])


@pytest.mark.parametrize('pending',['turn','context','goal',None])
def test_offline_refresh_checks_durable_work(tmp_path,monkeypatch,pending):
    def offline(*args,**kwargs):raise ConnectionRefusedError()
    monkeypatch.setattr(socket,'create_connection',offline)
    (tmp_path/'state').mkdir()
    with sqlite3.connect(tmp_path/'state/pathoreason.sqlite3') as db:
        db.executescript('CREATE TABLE turns(status);CREATE TABLE context_operations(status);CREATE TABLE research_goals(document);CREATE TABLE conversations(directory,native_session);')
        db.execute('INSERT INTO conversations VALUES(?,?)',('/project','session'))
        if pending=='turn':db.execute("INSERT INTO turns VALUES('recovery_required')")
        if pending=='context':db.execute("INSERT INTO context_operations VALUES('running')")
        if pending=='goal':db.execute('INSERT INTO research_goals VALUES(?)',(json.dumps({'state':'active'}),))
    if pending:
        with pytest.raises(RuntimeError,match='unresolved|active'):maintenance_directories(tmp_path,1)
    else:assert maintenance_directories(tmp_path,1)==['/project']
