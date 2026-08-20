import cv2
import json
import time
import threading
import datetime
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from ultralytics import YOLO
import mediapipe as mp
from mediapipe.framework.formats import landmark_pb2


@dataclass(frozen=True)
class CameraConfig:
    camera_id: str = "cam1"
    view_type: str = "side"
    video_path: str = "http://172.30.1.70:8080/video"
    target_width: int = 640
    target_height: int = 480
    frame_skip_interval: int = 2
    yolo_conf: float = 0.45
    yolo_iou: float = 0.35
    yolo_classes: int = 0
    phone_conf: float = 0.2
    phone_imgsz: int = 640
    phone_detection_interval: int = 4
    object_detection_hold_cycles: int = 1
    exercise_window_sec: float = 3.0
    exercise_min_samples: int = 5
    exercise_motion_threshold: float = 1.2
    exercise_min_active_joints: int = 2
    exercise_posture_settle_sec: float = 2.0
    exercise_transition_window_sec: float = 6.0
    squat_min_transitions: int = 3
    arm_exercise_motion_threshold: float = 1.4
    walking_motion_threshold: float = 1.2
    push_up_arm_motion_threshold: float = 0.9
    pose_min_detection_confidence: float = 0.6
    pose_min_tracking_confidence: float = 0.6
    transition_threshold: float = 1.0
    log_save_interval_sec: float = 30.0


CONFIG = CameraConfig(
    camera_id="side_cam",
    video_path="http://172.30.1.70:8080/video",
    view_type="side",
)


class VideoCaptureThreading:
    def __init__(self, src: str) -> None:
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ret, self.frame = self.cap.read()
        self.running = True
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()

    def update(self) -> None:
        while self.running:
            try:
                ret, frame = self.cap.read()
                if ret:
                    self.frame = frame
                else:
                    time.sleep(0.01)
            except Exception:
                break

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        return True, self.frame

    def release(self) -> None:
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.cap.release()

    def isOpened(self) -> bool:
        return self.cap.isOpened()


class TrackerManager:
    def __init__(self, transition_threshold: float) -> None:
        self.transition_threshold = transition_threshold
        self.trackers: Dict[int, Dict[str, Any]] = {}
        self.state_logs: List[Dict[str, Any]] = []
        self.transition_logs: List[Dict[str, Any]] = []
        self.summary_logs: List[Dict[str, Any]] = []

    def _create_tracker(self, master_id: int, raw_posture: str, raw_activity: str, current_sec: float) -> Dict[str, Any]:
        return {
            "current_posture": raw_posture,
            "current_activity": raw_activity,
            "state_start_time": current_sec,
            "start_time_str": datetime.datetime.now().strftime("%H:%M:%S"),
            "candidate_posture": raw_posture,
            "candidate_posture_start_time": current_sec,
            "candidate_posture_streak": 1,
            "candidate_activity": raw_activity,
            "candidate_activity_start_time": current_sec,
            "candidate_activity_streak": 1,
            "posture_summary": {"SITTING": 0.0, "LYING": 0.0, "STANDING": 0.0, "UNKNOWN": 0.0},
            "activity_summary": {
                "IDLE": 0.0,
                "PHONE_USE": 0.0,
                "READING": 0.0,
                "EXERCISING": 0.0,
                "SQUAT": 0.0,
                "ARM_EXERCISE": 0.0,
                "WALKING": 0.0,
                "PUSH_UP": 0.0,
            },
            "transition_count": 0,
            "last_seen": current_sec,
        }

    def register_or_get(self, master_id: int, raw_posture: str, raw_activity: str, current_sec: float) -> Dict[str, Any]:
        tracker = self.trackers.get(master_id)
        if tracker is None:
            tracker = self._create_tracker(master_id, raw_posture, raw_activity, current_sec)
            self.trackers[master_id] = tracker
        tracker["last_seen"] = current_sec

        if raw_posture == "UNKNOWN":
            tracker["candidate_posture_streak"] = 0
        elif raw_posture != tracker["candidate_posture"]:
            tracker["candidate_posture"] = raw_posture
            tracker["candidate_posture_start_time"] = current_sec
            tracker["candidate_posture_streak"] = 1
        else:
            tracker["candidate_posture_streak"] += 1

        if raw_activity != tracker["candidate_activity"]:
            tracker["candidate_activity"] = raw_activity
            tracker["candidate_activity_start_time"] = current_sec
            tracker["candidate_activity_streak"] = 1
        else:
            tracker["candidate_activity_streak"] += 1

        confirmed_posture = tracker["current_posture"]
        if (
            raw_posture != "UNKNOWN"
            and tracker["candidate_posture_streak"] >= 2
            and current_sec - tracker["candidate_posture_start_time"] >= self.transition_threshold
        ):
            confirmed_posture = tracker["candidate_posture"]

        confirmed_activity = tracker["current_activity"]
        if (
            tracker["candidate_activity_streak"] >= 2
            and current_sec - tracker["candidate_activity_start_time"] >= self.transition_threshold
        ):
            confirmed_activity = tracker["candidate_activity"]

        if (
            confirmed_posture != tracker["current_posture"]
            or confirmed_activity != tracker["current_activity"]
        ):
            self._record_state_change(master_id, tracker, confirmed_posture, confirmed_activity, current_sec)

        return tracker

    def _build_state_entry(self, master_id: int, tracker: Dict[str, Any], end_time_str: str, stay_time: float) -> Dict[str, Any]:
        return {
            "id": master_id,
            "start_time": tracker["start_time_str"],
            "end_time": end_time_str,
            "posture": tracker["current_posture"],
            "activity": tracker["current_activity"],
            "stay_time": round(stay_time, 1),
            "Source": "Camera",
        }

    def _build_summary_entry(self, tracker: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "total_sitting": format_duration(tracker["posture_summary"]["SITTING"]),
            "total_lying": format_duration(tracker["posture_summary"]["LYING"]),
            "total_standing": format_duration(tracker["posture_summary"]["STANDING"]),
            "total_phone_use": format_duration(tracker["activity_summary"]["PHONE_USE"]),
            "total_reading": format_duration(tracker["activity_summary"]["READING"]),
            "total_exercising": format_duration(tracker["activity_summary"]["EXERCISING"]),
            "total_squat": format_duration(tracker["activity_summary"]["SQUAT"]),
            "total_arm_exercise": format_duration(tracker["activity_summary"]["ARM_EXERCISE"]),
            "total_walking": format_duration(tracker["activity_summary"]["WALKING"]),
            "total_push_up": format_duration(tracker["activity_summary"]["PUSH_UP"]),
            "transition_count": tracker["transition_count"],
        }

    def _record_state_change(self, master_id: int, tracker: Dict[str, Any], confirmed_posture: str, confirmed_activity: str, current_sec: float) -> None:
        end_time_str = datetime.datetime.now().strftime("%H:%M:%S")
        stay_time = current_sec - tracker["state_start_time"]

        if tracker["current_posture"] in tracker["posture_summary"]:
            tracker["posture_summary"][tracker["current_posture"]] += stay_time
        tracker["activity_summary"][tracker["current_activity"]] += stay_time

        self.state_logs.append(self._build_state_entry(master_id, tracker, end_time_str, stay_time))

        if confirmed_posture != tracker["current_posture"]:
            tracker["transition_count"] += 1
            self.transition_logs.append(
                {
                    "id": master_id,
                    "transition_type": "posture",
                    "from_activity": tracker["current_posture"],
                    "to_activity": confirmed_posture,
                    "timestamp": end_time_str,
                }
            )
        if confirmed_activity != tracker["current_activity"]:
            self.transition_logs.append(
                {
                    "id": master_id,
                    "transition_type": "activity",
                    "from_activity": tracker["current_activity"],
                    "to_activity": confirmed_activity,
                    "timestamp": end_time_str,
                }
            )

        tracker["current_posture"] = confirmed_posture
        tracker["current_activity"] = confirmed_activity
        tracker["state_start_time"] = current_sec
        tracker["start_time_str"] = end_time_str

    def finalize(self, current_sec: float) -> None:
        for master_id, tracker in self.trackers.items():
            stay_time = current_sec - tracker["state_start_time"]
            end_time_str = datetime.datetime.now().strftime("%H:%M:%S")

            if tracker["current_posture"] in tracker["posture_summary"]:
                tracker["posture_summary"][tracker["current_posture"]] += stay_time
            tracker["activity_summary"][tracker["current_activity"]] += stay_time

            self.state_logs.append(self._build_state_entry(master_id, tracker, end_time_str, stay_time))
            self.summary_logs.append({"id": master_id, **self._build_summary_entry(tracker)})

    def snapshot_logs(self, current_sec: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        state_logs = list(self.state_logs)
        summary_logs = list(self.summary_logs)
        end_time_str = datetime.datetime.now().strftime("%H:%M:%S")
        for master_id, tracker in self.trackers.items():
            stay_time = max(0.0, current_sec - tracker["state_start_time"])
            state_entry = self._build_state_entry(master_id, tracker, end_time_str, stay_time)
            state_entry["in_progress"] = True
            state_logs.append(state_entry)

            posture_summary = dict(tracker["posture_summary"])
            activity_summary = dict(tracker["activity_summary"])
            if tracker["current_posture"] in posture_summary:
                posture_summary[tracker["current_posture"]] += stay_time
            activity_summary[tracker["current_activity"]] += stay_time
            summary_tracker = dict(tracker)
            summary_tracker["posture_summary"] = posture_summary
            summary_tracker["activity_summary"] = activity_summary
            summary_logs.append({
                "id": master_id,
                **self._build_summary_entry(summary_tracker),
                "in_progress": True,
            })
        return state_logs, list(self.transition_logs), summary_logs

    def assign_ids(self, detected_id: int, current_sec: float, max_gap: float = 20.0) -> int:
        for existing_id, tracker in self.trackers.items():
            last_seen = tracker.get("last_seen", 0)
            if 0 < current_sec - last_seen < max_gap:
                return existing_id
        return detected_id


def format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def has_skeleton_in_bbox(pose_landmarks: Any, bbox: Tuple[float, float, float, float], width: int, height: int) -> bool:
    if pose_landmarks is None:
        return False

    x1, y1, x2, y2 = bbox
    visible_points = 0
    for joint_idx in [0, 2, 5, 11, 12, 23, 24]:
        landmark = pose_landmarks.landmark[joint_idx]
        if landmark.visibility <= 0.2:
            continue

        px = int(landmark.x * width)
        py = int(landmark.y * height)
        if x1 <= px <= x2 and y1 <= py <= y2:
            visible_points += 1

    return visible_points >= 2


def classify_posture(pose_landmarks: Any, bbox: Tuple[float, float, float, float]) -> str:
    if pose_landmarks is None:
        return "UNKNOWN"

    lm = pose_landmarks.landmark
    x1, y1, x2, y2 = bbox
    is_box_wide = (x2 - x1) > (y2 - y1) * 1.45
    is_box_lying = False
    is_landmark_lying = False

    if lm[11].visibility > 0.3 and lm[23].visibility > 0.3:
        y_dist = abs(lm[11].y - lm[23].y)
        x_dist = abs(lm[11].x - lm[23].x)
        is_box_lying = is_box_wide and x_dist > y_dist * 0.8

        if x_dist > y_dist * 1.2:
            is_landmark_lying = True

        if y_dist > x_dist and lm[11].y < lm[23].y:
            is_box_lying = False
            is_landmark_lying = False

    if is_box_lying or is_landmark_lying:
        return "LYING"

    # A standing person can look vertically compressed because of camera
    # perspective.  Use the actual hip-knee-ankle bend before comparing
    # vertical distances so straight legs are not mistaken for sitting.
    knee_angles = []
    for hip_idx, knee_idx, ankle_idx in ((23, 25, 27), (24, 26, 28)):
        hip, knee, ankle = lm[hip_idx], lm[knee_idx], lm[ankle_idx]
        if min(hip.visibility, knee.visibility, ankle.visibility) <= 0.3:
            continue
        hip_vector = np.array([hip.x - knee.x, hip.y - knee.y], dtype=float)
        ankle_vector = np.array([ankle.x - knee.x, ankle.y - knee.y], dtype=float)
        denominator = np.linalg.norm(hip_vector) * np.linalg.norm(ankle_vector)
        if denominator <= 1e-6:
            continue
        cosine = np.clip(np.dot(hip_vector, ankle_vector) / denominator, -1.0, 1.0)
        knee_angles.append(float(np.degrees(np.arccos(cosine))))

    if knee_angles:
        knee_angle = float(np.median(knee_angles))
        if knee_angle >= 150.0:
            return "STANDING"
        if knee_angle <= 135.0:
            return "SITTING"

    shoulder_y = (lm[11].y + lm[12].y) / 2.0 if lm[11].visibility > 0.3 and lm[12].visibility > 0.3 else lm[11].y
    hip_y = (lm[23].y + lm[24].y) / 2.0 if lm[23].visibility > 0.3 and lm[24].visibility > 0.3 else lm[23].y
    torso_height = max(0.001, abs(shoulder_y - hip_y))

    knee_positions = []
    for knee_idx in (25, 26):
        if lm[knee_idx].visibility > 0.3:
            knee_positions.append(lm[knee_idx].y)

    if not knee_positions:
        return "UNKNOWN"

    knee_to_hip = sum(abs(knee_y - hip_y) for knee_y in knee_positions) / len(knee_positions)
    if knee_to_hip <= torso_height * 0.70:
        return "SITTING"

    return "STANDING"


def is_phone_in_use(person_pose: Any, person_bbox: Tuple[float, float, float, float], phone_boxes: np.ndarray, frame_width: int, frame_height: int, view_type: str = "side") -> bool:
    if person_pose is None or len(phone_boxes) == 0:
        return False

    x1, y1, x2, y2 = person_bbox
    padding_x = (x2 - x1) * 0.20
    padding_y = (y2 - y1) * 0.20
    wrist_distance = min(170.0, max(60.0, (x2 - x1) * 0.50))

    upper_body_limit: Optional[float] = None
    if view_type != "top":
        shoulder_points = [person_pose.landmark[idx] for idx in (11, 12) if person_pose.landmark[idx].visibility > 0.35]
        hip_points = [person_pose.landmark[idx] for idx in (23, 24) if person_pose.landmark[idx].visibility > 0.35]
        if shoulder_points and hip_points:
            shoulder_y = sum(point.y for point in shoulder_points) / len(shoulder_points) * frame_height
            hip_y = sum(point.y for point in hip_points) / len(hip_points) * frame_height
            upper_body_limit = hip_y + abs(hip_y - shoulder_y) * 0.15
        else:
            upper_body_limit = y1 + (y2 - y1) * 0.60

    for phone_x1, phone_y1, phone_x2, phone_y2 in phone_boxes:
        phone_center = ((phone_x1 + phone_x2) / 2.0, (phone_y1 + phone_y2) / 2.0)
        if not (x1 - padding_x <= phone_center[0] <= x2 + padding_x and y1 - padding_y <= phone_center[1] <= y2 + padding_y):
            continue
        if upper_body_limit is not None and phone_center[1] > upper_body_limit:
            continue

        for wrist_idx in (15, 16):
            wrist = person_pose.landmark[wrist_idx]
            if wrist.visibility <= 0.35:
                continue
            wrist_pos = (wrist.x * frame_width, wrist.y * frame_height)
            if np.hypot(phone_center[0] - wrist_pos[0], phone_center[1] - wrist_pos[1]) <= wrist_distance:
                return True

    return False


def is_reading(person_pose: Any, person_bbox: Tuple[float, float, float, float], book_boxes: np.ndarray, frame_width: int, frame_height: int, view_type: str = "side") -> bool:
    if person_pose is None or len(book_boxes) == 0:
        return False

    x1, y1, x2, y2 = person_bbox
    padding_x = (x2 - x1) * 0.20
    padding_y = (y2 - y1) * 0.20
    wrist_distance = min(190.0, max(70.0, (x2 - x1) * 0.60))

    book_height_limit: Optional[float] = None
    if view_type != "top":
        shoulder_points = [person_pose.landmark[idx] for idx in (11, 12) if person_pose.landmark[idx].visibility > 0.35]
        hip_points = [person_pose.landmark[idx] for idx in (23, 24) if person_pose.landmark[idx].visibility > 0.35]
        if shoulder_points and hip_points:
            shoulder_y = sum(point.y for point in shoulder_points) / len(shoulder_points) * frame_height
            hip_y = sum(point.y for point in hip_points) / len(hip_points) * frame_height
            book_height_limit = hip_y + abs(hip_y - shoulder_y) * 0.50
        else:
            book_height_limit = y1 + (y2 - y1) * 0.80

    for book_x1, book_y1, book_x2, book_y2 in book_boxes:
        book_center = ((book_x1 + book_x2) / 2.0, (book_y1 + book_y2) / 2.0)
        if not (x1 - padding_x <= book_center[0] <= x2 + padding_x and y1 - padding_y <= book_center[1] <= y2 + padding_y):
            continue
        if book_height_limit is not None and book_center[1] > book_height_limit:
            continue

        for wrist_idx in (15, 16):
            wrist = person_pose.landmark[wrist_idx]
            if wrist.visibility <= 0.35:
                continue
            wrist_pos = (wrist.x * frame_width, wrist.y * frame_height)
            if np.hypot(book_center[0] - wrist_pos[0], book_center[1] - wrist_pos[1]) <= wrist_distance:
                return True

    return False


def draw_detection_info(annotated: np.ndarray, bbox: Tuple[float, float, float, float], master_id: int, posture: str, activity: str, current_stay_time: float, is_warn: bool) -> None:
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
        f"ID:{master_id} {posture} | {activity}",
        (int(x1), label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        color,
        2,
    )


def save_logs(state_logs: List[Dict[str, Any]], transition_logs: List[Dict[str, Any]], summary_logs: List[Dict[str, Any]], camera_id: str = "cam1") -> None:
    log_dir = Path(__file__).resolve().parents[1] / "data" / "camera_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    def write_json(filename, data):
        path = log_dir / f"{filename}_{timestamp}.json"
        number = 2
        while path.exists():
            path = log_dir / f"{filename}_{timestamp}_{number}.json"
            number += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(list(data), f, indent=4, ensure_ascii=False)

    write_json(f"{camera_id}_state_log", state_logs)
    write_json(f"{camera_id}_transition_log", transition_logs)
    write_json(f"{camera_id}_summary_log", summary_logs)


def get_pose_landmarks_in_bbox(frame: np.ndarray, bbox: Tuple[float, float, float, float], pose_model: Any, prev_landmarks: Optional[Any] = None) -> Optional[Any]:
    x1, y1, x2, y2 = bbox
    pad_x = max(20, int((x2 - x1) * 0.25))
    pad_y = max(20, int((y2 - y1) * 0.35))
    x1i = max(0, int(x1) - pad_x)
    y1i = max(0, int(y1) - pad_y)
    x2i = min(frame.shape[1], int(x2) + pad_x)
    y2i = min(frame.shape[0], int(y2) + pad_y)

    roi = frame[y1i:y2i, x1i:x2i]
    if roi.size == 0:
        return prev_landmarks

    rgb_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
    pose_result = pose_model.process(rgb_roi)
    if not pose_result.pose_landmarks:
        return prev_landmarks

    roi_w = roi.shape[1]
    roi_h = roi.shape[0]
    landmark_list = landmark_pb2.NormalizedLandmarkList()
    for idx, landmark in enumerate(pose_result.pose_landmarks.landmark):
        new_landmark = landmark_pb2.NormalizedLandmark()
        visibility = landmark.visibility if landmark.visibility is not None else 0.0

        if visibility < 0.2:
            if prev_landmarks is not None and idx < len(prev_landmarks.landmark):
                prev_landmark = prev_landmarks.landmark[idx]
                new_landmark.x = prev_landmark.x
                new_landmark.y = prev_landmark.y
            new_landmark.visibility = 0.0
            landmark_list.landmark.append(new_landmark)
            continue

        new_x = (x1i + landmark.x * roi_w) / frame.shape[1]
        new_y = (y1i + landmark.y * roi_h) / frame.shape[0]
        if prev_landmarks is not None and idx < len(prev_landmarks.landmark):
            prev_landmark = prev_landmarks.landmark[idx]
            new_x = 0.7 * prev_landmark.x + 0.3 * new_x
            new_y = 0.7 * prev_landmark.y + 0.3 * new_y

        new_landmark.x = new_x
        new_landmark.y = new_y
        new_landmark.visibility = visibility
        landmark_list.landmark.append(new_landmark)

    return landmark_list


def create_yolo_model() -> YOLO:
    model_path = Path(__file__).resolve().parents[1] / "models" / "yolov8n.pt"
    return YOLO(str(model_path))


def create_pose_model(config: CameraConfig) -> Any:
    return mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        min_detection_confidence=config.pose_min_detection_confidence,
        min_tracking_confidence=config.pose_min_tracking_confidence,
    )


class HomeCamAnalyzer:
    def __init__(self, config: Optional[CameraConfig] = None) -> None:
        self.config = config or CONFIG
        self.device = 0 if torch.cuda.is_available() else "cpu"
        print(f"[{self.config.camera_id}] YOLO device: {'CUDA:0' if self.device == 0 else 'CPU'}")
        self.model = create_yolo_model()
        self.mp_pose = create_pose_model(self.config)
        self.mp_drawing = mp.solutions.drawing_utils
        self.tracker_manager = TrackerManager(transition_threshold=self.config.transition_threshold)
        self.id_mapping: Dict[int, int] = {}
        self.prev_pose_cache: Dict[int, Any] = {}
        self.phone_boxes = np.empty((0, 4), dtype=np.float32)
        self.book_boxes = np.empty((0, 4), dtype=np.float32)
        self.phone_missed_detection_cycles = 0
        self.book_missed_detection_cycles = 0
        self.motion_history: Dict[int, List[Tuple[float, Dict[int, Tuple[float, float]]]]] = {}
        self.last_raw_posture: Dict[int, str] = {}
        self.posture_stable_since: Dict[int, float] = {}
        self.posture_transition_history: Dict[int, List[Tuple[float, str]]] = {}

    def _is_posture_stable_for_exercise(self, master_id: int, raw_posture: str, current_sec: float) -> bool:
        if raw_posture == "UNKNOWN":
            self.motion_history.pop(master_id, None)
            return False

        transitions = self.posture_transition_history.setdefault(master_id, [])
        cutoff = current_sec - self.config.exercise_transition_window_sec
        transitions[:] = [(timestamp, posture) for timestamp, posture in transitions if timestamp >= cutoff]
        previous_posture = self.last_raw_posture.get(master_id)
        if previous_posture != raw_posture:
            self.last_raw_posture[master_id] = raw_posture
            self.posture_stable_since[master_id] = current_sec
            transitions.append((current_sec, raw_posture))
            self.motion_history.pop(master_id, None)
            return False

        stable_since = self.posture_stable_since.get(master_id, current_sec)
        return current_sec - stable_since >= self.config.exercise_posture_settle_sec

    def _has_squat_pattern(self, master_id: int) -> bool:
        transitions = self.posture_transition_history.get(master_id, [])
        squat_postures = [posture for _, posture in transitions if posture in {"SITTING", "STANDING"}]
        posture_changes = sum(previous != current for previous, current in zip(squat_postures, squat_postures[1:]))
        return posture_changes >= self.config.squat_min_transitions

    def _classify_exercise(self, master_id: int, person_pose: Any, raw_posture: str, current_sec: float, posture_stable: bool) -> str:
        if raw_posture == "SITTING":
            self.motion_history.pop(master_id, None)
            return "IDLE"

        if self._has_squat_pattern(master_id):
            return "SQUAT"
        if not posture_stable:
            return "IDLE"

        landmarks = person_pose.landmark
        shoulder_points = [landmarks[idx] for idx in (11, 12) if landmarks[idx].visibility > 0.35]
        hip_points = [landmarks[idx] for idx in (23, 24) if landmarks[idx].visibility > 0.35]
        if not shoulder_points or not hip_points:
            return "IDLE"

        shoulder_x = sum(point.x for point in shoulder_points) / len(shoulder_points)
        shoulder_y = sum(point.y for point in shoulder_points) / len(shoulder_points)
        hip_x = sum(point.x for point in hip_points) / len(hip_points)
        hip_y = sum(point.y for point in hip_points) / len(hip_points)
        torso_size = np.hypot(shoulder_x - hip_x, shoulder_y - hip_y)
        if torso_size < 0.03:
            return "IDLE"

        center_x = (shoulder_x + hip_x) / 2.0
        center_y = (shoulder_y + hip_y) / 2.0
        joint_positions: Dict[int, Tuple[float, float]] = {}
        for joint_idx in (11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28):
            landmark = landmarks[joint_idx]
            if landmark.visibility > 0.35:
                joint_positions[joint_idx] = ((landmark.x - center_x) / torso_size, (landmark.y - center_y) / torso_size)

        history = self.motion_history.setdefault(master_id, [])
        history.append((current_sec, joint_positions))
        cutoff = current_sec - self.config.exercise_window_sec
        history[:] = [(timestamp, positions) for timestamp, positions in history if timestamp >= cutoff]
        if len(history) < self.config.exercise_min_samples:
            return "IDLE"

        joint_motion: Dict[int, float] = {}
        for (_, previous_positions), (_, current_positions) in zip(history, history[1:]):
            for joint_idx in previous_positions.keys() & current_positions.keys():
                previous_x, previous_y = previous_positions[joint_idx]
                current_x, current_y = current_positions[joint_idx]
                joint_motion[joint_idx] = joint_motion.get(joint_idx, 0.0) + np.hypot(current_x - previous_x, current_y - previous_y)

        active_joints = sum(motion >= 0.35 for motion in joint_motion.values())
        total_motion = sum(joint_motion.values())
        arm_motion = sum(joint_motion.get(joint_idx, 0.0) for joint_idx in (13, 14, 15, 16))
        leg_motion = sum(joint_motion.get(joint_idx, 0.0) for joint_idx in (25, 26, 27, 28))

        if raw_posture == "LYING" and arm_motion >= self.config.push_up_arm_motion_threshold:
            return "PUSH_UP"
        if arm_motion >= self.config.arm_exercise_motion_threshold and arm_motion > leg_motion * 1.4:
            return "ARM_EXERCISE"
        if leg_motion >= self.config.walking_motion_threshold and leg_motion >= arm_motion * 0.8:
            return "WALKING"
        if active_joints >= self.config.exercise_min_active_joints and total_motion >= self.config.exercise_motion_threshold:
            return "EXERCISING"
        return "IDLE"

    def process_detection(self, frame: np.ndarray, annotated: np.ndarray, bbox: Tuple[float, float, float, float], detection_id: int, current_sec: float, phone_boxes: np.ndarray, book_boxes: np.ndarray) -> Tuple[np.ndarray, Dict[int, Any]]:
        x1, y1, x2, y2 = bbox
        cache_key = int(detection_id)
        prev_pose = self.prev_pose_cache.get(cache_key)
        person_pose = get_pose_landmarks_in_bbox(frame, bbox, self.mp_pose, prev_pose)
        if person_pose is None:
            return annotated, self.prev_pose_cache

        self.prev_pose_cache[cache_key] = person_pose

        if has_skeleton_in_bbox(person_pose, bbox, self.config.target_width, self.config.target_height):
            self.mp_drawing.draw_landmarks(annotated, person_pose, mp.solutions.pose.POSE_CONNECTIONS)

        master_id = self.id_mapping.get(cache_key)
        if master_id is None:
            master_id = self.tracker_manager.assign_ids(cache_key, current_sec)
            self.id_mapping[cache_key] = master_id

        raw_posture = classify_posture(person_pose, bbox)
        posture_stable = self._is_posture_stable_for_exercise(master_id, raw_posture, current_sec)
        exercise_activity = self._classify_exercise(master_id, person_pose, raw_posture, current_sec, posture_stable)
        if is_phone_in_use(person_pose, bbox, phone_boxes, self.config.target_width, self.config.target_height, view_type=self.config.view_type):
            raw_activity = "PHONE_USE"
        elif is_reading(person_pose, bbox, book_boxes, self.config.target_width, self.config.target_height, view_type=self.config.view_type):
            raw_activity = "READING"
        elif exercise_activity != "IDLE":
            raw_activity = exercise_activity
        else:
            raw_activity = "IDLE"
        tracker = self.tracker_manager.register_or_get(master_id, raw_posture, raw_activity, current_sec)
        current_stay_time = current_sec - tracker["state_start_time"]
        is_warn = False
        draw_detection_info(annotated, bbox, master_id, tracker["current_posture"], tracker["current_activity"], current_stay_time, is_warn)
        return annotated, self.prev_pose_cache

    def _update_object_cache(self, cached_boxes: np.ndarray, new_boxes: np.ndarray, missed_cycles: int) -> Tuple[np.ndarray, int]:
        if len(new_boxes) > 0:
            return new_boxes, 0
        if len(cached_boxes) > 0 and missed_cycles < self.config.object_detection_hold_cycles:
            return cached_boxes, missed_cycles + 1
        return np.empty((0, 4), dtype=np.float32), 0

    def analyze_frame(self, frame: np.ndarray, current_sec: float) -> np.ndarray:
        resized_frame = cv2.resize(frame, (self.config.target_width, self.config.target_height))
        yolo_res = self.model.track(
            resized_frame,
            persist=True,
            verbose=False,
            classes=[0, 67, 73],
            conf=min(self.config.yolo_conf, self.config.phone_conf),
            iou=self.config.yolo_iou,
            imgsz=self.config.phone_imgsz,
            device=self.device,
        )[0]
        annotated = resized_frame.copy()

        if yolo_res.boxes is None or len(yolo_res.boxes) == 0:
            return annotated

        all_boxes = yolo_res.boxes.xyxy.cpu().numpy()
        all_classes = yolo_res.boxes.cls.cpu().numpy().astype(int)
        all_confidences = yolo_res.boxes.conf.cpu().numpy()
        detected_phone_boxes = all_boxes[all_classes == 67]
        detected_book_boxes = all_boxes[all_classes == 73]
        self.phone_boxes, self.phone_missed_detection_cycles = self._update_object_cache(self.phone_boxes, detected_phone_boxes, self.phone_missed_detection_cycles)
        self.book_boxes, self.book_missed_detection_cycles = self._update_object_cache(self.book_boxes, detected_book_boxes, self.book_missed_detection_cycles)
        phone_boxes = self.phone_boxes
        book_boxes = self.book_boxes
        for phone_x1, phone_y1, phone_x2, phone_y2 in phone_boxes.astype(int):
            cv2.rectangle(annotated, (phone_x1, phone_y1), (phone_x2, phone_y2), (255, 128, 0), 2)
            cv2.putText(annotated, "PHONE", (phone_x1, max(20, phone_y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 128, 0), 2)
        for book_x1, book_y1, book_x2, book_y2 in book_boxes.astype(int):
            cv2.rectangle(annotated, (book_x1, book_y1), (book_x2, book_y2), (255, 0, 255), 2)
            cv2.putText(annotated, "BOOK", (book_x1, max(20, book_y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

        if yolo_res.boxes.id is None:
            return annotated
        all_ids = yolo_res.boxes.id.cpu().numpy().astype(int)
        person_mask = (all_classes == self.config.yolo_classes) & (all_confidences >= self.config.yolo_conf)
        boxes = all_boxes[person_mask]
        ids = all_ids[person_mask]
        for bbox, detection_id in zip(boxes, ids):
            annotated, self.prev_pose_cache = self.process_detection(resized_frame, annotated, tuple(bbox), int(detection_id), current_sec, phone_boxes, book_boxes)

        return annotated

    def open_capture(self) -> VideoCaptureThreading:
        return VideoCaptureThreading(self.config.video_path)

    def process_frame(self, frame: np.ndarray, current_sec: float) -> np.ndarray:
        annotated = self.analyze_frame(frame, current_sec)
        return annotated

    def finalize_and_save(self, total_elapsed: float) -> None:
        self.tracker_manager.finalize(total_elapsed)
        save_logs(self.tracker_manager.state_logs, self.tracker_manager.transition_logs, self.tracker_manager.summary_logs, camera_id=self.config.camera_id)

    def run(self) -> None:
        cap = self.open_capture()
        if not cap.isOpened():
            print(f"[{self.config.camera_id}] 카메라를 열 수 없습니다. video_path를 확인하세요.")
            return

        frame_count = 0
        start_time_real = time.time()
        last_log_save = time.monotonic()
        window_name = f"Advanced Home Cam AI - {self.config.camera_id}"

        print(f">> [{self.config.camera_id}] [STEP 2] 실시간 분석 시작... (q: 종료)")

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame is None:
                print(f"[{self.config.camera_id}] 스트림이 끊겼거나 카메라 연결이 종료되었습니다.")
                break

            frame_count += 1
            now_monotonic = time.monotonic()
            if now_monotonic - last_log_save >= self.config.log_save_interval_sec:
                snapshot_logs = self.tracker_manager.snapshot_logs(time.time() - start_time_real)
                save_logs(
                    *snapshot_logs,
                    camera_id=self.config.camera_id,
                )
                last_log_save = now_monotonic
            if frame_count % self.config.frame_skip_interval != 0:
                continue

            current_sec = time.time() - start_time_real
            annotated = self.process_frame(frame, current_sec)
            cv2.imshow(window_name, annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyWindow(window_name)
        self.finalize_and_save(time.time() - start_time_real)
        print(f"[{self.config.camera_id}] 분석 완료! (data/camera_log 폴더에 로그 저장됨)")


def main() -> None:
    HomeCamAnalyzer(CONFIG).run()


if __name__ == "__main__":
    main()
