import asyncio
import signal
import sys
import threading
import time
from queue import Queue
import cv2
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, Response
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
from tello_face_tracker_web import TelloFaceTracker
from drone_auto_pilot_web import DroneAutoPilot

# Global variables
frame_queue = Queue(maxsize=10)
tracker = None
stop_event = threading.Event()
tracking_thread = None
recording_active = False
video_writer = None
recording_filename = None
recording_path = Path("recordings")
recording_path.mkdir(exist_ok=True)

frame_queue_sky_scan = Queue(maxsize=10)

@asynccontextmanager
async def lifespan(app):
    yield
    cleanup()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def cleanup():
    print("\nShutting down application...")
    stop_event.set()
    global tracker
    if tracker:
        print("Landing drone...")
        tracker.disconnect()
        tracker = None


def signal_handler(sig, frame):
    print("\nReceived stop signal...")
    cleanup()
    sys.exit(0)

def face_tracking_loop():
    while not stop_event.is_set():
        if tracker and tracker.is_tracking and tracker.mydrone:
            try:
                img = tracker.telloGetFrame()
                if img is not None:
                    img, info = tracker.findFace(img)
                    tracker.pError = tracker.trackFace(info)

                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except:
                            pass
                    frame_queue.put(img)
            except Exception as e:
                print(f"Error in face tracking: {e}")
        time.sleep(0.03)


def generate_frames():
    while not stop_event.is_set():
        if not frame_queue.empty():
            try:
                img = list(frame_queue.queue)[-1]
                if img is not None:
                    _, buffer = cv2.imencode('.jpg', img)
                    frame = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n'
                           b'Access-Control-Allow-Origin: *\r\n\r\n' +
                           frame + b'\r\n')
            except Exception as e:
                print(f"Error generating frame: {e}")
        time.sleep(0.03)


def process_recording_frames():
    global recording_active, video_writer

    while recording_active and video_writer is not None:
        if not frame_queue.empty():
            try:
                img = list(frame_queue.queue)[-1]
                if img is not None:
                    video_writer.write(img)
            except Exception as e:
                print(f"Eroare la scrierea frame-ului video: {e}")
        time.sleep(0.05)


@app.get("/")
def read_root():
    return {
        "message": "Tello Drone Face Tracking API",
        "status": "running",
        "endpoints": {
            "video_feed": "/followme/video",
            "single_frame": "/followme/frame",
            "drone_stats": "/followme/stats",
            "start_tracking": "/followme/start",
            "stop_tracking": "/followme/stop",
            "land_drone": "/followme/land",
            "recording_start": "/followme/recording/start",
            "recording_stop": "/followme/recording/stop",
            "recording_download": "/followme/recording/download/{filename}"
        }
    }


@app.get("/followme/stats")
async def get_drone_stats():
    global tracker

    if not tracker:
        return {
            "success": True,
            "stats": {
                "tracking_active": False,
                "battery": None,
                "connection": "Not Initialized"
            }
        }

    try:
        if not tracker.mydrone:
            return {
                "success": True,
                "stats": {
                    "tracking_active": False,
                    "battery": None,
                    "connection": "Not Connected"
                }
            }

        try:
            battery = tracker.mydrone.get_battery()
            print(f"Battery level from drone: {battery}")
        except Exception as e:
            print(f"Error getting battery: {e}")
            battery = None

        stats = {
            "tracking_active": getattr(tracker, "is_tracking", False),
            "battery": battery,
            "height": 0,
            "connection": "Connected"
        }

        return {"success": True, "stats": stats}
    except Exception as e:
        print(f"Error in get_drone_stats: {e}")
        return {
            "success": True,
            "stats": {
                "tracking_active": False,
                "battery": None,
                "connection": "Error",
                "error": str(e)
            }
        }


@app.post("/followme/recording/start")
async def start_recording():
    global recording_active, video_writer, recording_filename

    try:
        if recording_active:
            return {"success": False, "message": "O înregistrare este deja în curs"}

        if video_writer is not None:
            video_writer.release()
            video_writer = None

        if frame_queue.empty():
            return {"success": False, "message": "Nu există frame-uri disponibile pentru înregistrare"}

        sample_frame = list(frame_queue.queue)[-1]
        if sample_frame is None:
            return {"success": False, "message": "Frame-ul eșantion este invalid"}

        now = datetime.now()
        recording_filename = f"drone_video_{now.strftime('%Y%m%d_%H%M%S')}.mp4"
        file_path = recording_path / recording_filename

        height, width = sample_frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(
            str(file_path),
            fourcc,
            20.0,
            (width, height)
        )

        recording_active = True

        threading.Thread(
            target=process_recording_frames,
            daemon=True
        ).start()

        return {"success": True, "message": "Înregistrarea a început"}

    except Exception as e:
        print(f"Eroare la pornirea înregistrării: {e}")
        return {"success": False, "message": str(e)}


@app.post("/followme/recording/stop")
async def stop_recording():
    global recording_active, video_writer, recording_filename

    try:
        if not recording_active:
            return {"success": False, "message": "Nu există o înregistrare activă"}
        recording_active = False
        time.sleep(0.5)

        if video_writer is not None:
            video_writer.release()

        saved_filename = recording_filename
        video_writer = None
        recording_filename = None

        return {
            "success": True,
            "message": "Înregistrarea a fost oprită cu succes",
            "filename": saved_filename
        }

    except Exception as e:
        print(f"Eroare la oprirea înregistrării: {e}")
        return {"success": False, "message": str(e)}


@app.get("/followme/recording/download/{filename}")
async def download_recording(filename: str):
    file_path = recording_path / filename
    print(file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fișierul nu a fost găsit")

    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/followme/video")
async def video_feed():
    response = StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


@app.get("/followme/frame")
async def get_frame():
    if not frame_queue.empty():
        try:
            img = list(frame_queue.queue)[-1]
            if img is not None:
                _, buffer = cv2.imencode('.jpg', img)
                frame = buffer.tobytes()

                return Response(
                    content=frame,
                    media_type="image/jpeg",
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Content-Disposition": "attachment; filename=frame.jpg"
                    }
                )
        except Exception as e:
            print(f"Error getting frame: {e}")

    return {"success": False, "message": "No frame available"}


@app.post("/followme/start")
async def start_face_tracking():
    global tracker, tracking_thread

    if not tracker:
        tracker = TelloFaceTracker()

    try:
        success = tracker.start_face_tracking()

        if not success:
            return {"success": False, "message": "Failed to initialize drone"}

        if not tracking_thread or not tracking_thread.is_alive():
            tracking_thread = threading.Thread(
                target=face_tracking_loop,
                daemon=True
            )
            tracking_thread.start()

        return {
            "success": True,
            "message": "Face tracking started"
        }
    except Exception as e:
        print(f"Error starting face tracking: {e}")
        return {"success": False, "message": str(e)}


@app.post("/followme/stop")
async def stop_tracking():
    global tracker
    if tracker:
        tracker.stop_tracking()
        return {"success": True, "message": "Tracking stopped"}
    return {"success": False, "message": "Tracker not initialized"}


@app.post("/followme/land")
async def land_drone():
    global tracker
    if tracker and tracker.mydrone:
        try:
            tracker.disconnect()
            tracker = None
            return {"success": True, "message": "Drone landed successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to land drone: {str(e)}")
    return {"success": False, "message": "No active drone connection"}


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("Starting FastAPI server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)