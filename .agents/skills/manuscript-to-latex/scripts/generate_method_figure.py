#!/usr/bin/env python3
"""One-shot Seedream raster candidate generation; never approves or packages a figure."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MAX_RESPONSE = 48 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def generate(request_path: Path, output: Path):
    from PIL import Image
    request_bytes = request_path.read_bytes()
    request = json.loads(request_bytes)
    config = request["config"]
    if config.get("provider") != "seedream":
        raise ValueError("Unsupported image provider")
    model = config.get("model", "").strip()
    prompt = request.get("prompt", "").strip()
    env = config.get("api_key_env", "ARK_API_KEY")
    size = config.get("size", "2K")
    if not model or not prompt or len(prompt) > 16000 or size not in {"2K", "4K"}:
        raise ValueError("A model, bounded visual brief and supported size are required")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env):
        raise ValueError("Invalid credential environment variable")
    key = os.environ.get(env)
    if not key:
        raise ValueError(f"Missing credential environment variable: {env}")
    sources = []
    for name in request.get("sources", []):
        path = Path(name)
        if not path.is_absolute():
            path = request_path.parent / path
        sources.append({"path": str(path.resolve()), "sha256": digest(path.read_bytes())})
    if not sources:
        raise ValueError("Methodology source files are required")
    payload = {"model": model, "prompt": prompt, "size": size,
               "response_format": "b64_json", "stream": False, "watermark": True}
    references = request.get("reference_images", [])
    if not isinstance(references, list) or len(references) > 4:
        raise ValueError("At most four local reference images are supported")
    encoded = []
    for name in references:
        path = Path(name)
        if not path.is_absolute():
            path = request_path.parent / path
        if path.stat().st_size > 30 * 1024 * 1024:
            raise ValueError("Reference image too large")
        data = path.read_bytes()
        with Image.open(io.BytesIO(data)) as reference:
            fmt = reference.format
            reference.verify()
        if fmt not in {"PNG", "JPEG"}:
            raise ValueError("Reference must be PNG or JPEG")
        mime = "png" if fmt == "PNG" else "jpeg"
        encoded.append(f"data:image/{mime};base64," + base64.b64encode(data).decode())
        sources.append({"path": str(path.resolve()), "sha256": digest(data), "role": "reference_image"})
    if encoded:
        payload["image"] = encoded
    # Exclusive directory creation is the retry/concurrent-call guard. Never overwrite a candidate.
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": "method-figure-candidate/1.0", "status": "requested",
               "provider": "seedream", "model": model, "endpoint": ENDPOINT,
               "created_at": datetime.now(timezone.utc).isoformat(), "sources": sources,
               "prompt": prompt, "request_sha256": digest(request_bytes), "size": size,
               "author_approved": False, "editable": False}
    receipt["reference_image_count"] = len(encoded)
    receipt_path = output / "candidate.json"
    def save():
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    save()
    try:
        req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        # Redirects must not forward credentials to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with urllib.request.build_opener(NoRedirect).open(req, timeout=180) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("Image response too large")
        result = json.loads(raw)
        items = result.get("data", [])
        if len(items) != 1 or not items[0].get("b64_json") or items[0].get("error"):
            raise ValueError("Expected one successful base64 image")
        image_bytes = base64.b64decode(items[0]["b64_json"], validate=True)
        with Image.open(io.BytesIO(image_bytes)) as image:
            fmt, dimensions = image.format, list(image.size)
            image.verify()
        if fmt not in {"PNG", "JPEG"}:
            raise ValueError("Expected a PNG or JPEG image")
        filename = "original.png" if fmt == "PNG" else "original.jpg"
        (output / filename).write_bytes(image_bytes)
        receipt.update(status="pending_review", image=filename, sha256=digest(image_bytes),
                       dimensions=dimensions)
        save()
    except Exception as exc:
        # Provider bodies can echo prompts/secrets; persist only a safe failure category.
        receipt.update(status="failed", error_type=type(exc).__name__)
        if isinstance(exc, urllib.error.HTTPError):
            receipt["http_status"] = exc.code
        save()
        raise RuntimeError(f"Image generation failed ({type(exc).__name__}); inspect candidate.json; no automatic retry") from None
    return receipt_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(generate(args.request, args.output_dir))


if __name__ == "__main__":
    main()
