import cv2
import json
import time
import numpy as np
import datetime
from ultralytics import YOLO
import mediapipe as mp
import matplotlib.pyplot as plt
import threading

# --- 실시간 딜레이 제거를 위한 백그라운드 프레임 읽기 클래스 ---
class VideoCaptureThreading:
    def __init__(self, src):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ret, self.frame = self.cap.read()
        self.running = True
        
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True 
        self.thread.start()

    def update(self):
        while self.running:
            try:
                ret, frame = self.cap.read()
                if ret:
                    self.frame = frame
                else:
                    time.sleep(0.01) 
            except Exception as e:
                break 

    def read(self):
        return True, self.frame

    def release(self):
        self.running = False 
        if self.thread.is_alive():
            self.thread.join(timeout=1.0) 
        self.cap.release()

    def isOpened(self):
        return self.cap.isOpened()

# --- 1. 기본 설정 및 초기화 ---
# 🔥 수정됨: YOLO 모델 경로를 models/ 폴더로 변경
model = YOLO('models/yolov8n.pt') 
mp_pose = mp.solutions.pose.Pose(model_complexity=1)
mp_drawing = mp.solutions.drawing_utils

# IP Webcam 주소 입력 (본인 스마트폰 화면의 IPv4 주소로 변경)
video_path = 'http://192.168.0.248:8080/video'  # 401 = 192.168.0.241:8080, 501 = 192.168.0.248:8080

zones = {}
state_logs = []
transition_logs = []
summary_logs = []
trackers = {}
TRANSITION_THRESHOLD_SEC = 1.0  

TARGET_WIDTH = 960
TARGET_HEIGHT = 540

def format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h}h {m}m {s}s"
    elif m > 0: return f"{m}m {s}s"
    else: return f"{s}s"

def setup_zones(first_frame):
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
cap = VideoCaptureThreading(video_path)

if cap.isOpened():
    ret, frame = cap.read()
    if ret: setup_zones(frame)

frame_skip_interval = 3 
frame_count = 0
id_mapping = {}

print(">> [STEP 2] 실시간 분석 시작... (q: 종료)")

start_time_real = time.time()

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: 
        print("스트림이 끊겼거나 카메라 연결이 종료되었습니다.")
        break

    frame_count += 1
    if frame_count % frame_skip_interval != 0:
        continue 

    frame = cv2.resize(frame, (TARGET_WIDTH, TARGET_HEIGHT)) 
    
    yolo_res = model.track(frame, persist=True, verbose=False, classes=0, conf=0.4, iou=0.3)[0]
    pose_res = mp_pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    
    annotated = yolo_res.plot()
    current_sec = time.time() - start_time_real

    if pose_res.pose_landmarks:
        mp_drawing.draw_landmarks(annotated, pose_res.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS)

    if yolo_res.boxes.id is not None:
        boxes = yolo_res.boxes.xyxy.cpu().numpy()
        ids = yolo_res.boxes.id.cpu().numpy().astype(int)
        h, w = TARGET_HEIGHT, TARGET_WIDTH

        for (x1, y1, x2, y2), t_id in zip(boxes, ids):
            has_skeleton = False
            if pose_res.pose_landmarks:
                lm = pose_res.pose_landmarks.landmark
                for joint_idx in [0, 2, 5, 11, 12, 23, 24]:
                    jx = int(lm[joint_idx].x * w)
                    jy = int(lm[joint_idx].y * h)
                    if (x1 <= jx <= x2) and (y1 <= jy <= y2) and (lm[joint_idx].visibility > 0.3):
                        has_skeleton = True
                        break
            
            if not has_skeleton: continue
            
            master_id = int(t_id)
            if master_id in id_mapping:
                master_id = id_mapping[master_id]
            else:
                for existing_id, tk_data in trackers.items():
                    time_diff = current_sec - tk_data.get('last_seen', 0)
                    if 0 < time_diff < 20.0: 
                        master_id = existing_id
                        id_mapping[int(t_id)] = master_id 
                        break

            feet_pos = (int((x1 + x2) / 2), int(y2))
            
            raw_posture = "UNKNOWN"
            if pose_res.pose_landmarks:
                lm = pose_res.pose_landmarks.landmark
                
                is_box_lying = (x2 - x1) > (y2 - y1) * 1.2
                is_landmark_lying = False
                
                if lm[11].visibility > 0.3 and lm[23].visibility > 0.3:
                    y_dist = abs(lm[11].y - lm[23].y) 
                    x_dist = abs(lm[11].x - lm[23].x) 
                    
                    if y_dist < x_dist: 
                        is_landmark_lying = True

                    if y_dist > x_dist and lm[11].y < lm[23].y:
                        is_box_lying = False 
                        is_landmark_lying = False

                if is_box_lying or is_landmark_lying: 
                    raw_posture = "LYING"
                elif abs(lm[25].y - lm[23].y) < abs(lm[23].y - lm[11].y) * 0.7: 
                    raw_posture = "SITTING"
                else: 
                    raw_posture = "STANDING"

            current_zone = "NONE"
            for z_name, info in zones.items():
                if cv2.pointPolygonTest(info['points'], feet_pos, False) >= 0:
                    current_zone = z_name
                    break

            if master_id not in trackers:
                trackers[master_id] = {
                    'current_activity': raw_posture,
                    'current_zone': current_zone,
                    'state_start_time': current_sec,
                    'start_time_str': datetime.datetime.now().strftime("%H:%M:%S"), # 시작 시간 박제
                    'candidate_activity': raw_posture,
                    'candidate_start_time': current_sec,
                    'summary': {'SITTING': 0.0, 'LYING': 0.0, 'STANDING': 0.0, 'UNKNOWN': 0.0},
                    'transition_count': 0,
                    'last_seen': current_sec
                }
            
            tk = trackers[master_id]
            tk['last_seen'] = current_sec

            if raw_posture != tk['candidate_activity']:
                tk['candidate_activity'] = raw_posture
                tk['candidate_start_time'] = current_sec
            
            confirmed_posture = tk['current_activity']
            if (current_sec - tk['candidate_start_time']) >= TRANSITION_THRESHOLD_SEC:
                confirmed_posture = tk['candidate_activity']

            if confirmed_posture != tk['current_activity'] or current_zone != tk['current_zone']:
                end_time_str = datetime.datetime.now().strftime("%H:%M:%S") # 상태 종료 시간 박제
                
                if confirmed_posture != tk['current_activity']:
                    transition_logs.append({
                        "id": master_id,
                        "from_activity": tk['current_activity'],
                        "to_activity": confirmed_posture,
                        "timestamp": end_time_str
                    })
                    tk['transition_count'] += 1

                stay_time = current_sec - tk['state_start_time']
                state_logs.append({
                    "id": master_id,
                    "start_time": tk['start_time_str'],
                    "end_time": end_time_str,
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
                tk['start_time_str'] = end_time_str # 다음 행동을 위한 시작 시간 리셋

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

    for info in zones.values(): 
        cv2.polylines(annotated, [info['points']], True, (255, 0, 0), 2)
    cv2.imshow("Advanced Home Cam AI", annotated)
    
    k = cv2.waitKey(1) & 0xFF
    if k == ord('q'): break

# --- 4. 영상 종료 후 남은 상태 기록 및 정리 ---
for t_id, tk in trackers.items():
    stay_time = current_sec - tk['state_start_time']
    end_time_str = datetime.datetime.now().strftime("%H:%M:%S")
    
    state_logs.append({
        "id": int(t_id),
        "start_time": tk['start_time_str'],
        "end_time": end_time_str,
        "activity": tk['current_activity'],
        "zone": tk['current_zone'],
        "stay_time": round(stay_time, 1),
        "Source": "Camera"
    })
    if tk['current_activity'] in tk['summary']:
        tk['summary'][tk['current_activity']] += stay_time

    summary_logs.append({
        "id": int(t_id),
        "total_sitting": format_duration(tk['summary']['SITTING']),
        "total_lying": format_duration(tk['summary']['LYING']),
        "total_standing": format_duration(tk['summary']['STANDING']),
        "transition_count": tk['transition_count']
    })

cap.release()
cv2.destroyAllWindows()

# 🔥 수정됨: JSON 파일 3개가 모두 data 폴더 안에 저장되도록 경로 변경
with open('data/state_log.json', 'w', encoding='utf-8') as f:
    json.dump(state_logs, f, indent=4, ensure_ascii=False)
with open('data/transition_log.json', 'w', encoding='utf-8') as f:
    json.dump(transition_logs, f, indent=4, ensure_ascii=False)
with open('data/summary_log.json', 'w', encoding='utf-8') as f:
    json.dump(summary_logs, f, indent=4, ensure_ascii=False)

print("분석 완료! (data 폴더 내에 state, transition, summary 로그 저장됨)")