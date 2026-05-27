import json
from datetime import datetime

# ==========================================
# 1. PC 및 카메라 로그 파일 불러오기
# ==========================================
try:
    with open('state_log.json', 'r', encoding='utf-8') as f:
        camera_logs = json.load(f)
    with open('laptop_log.json', 'r', encoding='utf-8') as f:
        laptop_logs = json.load(f)
except FileNotFoundError:
    print("❌ 로그 파일을 찾을 수 없습니다. (state_log.json 또는 laptop_log.json)")
    exit()

final_timeline_logs = []
laptop_final_summary = None  # 최종 요약본 리포트를 구출해 담을 변수

def str_to_time(time_str):
    try:
        # 1. 새로운 형식 (예: 2026-05-26 21:45:55) 대응
        if " " in time_str:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").time()
        # 2. 예전 형식 (예: 21:45:55) 대응
        else:
            return datetime.strptime(time_str, "%H:%M:%S").time()
    except Exception as e:
        print(f"시간 변환 오류: {time_str} - {e}")
        return None

print(">> 🔄 데이터 통합을 시작합니다...")

# ==========================================
# 2. 랩탑 최신 요약본(final_summary) 구출
# ==========================================
# 파일의 맨 뒤(최신 데이터)부터 거꾸로 스캔하여 가장 마지막 요약본을 구출합니다!
for lap_log in reversed(laptop_logs):
    if lap_log.get("trigger") == "final_summary":
        laptop_final_summary = lap_log
        break

# ==========================================
# 3. 카메라 자세 데이터 + PC 타임라인 병합
# ==========================================
for cam_log in camera_logs:
    start_t = str_to_time(cam_log["start_time"])
    end_t = str_to_time(cam_log["end_time"])
    
    digital_activities = []
    
    # [1] 자세가 바뀌는 바로 그 시점(start_t)에 켜져 있던 프로그램 찾기
    current_app = None
    for lap_log in laptop_logs:
        if lap_log.get("trigger") == "final_summary":
            continue
            
        lap_t = str_to_time(lap_log["timestamp"])
        if lap_t and start_t and lap_t <= start_t:
            if "foreground_app" in lap_log:
                current_app = f"{lap_log.get('foreground_app')} ({lap_log.get('foreground_title', '')})"
            else:
                current_app = lap_log.get("active_window", "unknown")
    
    # [2] 노트북을 안 건드렸어도, 자세 변환 시간에 맞춰 무조건 로그 1개 강제 생성
    if current_app:
        digital_activities.append({
            "time": cam_log["start_time"],
            "app": current_app
        })
        
    # [3] 자세 유지 기간 도중 마우스/키보드로 창을 바꾼 기록 추가
    for lap_log in laptop_logs:
        if lap_log.get("trigger") == "final_summary":
            continue
            
        lap_t = str_to_time(lap_log["timestamp"])
        if lap_t and start_t and end_t and start_t < lap_t <= end_t: 
            
            # 새 포맷과 옛 포맷 통합 매칭 처리
            if "foreground_app" in lap_log:
                lap_app_name = f"{lap_log.get('foreground_app')} ({lap_log.get('foreground_title', '')})"
            else:
                lap_app_name = lap_log.get("active_window", "unknown")
                
            if not digital_activities or digital_activities[-1]["app"] != lap_app_name:
                digital_activities.append({
                    "time": lap_log["timestamp"],
                    "app": lap_app_name
                })
    
    # 4. 통합된 하나의 데이터 블록 생성
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
    with open('mobile_log.json', 'r', encoding='utf-8') as f:
        mobile_logs = json.load(f)
        # 리스트 형태로 저장되어 있다면 가장 최신(마지막) 데이터를 가져옵니다.
        if isinstance(mobile_logs, list) and len(mobile_logs) > 0:
            mobile_final_summary = mobile_logs[-1]
        elif isinstance(mobile_logs, dict):
            mobile_final_summary = mobile_logs
except FileNotFoundError:
    print("⚠️ 모바일 로그 파일(mobile_log.json)이 없어 모바일 데이터는 생략합니다.")

# ==========================================
# 5. 최종 구조화 및 파일 저장
# ==========================================
final_output = {
    "timeline_data": final_timeline_logs,
    "laptop_final_summary": laptop_final_summary, 
    "mobile_final_summary": mobile_final_summary  # 📱 모바일 데이터 추가 완료!
}

with open('final_log.json', 'w', encoding='utf-8') as f:
    json.dump(final_output, f, indent=4, ensure_ascii=False)

print(">> 🔗 통합 완료! [final_log.json] 파일에 자세/PC/모바일 3종 데이터가 모두 병합되었습니다.")