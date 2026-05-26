import cv2
import json
import time
import numpy as np
import datetime
from ultralytics import YOLO
import mediapipe as mp
import matplotlib.pyplot as plt

# --- 1. 기본 설정 및 초기화 ---
# s 대신 n(Nano) 모델을 사용하여 속도를 개선합니다. conf 값은 0.45로 유지하여 누운 사람 탐지 유도
model = YOLO('yolov8n.pt') 
mp_pose = mp.solutions.pose.Pose(model_complexity=1)
mp_drawing = mp.solutions.drawing_utils

video_path = 'sample_video1.mp4'
zones = {}

# 로그 저장을 위한 리스트
state_logs = []
transition_logs = []
summary_logs = []

# 상태 추적을 위한 딕셔너리
trackers = {}
TRANSITION_THRESHOLD_SEC = 2.0  # 자세가 완전히 전환되었다고 판단할 유지 시간 (N초)

# 영상 재생 시간(00:00:00)부터 기록하도록 설정
base_time = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

# ===== [추가] 목표 해상도 설정 변수 =====
# "조금만" 키우고 싶다면, 원본 16:9 비율을 유지하는 960x540을 제안합니다.
TARGET_WIDTH = 960
TARGET_HEIGHT = 540
# ======================================

def get_time_str(seconds):
    """초(sec) 단위 시간을 HH:MM:SS 형식으로 변환"""
    return (base_time + datetime.timedelta(seconds=seconds)).strftime("%H:%M:%S")

def format_duration(seconds):
    """초를 분, 시간 단위 문자열로 변환 (예: '45m 20s')"""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h}h {m}m {s}s"
    elif m > 0: return f"{m}m {s}s"
    else: return f"{s}s"

# --- 2. 구역 설정 함수 (해상도 조정 반영) ---
def setup_zones(first_frame):
    # 구역 설정 시에도 해상도를 조정하여 보여줍니다.
    img = cv2.resize(first_frame, (TARGET_WIDTH, TARGET_HEIGHT))
    pts = []
    
    def draw_roi(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            pts.append([x, y])
            cv2.circle(img, (x, y), 5, (0, 0, 255), -1)
            if len(pts) > 1: cv2.line(img, tuple(pts[-2]), tuple(pts[-1]), (0, 255, 0), 2)
            cv2.imshow("Setup Zones", img)

    cv2.imshow("Setup Zones", img)
    cv2.setMouseCallback("Setup Zones", draw_roi)
    print(">> [STEP 1] 클릭으로 다각형 생성 -> 's'로 저장 -> 'q'로 완료")
    
    while True:
        k = cv2.waitKey(1) & 0xFF
        if k == ord('s') and len(pts) > 2:
            z_name = f"ZONE_{len(zones)+1}"
            zones[z_name] = {"points": np.array(pts, np.int32), "threshold": 5.0}
            pts.clear()
            print(f"{z_name} 구역 저장됨!")
        elif k == ord('q'): break
    cv2.destroyWindow("Setup Zones")

# --- 3. 메인 분석 실행 ---
cap = cv2.VideoCapture(video_path)
if cap.isOpened():
    ret, frame = cap.read()
    if ret: setup_zones(frame)

# [추가] FPS와 skip_frames 변수를 다시 선언합니다.
fps = cap.get(cv2.CAP_PROP_FPS)
skip_frames = int(fps * 5)

frame_skip_interval = 2
frame_count = 0

# ===== [추가] ID 깜빡임 및 시간 초기화 방지 변수 =====
id_mapping = {}

print(">> [STEP 2] 실시간 분석 시작... (a/d: 5초 이동, q: 종료)")
while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    # [설정] 2. 프레임 카운트 증가 및 건너뛰기 로직
    frame_count += 1
    if frame_count % frame_skip_interval != 0:
        continue 

    # [추가 및 변경] 3. 해상도를 목표 해상도로 조정합니다.
    # 이전 640x360에서 960x540으로 키워 인식률 개선을 도모합니다.
    frame = cv2.resize(frame, (TARGET_WIDTH, TARGET_HEIGHT)) 
    
    # YOLO & MediaPipe 처리
    yolo_res = model.track(frame, persist=True, verbose=False, classes=0, conf=0.25, iou=0.3)[0]
    pose_res = mp_pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    
    annotated = yolo_res.plot()
    current_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

    if pose_res.pose_landmarks:
        mp_drawing.draw_landmarks(annotated, pose_res.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS)

    if yolo_res.boxes.id is not None:
        boxes = yolo_res.boxes.xyxy.cpu().numpy()
        ids = yolo_res.boxes.id.cpu().numpy().astype(int)
        
        # 조정된 해상도를 가져옵니다. (TARGET_WIDTH, TARGET_HEIGHT 사용)
        h, w = TARGET_HEIGHT, TARGET_WIDTH

        for (x1, y1, x2, y2), t_id in zip(boxes, ids):
            
            # ===== [기존 기능 유지] 뼈대 좌표 교차 검증 (이불 덮은 사람 고려) =====
            has_skeleton = False
            if pose_res.pose_landmarks:
                lm = pose_res.pose_landmarks.landmark
                for joint_idx in [0, 2, 5, 11, 12, 23, 24]:
                    jx = int(lm[joint_idx].x * w)
                    jy = int(lm[joint_idx].y * h)
                    
                    if (x1 <= jx <= x2) and (y1 <= jy <= y2) and (lm[joint_idx].visibility > 0.3):
                        has_skeleton = True
                        break
            
            if not has_skeleton:
                continue
            # ========================================================
            
            # ===== [새로운 기능 추가] ID 기억력 로직 (끊긴 ID 이어붙이기) =====
            master_id = int(t_id)
            if master_id in id_mapping:
                # 이미 기억된 ID라면 (예전 번호로 강제 변환)
                master_id = id_mapping[master_id]
            else:
                # 처음 보는 ID라면, 최근 20초 내에 놓쳤던 예전 사람이 있는지 확인
                for existing_id, tk_data in trackers.items():
                    time_diff = current_sec - tk_data.get('last_seen', 0)
                    if 0 < time_diff < 20.0:  # 20초 안에 화면에서 사라졌던 사람이라면
                        master_id = existing_id
                        id_mapping[int(t_id)] = master_id # 새로 부여된 ID를 예전 ID로 묶어줌
                        break
            # ========================================================

            feet_pos = (int((x1 + x2) / 2), int(y2))
            
            # --- [1] 현재 프레임의 자세 판별 (비율 기반 누운 자세 판별로 수정) ---
            raw_posture = "UNKNOWN"
            if pose_res.pose_landmarks:
                lm = pose_res.pose_landmarks.landmark
                
                # 조건 A: YOLO 바운딩 박스가 가로로 1.2배 이상 길면 누운 것으로 간주
                is_box_lying = (x2 - x1) > (y2 - y1) * 1.2
                
                # 조건 B: 화면 비율이 아닌, '몸 자체의 비율'로 판단 (거리 상관없이 정확함)
                is_landmark_lying = False
                if lm[11].visibility > 0.3 and lm[23].visibility > 0.3:
                    # 왼쪽 어깨(11)와 골반(23) 사이의 세로 거리와 가로 거리를 비교
                    y_dist = abs(lm[11].y - lm[23].y) # 세로 거리
                    x_dist = abs(lm[11].x - lm[23].x) # 가로 거리
                    
                    # 어깨와 골반의 세로 거리보다 가로 거리가 더 길다면 가로로 누워있는 상태!
                    if y_dist < x_dist: 
                        is_landmark_lying = True

                # A나 B 둘 중 하나라도 만족하면 누운 상태
                if is_box_lying or is_landmark_lying: 
                    raw_posture = "LYING"
                elif abs(lm[25].y - lm[23].y) < abs(lm[23].y - lm[11].y) * 0.7: 
                    raw_posture = "SITTING"
                else: 
                    raw_posture = "STANDING"

            # --- [2] 현재 프레임의 구역 판별 ---
            current_zone = "NONE"
            for z_name, info in zones.items():
                if cv2.pointPolygonTest(info['points'], feet_pos, False) >= 0:
                    current_zone = z_name
                    break

            # --- [3] 상태 추적기(Tracker) 초기화 (t_id 대신 master_id 사용) ---
            if master_id not in trackers:
                trackers[master_id] = {
                    'current_activity': raw_posture,
                    'current_zone': current_zone,
                    'state_start_time': current_sec,
                    'candidate_activity': raw_posture,
                    'candidate_start_time': current_sec,
                    'summary': {'SITTING': 0.0, 'LYING': 0.0, 'STANDING': 0.0, 'UNKNOWN': 0.0},
                    'transition_count': 0,
                    'last_seen': current_sec  # [기억력 추가] 마지막 목격 시간
                }
            
            tk = trackers[master_id]
            tk['last_seen'] = current_sec  # [기억력 추가] 화면에 보일 때마다 목격 시간 갱신

            # --- [4] 자세 유지 디바운싱 로직 ---
            if raw_posture != tk['candidate_activity']:
                tk['candidate_activity'] = raw_posture
                tk['candidate_start_time'] = current_sec
            
            confirmed_posture = tk['current_activity']
            if (current_sec - tk['candidate_start_time']) >= TRANSITION_THRESHOLD_SEC:
                confirmed_posture = tk['candidate_activity']

            # --- [5] 상태 변경 및 로그 저장 (t_id 대신 master_id 저장) ---
            if confirmed_posture != tk['current_activity'] or current_zone != tk['current_zone']:
                if confirmed_posture != tk['current_activity']:
                    transition_logs.append({
                        "id": master_id,
                        "from_activity": tk['current_activity'],
                        "to_activity": confirmed_posture,
                        "timestamp": get_time_str(current_sec)
                    })
                    tk['transition_count'] += 1

                stay_time = current_sec - tk['state_start_time']
                state_logs.append({
                    "id": master_id,
                    "start_time": get_time_str(tk['state_start_time']),
                    "end_time": get_time_str(current_sec),
                    "activity": tk['current_activity'],
                    "zone": tk['current_zone'],
                    "stay_time": round(stay_time, 1),
                    "Source": "Camera"
                })

                if tk['current_activity'] in tk['summary']:
                    tk['summary'][tk['current_activity']] += stay_time

                tk['current_activity'] = confirmed_posture
                tk['current_zone'] = current_zone
                tk['state_start_time'] = current_sec

            # --- [6] 화면 출력 (기존 화면 밖 잘림 방지 기능 유지) ---
            current_stay_time = current_sec - tk['state_start_time']
            is_warn = current_zone in zones and current_stay_time >= zones[current_zone]['threshold']
            
            text_y1 = int(y1) - 40 
            text_y2 = int(y1) - 10 
            
            if y1 < 70: 
                text_y1 = int(y1) + 40
                text_y2 = int(y1) + 70

            cv2.putText(annotated, f"Zone Stay: {current_stay_time:.1f}s", (int(x1), text_y1),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255) if is_warn else (0, 255, 255), 2)
            
            color = (0, 0, 255) if is_warn else (0, 255, 0)
            cv2.putText(annotated, f"ID:{master_id} {confirmed_posture}", (int(x1), text_y2), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # 구역 그리기 및 화면 출력 (TARGET_WIDTH, TARGET_HEIGHT 사용)
    for info in zones.values(): 
        cv2.polylines(annotated, [info['points']], True, (255, 0, 0), 2)
    cv2.imshow("Advanced Home Cam AI", annotated)
    
    k = cv2.waitKey(1) & 0xFF
    if k == ord('q'): break
    elif k in [ord('a'), ord('d')]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, cap.get(cv2.CAP_PROP_POS_FRAMES) + (skip_frames if k == ord('d') else -skip_frames))

# --- 4. 영상 종료 후 남은 상태 기록 및 정리 ---
for t_id, tk in trackers.items():
    stay_time = current_sec - tk['state_start_time']
    # 마지막 닫히지 않은 상태 저장
    state_logs.append({
        "id": int(t_id),
        "start_time": get_time_str(tk['state_start_time']),
        "end_time": get_time_str(current_sec),
        "activity": tk['current_activity'],
        "zone": tk['current_zone'],
        "stay_time": round(stay_time, 1),
        "Source": "Camera"
    })
    if tk['current_activity'] in tk['summary']:
        tk['summary'][tk['current_activity']] += stay_time

    # 요약 로그 생성
    summary_logs.append({
        "id": int(t_id),
        "total_sitting": format_duration(tk['summary']['SITTING']),
        "total_lying": format_duration(tk['summary']['LYING']),
        "total_standing": format_duration(tk['summary']['STANDING']),
        "transition_count": tk['transition_count']
    })

cap.release()
cv2.destroyAllWindows()

# --- 5. JSON 파일 저장 ---
with open('state_log.json', 'w', encoding='utf-8') as f:
    json.dump(state_logs, f, indent=4, ensure_ascii=False)
with open('transition_log.json', 'w', encoding='utf-8') as f:
    json.dump(transition_logs, f, indent=4, ensure_ascii=False)
with open('summary_log.json', 'w', encoding='utf-8') as f:
    json.dump(summary_logs, f, indent=4, ensure_ascii=False)

print("분석 완료! (state_log.json, transition_log.json, summary_log.json 파일 저장됨)")

# --- 6. 종합 통계 그래프 출력 (Matplotlib) ---
if trackers:
    ids = list(trackers.keys())
    activities = ['SITTING', 'LYING', 'STANDING']
    
    fig, ax = plt.subplots(figsize=(10, 6))
    bottom = np.zeros(len(ids))
    
    # 시간 단위(초)를 분(Minute)으로 변환하여 누적 막대그래프 생성
    colors = {'SITTING': '#4CAF50', 'LYING': '#2196F3', 'STANDING': '#FFC107'}
    
    for act in activities:
        # 각 ID별 해당 활동의 시간을 분 단위로 추출
        durations = [trackers[i]['summary'][act] / 60.0 for i in ids]
        ax.bar([f"ID {i}" for i in ids], durations, label=act, bottom=bottom, color=colors[act])
        bottom += np.array(durations)
        
    ax.set_ylabel("Total Time (Minutes)")
    ax.set_title("Total Activity Time per Person")
    ax.legend()
    plt.tight_layout()
    plt.show()
else:
    print("감지된 객체가 없어 그래프를 출력하지 않습니다.")