import asyncio
import signal
import sys
import threading
import time
from queue import Queue
import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import datetime
import tkinter as tk
from PIL import Image, ImageTk
from numpy import expand_dims
import queue
import math
import base64

from drone_auto_pilot_web2 import DroneAutoPilot
from utils import *
from tello_controller import TelloController
from face_database import FaceDatabase

skyscan_frame_queue = Queue(maxsize=15)
skyscan_drone_autopilot = None
skyscan_is_running = False
skyscan_is_initializing = False
skyscan_stop_event = threading.Event()

skyscan_face_detector = None
skyscan_face_net = None
skyscan_face_db = None
skyscan_database = None
skyscan_unknown_faces_queue = Queue(maxsize=5)
skyscan_latest_faces = {}
skyscan_faces_lock = threading.Lock()

skyscan_faces_history = {}
skyscan_faces_history_lock = threading.Lock()

skyscan_unknown_faces = {}
skyscan_unknown_faces_lock = threading.Lock()
skyscan_face_id_counter = 0

@asynccontextmanager
async def skyscan_lifespan(app):
    yield
    skyscan_cleanup()

app = FastAPI(lifespan=skyscan_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def skyscan_cleanup():
    print("\nShutting down application...")
    skyscan_stop_event.set()
    global skyscan_drone_autopilot
    if skyscan_drone_autopilot:
        print("Stopping drone operations...")
        skyscan_drone_autopilot.stop()
        skyscan_drone_autopilot = None

def skyscan_signal_handler(sig, frame):
    print("\nReceived stop signal...")
    skyscan_cleanup()
    sys.exit(0)

def initialize_face_recognition():
    global skyscan_face_detector, skyscan_face_net, skyscan_face_db, skyscan_database

    print("Initializing face recognition system...")
    skyscan_face_detector = cv2.FaceDetectorYN.create(
        "./Configuration/face_detection_yunet_2023mar.onnx", "", [320, 320], 0.6, 0.3, 5000, 0, 0)
    skyscan_face_net = FaceNet()
    skyscan_face_db = FaceDatabase()
    skyscan_database = skyscan_face_db.load_database_from_firebase()
    unknown_face_thread = threading.Thread(target=consume_unknown_faces, daemon=True)
    unknown_face_thread.start()

    print("Face recognition system initialized")

def is_image_clear(image, sharpness_threshold=6):
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
    sharpness = laplacian.var()
    print(f"Sharpness: {sharpness}")
    return sharpness >= sharpness_threshold

def is_face_in_database(face_embedding):
    min_distance = float('inf')
    for key, value in skyscan_database.items():
        stored_signature = np.array(value['signature'])
        dist = np.linalg.norm(stored_signature - face_embedding)
        if dist < min_distance:
            min_distance = dist
    return min_distance < 1

def consume_unknown_faces():
    global skyscan_face_id_counter

    while not skyscan_stop_event.is_set():
        try:
            face_image, face_embedding = skyscan_unknown_faces_queue.get(timeout=1.0)

            if not is_face_in_database(face_embedding):
                with skyscan_unknown_faces_lock:
                    skyscan_face_id_counter += 1
                    unknown_face_id = f"unknown_{skyscan_face_id_counter}"

                    face_array = np.array(face_image)
                    is_clear = is_image_clear(face_array)

                    if is_clear:
                        face_array_rgb = cv2.cvtColor(face_array, cv2.COLOR_BGR2RGB)
                        _, buffer = cv2.imencode('.jpg', face_array_rgb)
                        face_base64 = base64.b64encode(buffer).decode('utf-8')

                        skyscan_unknown_faces[unknown_face_id] = {
                            'id': unknown_face_id,
                            'image': face_base64,
                            'embedding': face_embedding.tolist(),
                            'timestamp': datetime.datetime.now().timestamp() * 1000,
                            'is_clear': True
                        }
                    else:
                        print("The unknown face image is not clear, skipping")

            skyscan_unknown_faces_queue.task_done()
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error processing unknown face: {e}")

def remove_unknown_face(face_id):
    with skyscan_unknown_faces_lock:
        if face_id in skyscan_unknown_faces:
            del skyscan_unknown_faces[face_id]
            return True
        return False

def add_new_face(face_image, face_embedding):
    face_array = np.array(face_image)
    if not is_image_clear(face_array):
        print("The image is not clear. The window will not be opened.")
        return

    root = tk.Tk()
    root.title("Add New Face")

    def on_submit():
        name = entry.get()
        if name:
            person_id = FaceDatabase.generate_unique_id()
            date_added = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            new_entry = {
                "name": name,
                "date_added": date_added,
                "last_recognition": date_added,
                "total_recognition": 1,
                "signature": face_embedding.tolist()
            }

            skyscan_database[person_id] = new_entry
            db.reference('People').child(person_id).set(new_entry)

            print(f"Added new person: {name}")

        root.destroy()

    def on_cancel():
        root.destroy()

    face_image_pil = Image.fromarray(face_array)
    img = ImageTk.PhotoImage(image=face_image_pil)

    panel = tk.Label(root, image=img)
    panel.pack(side="top", fill="both", expand="yes")

    entry = tk.Entry(root)
    entry.pack(side="top", fill="both", expand="yes")
    entry.focus()

    btn_ok = tk.Button(root, text="OK", command=on_submit)
    btn_ok.pack(side="left", fill="both", expand="yes")

    btn_cancel = tk.Button(root, text="Cancel", command=on_cancel)
    btn_cancel.pack(side="right", fill="both", expand="yes")

    root.mainloop()

def process_frame_for_faces(frame):
    global skyscan_latest_faces, skyscan_face_detector, skyscan_face_net, skyscan_database, skyscan_faces_history

    if frame is None:
        return {}

    try:
        results = {}

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        img_width = int(frame_rgb.shape[1])
        img_height = int(frame_rgb.shape[0])
        skyscan_face_detector.setInputSize((img_width, img_height))
        detections = skyscan_face_detector.detect(frame_rgb)

        if detections[1] is not None and len(detections[1]) > 0:
            for i, detection in enumerate(detections[1]):
                x, y, w, h = detection[:4].astype(int)

                x1, y1 = abs(x), abs(y)
                x2, y2 = x1 + w, y1 + h

                if x1 >= frame.shape[1] or y1 >= frame.shape[0] or x2 <= 0 or y2 <= 0:
                    continue

                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(frame.shape[1], x2)
                y2 = min(frame.shape[0], y2)

                if (x2 - x1) < 20 or (y2 - y1) < 20:
                    continue

                face_region = frame_rgb[y1:y2, x1:x2]

                if face_region.size == 0 or face_region.shape[0] == 0 or face_region.shape[1] == 0:
                    continue

                face_image = Image.fromarray(face_region)
                face_image = face_image.resize((160, 160))
                face_array = np.asarray(face_image)
                face_array = expand_dims(face_array, axis=0)

                with tf.device('/GPU:0'):
                    face_embedding = skyscan_face_net.embeddings(face_array)[0]

                min_distance = float('inf')
                identity = 'UNKNOWN'
                face_id = f"face_{i}"
                is_known = False
                matched_key = None

                for key, value in skyscan_database.items():
                    stored_signature = np.array(value['signature'])
                    dist = np.linalg.norm(stored_signature - face_embedding)
                    if dist < min_distance:
                        min_distance = dist
                        identity = value['name']
                        matched_key = key

                if min_distance < 1:
                    is_known = True
                    face_id = matched_key
                    if matched_key in skyscan_database:
                        try:
                            skyscan_database[matched_key]['total_recognition'] += 1
                            skyscan_database[matched_key]['last_recognition'] = datetime.datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S")

                            if skyscan_database[matched_key]['total_recognition'] % 10 == 0:
                                db.reference('People').child(matched_key).update({
                                    'total_recognition': skyscan_database[matched_key]['total_recognition'],
                                    'last_recognition': skyscan_database[matched_key]['last_recognition']
                                })
                        except Exception as e:
                            print(f"Error updating recognition stats: {e}")
                else:
                    if skyscan_unknown_faces_queue.qsize() < skyscan_unknown_faces_queue.maxsize - 1:
                        skyscan_unknown_faces_queue.put((face_image, face_embedding))

                results[face_id] = {
                    'bbox': (x1, y1, x2, y2),
                    'name': identity,
                    'is_known': is_known,
                    'confidence': 1.0 - min(min_distance, 1.0) if min_distance != float('inf') else 0.0,
                    'lastSeen': datetime.datetime.now().timestamp() * 1000
                }

                if is_known:
                    with skyscan_faces_history_lock:
                        skyscan_faces_history[face_id] = {
                            'id': face_id,
                            'name': identity,
                            'is_known': is_known,
                            'confidence': 1.0 - min(min_distance, 1.0) if min_distance != float('inf') else 0.0,
                            'lastSeen': datetime.datetime.now().timestamp() * 1000
                        }

        with skyscan_faces_lock:
            skyscan_latest_faces = results

        return results

    except Exception as e:
        print(f"Error in face processing: {e}")
        return {}

def draw_faces_on_frame(frame):
    if frame is None:
        return frame

    try:
        with skyscan_faces_lock:
            faces = skyscan_latest_faces.copy()

        if not faces:
            return frame

        annotated_frame = frame.copy()

        for face_id, face_data in faces.items():
            x1, y1, x2, y2 = face_data['bbox']
            name = face_data['name']
            is_known = face_data['is_known']
            confidence = face_data.get('confidence', 0.0)

            color = (0, 255, 0) if is_known else (0, 0, 255)

            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

            if is_known:
                conf_text = f"{name} ({confidence:.2f})"
                cv2.putText(annotated_frame, conf_text, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            else:
                cv2.putText(annotated_frame, "UNKNOWN", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        return annotated_frame

    except Exception as e:
        print(f"Error drawing on frame: {e}")
        return frame

def skyscan_capture_frames_loop():
    global skyscan_drone_autopilot, skyscan_frame_queue, skyscan_stop_event

    print("Starting frame capture loop")
    initialize_face_recognition()
    last_log_time = time.time()
    frame_count = 0
    face_process_count = 0
    dropped_frames = 0
    success_frames = 0

    while not skyscan_stop_event.is_set() and skyscan_drone_autopilot and skyscan_drone_autopilot.keep_flying:
        try:
            if hasattr(skyscan_drone_autopilot, 'current_frame') and skyscan_drone_autopilot.current_frame is not None:
                with skyscan_drone_autopilot.frame_lock:
                    frame = skyscan_drone_autopilot.current_frame.copy()

                faces = process_frame_for_faces(frame)
                face_process_count += 1

                frame = draw_faces_on_frame(frame)

                if skyscan_frame_queue.full():
                    try:
                        to_remove = skyscan_frame_queue.maxsize // 2
                        for _ in range(to_remove):
                            skyscan_frame_queue.get_nowait()
                        dropped_frames += to_remove
                    except Exception as e:
                        print(f"Error managing frame queue: {e}")

                try:
                    skyscan_frame_queue.put(frame, block=False)
                    success_frames += 1
                except queue.Full:
                    dropped_frames += 1

                frame_count += 1

                current_time = time.time()
                if current_time - last_log_time >= 5:
                    elapsed = current_time - last_log_time
                    fps = frame_count / elapsed
                    face_fps = face_process_count / elapsed
                    frame_count = 0
                    face_process_count = 0
                    dropped_frames = 0
                    success_frames = 0
                    last_log_time = current_time
            else:
                blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank_frame, "Waiting for video feed...", (80, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

                if skyscan_frame_queue.full():
                    try:
                        skyscan_frame_queue.get_nowait()
                    except:
                        pass

                skyscan_frame_queue.put(blank_frame)

        except Exception as e:
            print(f"Error in capture loop: {e}")

    print("Frame capture loop ended")

def skyscan_generate_frames():
    global skyscan_frame_queue, skyscan_stop_event, skyscan_is_initializing, skyscan_is_running

    print("Starting frame generator for video stream")
    last_frame = None

    while not skyscan_stop_event.is_set():
        try:
            if skyscan_is_initializing:
                blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank_frame, "Initializing drone...", (80, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
                _, buffer = cv2.imencode('.jpg', blank_frame, encode_param)
                frame_bytes = buffer.tobytes()

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Access-Control-Allow-Origin: *\r\n\r\n' +
                       frame_bytes + b'\r\n')
                continue

            if not skyscan_frame_queue.empty():
                try:
                    img = list(skyscan_frame_queue.queue)[-1]
                    last_frame = img

                    if img is not None:
                        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                        _, buffer = cv2.imencode('.jpg', img, encode_param)
                        frame_bytes = buffer.tobytes()

                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n'
                               b'Access-Control-Allow-Origin: *\r\n\r\n' +
                               frame_bytes + b'\r\n')
                except Exception as e:
                    print(f"Error accessing frame queue: {e}")
            elif last_frame is not None:
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                _, buffer = cv2.imencode('.jpg', last_frame, encode_param)
                frame_bytes = buffer.tobytes()

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Access-Control-Allow-Origin: *\r\n\r\n' +
                       frame_bytes + b'\r\n')
            else:
                blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank_frame, "No video feed available", (80, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
                _, buffer = cv2.imencode('.jpg', blank_frame, encode_param)
                frame_bytes = buffer.tobytes()

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Access-Control-Allow-Origin: *\r\n\r\n' +
                       frame_bytes + b'\r\n')

        except Exception as e:
            print(f"Error generating frame: {e}")

            blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank_frame, f"Stream error", (150, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
            _, buffer = cv2.imencode('.jpg', blank_frame, encode_param)
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Access-Control-Allow-Origin: *\r\n\r\n' +
                   frame_bytes + b'\r\n')

def skyscan_run_drone_autopilot():
    global skyscan_drone_autopilot, skyscan_is_running, skyscan_is_initializing

    capture_thread = None
    skyscan_is_initializing = True

    try:
        print("Starting drone autopilot")

        skyscan_drone_autopilot = DroneAutoPilot()

        capture_thread = threading.Thread(target=skyscan_capture_frames_loop, daemon=True)
        capture_thread.start()
        print("Frame capture thread started")

        skyscan_is_running = True
        skyscan_is_initializing = False

        skyscan_drone_autopilot.connect_and_stream()

    except Exception as e:
        print(f"Error in drone autopilot: {e}")
    finally:
        print("Stopping drone autopilot")
        skyscan_stop_event.set()
        skyscan_is_initializing = False

        if skyscan_drone_autopilot:
            skyscan_drone_autopilot.stop()

        skyscan_is_running = False

        if capture_thread and capture_thread.is_alive():
            capture_thread.join(timeout=3.0)

@app.post("/skyscan/start")
async def skyscan_start_drone(background_tasks: BackgroundTasks):
    global skyscan_is_running, skyscan_is_initializing, skyscan_drone_autopilot

    if skyscan_is_running or skyscan_is_initializing:
        return {"status": "already_running", "message": "Drone is already running or initializing"}
    skyscan_stop_event.clear()
    skyscan_is_initializing = True
    background_tasks.add_task(skyscan_run_drone_autopilot)
    return {"status": "success", "message": "Drone starting up. Please wait..."}


@app.post("/skyscan/stop")
async def skyscan_stop_drone():
    global skyscan_is_running, skyscan_is_initializing, skyscan_drone_autopilot, skyscan_stop_event

    if not skyscan_is_running and not skyscan_is_initializing:
        return {"status": "not_running", "message": "Drone is not running"}

    skyscan_stop_event.set()
    skyscan_is_initializing = False
    skyscan_is_running = False

    if skyscan_drone_autopilot:
        try:
            print("Landing drone before stopping...")
            try:
                skyscan_drone_autopilot.controller.send_rc_control(0, 0, 0, 0)
                time.sleep(0.5)
            except Exception as e:
                print(f"Error stopping movement: {e}")

            skyscan_drone_autopilot.controller.land()

            time.sleep(5)

            skyscan_drone_autopilot.keep_flying = False
            skyscan_drone_autopilot.stop()
            skyscan_drone_autopilot = None

        except Exception as e:
            print(f"Error during landing sequence: {e}")
            # Încercăm o oprire de urgență în caz de eroare
            try:
                if skyscan_drone_autopilot:
                    skyscan_drone_autopilot.stop()
                    skyscan_drone_autopilot = None
            except:
                pass

    return {"status": "success", "message": "Drone landing initiated and operations stopped"}

@app.get("/skyscan/status")
async def skyscan_get_status():
    global skyscan_is_running, skyscan_is_initializing, skyscan_drone_autopilot

    if skyscan_is_initializing:
        return {
            "status": "initializing",
            "message": "Drone is initializing, please wait...",
            "metrics": {
                "right_distance": 0,
                "left_distance": 0,
                "right_sweep_angle": 0,
                "left_sweep_angle": 0
            }
        }

    if not skyscan_is_running or not skyscan_drone_autopilot:
        return {
            "status": "stopped",
            "message": "Drone is not running",
            "metrics": {
                "right_distance": 0,
                "left_distance": 0,
                "right_sweep_angle": 0,
                "left_sweep_angle": 0
            }
        }

    try:
        right_distance = float(skyscan_drone_autopilot.right_distance)
        left_distance = float(skyscan_drone_autopilot.left_distance)
        right_sweep_angle = float(skyscan_drone_autopilot.calculate_sweep_angle(right_distance))
        left_sweep_angle = float(skyscan_drone_autopilot.calculate_sweep_angle(left_distance))

        return {
            "status": "running",
            "message": "Drone is running",
            "metrics": {
                "right_distance": right_distance,
                "left_distance": left_distance,
                "right_sweep_angle": right_sweep_angle,
                "left_sweep_angle": left_sweep_angle
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error getting drone status: {str(e)}",
            "metrics": {
                "right_distance": 0,
                "left_distance": 0,
                "right_sweep_angle": 0,
                "left_sweep_angle": 0
            }
        }

@app.get("/skyscan/video-stream")
async def skyscan_video_stream():
    response = StreamingResponse(
        skyscan_generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"

    return response

@app.get("/skyscan/video")
async def skyscan_video_feed():
    return await skyscan_video_stream()

@app.get("/skyscan/faces")
async def skyscan_get_detected_faces():
    global skyscan_latest_faces, skyscan_is_running, skyscan_faces_history

    if not skyscan_is_running:
        return {
            "status": "stopped",
            "message": "Drone is not running",
            "faces": []
        }

    try:
        with skyscan_faces_lock:
            current_faces = skyscan_latest_faces.copy()

        with skyscan_faces_history_lock:
            history_faces = skyscan_faces_history.copy()

        current_face_list = []
        for face_id, face_data in current_faces.items():
            face_info = {
                "id": face_id,
                "name": face_data['name'],
                "is_known": face_data['is_known'],
                "confidence": face_data['confidence'],
                "active": True
            }
            current_face_list.append(face_info)

        history_face_list = []
        for face_id, face_data in history_faces.items():
            if not any(face["id"] == face_id for face in current_face_list):
                face_info = {
                    "id": face_id,
                    "name": face_data['name'],
                    "is_known": face_data['is_known'],
                    "confidence": face_data['confidence'],
                    "active": False
                }
                history_face_list.append(face_info)

        all_faces = current_face_list + history_face_list
        all_faces.sort(key=lambda x: x["id"])

        return {
            "status": "success",
            "message": "Faces detected",
            "faces": all_faces
        }
    except Exception as e:
        print(f"Error retrieving face data: {str(e)}")
        return {
            "status": "error",
            "message": f"Error retrieving face data: {str(e)}",
            "faces": []
        }

def reset_face_history():
    global skyscan_faces_history
    with skyscan_faces_history_lock:
        skyscan_faces_history = {}
    print("Face history reset successfully")

@app.post("/skyscan/reset-faces")
async def skyscan_reset_faces():
    reset_face_history()
    return {
        "status": "success",
        "message": "Face history reset successfully"
    }

@app.get("/skyscan/unknown-faces")
async def skyscan_get_unknown_faces():
    if not skyscan_is_running:
        return {
            "status": "stopped",
            "message": "Drone is not running",
            "faces": []
        }

    try:
        with skyscan_unknown_faces_lock:
            unknown_faces_list = list(skyscan_unknown_faces.values())

        unknown_faces_list.sort(key=lambda x: x['timestamp'], reverse=True)

        return {
            "status": "success",
            "message": "Unknown faces retrieved",
            "faces": unknown_faces_list
        }
    except Exception as e:
        print(f"Error retrieving unknown faces: {str(e)}")
        return {
            "status": "error",
            "message": f"Error retrieving unknown faces: {str(e)}",
            "faces": []
        }

@app.delete("/skyscan/unknown-faces/{face_id}")
async def skyscan_delete_unknown_face(face_id: str):
    success = remove_unknown_face(face_id)

    if success:
        return {
            "status": "success",
            "message": f"Unknown face {face_id} removed successfully"
        }
    else:
        return {
            "status": "error",
            "message": f"Unknown face {face_id} not found"
        }

@app.post("/skyscan/add-person")
async def skyscan_add_person(person_data: dict):
    try:
        face_id = person_data.get("face_id")
        name = person_data.get("name")

        if not face_id or not name:
            return {
                "status": "error",
                "message": "Missing face_id or name parameter"
            }

        with skyscan_unknown_faces_lock:
            if face_id not in skyscan_unknown_faces:
                return {
                    "status": "error",
                    "message": f"Unknown face {face_id} not found"
                }

            face_data = skyscan_unknown_faces[face_id]
            face_embedding = face_data['embedding']

            person_id = FaceDatabase.generate_unique_id()
            date_added = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            new_entry = {
                "name": name,
                "date_added": date_added,
                "last_recognition": date_added,
                "total_recognition": 1,
                "signature": face_embedding
            }

            skyscan_database[person_id] = new_entry
            db.reference('People').child(person_id).set(new_entry)
            del skyscan_unknown_faces[face_id]

            return {
                "status": "success",
                "message": f"Person {name} added successfully",
                "person_id": person_id
            }

    except Exception as e:
        print(f"Error adding person: {str(e)}")
        return {
            "status": "error",
            "message": f"Error adding person: {str(e)}"
        }

if __name__ == "__main__":
    signal.signal(signal.SIGINT, skyscan_signal_handler)
    signal.signal(signal.SIGTERM, skyscan_signal_handler)

    print("Starting FastAPI server on http://0.0.0.0:8000")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        timeout_keep_alive=120,
        log_level="info"
    )