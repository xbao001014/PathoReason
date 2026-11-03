"""Read native metadata to label terminal history; original text/tools/budgets stay untouched."""
import hashlib,json
from .activity import tool_summary
from .persistence import ACTIVE,Conflict,encoded

async def refresh_process(store,runtime,tid):
    row=store.turn(tid)
    if row['status'] in ACTIVE:raise Conflict('process_turn_active')
    conv=store.conversation(row['conversation_id'])
    if not conv['native_session']:raise Conflict('process_native_session_missing')
    native=await runtime.messages(conv['native_session'],conv['directory'])
    matching={}
    for message in native:
        info=message.get('info') or {}
        if info.get('role')=='assistant' and info.get('parentID')==row['native_message_id']:
            for part in message.get('parts',[]):
                if part.get('type')=='tool':matching[part['id']]=tool_summary(part)
    original=json.loads(row['tools']);enriched=[]
    for tool in original:
        found=matching.get(tool['id'])
        if not found or found['name']!=tool['name']:raise Conflict('process_source_incomplete')
        enriched.append({**tool,**{k:found[k] for k in ('summary','kind','repeat_key','targets','target_count','operation','working_directory')}})
    digest=hashlib.sha256(row['tools'].encode()).hexdigest()
    with store.connect(True) as db:
        store.check_conversation(db,row['conversation_id'])
        latest=db.execute('SELECT status,tools FROM turns WHERE id=?',(tid,)).fetchone()
        if latest['status'] in ACTIVE or latest['tools']!=row['tools']:raise Conflict('process_source_changed')
        db.execute('INSERT INTO turn_process_projection VALUES(?,?,?) ON CONFLICT(turn_id) DO UPDATE SET source_sha256=excluded.source_sha256,document=excluded.document',(tid,digest,encoded(enriched)))
    return {'turn_id':tid,'tool_count':len(enriched),'original_tools_sha256':digest,'original_records_unchanged':True}
