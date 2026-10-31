"""Auditable turn accounting: preserve legacy charges and union observed tool intervals."""
import json
import math
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field

MODE = 'tool_excluded_v1'

class TurnTiming(BaseModel):
    mode: Literal['legacy_wall', 'tool_excluded_v1']
    wall_seconds: float = Field(ge=0)
    budget_seconds: float = Field(ge=0)
    agent_seconds: float | None = Field(default=None, ge=0)
    tool_seconds: float | None = Field(default=None, ge=0)


def timestamp(value):
    return datetime.fromisoformat(value).timestamp()


def bounds(row, at=None):
    doc=json.loads(row['document'])
    start=timestamp(row['created_at'])
    end=timestamp(doc['finished_at']) if doc.get('finished_at') else (at if at is not None else datetime.now(timezone.utc).timestamp())
    return start,max(start,end)


def valid(value):
    return type(value) in (int,float) and math.isfinite(value)


def observe(document, messages, parent, start, at):
    spans=dict(document.get('spans',{}))
    for message in messages:
        info=message.get('info') or {}
        if info.get('role')!='assistant' or info.get('parentID')!=parent:continue
        for part in message.get('parts',[]):
            if part.get('type')!='tool' or not isinstance(part.get('id'),str):continue
            state=part.get('state') or {};timing=state.get('time') or {}
            begin,end=timing.get('start'),timing.get('end')
            # Native timestamps only. Unknown times remain charged, never invented as free time.
            if not valid(begin):continue
            begin=begin/1000
            if begin<start or begin>at:continue
            if valid(end):
                end=end/1000
                if end<begin or end>at:continue
            elif state.get('status') in ('running','pending'):
                end=at  # Proven occupied until this observation, not indefinitely after disconnect.
            else:continue
            spans[part['id']]=[begin,end]
    return {'mode':MODE,'spans':spans,'observed_at':at}


def seconds(row, document=None, at=None):
    start,end=bounds(row,at);wall=end-start
    finished=json.loads(row["document"]).get("finished_at")
    # Preserve the original datetime precision of terminal legacy charges.
    if finished:wall=max(0.,(datetime.fromisoformat(finished)-datetime.fromisoformat(row["created_at"])).total_seconds())
    if not document:return TurnTiming(mode='legacy_wall',wall_seconds=wall,budget_seconds=wall)
    intervals=[]
    for begin,finish in document.get('spans',{}).values():
        if valid(begin) and valid(finish) and finish>=begin:
            left,right=max(start,begin),min(end,finish)
            if right>left:intervals.append((left,right))
    total=0.;right=start
    for left,finish in sorted(intervals):
        if finish>right:total+=finish-max(left,right);right=finish
    total=min(wall,total)
    return TurnTiming(mode=MODE,wall_seconds=wall,budget_seconds=wall-total,agent_seconds=wall-total,tool_seconds=total)


def totals(rows, at=None):
    values=[seconds(r,json.loads(r['timing']) if r['timing'] else None,at) for r in rows]
    return {'wall_seconds':sum(v.wall_seconds for v in values),'budget_seconds':sum(v.budget_seconds for v in values),
            'tool_seconds':sum(v.tool_seconds or 0 for v in values),'legacy_seconds':sum(v.wall_seconds for v in values if v.mode=='legacy_wall')}
