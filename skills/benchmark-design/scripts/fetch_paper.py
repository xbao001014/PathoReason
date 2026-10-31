"""Bounded public PDF retrieval and text extraction with exclusive provenance files."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import urllib.request
from urllib.parse import urlparse


@contextmanager
def deadline(seconds):
    def expired(*_):
        raise TimeoutError('whole_download_deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def destination(workspace, relative):
    root = Path(workspace).resolve(strict=True)
    part = Path(relative)
    if part.is_absolute() or '..' in part.parts or not part.parts or part.parts[0] != 'plans':
        raise ValueError('output must be a new workspace-relative plans directory')
    path = root / part
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve().is_relative_to(root):
        raise ValueError('symlink or path escape')
    path.mkdir(parents=True, exist_ok=False)
    return path


def extract(pdf, output):
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    from pypdf import PdfReader, __version__
    reader = PdfReader(pdf)
    if reader.is_encrypted or len(reader.pages) > 200:
        raise ValueError('encrypted PDF or page cap exceeded')
    pages = [page.extract_text() or '' for page in reader.pages]
    if not any(text.strip() for text in pages):
        raise ValueError('no extractable text; OCR not performed')
    text = '\n\n'.join('--- Page ' + str(i + 1) + ' ---\n' + value for i, value in enumerate(pages))
    if len(text.encode()) > 10 * 1024 ** 2:
        raise ValueError('extracted text size cap exceeded')
    Path(output).write_text(text)
    print(json.dumps({'pages': len(pages), 'text_characters': len(text), 'parser': 'pypdf', 'parser_version': __version__}))


def retrieve(workspace, url, relative, timeout=60, max_bytes=20 * 1024 ** 2, opener=urllib.request.urlopen):
    parsed = urlparse(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('public HTTP(S) URL without credentials required')
    if not 0 < timeout <= 120 or not 0 < max_bytes <= 50 * 1024 ** 2:
        raise ValueError('invalid retrieval bounds')
    out = destination(workspace, relative)
    receipt = {'schema_version': 'pathoreason.paper-retrieval/1', 'url': url,
               'accessed_at': datetime.now(timezone.utc).isoformat(), 'state': 'started',
               'download_deadline_seconds': timeout, 'parse_deadline_seconds': 30,
               'max_bytes': max_bytes, 'scientific_verification': False}
    receipt_path = out / 'receipt.json'
    def save():
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    save()
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'PathoReason literature retrieval', 'Accept': 'application/pdf'})
        size = 0
        with deadline(timeout):
            with opener(request, timeout=min(timeout, 15)) as response, (out / 'source.partial').open('xb') as target:
                receipt.update(http_status=response.status, resolved_url=response.geturl())
                if response.status != 200:
                    raise ValueError('HTTP response not successful')
                while chunk := response.read(64 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError('response size cap exceeded')
                    target.write(chunk)
        raw = (out / 'source.partial').read_bytes()
        if not raw.startswith(b'%PDF-'):
            raise ValueError('response is not a PDF')
        pdf = out / 'source.pdf'
        (out / 'source.partial').rename(pdf)
        receipt.update(pdf_sha256=hashlib.sha256(raw).hexdigest(), pdf_bytes=size)
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--extract', str(pdf), str(out / 'text.txt')],
                                capture_output=True, text=True, timeout=30, check=True)
        receipt.update(json.loads(result.stdout), state='text_extracted',
                       text_sha256=hashlib.sha256((out / 'text.txt').read_bytes()).hexdigest())
        save()
        return receipt
    except Exception as exc:
        receipt.update(state='failed', error_type=type(exc).__name__, received_bytes=size)
        # Parser/HTTP diagnostics stay local; do not emit remote response bodies.
        save()
        raise


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--extract':
        extract(sys.argv[2], sys.argv[3])
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--workspace', required=True)
        parser.add_argument('--url', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--timeout', type=float, default=60)
        args = parser.parse_args()
        try:
            result = retrieve(args.workspace, args.url, args.output, args.timeout)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as exc:
            print(json.dumps({'state': 'failed', 'error_type': type(exc).__name__, 'detail': str(exc)[:300]}))
            raise SystemExit(1)
