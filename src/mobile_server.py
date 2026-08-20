import json
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.serving import make_server


app = Flask(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "mobile_log"
LATEST_FILE = DATA_DIR / "mobile_log.json"
LOG_SAVE_INTERVAL_SEC = 30.0
SHUTDOWN_TOKEN = "0f25d7b3b5354e23a863af93dd06f3a4"

data_lock = threading.Lock()
http_server = None


def _atomic_write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
            file.flush()
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _next_snapshot_path(timestamp):
    path = DATA_DIR / f"mobile_log_{timestamp}.json"
    number = 2
    while path.exists():
        path = DATA_DIR / f"mobile_log_{timestamp}_{number}.json"
        number += 1
    return path


@app.route("/upload_mobile_log", methods=["POST"])
def upload_log():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No data"}), 400

    try:
        with data_lock:
            _atomic_write_json(LATEST_FILE, data)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_path = _next_snapshot_path(timestamp)
            _atomic_write_json(snapshot_path, data)
        first_entry = data[0] if isinstance(data, list) and data else data
        is_in_progress = isinstance(first_entry, dict) and first_entry.get("in_progress") is True
        save_type = "진행 중" if is_in_progress else "최종"
        print(f">> [{save_type} 저장] 모바일 로그: {snapshot_path}")
        return jsonify({"status": "success", "snapshot_interval_sec": LOG_SAVE_INTERVAL_SEC}), 200
    except OSError as error:
        print(f">> 모바일 로그 최신 파일 저장 오류: {error}")
        return jsonify({"status": "error", "message": "Failed to save log"}), 500


@app.route("/connect", methods=["POST"])
def connect_mobile_app():
    if request.headers.get("X-Shutdown-Token") != SHUTDOWN_TOKEN:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    print(f">> 모바일 앱 연결됨: {request.remote_addr}")
    return jsonify({"status": "success", "message": "Mobile app connected"}), 200


@app.route("/shutdown", methods=["POST"])
def shutdown_server():
    if request.headers.get("X-Shutdown-Token") != SHUTDOWN_TOKEN:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    if http_server is None:
        return jsonify({"status": "error", "message": "Server is not running"}), 503
    threading.Thread(target=http_server.shutdown, name="mobile-server-shutdown", daemon=True).start()
    return jsonify({"status": "success", "message": "Server shutdown requested"}), 200


def main():
    global http_server
    print(
    f">> 모바일 로그 수신 서버 시작 "
    f"(앱 {LOG_SAVE_INTERVAL_SEC:g}초 업로드 즉시 저장): {DATA_DIR}"
)
    try:
        http_server = make_server("0.0.0.0", 5000, app, threaded=True)
        print(">> 서버 주소: http://0.0.0.0:5000")
        http_server.serve_forever()
    finally:
        http_server = None


if __name__ == "__main__":
    main()
