import cv2
import json
import time
import math
from datetime import datetime
from ultralytics import YOLO
import mediapipe as mp


# 1. YOLO 및 MediaPipe 초기화
# 🔥 수정됨: YOLO 모델 경로를 models/ 폴더로 변경
model = YOLO('models/yolov8n.pt') 
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    static_image_mode=False  # 👈 실시간 영상 스트리밍 모드임을 명시!
)

video_path = 0 # 웹캠
cap = cv2.VideoCapture(video_path)
log_data = []

log_interval = 10.0  # 10초마다 기록
last_log_time = time.time()

# 2. 눈 사이 거리(EAR) 계산 함수
def calculate_ear(eye_landmarks):
    # 눈꺼풀 위아래 거리 계산
    vertical_1 = math.dist((eye_landmarks[1].x, eye_landmarks[1].y), (eye_landmarks[5].x, eye_landmarks[5].y))
    vertical_2 = math.dist((eye_landmarks[2].x, eye_landmarks[2].y), (eye_landmarks[4].x, eye_landmarks[4].y))
    # 눈 양끝 가로 거리 계산
    horizontal = math.dist((eye_landmarks[0].x, eye_landmarks[0].y), (eye_landmarks[3].x, eye_landmarks[3].y))
    
    if horizontal == 0:
        return 0
    ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
    return ear

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # MediaPipe 분석을 위해 RGB로 변환
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # 현재 시간 (초 단위)
    current_time_sec = time.time()

    if current_time_sec - last_log_time >= log_interval:
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1차: YOLO로 사람(바운딩 박스) 탐지
        yolo_results = model(frame, classes=0, verbose=False)
        person_detected = False
        
        # 2차: MediaPipe로 얼굴 랜드마크 탐지 및 눈 상태 분석
        mesh_results = face_mesh.process(rgb_frame)
        eye_status = "unknown" # 기본값

        if mesh_results.multi_face_landmarks:
            for face_landmarks in mesh_results.multi_face_landmarks:
                # 왼쪽 눈 랜드마크 인덱스 (MediaPipe 기준)
                left_eye_indices = [362, 385, 387, 263, 373, 380]
                left_eye_points = [face_landmarks.landmark[i] for i in left_eye_indices]
                
                # 오른쪽 눈 랜드마크 인덱스
                right_eye_indices = [33, 160, 158, 133, 153, 144]
                right_eye_points = [face_landmarks.landmark[i] for i in right_eye_indices]

                # 양쪽 눈의 EAR 계산
                left_ear = calculate_ear(left_eye_points)
                right_ear = calculate_ear(right_eye_points)
                avg_ear = (left_ear + right_ear) / 2.0

                # EAR 임계값(Threshold) 설정: 보통 0.2 ~ 0.25 미만이면 눈 감은 것으로 판단
                if avg_ear < 0.22: 
                    eye_status = "eyes_closed"
                else:
                    eye_status = "eyes_open"
                
                # 디버깅용 화면 텍스트 (옵션)
                cv2.putText(frame, f"Eye Status: {eye_status}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # 로그 기록 (YOLO로 사람이 인식되었을 때만)
        for result in yolo_results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                confidence = box.conf[0].item()

                activity_log = {
                    "timestamp": current_time_str,
                    "type": "physical_activity",
                    "object": "person",
                    "confidence": round(confidence, 2),
                    "location": {
                        "x1": round(x1, 2), "y1": round(y1, 2),
                        "x2": round(x2, 2), "y2": round(y2, 2)
                    },
                    "status": eye_status # 👈 추가된 상태 기록!
                }
                log_data.append(activity_log)
                person_detected = True
        
        if person_detected:
            last_log_time = current_time_sec 

    # YOLO 바운딩 박스를 화면에 그려줌
    annotated_frame = model(frame, classes=0, verbose=False)[0].plot()
    # (위에서 추가한 눈 상태 텍스트가 덮어씌워지지 않도록 다시 그리기)
    if 'eye_status' in locals():
         cv2.putText(annotated_frame, f"Status: {eye_status}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    cv2.imshow("Vision AI with Status", annotated_frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# 🔥 수정됨: JSON 파일 저장 경로를 data 폴더로 변경
with open('data/webcam_activitylog.json', 'w', encoding='utf-8') as f:
    json.dump(log_data, f, indent=4, ensure_ascii=False)

print("JSON 로그 추출 완료! (data/webcam_activitylog.json 파일 저장됨)")