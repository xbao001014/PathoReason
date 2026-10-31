"""Export structural JSON Schema; relational invariants remain server-side."""
import json
from pathlib import Path
from pathoreason import contracts

root = Path(__file__).resolve().parents[1] / "contracts" / "v1"
root.mkdir(parents=True, exist_ok=True)
for name, cls in vars(contracts).items():
    if isinstance(cls, type) and issubclass(cls, contracts.Contract) and cls is not contracts.Contract:
        schema = cls.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:pathoreason:contracts:v1:{name}"
        (root / f"{name}.schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
print("Exported", len(list(root.glob("*.schema.json"))), "contract schemas")
