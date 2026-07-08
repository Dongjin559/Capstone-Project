import cv2
import json
import os
import time
import numpy as np
import datetime
from ultralytics import YOLO
import mediapipe as mp
import threading

# --- 입력 소스 및 해상도 설정 ---
video_path = 'http://172.30.1.42:8080/video'  # IP Webcam 주소 또는 카메라 스트림 URL
TARGET_WIDTH = 960
TARGET_HEIGHT = 540

# --- 딜레이 제거 멀티 스레딩 ---
class VideoCaptureThreading:
    def __init__(self, src):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ret, self.frame = self.cap.read()
        self.running = True
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()

    def update(self):
        while self.running:
            try:
                ret, frame = self.cap.read()
                if ret:
                    self.frame = frame
                else:
                    time.sleep(0.01)
            except Exception:
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


class ZoneManager:
    def __init__(self, threshold=5.0):
        self.zones = {}
        self.threshold = threshold

    def add_zone(self, points):
        zone_name = f"ZONE_{len(self.zones) + 1}"
        self.zones[zone_name] = {"points": np.array(points, np.int32), "threshold": self.threshold}
        return zone_name

    def find_zone(self, point):
        for zone_name, info in self.zones.items():
            if cv2.pointPolygonTest(info["points"], point, False) >= 0:
                return zone_name
        return "NONE"

    def draw(self, image):
        for info in self.zones.values():
            cv2.polylines(image, [info["points"]], True, (255, 0, 0), 2)


class TrackerManager:
    def __init__(self, transition_threshold):
        self.transition_threshold = transition_threshold
        self.trackers = {}
        self.state_logs = []
        self.transition_logs = []
        self.summary_logs = []

    def _create_tracker(self, master_id, raw_posture, current_zone, current_sec):
        return {
            "current_activity": raw_posture,
            "current_zone": current_zone,
            "state_start_time": current_sec,
            "start_time_str": datetime.datetime.now().strftime("%H:%M:%S"),
            "candidate_activity": raw_posture,
            "candidate_start_time": current_sec,
            "summary": {"SITTING": 0.0, "LYING": 0.0, "STANDING": 0.0, "UNKNOWN": 0.0},
            "transition_count": 0,
            "last_seen": current_sec,
        }

    def register_or_get(self, master_id, raw_posture, current_zone, current_sec):
        tracker = self.trackers.get(master_id)
        if tracker is None:
            tracker = self._create_tracker(master_id, raw_posture, current_zone, current_sec)
            self.trackers[master_id] = tracker
        tracker["last_seen"] = current_sec

        if raw_posture != tracker["candidate_activity"]:
            tracker["candidate_activity"] = raw_posture
            tracker["candidate_start_time"] = current_sec

        confirmed_posture = tracker["current_activity"]
        if current_sec - tracker["candidate_start_time"] >= self.transition_threshold:
            confirmed_posture = tracker["candidate_activity"]

        if confirmed_posture != tracker["current_activity"] or current_zone != tracker["current_zone"]:
            self._record_state_change(master_id, tracker, confirmed_posture, current_zone, current_sec)

        return tracker

    def _record_state_change(self, master_id, tracker, confirmed_posture, current_zone, current_sec):
        end_time_str = datetime.datetime.now().strftime("%H:%M:%S")
        stay_time = current_sec - tracker["state_start_time"]

        if tracker["current_activity"] in tracker["summary"]:
            tracker["summary"][tracker["current_activity"]] += stay_time

        self.state_logs.append(
            {
                "id": master_id,
                "start_time": tracker["start_time_str"],
                "end_time": end_time_str,
                "activity": tracker["current_activity"],
                "zone": tracker["current_zone"],
                "stay_time": round(stay_time, 1),
                "Source": "Camera",
            }
        )

        if confirmed_posture != tracker["current_activity"]:
            tracker["transition_count"] += 1
            self.transition_logs.append(
                {
                    "id": master_id,
                    "from_activity": tracker["current_activity"],
                    "to_activity": confirmed_posture,
                    "timestamp": end_time_str,
                }
            )

        tracker["current_activity"] = confirmed_posture
        tracker["current_zone"] = current_zone
        tracker["state_start_time"] = current_sec
        tracker["start_time_str"] = end_time_str

    def finalize(self, current_sec):
        for master_id, tracker in self.trackers.items():
            stay_time = current_sec - tracker["state_start_time"]
            end_time_str = datetime.datetime.now().strftime("%H:%M:%S")

            if tracker["current_activity"] in tracker["summary"]:
                tracker["summary"][tracker["current_activity"]] += stay_time

            self.state_logs.append(
                {
                    "id": master_id,
                    "start_time": tracker["start_time_str"],
                    "end_time": end_time_str,
                    "activity": tracker["current_activity"],
                    "zone": tracker["current_zone"],
                    "stay_time": round(stay_time, 1),
                    "Source": "Camera",
                }
            )
            self.summary_logs.append(
                {
                    "id": master_id,
                    "total_sitting": format_duration(tracker["summary"]["SITTING"]),
                    "total_lying": format_duration(tracker["summary"]["LYING"]),
                    "total_standing": format_duration(tracker["summary"]["STANDING"]),
                    "transition_count": tracker["transition_count"],
                }
            )

    def assign_ids(self, detected_id, current_sec, max_gap=20.0):
        for existing_id, tracker in self.trackers.items():
            last_seen = tracker.get("last_seen", 0)
            if 0 < current_sec - last_seen < max_gap:
                return existing_id
        return detected_id


def format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def setup_zones(first_frame, zone_manager):
    display_frame = cv2.resize(first_frame, (TARGET_WIDTH, TARGET_HEIGHT))
    points = []

    def draw_roi(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append([x, y])
            cv2.circle(display_frame, (x, y), 5, (0, 0, 255), -1)
            if len(points) > 1:
                cv2.line(display_frame, tuple(points[-2]), tuple(points[-1]), (0, 255, 0), 2)
            cv2.imshow("Setup Zones", display_frame)

    cv2.imshow("Setup Zones", display_frame)
    cv2.setMouseCallback("Setup Zones", draw_roi)
    print(">> [STEP 1] 클릭으로 다각형 생성 -> 's'로 저장 -> 'q'로 완료")

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord("s") and len(points) > 2:
            zone_name = zone_manager.add_zone(points)
            points.clear()
            print(f"{zone_name} 구역 저장됨!")
        elif key == ord("q"):
            break

    cv2.destroyWindow("Setup Zones")


def has_skeleton_in_bbox(pose_landmarks, bbox, width, height):
    if pose_landmarks is None:
        return False

    x1, y1, x2, y2 = bbox
    for joint_idx in [0, 2, 5, 11, 12, 23, 24]:
        landmark = pose_landmarks.landmark[joint_idx]
        if landmark.visibility <= 0.3:
            continue

        px = int(landmark.x * width)
        py = int(landmark.y * height)
        if x1 <= px <= x2 and y1 <= py <= y2:
            return True

    return False


def classify_posture(pose_landmarks, bbox):
    if pose_landmarks is None:
        return "UNKNOWN"

    lm = pose_landmarks.landmark
    x1, y1, x2, y2 = bbox
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
        return "LYING"

    if abs(lm[25].y - lm[23].y) < abs(lm[23].y - lm[11].y) * 0.7:
        return "SITTING"

    return "STANDING"


def draw_detection_info(annotated, bbox, master_id, posture, current_stay_time, is_warn):
    x1, y1, _, _ = bbox
    top_y = int(y1) - 40
    label_y = int(y1) - 10
    if y1 < 70:
        top_y = int(y1) + 40
        label_y = int(y1) + 70

    color = (0, 0, 255) if is_warn else (0, 255, 0)
    cv2.putText(
        annotated,
        f"Zone Stay: {current_stay_time:.1f}s",
        (int(x1), top_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255) if is_warn else (0, 255, 255),
        2,
    )
    cv2.putText(
        annotated,
        f"ID:{master_id} {posture}",
        (int(x1), label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        color,
        2,
    )


def save_logs(state_logs, transition_logs, summary_logs):
    os.makedirs("data", exist_ok=True)
    with open("data/state_log.json", "w", encoding="utf-8") as f:
        json.dump(state_logs, f, indent=4, ensure_ascii=False)
    with open("data/transition_log.json", "w", encoding="utf-8") as f:
        json.dump(transition_logs, f, indent=4, ensure_ascii=False)
    with open("data/summary_log.json", "w", encoding="utf-8") as f:
        json.dump(summary_logs, f, indent=4, ensure_ascii=False)


def main():
    model = YOLO("models/yolov8n.pt")
    mp_pose = mp.solutions.pose.Pose(model_complexity=1)
    mp_drawing = mp.solutions.drawing_utils

    zone_manager = ZoneManager()
    tracker_manager = TrackerManager(transition_threshold=1.0)
    id_mapping = {}

    cap = VideoCaptureThreading(video_path)
    if not cap.isOpened():
        print("카메라를 열 수 없습니다. video_path를 확인하세요.")
        return

    ret, frame = cap.read()
    if ret:
        setup_zones(frame, zone_manager)

    frame_skip_interval = 3
    frame_count = 0
    start_time_real = time.time()

    print(">> [STEP 2] 실시간 분석 시작... (q: 종료)")

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
            for (x1, y1, x2, y2), detection_id in zip(boxes, ids):
                bbox = (x1, y1, x2, y2)
                if not has_skeleton_in_bbox(pose_res.pose_landmarks, bbox, TARGET_WIDTH, TARGET_HEIGHT):
                    continue

                master_id = id_mapping.get(int(detection_id))
                if master_id is None:
                    master_id = tracker_manager.assign_ids(int(detection_id), current_sec)
                    id_mapping[int(detection_id)] = master_id

                raw_posture = classify_posture(pose_res.pose_landmarks, bbox)
                feet_pos = (int((x1 + x2) / 2), int(y2))
                current_zone = zone_manager.find_zone(feet_pos)

                tracker = tracker_manager.register_or_get(master_id, raw_posture, current_zone, current_sec)
                current_stay_time = current_sec - tracker["state_start_time"]
                is_warn = current_zone in zone_manager.zones and current_stay_time >= zone_manager.zones[current_zone]["threshold"]
                draw_detection_info(annotated, bbox, master_id, tracker["current_activity"], current_stay_time, is_warn)

        zone_manager.draw(annotated)
        cv2.imshow("Advanced Home Cam AI", annotated)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    tracker_manager.finalize(time.time() - start_time_real)
    cap.release()
    cv2.destroyAllWindows()
    save_logs(tracker_manager.state_logs, tracker_manager.transition_logs, tracker_manager.summary_logs)
    print("분석 완료! (data 폴더 내에 state, transition, summary 로그 저장됨)")


if __name__ == "__main__":
    main()
