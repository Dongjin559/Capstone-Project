import json
from datetime import datetime

# ==========================================
# 1. PC 및 카메라 로그 파일 불러오기
# ==========================================
try:
    with open('data/state_log.json', 'r', encoding='utf-8') as f:
        camera_logs = json.load(f)
    with open('data/laptop_log.json', 'r', encoding='utf-8') as f:
        laptop_logs = json.load(f)
except FileNotFoundError:
    print("❌ 로그 파일을 찾을 수 없습니다. (data/state_log.json 또는 data/laptop_log.json)")
    exit()

final_timeline_logs = []
laptop_final_summary = None

def str_to_time(time_str):
    try:
        if " " in time_str:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").time()
        else:
            return datetime.strptime(time_str, "%H:%M:%S").time()
    except Exception:
        return None

# ==========================================
# 2. 랩탑 최신 요약본(final_summary) 
# ==========================================
for lap_log in reversed(laptop_logs):
    if lap_log.get("trigger") == "final_summary":
        laptop_final_summary = lap_log
        break

if not laptop_final_summary:
    for lap_log in reversed(laptop_logs):
        if "app_accumulated_durations_sec" in lap_log:
            laptop_final_summary = {
                "trigger": "final_summary_recovered",
                "source": "laptop",
                "final_accumulated_durations_sec": lap_log["app_accumulated_durations_sec"]
            }
            break

# ==========================================
# 3. 카메라 자세 데이터 + PC 타임라인 병합
# ==========================================
for cam_log in camera_logs:
    start_t = str_to_time(cam_log["start_time"])
    end_t = str_to_time(cam_log["end_time"])
    
    digital_activities = []
    current_app = None
    
    for lap_log in laptop_logs:
        if lap_log.get("trigger") in ["final_summary", "final_summary_recovered"]:
            continue
            
        lap_t = str_to_time(lap_log["timestamp"])
        if lap_t and start_t and lap_t <= start_t:
            if "foreground_app" in lap_log:
                current_app = f"{lap_log.get('foreground_app')} ({lap_log.get('foreground_title', '')})"
            else:
                current_app = lap_log.get("active_window", "unknown")
    
    if current_app:
        digital_activities.append({
            "time": cam_log["start_time"],
            "app": current_app
        })
        
    for lap_log in laptop_logs:
        if lap_log.get("trigger") in ["final_summary", "final_summary_recovered"]:
            continue
            
        lap_t = str_to_time(lap_log["timestamp"])
        if lap_t and start_t and end_t and start_t < lap_t <= end_t: 
            if "foreground_app" in lap_log:
                lap_app_name = f"{lap_log.get('foreground_app')} ({lap_log.get('foreground_title', '')})"
            else:
                lap_app_name = lap_log.get("active_window", "unknown")
                
            if not digital_activities or digital_activities[-1]["app"] != lap_app_name:
                digital_activities.append({
                    "time": lap_log["timestamp"],
                    "app": lap_app_name
                })
    
    merged_entry = {
        "id": cam_log["id"],
        "activity_time": f"{cam_log['start_time']} ~ {cam_log['end_time']}",
        "physical_posture": cam_log["activity"],
        "zone": cam_log["zone"],
        "stay_time_sec": cam_log["stay_time"],
        "digital_log": digital_activities
    }
    final_timeline_logs.append(merged_entry)

# ==========================================
# 4. 모바일 로그 데이터 불러오기
# ==========================================
mobile_final_summary = None
try:
    with open('data/mobile_log.json', 'r', encoding='utf-8') as f:
        mobile_logs = json.load(f)
        if isinstance(mobile_logs, list) and len(mobile_logs) > 0:
            mobile_final_summary = mobile_logs[-1]
        elif isinstance(mobile_logs, dict):
            mobile_final_summary = mobile_logs
except FileNotFoundError:
    pass

# ==========================================
# 5. 최종 구조화 및 파일 저장
# ==========================================
final_output = {
    "timeline_data": final_timeline_logs,
    "laptop_final_summary": laptop_final_summary, 
    "mobile_final_summary": mobile_final_summary 
}

with open('data/final_log.json', 'w', encoding='utf-8') as f:
    json.dump(final_output, f, indent=4, ensure_ascii=False)

print(">> 🔗 통합 완료! [data/final_log.json] 병합 성공.")