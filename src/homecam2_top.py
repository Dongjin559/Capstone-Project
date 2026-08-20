import cv2
import ctypes
import datetime
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from ultralytics import YOLO


Point = Tuple[int, int]
TOP_ZONE_FILE = Path(__file__).resolve().parents[1] / "data" / "camera_config" / "top_cam_zones.json"


@dataclass(frozen=True)
class CameraConfig:
    camera_id: str = "top_cam"
    video_path: str = "rtsp://admin:applemarch559!@172.30.1.85:554/onvif1"
    target_width: int = 640
    target_height: int = 480
    frame_skip_interval: int = 2
    yolo_conf: float = 0.35
    yolo_iou: float = 0.35
    inactive_track_timeout: float = 3.0
    max_read_failures: int = 30
    min_move_pixels: float = 3.0
    path_length: int = 100
    log_save_interval_sec: float = 30.0


CONFIG = CameraConfig()


class VideoCaptureThreading:
    def __init__(self, src: str, max_failures: int) -> None:
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ret, self.frame = self.cap.read()
        self.failures = 0 if self.ret else 1
        self.max_failures = max_failures
        self.running = True
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self) -> None:
        while self.running:
            try:
                ret, frame = self.cap.read()
            except cv2.error:
                if self.running:
                    with self.lock:
                        self.ret = False
                        self.failures = self.max_failures
                break
            with self.lock:
                self.ret = ret
                if ret:
                    self.frame, self.failures = frame, 0
                else:
                    self.failures += 1
            if not ret:
                time.sleep(0.01)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        with self.lock:
            if self.failures >= self.max_failures:
                return False, None
            return self.ret, self.frame

    def isOpened(self) -> bool:
        return self.cap.isOpened()

    def release(self) -> None:
        self.running = False
        self.thread.join(timeout=1.0)
        self.cap.release()
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)


class ZoneManager:
    def __init__(self) -> None:
        self.zones: Dict[str, np.ndarray] = {}

    def setup(self, frame: np.ndarray) -> None:
        canvas = frame.copy()
        points: List[Point] = []
        window = "Zone setup"

        def on_click(event: int, x: int, y: int, _flags: int, _param: object) -> None:
            if event == cv2.EVENT_LBUTTONDOWN:
                points.append((x, y))

        cv2.namedWindow(window)
        cv2.setMouseCallback(window, on_click)
        print("[구역 설정] 클릭: 꼭짓점, s: 저장, q: 분석 시작 (출입문 이름은 DOOR)")
        while True:
            view = canvas.copy()
            self.draw(view)
            if points:
                cv2.polylines(view, [np.array(points)], False, (0, 255, 255), 2)
                for point in points:
                    cv2.circle(view, point, 4, (0, 0, 255), -1)
            cv2.imshow(window, view)
            key = cv2.waitKey(20) & 0xFF
            if key == ord("s") and len(points) >= 3:
                name = input("구역 이름: ").strip().upper() or f"ZONE_{len(self.zones) + 1}"
                self.zones[name] = np.array(points, np.int32)
                points.clear()
            elif key == ord("q"):
                break
        cv2.destroyWindow(window)
        self.save()

    def load(self) -> bool:
        if not TOP_ZONE_FILE.exists():
            return False
        try:
            with TOP_ZONE_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
            loaded_zones = {
                name: np.array(points, np.int32)
                for name, points in data.get("zones", {}).items()
                if len(points) >= 3
            }
            if not loaded_zones:
                return False
            self.zones = loaded_zones
            print(f"[top_cam] 이전 구역 {len(self.zones)}개 불러오기 완료: {TOP_ZONE_FILE}")
            return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            print(f"[top_cam] 이전 구역 불러오기 실패: {error}")
            return False

    def ask_to_load_previous(self) -> bool:
        if not TOP_ZONE_FILE.exists():
            return False
        message = "이전에 저장한 탑캠 구역을 불러오시겠습니까?\n\n예: 기존 구역 사용\n아니요: 구역 새로 그리기"
        title = "탑캠 구역 설정"
        result = ctypes.windll.user32.MessageBoxW(None, message, title, 0x00000004 | 0x00000020)
        return result == 6

    def save(self) -> None:
        if not self.zones:
            return
        TOP_ZONE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_path = TOP_ZONE_FILE.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(
                {"zones": {name: polygon.tolist() for name, polygon in self.zones.items()}},
                file,
                indent=2,
                ensure_ascii=False,
            )
        temp_path.replace(TOP_ZONE_FILE)
        print(f"[top_cam] 구역 저장 완료: {TOP_ZONE_FILE}")

    def find(self, point: Point) -> str:
        for name, polygon in self.zones.items():
            if cv2.pointPolygonTest(polygon, point, False) >= 0:
                return name
        return "NONE"

    def draw(self, frame: np.ndarray) -> None:
        for name, polygon in self.zones.items():
            cv2.polylines(frame, [polygon], True, (255, 180, 0), 2)
            center = tuple(np.mean(polygon, axis=0).astype(int))
            cv2.putText(frame, name, center, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 180, 0), 2)


class PersonTracker:
    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self.people: Dict[int, dict] = {}
        self.zone_logs: List[dict] = []
        self.entry_exit_logs: List[dict] = []
        self.summary_logs: List[dict] = []

    @staticmethod
    def _clock() -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    def update(self, person_id: int, point: Point, zone: str, now: float) -> dict:
        person = self.people.get(person_id)
        if person is None:
            person = {
                "zone": zone, "zone_start": now, "zone_start_clock": self._clock(),
                "last_seen": now, "last_point": point, "distance": 0.0,
                "path": [point], "zone_totals": {}, "entered": zone != "DOOR",
                "exit_pending": False,
            }
            self.people[person_id] = person

        distance = float(np.hypot(point[0] - person["last_point"][0], point[1] - person["last_point"][1]))
        if distance >= self.config.min_move_pixels:
            person["distance"] += distance
            person["path"].append(point)
            person["path"] = person["path"][-self.config.path_length:]
            person["last_point"] = point

        previous_zone = person["zone"]
        if zone != previous_zone:
            self._close_zone(person_id, person, now)
            person["zone"], person["zone_start"], person["zone_start_clock"] = zone, now, self._clock()
            if previous_zone == "DOOR" and zone not in {"DOOR", "NONE"} and not person["entered"]:
                person["entered"] = True
                person["exit_pending"] = False
                self._event(person_id, "ENTER")
            elif zone == "DOOR" and person["entered"]:
                person["exit_pending"] = True
            elif zone not in {"DOOR", "NONE"}:
                person["exit_pending"] = False

        person["last_seen"] = now
        return person

    def _close_zone(self, person_id: int, person: dict, now: float) -> None:
        duration = max(0.0, now - person["zone_start"])
        zone = person["zone"]
        person["zone_totals"][zone] = person["zone_totals"].get(zone, 0.0) + duration
        self.zone_logs.append({
            "id": person_id, "zone": zone, "start_time": person["zone_start_clock"],
            "end_time": self._clock(), "stay_time_sec": round(duration, 1),
        })

    def _event(self, person_id: int, event: str) -> None:
        self.entry_exit_logs.append({"id": person_id, "event": event, "timestamp": self._clock()})
        print(f"[{event}] ID:{person_id} - {self._clock()}")

    def expire(self, now: float) -> None:
        for person_id, person in list(self.people.items()):
            if now - person["last_seen"] < self.config.inactive_track_timeout:
                continue
            if person["exit_pending"] and person["entered"]:
                self._event(person_id, "EXIT")
            self._finish(person_id, person, person["last_seen"])
            del self.people[person_id]

    def _finish(self, person_id: int, person: dict, now: float) -> None:
        self._close_zone(person_id, person, now)
        self.summary_logs.append({
            "id": person_id,
            "total_distance_pixels": round(person["distance"], 1),
            "zone_stay_sec": {name: round(value, 1) for name, value in person["zone_totals"].items()},
        })

    def finalize(self, now: float) -> None:
        for person_id, person in list(self.people.items()):
            self._finish(person_id, person, now)
        self.people.clear()


def save_logs(tracker: PersonTracker, camera_id: str, current_sec: Optional[float] = None) -> None:
    log_dir = Path(__file__).resolve().parents[1] / "data" / "camera_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zone_logs = list(tracker.zone_logs)
    summary_logs = list(tracker.summary_logs)
    if current_sec is not None:
        end_time = datetime.datetime.now().strftime("%H:%M:%S")
        for person_id, person in tracker.people.items():
            active_duration = max(0.0, current_sec - person["zone_start"])
            zone_logs.append({
                "id": person_id,
                "zone": person["zone"],
                "start_time": person["zone_start_clock"],
                "end_time": end_time,
                "stay_time_sec": round(active_duration, 1),
                "in_progress": True,
            })
            zone_totals = dict(person["zone_totals"])
            zone = person["zone"]
            zone_totals[zone] = zone_totals.get(zone, 0.0) + active_duration
            summary_logs.append({
                "id": person_id,
                "total_distance_pixels": round(person["distance"], 1),
                "zone_stay_sec": {name: round(value, 1) for name, value in zone_totals.items()},
                "in_progress": True,
            })
    for name, data in {
        "zone_log": zone_logs,
        "entry_exit_log": list(tracker.entry_exit_logs),
        "movement_summary": summary_logs,
    }.items():
        filename = f"{camera_id}_{name}_{timestamp}"
        path = log_dir / f"{filename}.json"
        number = 2
        while path.exists():
            path = log_dir / f"{filename}_{number}.json"
            number += 1
        with path.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False,
                default=lambda value: value.item() if isinstance(value, np.generic) else str(value),
            )


class HomeCamAnalyzer:
    def __init__(self, config: CameraConfig = CONFIG) -> None:
        self.config = config
        self.device = 0 if torch.cuda.is_available() else "cpu"
        print(f"[{self.config.camera_id}] YOLO device: {'CUDA:0' if self.device == 0 else 'CPU'}")
        model_path = Path(__file__).resolve().parents[1] / "models" / "yolov8n.pt"
        self.model = YOLO(str(model_path))
        self.zones = ZoneManager()
        self.tracker = PersonTracker(config)

    def analyze(self, frame: np.ndarray, now: float) -> np.ndarray:
        frame = cv2.resize(frame, (self.config.target_width, self.config.target_height))
        result = self.model.track(
            frame, persist=True, verbose=False, classes=0,
            conf=self.config.yolo_conf, iou=self.config.yolo_iou,
            device=self.device,
        )[0]
        output = frame.copy()
        self.zones.draw(output)

        if result.boxes.id is not None:
            boxes = result.boxes.xyxy.cpu().numpy()
            confidence = result.boxes.conf.cpu().numpy()
            x1, y1, x2, y2 = boxes[int(np.argmax(confidence))]
            person_id = 1
            point = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            zone = self.zones.find(point)
            person = self.tracker.update(person_id, point, zone, now)
            path = np.array(person["path"], np.int32)
            if len(path) > 1:
                cv2.polylines(output, [path], False, (0, 255, 255), 2)
            stay = now - person["zone_start"]
            label = f"ID:1 {zone} {stay:.1f}s {person['distance']:.0f}px"
            cv2.rectangle(output, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.circle(output, point, 5, (0, 0, 255), -1)
            cv2.putText(output, label, (int(x1), max(20, int(y1) - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        self.tracker.expire(now)
        return output

    def run(self) -> None:
        capture = VideoCaptureThreading(self.config.video_path, self.config.max_read_failures)
        if not capture.isOpened():
            capture.release()
            print("카메라를 열 수 없습니다.")
            return

        zones_loaded = self.zones.ask_to_load_previous() and self.zones.load()
        ret, first_frame = capture.read()
        if not zones_loaded and ret and first_frame is not None:
            setup_frame = cv2.resize(first_frame, (self.config.target_width, self.config.target_height))
            self.zones.setup(setup_frame)

        start, frame_count = time.time(), 0
        last_log_save = time.monotonic()
        window = f"Top View Tracking - {self.config.camera_id}"
        while capture.isOpened():
            ret, frame = capture.read()
            if not ret or frame is None:
                break
            frame_count += 1
            now_monotonic = time.monotonic()
            if now_monotonic - last_log_save >= self.config.log_save_interval_sec:
                save_logs(self.tracker, self.config.camera_id, time.time() - start)
                last_log_save = now_monotonic
            if frame_count % self.config.frame_skip_interval:
                continue
            output = self.analyze(frame, time.time() - start)
            cv2.imshow(window, output)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        elapsed = time.time() - start
        capture.release()
        cv2.destroyWindow(window)
        self.tracker.finalize(elapsed)
        save_logs(self.tracker, self.config.camera_id)
        print("분석 완료: data/camera_log 폴더에 로그를 저장했습니다.")


def main() -> None:
    HomeCamAnalyzer(CONFIG).run()


if __name__ == "__main__":
    main()
