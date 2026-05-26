import json
from datetime import datetime

# 1. 파일 불러오기
try:
    with open('state_log.json', 'r', encoding='utf-8') as f:
        camera_logs = json.load(f)
    with open('laptop_log.json', 'r', encoding='utf-8') as f:
        laptop_logs = json.load(f)
except FileNotFoundError:
    print("로그 파일을 찾을 수 없습니다.")
    exit()

final_logs = []

def str_to_time(time_str):
    return datetime.strptime(time_str, "%H:%M:%S").time()

print(">> 데이터 통합을 시작합니다...")

for cam_log in camera_logs:
    start_t = str_to_time(cam_log["start_time"])
    end_t = str_to_time(cam_log["end_time"])
    
    digital_activities = []
    
    # [1] 자세가 바뀌는 바로 그 시점(start_t)에 켜져 있던 프로그램 찾기
    current_app = None
    for lap_log in laptop_logs:
        lap_t = str_to_time(lap_log["timestamp"])
        if lap_t <= start_t:
            current_app = lap_log["active_window"]
    
    # [2] 노트북을 안 건드렸어도, 자세 변환 시간에 맞춰 무조건 로그 1개 강제 생성!
    if current_app:
        digital_activities.append({
            "time": cam_log["start_time"],  # 카메라 자세 변환 시간을 그대로 씁니다!
            "app": current_app
        })
        
    # [3] 자세 유지 기간 도중 마우스/키보드로 창을 바꾼 기록 추가
    for lap_log in laptop_logs:
        lap_t = str_to_time(lap_log["timestamp"])
        if start_t < lap_t <= end_t: # 시작 시간 이후의 기록만 (중복 방지)
            if not digital_activities or digital_activities[-1]["app"] != lap_log["active_window"]:
                digital_activities.append({
                    "time": lap_log["timestamp"],
                    "app": lap_log["active_window"]
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
    final_logs.append(merged_entry)

# 5. 최종 결과물 저장
with open('final_log.json', 'w', encoding='utf-8') as f:
    json.dump(final_logs, f, indent=4, ensure_ascii=False)

print(">> 통합 완료! [final_log.json] 파일을 확인해 보세요.")