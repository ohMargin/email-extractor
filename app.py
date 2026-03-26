"""
Flask application — polling-based architecture (reliable on Windows).

Routes:
  GET  /                       — frontend SPA
  POST /api/extract            — start task, return task_id
  GET  /api/results/<task_id>  — poll for current results (frontend calls every 2s)
  POST /api/export             — download CSV
"""

import csv
import io
import json
import logging
import os
import sys
import threading
import traceback
import uuid

from flask import Flask, jsonify, render_template, request, Response

from extractor import extract_emails_from_site

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Resolve template folder — works in both dev mode and PyInstaller bundle
# --------------------------------------------------------------------------

def _base_dir() -> str:
    """Return the directory that contains templates/ and other assets."""
    # RESOURCE_PATH_BASE is set by launcher.py when running as a bundle
    if "RESOURCE_PATH_BASE" in os.environ:
        return os.environ["RESOURCE_PATH_BASE"]
    # Fallback: directory of this file
    return os.path.dirname(os.path.abspath(__file__))


_TEMPLATE_FOLDER = os.path.join(_base_dir(), "templates")

app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)

# task_id -> {
#   "results": [...],      # completed site results so far
#   "progress": {...},     # latest progress message
#   "done": bool,
#   "total": int,
# }
_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _run_extraction(task_id: str, urls: list[str]) -> None:
    total = len(urls)
    for idx, url in enumerate(urls, 1):
        url = url.strip()
        if not url:
            continue

        log.info("Processing (%d/%d): %s", idx, total, url)

        with _tasks_lock:
            _tasks[task_id]["progress"] = {
                "index": idx,
                "total": total,
                "url": url,
                "message": f"正在处理 ({idx}/{total}): {url}",
            }

        try:
            result = extract_emails_from_site(url)
            log.info(
                "Done %s — official=%s count=%d",
                url, result.get("official_email"), len(result.get("all_emails", []))
            )
        except Exception:
            err = traceback.format_exc()
            log.error("Error on %s:\n%s", url, err)
            result = {
                "url": url,
                "status": "error",
                "error": f"提取失败: {err.splitlines()[-1]}",
                "official_email": None,
                "all_emails": [],
            }

        with _tasks_lock:
            _tasks[task_id]["results"].append(result)

    with _tasks_lock:
        _tasks[task_id]["done"] = True

    log.info("Task %s finished.", task_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/extract")
def api_extract():
    data = request.get_json(silent=True) or {}
    raw_urls: str = data.get("urls", "")
    urls = [u.strip() for u in raw_urls.splitlines() if u.strip()]

    if not urls:
        return jsonify({"error": "请至少输入一个网址"}), 400

    task_id = str(uuid.uuid4())
    with _tasks_lock:
        _tasks[task_id] = {
            "results": [],
            "progress": {"message": "任务已启动，准备处理…", "index": 0, "total": len(urls)},
            "done": False,
            "total": len(urls),
        }

    t = threading.Thread(target=_run_extraction, args=(task_id, urls), daemon=True)
    t.start()

    return jsonify({"task_id": task_id, "total": len(urls)})


@app.get("/api/results/<task_id>")
def api_results(task_id: str):
    """Polling endpoint — returns all results collected so far + done flag."""
    with _tasks_lock:
        task = _tasks.get(task_id)

    if task is None:
        return jsonify({"error": "任务不存在或已过期"}), 404

    return jsonify({
        "results":  task["results"],
        "progress": task["progress"],
        "done":     task["done"],
        "total":    task["total"],
    })


@app.post("/api/export")
def api_export():
    data = request.get_json(silent=True) or {}
    results: list[dict] = data.get("results", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["网站 URL", "官方邮箱", "所有邮箱（分号分隔）", "各邮箱分数"])

    for r in results:
        all_emails = r.get("all_emails", [])
        all_str    = "; ".join(e["email"] for e in all_emails)
        scores_str = "; ".join(f"{e['email']}({e['score']})" for e in all_emails)
        writer.writerow([
            r.get("url", ""),
            r.get("official_email", ""),
            all_str,
            scores_str,
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=email_results.csv"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
