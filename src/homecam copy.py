import cv2
import json
import time
import numpy as np
from ultralytics import YOLO
import mediapipe as mp

# 1. 초기화 (YOLOv8 + MediaPipe)
model = YOLO('models/yolov8s.pt')
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(
    static_image_mode=False, 
    model_complexity=1,          
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# ⭐ 복구됨: 뼈대 그리기 도구
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# --- 설정 변수 ---
video_path = 'samples/sample_video.mp4'
zones = {}           
current_points = []  
stay_tracker = {}    
log_data = []
log_interval = 5.0   
last_log_time = 0.0

# --- [기능 1] 마우스 클릭 구역 설정 함수 ---
def select_roi(event, x, y, flags, param):
    global current_points
    if event == cv2.EVENT_LBUTTONDOWN:
        current_points.append([x, y])
        cv2.circle(img_setup, (x, y), 5, (0, 0, 255), -1)
        if len(current_points) > 1:
            cv2.line(img_setup, tuple(current_points[-2]), tuple(current_points[-1]), (0, 255, 0), 2)
        cv2.imshow("Setup Zones", img_setup)

# --- [기능 2] 자세 판별 함수 ---
def classify_posture(landmarks, bbox_w, bbox_h):
    shoulder_y = (landmarks[11].y + landmarks[12].y) / 2.0
    hip_y = (landmarks[23].y + landmarks[24].y) / 2.0
    knee_y = (landmarks[25].y + landmarks[26].y) / 2.0
    
    if bbox_w > bbox_h * 1.5: return "lying_down"
    
    torso_length = abs(hip_y - shoulder_y)
    thigh_length = abs(knee_y - hip_y)
    if thigh_length < torso_length * 0.7: return "sitting"
    return "standing"

# --- 단계 1: 구역 설정 모드 ---
cap = cv2.VideoCapture(video_path)
ret, frame = cap.read()
if not ret:
    print("비디오를 불러올 수 없습니다.")
    exit()

# 프레임 건너뛰기 계산 (영상의 FPS 기준 5초)
fps = cap.get(cv2.CAP_PROP_FPS)      
skip_frames = int(fps * 5)           

img_setup = frame.copy()
cv2.imshow("Setup Zones", img_setup)
cv2.setMouseCallback("Setup Zones", select_roi)

print(">> [STEP 1] 구역 설정: 클릭으로 다각형 생성 -> 's'키로 저장 -> 완료되면 'q'키")
while True:
    key = cv2.waitKey(1) & 0xFF
    if key == ord('s') and len(current_points) > 2:
        z_name = f"Zone_{len(zones)+1}"
        zones[z_name] = {"points": np.array(current_points, np.int32), "threshold": 5.0}
        print(f"{z_name} 저장됨!")
        current_points = []
    elif key == ord('q'): break
cv2.destroyWindow("Setup Zones")

# --- 단계 2: 메인 분석 모드 ---
print(">> [STEP 2] 실시간 분석 시작... (a: 5초 뒤로, d: 5초 앞으로, q: 종료)")
while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    # YOLOv8 트래킹 및 MediaPipe 처리
    yolo_results = model.track(frame, persist=True, verbose=False, classes=0)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pose_results = pose.process(rgb_frame)
    
    current_time_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
    
    # ⭐ 복구됨: YOLO 기본 바운딩 박스가 포함된 도화지 사용
    annotated_frame = yolo_results[0].plot()

    # ⭐ 복구됨: 스켈레톤(뼈대) 화면에 그리기
    if pose_results.pose_landmarks:
        mp_drawing.draw_landmarks(
            annotated_frame,                  
            pose_results.pose_landmarks,      
            mp_pose.POSE_CONNECTIONS,         
            landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
        )

    if yolo_results[0].boxes.id is not None:
        boxes = yolo_results[0].boxes.xyxy.cpu().numpy()
        ids = yolo_results[0].boxes.id.cpu().numpy().astype(int)

        for i, track_id in enumerate(ids):
            x1, y1, x2, y2 = boxes[i]
            feet_pos = (int((x1 + x2) / 2), int(y2))
            
            # 1. 자세 분석
            posture = "unknown"
            if pose_results.pose_landmarks:
                posture = classify_posture(pose_results.pose_landmarks.landmark, x2-x1, y2-y1)

            # 2. 구역 및 체류 시간 분석
            in_zone = "none"
            is_warning = False
            for z_name, info in zones.items():
                if cv2.pointPolygonTest(info['points'], feet_pos, False) >= 0:
                    in_zone = z_name
                    if track_id not in stay_tracker: stay_tracker[track_id] = {}
                    if z_name not in stay_tracker[track_id]: stay_tracker[track_id][z_name] = time.time()
                    
                    stay_duration = time.time() - stay_tracker[track_id][z_name]
                    if stay_duration >= info['threshold']:
                        is_warning = True
                    
                    # 체류 시간 표시
                    cv2.putText(annotated_frame, f"Stay: {stay_duration:.1f}s", (int(x1), int(y1)-60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255) if is_warning else (0, 255, 255), 2)

            # 상태 텍스트 출력
            text_color = (0, 0, 255) if is_warning else (0, 255, 0)
            cv2.putText(annotated_frame, f"ID:{track_id} {posture}", (int(x1), int(y1)-30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)

            # 3. 로그 기록
            if current_time_sec - last_log_time >= log_interval:
                log_data.append({
                    "video_sec": round(current_time_sec, 2),
                    "id": int(track_id),
                    "posture": posture,
                    "zone": in_zone,
                    "warning": is_warning
                })
                last_log_time = current_time_sec

    # 구역 선 그리기
    for z_name, info in zones.items():
        cv2.polylines(annotated_frame, [info['points']], True, (255, 0, 0), 2)

    cv2.imshow("Advanced Home Cam AI", annotated_frame)
    
    # ⭐ 복구됨: 키보드 입력 처리 및 프레임 건너뛰기
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):       
        break
    elif key == ord('d'):     
        current_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame + skip_frames)
    elif key == ord('a'):     
        current_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, current_frame - skip_frames))

cap.release()
cv2.destroyAllWindows()

# 🔥 수정됨: JSON 저장 경로를 data 폴더로 지정
with open('data/homecam_advanced_log.json', 'w', encoding='utf-8') as f:
    json.dump(log_data, f, indent=4, ensure_ascii=False)
print("분석 종료 및 로그 저장 완료.")