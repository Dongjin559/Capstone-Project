import time
import json
import os
import win32gui
import win32process
import psutil

# 🔥 수정됨: JSON 파일이 data 폴더 안에 저장되도록 경로 변경
LOG_FILE = "data/laptop_log.json"

app_duration_tracker = {}
last_checked_time = None

def get_active_window_info():
    """현재 활성 창의 프로세스 이름과 창 제목을 가져옵니다."""
    hwnd = win32gui.GetForegroundWindow()
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        app_name = process.name().replace('.exe', '').lower()
        
        if app_name in ["explorer", "applicationframehost", "systemsettings", "searchhost"]:
            return "idle", ""
            
        window_title = win32gui.GetWindowText(hwnd)
        return app_name, window_title
    except Exception:
        return "unknown", ""

def get_background_windows(foreground_app):
    """백그라운드 창들의 목록을 가져옵니다."""
    bg_apps = []
    def enum_window_callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(pid)
                    app_name = process.name().replace('.exe', '').lower()
                    
                    if app_name != foreground_app and app_name not in [app for app, _ in bg_apps]:
                        if app_name not in ["explorer", "systemsettings", "unknown", "applicationframehost"]:
                            bg_apps.append((app_name, title))
                except Exception:
                    pass
    win32gui.EnumWindows(enum_window_callback, None)
    return [f"{app} ({title})" for app, title in bg_apps]

def load_existing_logs():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def convert_seconds_to_readable(seconds):
    """초 단위의 시간을 'X시간 Y분 Z초' 형태로 변환합니다."""
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    
    result = []
    if h > 0: result.append(f"{h}시간")
    if m > 0: result.append(f"{m}분")
    result.append(f"{s}초")
    return " ".join(result)

def record_final_summary(start_time):
    """프로그램 종료 시 총 세션 시간과 앱별 최종 누적 시간을 기록합니다."""
    current_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    total_session_seconds = int(time.time() - start_time)
    
    # 정수형 초 데이터와 읽기 좋은 문자열 데이터 매핑
    raw_durations = {k: int(v) for k, v in app_duration_tracker.items()}
    readable_durations = {k: convert_seconds_to_readable(v) for k, v in app_duration_tracker.items()}
    
    summary_entry = {
        "timestamp": current_timestamp,
        "trigger": "final_summary",  # 최종 요약 데이터임을 명시
        "source": "laptop",
        "total_monitoring_time": convert_seconds_to_readable(total_session_seconds),
        "total_monitoring_seconds": total_session_seconds,
        "final_accumulated_durations_sec": raw_durations,
        "final_accumulated_durations_readable": readable_durations
    }
    
    logs = load_existing_logs()
    logs.append(summary_entry)
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)
        
    print("\n" + "="*50)
    print("📋 [최종 분석 리포트 생성 완료]")
    print(f"총 모니터링 시간: {summary_entry['total_monitoring_time']}")
    print("-"*50)
    for app, t_str in readable_durations.items():
        print(f"• {app}: {t_str}")
    print("="*50)

def log_laptop_usage():
    global last_checked_time
    
    print("노트북 실시간 감시 시작... (종료 시 최종 리포트가 자동 저장됩니다.)")
    
    session_start_time = time.time()  # 프로그램이 켜진 시작 시간
    last_checked_time = time.time()
    last_logged_time = time.time()
    last_logged_title = None
    
    while True:
        try:
            current_time_sec = time.time()
            current_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            current_app, current_title = get_active_window_info()
            
            # 실시간 시간 누적
            elapsed_time = current_time_sec - last_checked_time
            if current_app != "idle" and current_app != "unknown":
                app_duration_tracker[current_app] = app_duration_tracker.get(current_app, 0) + elapsed_time
            
            last_checked_time = current_time_sec
            
            # 기록 조건 판단
            time_since_last_log = current_time_sec - last_logged_time
            is_window_changed = (current_title != last_logged_title)
            is_timeout = (time_since_last_log >= 3.0)
            
            if is_window_changed or is_timeout:
                background_apps = get_background_windows(current_app)
                display_durations = {k: int(v) for k, v in app_duration_tracker.items()}
                trigger_reason = "window_changed" if is_window_changed else "3sec_interval"
                
                log_entry = {
                    "timestamp": current_timestamp,
                    "foreground_app": current_app,
                    "foreground_title": current_title,
                    "background_apps": background_apps,
                    "app_accumulated_durations_sec": display_durations,
                    "source": "laptop",
                    "trigger": trigger_reason
                }
                
                logs = load_existing_logs()
                logs.append(log_entry)
                with open(LOG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(logs, f, indent=4, ensure_ascii=False)
                
                short_title = current_title[:30] + "..." if len(current_title) > 30 else current_title
                print(f"[{current_timestamp}] [{trigger_reason}] {current_app} ({short_title})")
                
                last_logged_title = current_title
                last_logged_time = current_time_sec
            
            time.sleep(0.1)
            
        except KeyboardInterrupt:
            # 사용자가 Ctrl+C를 눌렀을 때 마지막 요약본 기록 호출
            record_final_summary(session_start_time)
            break
        except Exception as e:
            print(f"에러 발생: {e}")
            time.sleep(1)

if __name__ == "__main__":
    log_laptop_usage()