# Web front end: a small FastAPI server plus one static HTML page.
#
#   python app.py            then open http://127.0.0.1:8000
#
# One assistant and one document index are shared by every browser tab; each
# tab sends its own session_id, and the conversation history is kept per
# session here, so two people asking at once do not see each other's follow-ups.

import os
import threading
import uuid

import uvicorn
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

import config
from qa.assistant import build_default_assistant
from qa.llm import LLMError

app = FastAPI(title="Document Q&A Assistant")
assistant = build_default_assistant()

sessions = {}
# uploads rebuild the index; the lock stops two uploads from rebuilding at once
index_lock = threading.Lock()

# only the last few turns are sent to the model anyway (config.HISTORY_TURNS);
# this just stops a long-lived tab from growing memory without limit
MAX_STORED_TURNS = 20


@app.get("/")
def index_page():
    return FileResponse(os.path.join(config.STATIC_DIR, "index.html"))


@app.get("/api/status")
def status():
    sample_docs = set(os.listdir(config.DOCS_DIR)) if os.path.isdir(config.DOCS_DIR) else set()
    docs = assistant.kb.summary()
    for d in docs:
        # sample documents ship with the project and cannot be deleted from the UI
        d["removable"] = d["source"] not in sample_docs
    return {
        "backend": assistant.backend.name,
        "model": getattr(assistant.backend, "model", None),
        "prompt_version": assistant.prompt_version,
        "uploads_enabled": config.ALLOW_UPLOADS,
        "documents": docs,
        "passages": len(assistant.kb.chunks),
    }


@app.post("/api/ask")
def ask(payload: dict = Body(...)):
    # a plain def, not async: the model call blocks, and FastAPI runs plain
    # functions in a worker thread so other requests keep being served
    question = str(payload.get("question", "")).strip()
    if not question:
        raise HTTPException(400, "question is empty")
    if len(question) > 2000:
        raise HTTPException(400, "question is too long (2000 characters max)")

    session_id = str(payload.get("session_id") or uuid.uuid4())
    history = sessions.setdefault(session_id, [])

    try:
        result = assistant.ask(question, history)
    except LLMError as e:
        raise HTTPException(502, str(e))

    history.append({"question": question, "answer": result["answer"]})
    del history[:-MAX_STORED_TURNS]

    result["session_id"] = session_id
    return result


@app.post("/api/reset")
def reset(payload: dict = Body(...)):
    sessions.pop(str(payload.get("session_id")), None)
    return {"ok": True}


@app.post("/api/upload")
def upload(file: UploadFile = File(...)):
    if not config.ALLOW_UPLOADS:
        raise HTTPException(403, "Uploads are disabled on this deployment.")
    # basename() drops any folder part, so a crafted name like "..\\x.md"
    # cannot write outside the uploads folder
    name = os.path.basename(file.filename or "")
    ext = os.path.splitext(name)[1].lower()
    if not name or ext not in config.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, "Only %s files are supported." % ", ".join(config.SUPPORTED_EXTENSIONS))

    data = file.file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File is larger than %d MB." % (config.MAX_UPLOAD_BYTES // (1024 * 1024)))

    os.makedirs(config.UPLOADS_DIR, exist_ok=True)
    path = os.path.join(config.UPLOADS_DIR, name)
    with open(path, "wb") as f:
        f.write(data)

    try:
        with index_lock:
            assistant.kb.add_file(path)
    except Exception as e:
        # a corrupt PDF should not stay on disk and break the next restart
        os.remove(path)
        raise HTTPException(400, "Could not read %s: %s" % (name, e))

    return status()


@app.delete("/api/documents/{source}")
def remove_document(source: str):
    if not config.ALLOW_UPLOADS:
        raise HTTPException(403, "Uploads are disabled on this deployment.")
    name = os.path.basename(source)
    path = os.path.join(config.UPLOADS_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(404, "Only uploaded documents can be removed.")
    with index_lock:
        os.remove(path)
        assistant.kb.remove(name)
    return status()


if __name__ == "__main__":
    print("Backend: %s | prompt %s | %d passages" % (
        assistant.backend.name, assistant.prompt_version, len(assistant.kb.chunks)))
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
