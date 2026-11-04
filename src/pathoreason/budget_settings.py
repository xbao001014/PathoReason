"""User-controlled limits with append-only receipts; never reset consumption."""
import json
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .contracts import Identifier, canonical_digest
from .formal import StudyView, StudyBudget
from .goals import GoalView, turns_in_window
from .persistence import Conflict, encoded, now
from .timing import totals


class ProjectBudgetChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:int=Field(ge=0)
    max_turns:int=Field(ge=1,le=1000)
    max_wall_seconds:int=Field(ge=60,le=86400)


class GoalLimitChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    goal_id:Identifier
    expected_revision:int=Field(ge=0)
    max_turns:int=Field(ge=1,le=40)


class BudgetSettingsUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_key:Identifier
    project:ProjectBudgetChange|None=None
    goal:GoalLimitChange|None=None

    @model_validator(mode='after')
    def has_change(self):
        if self.project is None and self.goal is None:raise ValueError('budget_change_required')
        return self


class BudgetSettingsView(BaseModel):
    project:StudyView
    goal:GoalView|None=None
    history:list[dict]=Field(default_factory=list)


class BudgetSettings:
    def __init__(self,service):
        self.s=service
        with service.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS budget_changes(project_id TEXT NOT NULL REFERENCES projects(id),request_key TEXT NOT NULL,input_digest TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(project_id,request_key))')

    def view(self,cid):
        conv=self.s.formal.mode(cid)
        with self.s.store.connect() as db:
            history=[json.loads(r[0]) for r in db.execute('SELECT document FROM budget_changes WHERE project_id=? ORDER BY rowid DESC LIMIT 10',(conv['project_id'],))]
        return BudgetSettingsView(project=self.s.formal.view(conv['project_id']),goal=self.s.goals.view(cid),history=history)

    async def update(self,cid,body):
        async with self.s.lock:
            conv=self.s.store.conversation(cid,writable=True);pid=conv['project_id']
            digest=canonical_digest({'conversation_id':cid,**body.model_dump(mode='json')})
            with self.s.store.connect(True) as db:
                self.s.store.check_conversation(db,cid,writable=True)
                original=db.execute('SELECT document FROM formal_studies WHERE project_id=?',(pid,)).fetchone()
                if not original:raise Conflict('formal_study_required')
                prior=db.execute('SELECT input_digest FROM budget_changes WHERE project_id=? AND request_key=?',(pid,body.request_key)).fetchone()
                if prior:
                    if prior[0]!=digest:raise Conflict('idempotency_key_conflict')
                else:
                    latest=db.execute('SELECT revision,document FROM study_budget_revisions WHERE project_id=? ORDER BY revision DESC LIMIT 1',(pid,)).fetchone()
                    revision=latest['revision'] if latest else 0
                    budget=StudyBudget.model_validate(json.loads(latest['document'] if latest else original[0])['budget']).model_dump()
                    before=dict(budget)
                    rows=self.s.store.budget_rows(db,pid);usage=totals(rows)
                    if body.project:
                        if body.project.expected_revision!=revision:raise Conflict('budget_revision_conflict')
                        if body.project.max_turns<len(rows) or body.project.max_wall_seconds<usage['budget_seconds']:raise Conflict('budget_below_usage')
                        budget.update(max_turns=body.project.max_turns,max_wall_seconds=body.project.max_wall_seconds)
                    goal=self.s.goals._latest(db,cid)
                    goal_before=None
                    if body.goal:
                        if not goal or goal['id']!=body.goal.goal_id or goal.get('limit_revision',0)!=body.goal.expected_revision:raise Conflict('goal_limit_revision_conflict')
                        if goal['state'] in ('completed','cancelled'):raise Conflict('goal_already_terminal')
                        if body.goal.max_turns<turns_in_window(goal):raise Conflict('goal_limit_below_usage')
                        goal_before={'id':goal['id'],'max_turns':goal['max_turns'],'limit_revision':goal.get('limit_revision',0),'turns_used':goal['turns_used'],'turn_window':goal.get('turn_window')}
                        if goal['max_turns']!=body.goal.max_turns:
                            goal.update(max_turns=body.goal.max_turns,limit_revision=goal.get('limit_revision',0)+1,updated_at=now())
                            # Execution revision/grants remain valid for the in-flight turn.
                            db.execute('UPDATE research_goals SET document=? WHERE id=?',(encoded(goal),goal['id']))
                            db.execute('INSERT INTO goal_events(goal_id,document) VALUES(?,?)',(goal['id'],encoded({'at':now(),'event':'user_budget_limit','revision':goal['revision'],'snapshot':goal})))
                    if budget!=before:
                        revision+=1
                        db.execute('INSERT INTO study_budget_revisions VALUES(?,?,?)',(pid,revision,encoded({'budget':budget,'at':now(),'conversation_id':cid})))
                    # Budget exhaustion can become resumable, but saving never dispatches.
                    if budget!=before or body.goal:
                        for row in db.execute('SELECT document FROM research_goals WHERE project_id=?',(pid,)).fetchall():
                            candidate=json.loads(row[0])
                            if candidate['state']=='budget_exhausted' and turns_in_window(candidate)<candidate['max_turns'] and len(rows)<budget['max_turns'] and usage['budget_seconds']<budget['max_wall_seconds']:
                                candidate.update(state='paused',reason='budget_updated')
                                self.s.goals._save(db,candidate,'budget_available')
                    receipt={'at':now(),'conversation_id':cid,'project_before':before,'project_after':budget,'budget_revision':revision,'used_turns':len(rows),'used_budget_seconds':usage['budget_seconds'],'goal_before':goal_before,'goal_after':({'id':goal['id'],'max_turns':goal['max_turns'],'limit_revision':goal.get('limit_revision',0),'turn_window':goal.get('turn_window')} if body.goal else None)}
                    db.execute('INSERT INTO budget_changes VALUES(?,?,?,?)',(pid,body.request_key,digest,encoded(receipt)))
            return self.view(cid)
