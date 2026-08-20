import atexit
import json
import signal
import time
from pathlib import Path

import psutil
import win32gui
import win32process


LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "laptop_log"
LOG_SAVE_INTERVAL_SEC = 30.0

app_duration_tracker = {}


def get_active_window_info():
    hwnd = win32gui.GetForegroundWindow()
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        app_name = process.name().removesuffix(".exe").lower()
        if app_name in {"explorer", "applicationframehost", "systemsettings", "searchhost"}:
            return "idle", ""
        return app_name, win32gui.GetWindowText(hwnd)
    except Exception:
        return "unknown", ""


def get_background_windows(foreground_app):
    background_apps = []
    seen_apps = set()

    def enum_window_callback(hwnd, extra):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            app_name = psutil.Process(pid).name().removesuffix(".exe").lower()
            ignored = {foreground_app, "explorer", "systemsettings", "unknown", "applicationframehost"}
            if app_name not in ignored and app_name not in seen_apps:
                seen_apps.add(app_name)
                background_apps.append(f"{app_name} ({title})")
        except Exception:
            pass

    win32gui.EnumWindows(enum_window_callback, None)
    return background_apps


def convert_seconds_to_readable(seconds):
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60
    parts = []
    if hours:
        parts.append(f"{hours}시간")
    if minutes:
        parts.append(f"{minutes}분")
    parts.append(f"{remaining_seconds}초")
    return " ".join(parts)


def _next_log_path(filename, timestamp):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{filename}_{timestamp}.json"
    number = 2
    while path.exists():
        path = LOG_DIR / f"{filename}_{timestamp}_{number}.json"
        number += 1
    return path


def save_json_snapshot(filename, data, timestamp):
    path = _next_log_path(filename, timestamp)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
            file.flush()
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def build_summary(start_time, in_progress):
    total_session_seconds = int(time.time() - start_time)
    raw_durations = {key: int(value) for key, value in app_duration_tracker.items()}
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trigger": "periodic_summary" if in_progress else "final_summary",
        "source": "laptop",
        "total_monitoring_time": convert_seconds_to_readable(total_session_seconds),
        "total_monitoring_seconds": total_session_seconds,
        "final_accumulated_durations_sec": raw_durations,
        "final_accumulated_durations_readable": {
            key: convert_seconds_to_readable(value) for key, value in app_duration_tracker.items()
        },
    }
    if in_progress:
        summary["in_progress"] = True
    return summary


def save_logs(pending_logs, start_time, in_progress=True):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    save_json_snapshot("laptop_usage_log", list(pending_logs), timestamp)
    save_json_snapshot("laptop_summary_log", [build_summary(start_time, in_progress)], timestamp)


def log_laptop_usage():
    print("랩탑 실시간 모니터링 시작... (Ctrl+C: 종료)")
    session_start_time = time.time()
    last_checked_time = session_start_time
    last_logged_time = session_start_time
    last_logged_window = None
    last_log_save = time.monotonic()
    pending_logs = []
    previous_app, _ = get_active_window_info()
    runtime_state = {"stop": False, "finalized": False}

    def request_stop(signum, frame):
        runtime_state["stop"] = True

    def finalize_once():
        nonlocal last_checked_time
        if runtime_state["finalized"]:
            return
        runtime_state["finalized"] = True
        final_time = time.time()
        elapsed_time = max(0.0, final_time - last_checked_time)
        if previous_app not in {"idle", "unknown"}:
            app_duration_tracker[previous_app] = app_duration_tracker.get(previous_app, 0.0) + elapsed_time
        last_checked_time = final_time
        save_logs(pending_logs, session_start_time, in_progress=False)
        print("최종 랩탑 로그 저장 완료")

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    atexit.register(finalize_once)

    try:
        while not runtime_state["stop"]:
            try:
                current_time = time.time()
                current_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                current_app, current_title = get_active_window_info()

                elapsed_time = max(0.0, current_time - last_checked_time)
                if previous_app not in {"idle", "unknown"}:
                    app_duration_tracker[previous_app] = app_duration_tracker.get(previous_app, 0.0) + elapsed_time
                last_checked_time = current_time
                previous_app = current_app

                current_window = (current_app, current_title)
                is_window_changed = current_window != last_logged_window
                is_timeout = current_time - last_logged_time >= 3.0
                if is_window_changed or is_timeout:
                    trigger = "window_changed" if is_window_changed else "3sec_interval"
                    pending_logs.append({
                        "timestamp": current_timestamp,
                        "foreground_app": current_app,
                        "foreground_title": current_title,
                        "background_apps": get_background_windows(current_app),
                        "app_accumulated_durations_sec": {
                            key: int(value) for key, value in app_duration_tracker.items()
                        },
                        "source": "laptop",
                        "trigger": trigger,
                    })
                    short_title = current_title[:30] + "..." if len(current_title) > 30 else current_title
                    print(f"[{current_timestamp}] [{trigger}] {current_app} ({short_title})")
                    last_logged_window = current_window
                    last_logged_time = current_time

                now_monotonic = time.monotonic()
                if now_monotonic - last_log_save >= LOG_SAVE_INTERVAL_SEC:
                    save_logs(pending_logs, session_start_time, in_progress=True)
                    pending_logs.clear()
                    last_log_save = now_monotonic

                time.sleep(0.1)
            except Exception as error:
                print(f"랩탑 로거 오류: {error}")
                time.sleep(1)
    finally:
        finalize_once()
        atexit.unregister(finalize_once)


if __name__ == "__main__":
    log_laptop_usage()
