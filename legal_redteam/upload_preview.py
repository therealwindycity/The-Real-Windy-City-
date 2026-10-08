"""Private, local upload-and-analyze preview for the offline red-team engine.

Uploads are staged below an ignored workspace directory. This module makes no
network calls other than serving the UI and does not invoke research providers.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import shutil
import uuid
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import urlsplit

from .analyzer import analyze_case
from .ingest import load_case
from .report import render_markdown

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / ".legal_redteam_private" / "uploads"
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_FILES_PER_BATCH = 500
BATCH_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Private Case Upload · Legal Red-Team Engine</title>
<style>
:root{color-scheme:dark;--bg:#10151e;--panel:#192231;--line:#34445a;--ink:#eff5fb;--muted:#a9b8c9;--teal:#79e0c2;--amber:#f2cb82;--red:#ff9e9e}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top,#1a2d3b 0,#10151e 55%);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:980px;margin:40px auto;padding:0 20px 60px}.eyebrow{color:var(--teal);text-transform:uppercase;letter-spacing:.15em;font-size:.76rem;font-weight:700}
h1{font-size:clamp(2rem,5vw,3.3rem);line-height:1.05;margin:.45rem 0 1rem;letter-spacing:-.04em}.lede{max-width:760px;color:var(--muted);font-size:1.06rem}
.card{background:rgba(25,34,49,.94);border:1px solid var(--line);border-radius:18px;padding:24px;margin:22px 0;box-shadow:0 16px 48px #05090f55}.privacy{border-color:#7b653a;background:#28251d}.privacy strong{color:var(--amber)}
label{display:block;font-weight:650;margin:12px 0 6px}.inputs{display:grid;grid-template-columns:1fr 1fr;gap:16px}input[type=file]{width:100%;padding:14px;border:1px dashed #648097;border-radius:12px;background:#111a26;color:var(--muted)}
.small{color:var(--muted);font-size:.9rem}.path{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;color:#c8d9e8;overflow-wrap:anywhere}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}button{border:0;border-radius:999px;padding:12px 18px;font:700 .95rem system-ui;cursor:pointer;background:var(--teal);color:#0e211f}button.secondary{background:#324255;color:var(--ink)}button.danger{background:#512e35;color:#ffd9da}button:disabled{opacity:.55;cursor:wait}
.status{margin-top:14px;color:var(--muted);white-space:pre-wrap}.status.error{color:var(--red)}.status.success{color:var(--teal)}
.summary{display:flex;gap:10px;flex-wrap:wrap}.pill{padding:7px 11px;background:#101923;border:1px solid var(--line);border-radius:999px;font-size:.9rem;color:#d6e3ee}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:70vh;overflow:auto;padding:18px;background:#0b1119;border:1px solid var(--line);border-radius:12px;color:#e5edf5;font:13px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace}
footer{margin-top:28px;color:#91a1b3;font-size:.85rem}a{color:var(--teal)}@media(max-width:650px){main{margin-top:24px}.inputs{grid-template-columns:1fr}.card{padding:18px}}
</style>
</head>
<body><main>
<div class="eyebrow">Offline legal issue-spotting</div>
<h1>Upload a source bundle.<br>Run the framework.</h1>
<p class="lede">Select the files individually or choose their containing folder. Markdown exports such as <code>.pdf.md</code> and double-extension names such as <code>.md.md</code> are supported. The analyzer keeps each source separate and does not treat extracted text as established fact.</p>
<section class="card privacy"><strong>Private workspace staging — review before uploading sensitive material.</strong>
<p class="small">Files are transferred to this Arena sandbox and saved in the ignored folder <span class="path">.legal_redteam_private/uploads/&lt;batch-id&gt;/</span>. They are not committed or pushed to GitHub. Analysis is offline: no legal-search, citator, or LLM provider is called. This is a workspace convenience, not a confidentiality or retention guarantee. Delete the batch when finished.</p></section>
<section class="card">
<h2>1 · Choose source files</h2>
<div class="inputs">
<div><label for="files">Choose multiple files</label><input id="files" type="file" multiple><p class="small">Markdown, text, PDF, DOCX, VTT, and SRT are supported by the ingester.</p></div>
<div><label for="folder">Choose a folder (preserves subfolders)</label><input id="folder" type="file" webkitdirectory multiple><p class="small">Folder upload uses the browser's directory picker when supported.</p></div>
</div>
<label style="display:flex;align-items:center;gap:9px;margin-top:18px"><input id="ocr" type="checkbox"> Enable OCR for textless PDFs (opt-in; requires local OCR dependencies)</label>
<div class="actions"><button id="upload">Upload selected files</button><button id="analyze" class="secondary" disabled>Analyze uploaded batch</button><button id="delete" class="danger" disabled>Delete batch from workspace</button></div>
<div id="status" class="status" role="status" aria-live="polite">No files selected.</div>
</section>
<section id="results" class="card" hidden>
<h2>2 · Offline analysis</h2><div id="summary" class="summary"></div>
<p class="small">The report is rendered as text here; source-derived content is not inserted as HTML. Download it if needed, then delete the uploaded batch.</p>
<div class="actions"><button id="download-md" class="secondary">Download Markdown report</button><button id="download-json" class="secondary">Download JSON report</button></div>
<pre id="report"></pre>
</section>
<footer>Human research and legal review remain necessary. A keyword match is a lead, not a legal conclusion or exhaustive coverage.</footer>
</main>
<script>
const $=id=>document.getElementById(id);const csrfToken='__CSRF_TOKEN__';let batchId=null,reportMd='',reportJson='';
function status(message,kind=''){const node=$('status');node.textContent=message;node.className='status '+kind;}
function setBusy(busy){$('upload').disabled=busy;$('analyze').disabled=busy||!batchId;$('delete').disabled=busy||!batchId;}
function filesFromInputs(){const seen=new Set(),out=[];for(const input of [$('files'),$('folder')])for(const file of input.files){const name=file.webkitRelativePath||file.name;const key=name+'\0'+file.size+'\0'+file.lastModified;if(!seen.has(key)){seen.add(key);out.push({file,name});}}return out;}
$('upload').addEventListener('click',async()=>{const selected=filesFromInputs();if(!selected.length){status('Choose one or more files or a folder first.','error');return;}if(batchId){status('Delete or finish the current batch before uploading a new one.','error');return;}const form=new FormData();for(const item of selected)form.append('files',item.file,item.name);setBusy(true);status(`Uploading ${selected.length} file(s)…`);try{const response=await fetch('/api/upload',{method:'POST',headers:{'X-Legal-Upload-Token':csrfToken},body:form,cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.error||`Upload failed (${response.status})`);batchId=data.batch_id;$('analyze').disabled=false;$('delete').disabled=false;status(`Uploaded ${data.file_count} file(s).\nPrivate batch ID: ${batchId}\nStored under .legal_redteam_private/uploads/${batchId}/`,'success');}catch(error){status(error.message,'error');}finally{$('upload').disabled=false;}});
$('analyze').addEventListener('click',async()=>{if(!batchId)return;setBusy(true);status('Running the deterministic offline analyzer…');try{const response=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json','X-Legal-Upload-Token':csrfToken},body:JSON.stringify({batch_id:batchId,enable_ocr:$('ocr').checked}),cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.error||`Analysis failed (${response.status})`);reportMd=data.report_markdown;reportJson=JSON.stringify(data.report_json,null,2);$('report').textContent=reportMd;$('summary').replaceChildren();for(const text of [`${data.source_count} sources`,`${data.fact_count} unclassified passages`,`${data.candidate_issue_count} candidate issue prompts`,`${data.warning_count} warnings`]){const pill=document.createElement('span');pill.className='pill';pill.textContent=text;$('summary').appendChild(pill);}$('results').hidden=false;status('Analysis complete. No online providers were called.','success');}catch(error){status(error.message,'error');}finally{setBusy(false);}});
function download(text,name,type){const blob=new Blob([text],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);}
$('download-md').addEventListener('click',()=>reportMd&&download(reportMd,'legal-redteam-review.md','text/markdown;charset=utf-8'));
$('download-json').addEventListener('click',()=>reportJson&&download(reportJson,'legal-redteam-review.json','application/json;charset=utf-8'));
$('delete').addEventListener('click',async()=>{if(!batchId)return;if(!confirm('Permanently delete the uploaded files in this batch from the sandbox?'))return;setBusy(true);try{const response=await fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json','X-Legal-Upload-Token':csrfToken},body:JSON.stringify({batch_id:batchId}),cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.error||'Deletion failed');batchId=null;reportMd='';reportJson='';$('results').hidden=true;$('report').textContent='';$('files').value='';$('folder').value='';$('upload').disabled=false;$('analyze').disabled=true;$('delete').disabled=true;status('Uploaded batch deleted from this workspace.','success');}catch(error){status(error.message,'error');setBusy(false);}});
</script></body></html>"""


def safe_relative_upload_name(filename: str) -> Path:
    """Normalize a multipart filename into a safe relative path."""
    if not isinstance(filename, str) or not filename.strip() or "\x00" in filename:
        raise ValueError("Upload contains a missing or invalid filename")
    normalized = filename.replace("\\", "/").strip()
    if re.match(r"^[A-Za-z]:", normalized):
        normalized = normalized[2:].lstrip("/")
    if normalized.startswith("/"):
        raise ValueError("Absolute upload paths are not accepted")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {".", "..", ""} for part in parts):
        raise ValueError("Upload filename contains an unsafe path component")
    cleaned = []
    for part in parts:
        if re.fullmatch(r"[A-Za-z]:", part):
            continue
        safe = "".join("_" if ord(char) < 32 else char for char in part).strip()
        if not safe or safe in {".", ".."}:
            raise ValueError("Upload filename contains an unsafe path component")
        cleaned.append(safe)
    if not cleaned:
        raise ValueError("Upload filename does not identify a file")
    return Path(*cleaned)


def parse_multipart_files(content_type: str, body: bytes) -> list[tuple[str, bytes]]:
    """Extract named uploaded file parts without using deprecated cgi.FieldStorage."""
    if "\r" in content_type or "\n" in content_type:
        raise ValueError("Invalid multipart content type")
    headers = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii", "strict")
        + body
    )
    message = BytesParser(policy=policy.default).parsebytes(headers)
    if not message.is_multipart():
        raise ValueError("Expected a multipart/form-data upload")
    uploads: list[tuple[str, bytes]] = []
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        field_name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        if field_name != "files" or filename is None:
            continue
        payload = part.get_payload(decode=True)
        uploads.append((filename, payload or b""))
    if not uploads:
        raise ValueError("No file parts were found in the upload")
    if len(uploads) > MAX_FILES_PER_BATCH:
        raise ValueError(f"A batch may contain at most {MAX_FILES_PER_BATCH} files")
    if sum(len(data) for _, data in uploads) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Total upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit")
    return uploads


def _unique_destination(batch_root: Path, relative: Path) -> Path:
    destination = batch_root / relative
    if not destination.exists():
        return destination
    stem, suffix = destination.stem, destination.suffix
    index = 2
    while True:
        candidate = destination.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def save_upload_batch(storage_root: Path, uploads: Iterable[tuple[str, bytes]]) -> tuple[str, list[str]]:
    """Store a batch with private permissions and return its ID and saved names."""
    upload_list = list(uploads)
    if not upload_list:
        raise ValueError("Choose at least one file")
    if len(upload_list) > MAX_FILES_PER_BATCH:
        raise ValueError(f"A batch may contain at most {MAX_FILES_PER_BATCH} files")
    if sum(len(data) for _, data in upload_list) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Total upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit")

    storage_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        storage_root.chmod(0o700)
    except OSError:
        pass
    batch_id = uuid.uuid4().hex
    batch_root = storage_root / batch_id
    batch_root.mkdir(mode=0o700)
    saved_names: list[str] = []
    try:
        for filename, data in upload_list:
            relative = safe_relative_upload_name(filename)
            destination = _unique_destination(batch_root, relative)
            parent = batch_root
            for component in destination.relative_to(batch_root).parent.parts:
                parent = parent / component
                parent.mkdir(mode=0o700, exist_ok=True)
                try:
                    parent.chmod(0o700)
                except OSError:
                    pass
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
            saved_names.append(destination.relative_to(batch_root).as_posix())
    except Exception:
        shutil.rmtree(batch_root, ignore_errors=True)
        raise
    return batch_id, saved_names


def _checked_batch_path(storage_root: Path, batch_id: object) -> Path:
    if not isinstance(batch_id, str) or not BATCH_ID_PATTERN.fullmatch(batch_id):
        raise ValueError("Invalid upload batch ID")
    path = storage_root / batch_id
    if not path.is_dir() or path.is_symlink():
        raise ValueError("Upload batch was not found")
    return path


def analyze_upload_batch(storage_root: Path, batch_id: object, *, enable_ocr: bool = False) -> dict[str, object]:
    """Run only the offline case-packet loader and analyzer for one staged batch."""
    batch_root = _checked_batch_path(storage_root, batch_id)
    case = load_case(batch_root, enable_ocr=enable_ocr)
    report = analyze_case(case)
    return {
        "source_count": len(case.documents),
        "fact_count": len(case.facts),
        "candidate_issue_count": len(report["candidate_issues"]),
        "warning_count": len(report["completeness_warnings"]),
        "report_markdown": render_markdown(report),
        "report_json": report,
    }


def delete_upload_batch(storage_root: Path, batch_id: object) -> None:
    """Delete only the validated batch directory selected by the user."""
    batch_root = _checked_batch_path(storage_root, batch_id)
    shutil.rmtree(batch_root)


class UploadPreviewHandler(BaseHTTPRequestHandler):
    server_version = "LegalRedteamUploadPreview/1.0"
    storage_root: Path = DEFAULT_STORAGE_ROOT
    csrf_token: str = ""

    def log_message(self, format: str, *args: object) -> None:
        # Avoid writing uploaded filenames or report contents to server logs.
        return

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'",
        )
        self.end_headers()

    def _json(self, status: int, data: dict[str, object]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _read_body(self, max_bytes: int) -> bytes:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "")
        except ValueError as exc:
            raise ValueError("Content-Length header is missing or invalid") from exc
        if length < 0 or length > max_bytes:
            raise ValueError(f"Request exceeds the {max_bytes // (1024 * 1024)} MiB limit")
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError("Upload ended before the declared Content-Length")
        return body

    def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler method
        route = urlsplit(self.path).path
        if route in {"/", "/index.html"}:
            body = PAGE.replace("__CSRF_TOKEN__", self.csrf_token).encode("utf-8")
            self._headers(200, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
        elif route == "/health":
            self._json(200, {"status": "ready", "analysis": "offline"})
        else:
            self._json(404, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP handler method
        route = urlsplit(self.path).path
        supplied_token = self.headers.get("X-Legal-Upload-Token", "")
        if not self.csrf_token or not hmac.compare_digest(supplied_token, self.csrf_token):
            self._json(403, {"error": "Upload session token is missing or invalid; reload the page."})
            return
        try:
            if route == "/api/upload":
                body = self._read_body(MAX_UPLOAD_BYTES)
                uploads = parse_multipart_files(self.headers.get("Content-Type", ""), body)
                batch_id, saved_names = save_upload_batch(self.storage_root, uploads)
                self._json(201, {"batch_id": batch_id, "file_count": len(saved_names), "files": saved_names})
                return
            if route in {"/api/analyze", "/api/delete"}:
                body = self._read_body(1024 * 1024)
                payload = json.loads(body.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Request body must be a JSON object")
                batch_id = payload.get("batch_id")
                if route == "/api/analyze":
                    enable_ocr = payload.get("enable_ocr", False)
                    if not isinstance(enable_ocr, bool):
                        raise ValueError("enable_ocr must be true or false")
                    self._json(200, analyze_upload_batch(self.storage_root, batch_id, enable_ocr=enable_ocr))
                else:
                    delete_upload_batch(self.storage_root, batch_id)
                    self._json(200, {"deleted": True})
                return
            self._json(404, {"error": "Not found"})
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private upload UI for offline legal-red-team analysis")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=Path(os.environ.get("LEGAL_REDTEAM_UPLOAD_ROOT", DEFAULT_STORAGE_ROOT)),
        help="private upload directory (default: ignored .legal_redteam_private/uploads)",
    )
    args = parser.parse_args(argv)
    storage_root = args.storage_root.resolve()
    storage_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        storage_root.chmod(0o700)
    except OSError:
        pass
    handler = type(
        "ConfiguredUploadPreviewHandler",
        (UploadPreviewHandler,),
        {"storage_root": storage_root, "csrf_token": secrets.token_hex(32)},
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.daemon_threads = True
    print(f"Legal red-team upload preview listening on http://{args.host}:{args.port}")
    print("Analysis is offline; uploaded files are stored in an ignored private workspace directory.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
