import asyncio
import json
import pytest
from pathoreason.activity import tool_summary
from pathoreason.api import ToolSummary
from pathoreason.tool_objects import command_objects, tool_objects
from pathoreason.process_projection import refresh_process
from test_p1_service import fixture, settled


def part(name, inputs):
    return {'id':'t','tool':name,'state':{'status':'completed','input':inputs,'output':'PRIVATE_OUTPUT','title':'PRIVATE_TITLE'}}


@pytest.mark.parametrize('name,action',[('write','write'),('read','read'),('edit','edit')])
def test_structured_file_reference_excludes_contents_and_private_fields(name,action):
    summary=tool_summary(part(name,{'filePath':'/workspace/scripts/train.py','content':'PRIVATE_CONTENT','grant':'PRIVATE_GRANT','oldString':'PRIVATE_OLD','newString':'PRIVATE_NEW'}))
    assert summary['targets']==[{'kind':'file','label':'/workspace/scripts/train.py','action':action}]
    assert summary['target_count']==1
    assert 'PRIVATE' not in json.dumps(summary)
    ToolSummary.model_validate(summary)


def test_patch_only_exports_paths_and_preserves_delete_and_move():
    patch='*** Begin Patch\n*** Add File: scripts/new.py\n+PRIVATE_BODY\n*** Update File: a.py\n*** Move to: b.py\n@@\n-PRIVATE_OLD\n+PRIVATE_NEW\n*** Delete File: old.py\n*** End Patch'
    summary=tool_summary(part('apply_patch',{'patchText':patch}))
    assert [(t['label'],t['action']) for t in summary['targets']]==[('scripts/new.py','write'),('a.py','edit'),('b.py','write'),('old.py','delete')]
    assert 'PRIVATE' not in json.dumps(summary)


def test_object_limit_is_explicit_and_duplicates_are_not_counted_twice():
    patch='\n'.join('*** Add File: files/'+str(i)+'.py' for i in range(15))+'\n*** Add File: files/0.py'
    summary=tool_summary(part('apply_patch',{'patchText':patch}))
    assert len(summary['targets'])==12 and summary['target_count']==15


@pytest.mark.parametrize('command,expected',[
    ('python scripts/train.py --config configs/test.yaml --token PRIVATE_TOKEN',[('scripts/train.py','run'),('configs/test.yaml','read')]),
    ('cat outputs/metrics.json && tail -n 20 logs/run.log',[('outputs/metrics.json','read'),('logs/run.log','read')]),
    ('echo PRIVATE_BODY > notes.txt',[('notes.txt','write')]),
    ('python -c \'from pathlib import Path; p=Path("scripts")/"train.py"; p.write_text("PRIVATE_CODE")\'',[('scripts/train.py','write')]),
    ('python - <<\'PY\'\nfrom pathlib import Path\nbase=Path("outputs")\np=base/"report.md"\np.write_text("PRIVATE_BODY")\nwith open("data.csv", "r") as f:\n    rows=f.read()\nPY\n',[('outputs/report.md','write'),('data.csv','read')]),
    ('python -c \'from pathlib import Path; Path("report.txt").open(mode="w")\'',[('report.txt','write')]),
    ('echo "python pretend.py"',[]),
    ('python -c \'print("PRIVATE_TOKEN")\'',[]),
    ('python -c \'def unused():\n open("unused.txt", "w")\'',[]),
    ('python -c \'from pathlib import Path; p=Path("old.txt"); p=unknown(); p.write_text("PRIVATE")\'',[]),
    ('bash -c "PRIVATE_COMMAND"',[]),
])
def test_shell_objects_follow_literal_operations_not_arbitrary_prose(command,expected):
    summary=tool_summary(part('bash',{'command':command,'workdir':'/workspace/project'}))
    assert [(t['label'],t['action']) for t in summary['targets']]==expected
    assert summary['working_directory']=='/workspace/project'
    assert 'PRIVATE' not in json.dumps(summary)
    ToolSummary.model_validate(summary)


@pytest.mark.parametrize('value',[None,{},[],42,'bad\nname.py','$(cat secret).py','file?token=PRIVATE'])
def test_malformed_or_dynamic_paths_do_not_escape(value):
    assert tool_objects('write',{'filePath':value})['targets']==[]


def test_known_mcp_operation_and_experiment_but_not_grant_or_reason():
    summary=tool_summary(part('pathoreason_dialogue_training',{'operation':'inspect','experiment_id':'exp_example','grant':'PRIVATE_GRANT','reason':'PRIVATE_REASON'}))
    assert summary['summary']=='检查训练实验'
    assert summary['operation']=='inspect'
    assert summary['targets'][0]['label']=='exp_example'
    assert 'PRIVATE' not in json.dumps(summary)
    assert tool_summary(part('pathoreason_dialogue_training',{'operation':{}}))['operation'] is None


def test_url_drops_userinfo_query_fragment_and_unknown_tools_drop_inputs():
    value=tool_objects('webfetch',{'url':'https://user:PRIVATE_PASSWORD@example.com/docs/page?key=PRIVATE_QUERY#PRIVATE_FRAGMENT'})
    assert value['targets']==[{'kind':'website','label':'https://example.com/docs/page','action':None}]
    assert tool_objects('unknown_tool',{'filePath':'PRIVATE_FIELD','operation':'PRIVATE_OPERATION'})['targets']==[]
    assert ToolSummary.model_validate({'id':'old','name':'read','status':'completed'}).targets==[]


def test_projection_adds_verified_objects_without_changing_originals(fixture):
    service,conv,request,runtime=fixture
    async def case():
        result=await service.submit(conv['id'],request);tid=result['turn']['id'];await settled(service,tid)
        original=service.store.turn(tid);before=service.store.timing(tid)
        messages=runtime.messages
        async def enriched(*args):
            native=await messages(*args)
            for msg in native:
                for item in msg.get('parts',[]):
                    if item.get('type')=='tool':item['state']['input']={'name':'results-explanation','grant':'PRIVATE_GRANT'}
            return native
        runtime.messages=enriched
        await refresh_process(service.store,runtime,tid)
        shown=service.view(original)['tools'][0]
        assert shown['targets'][0]['label']=='results-explanation'
        assert service.store.turn(tid)==original and service.store.timing(tid)==before
        assert 'PRIVATE_GRANT' not in json.dumps(shown)
    asyncio.run(case())


def test_search_exposes_file_scope_not_search_contents():
    glob=tool_objects('glob',{'pattern':'scripts/**/*.py','path':'/workspace'})
    assert glob['targets'][0]=={'kind':'pattern','label':'scripts/**/*.py','action':None}
    grep=tool_objects('grep',{'pattern':'PRIVATE_SEARCH','include':'*.py','path':'/workspace'})
    assert 'PRIVATE_SEARCH' not in json.dumps(grep)
    assert grep['targets'][0]['label']=='*.py'


def test_heredoc_data_and_dynamic_python_are_not_claimed_as_written_files():
    assert tool_objects('bash',{'command':'cat <<\'PY\'\nPath("fake.txt").write_text("PRIVATE")\nPY\n'})['targets']==[]
    assert tool_objects('bash',{'command':'python -c \'open(get_path(), "w")\''})['targets']==[]
