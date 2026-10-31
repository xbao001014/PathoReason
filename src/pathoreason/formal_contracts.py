"""Formal-study identities are never disguised as synthetic MIL or legacy evidence."""
from typing import Literal
from pydantic import BaseModel,ConfigDict
from . import contracts as c
class FormalRef(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    schema_version:Literal['pathoreason.formal/1']='pathoreason.formal/1'
    adapter:Literal['pathoreason.formal_study']='pathoreason.formal_study'
    project_id:c.Identifier
    resource_id:c.Text
    revision:c.Digest
    revision_kind:Literal['file_sha256']='file_sha256'
    access:Literal['read_only']='read_only'
class FormalArtifact(c.ArtifactIndex):
    schema_version:Literal['pathoreason/3']='pathoreason/3'
    storage_root:Literal['pathoreason_artifacts']='pathoreason_artifacts'
    source_ref:FormalRef
    run_ref:FormalRef|None
class FormalReference(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    kind:Literal['formal']='formal'
    reference:FormalRef
