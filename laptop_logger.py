import win32gui
import time
import json
import datetime

laptop_logs = []
last_window = ""
start_time = time.time()

print(">> 노트북 사용 기록 추적을 시작합니다...")

while True:
    window = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(window)
    
    if title != last_window and title != "":
        current_time = time.time()
        timestamp_str = datetime.datetime.now().strftime("%H:%M:%S")
        
        log_entry = {
            "timestamp": timestamp_str,
            "timestamp_sec": current_time,
            "active_window": title
        }
        laptop_logs.append(log_entry)
        print(f"[{timestamp_str}] 사용 중인 프로그램: {title}", flush=True)
        
        last_window = title
        
        # 데이터가 날아가지 않게 리스트에 추가될 때마다 즉시 파일로 저장
        with open('laptop_log.json', 'w', encoding='utf-8') as f:
            json.dump(laptop_logs, f, indent=4, ensure_ascii=False)
        
    time.sleep(2)