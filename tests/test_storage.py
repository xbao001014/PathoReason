import json
import pytest
from pathoreason.storage import data_root, allocate

@pytest.mark.parametrize("root",["/home/bxn/runtime","/data/bxn/auto-research","/data/bxn/auto-research/acceptance","/data/bxn","relative","/data/bxn/../escape"])
def test_wrong_storage_root_rejected(tmp_path,root):
    config=tmp_path/"config.json";config.write_text(json.dumps({"data_root":root}))
    with pytest.raises(ValueError):data_root(config)

@pytest.mark.parametrize("category,name",[("sealed","job"),("scratch","../job"),("state","a/b")])
def test_invalid_allocation_rejected_before_fs_access(tmp_path,category,name):
    with pytest.raises(ValueError):allocate(tmp_path/"missing.json",category,name)
