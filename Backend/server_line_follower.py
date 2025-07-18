import asyncio
import signal
import sys
import threading
import time
from queue import Queue
import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pathlib import Path
import keyboard
from tello_controller import TelloController

# Global variables
frame_queue = Queue(maxsize=10)
sensor_queues = [Queue(maxsize=10) for _ in range(3)]
stop_event = threading.Event()
drone_controller = None
is_flying = False
is_autonomous = False
processing_thread = None
mode_transition_lock = threading.Lock()

frame_width, frame_height = 480, 360
hsv_threshold_values = [0, 0, 57, 179, 255, 255]
virtual_sensor_count = 3
line_detection_threshold = 0.1
steering_sensitivity = 3
rotation_weights = [-28, -17, 0, 17, 28]
current_rotation = 0
forward_speed = 12
base_forward_speed = 12  # Viteza de bază când drona merge înainte
sensor_readings = [0, 0, 0]

# Variabile pentru stabilizare și predicție
last_rotations = [0] * 3  # Memorează ultimele rotații pentru stabilizare
rotation_index = 0  # Index pentru circulare în buffer
line_positions_history = []  # Istoricul pozițiilor liniei detectate
max_history_length = 5  # Câte poziții păstrăm în istoric


def stop_all_threads():
    global stop_event, processing_thread
    stop_event.set()
    time.sleep(0.3)
    stop_event.clear()

    active_threads = [t for t in threading.enumerate()
                      if t != threading.current_thread() and
                      (t.name.startswith("autonomous") or t == processing_thread)]

    for thread in active_threads:
        try:
            print(f"Așteptare terminare thread: {thread.name}")
            thread.join(timeout=1.0)  # Timeout pentru a evita blocarea
        except Exception as e:
            print(f"Eroare la oprirea thread-ului {thread.name}: {e}")

    # Resetăm referința la thread-ul principal de procesare
    processing_thread = None

    print("Toate thread-urile de control au fost oprite")


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
    """Funcție pentru curățare la oprirea serverului"""
    print("\nÎnchidere aplicație...")
    stop_event.set()
    global drone_controller, is_flying, is_autonomous

    # Mai întâi setăm flags-urile pentru a opri buclele
    is_autonomous = False
    is_flying = False

    # Aterizăm drona dacă este activă
    if drone_controller:
        print("Aterizare dronă...")
        try:
            drone_controller.land()
        except Exception as e:
            print(f"Eroare la aterizare în cleanup: {e}")

        # Eliberăm resursele controller-ului
        try:
            temp = drone_controller
            drone_controller = None
            del temp
        except:
            pass

    # Resetăm cozile pentru a elibera memoria
    reset_queues()


def signal_handler(sig, frame):
    """Handler pentru semnale de oprire"""
    print("\nSemnal de oprire primit...")
    cleanup()
    sys.exit(0)


# Funcție pentru a reseta cozile de streaming
def reset_queues():
    """Resetează toate cozile pentru a asigura streaming-ul corect după repornire"""
    global frame_queue, sensor_queues

    # Golește coada pentru frame-uri
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except:
            pass

    # Golește cozile pentru senzori
    for queue in sensor_queues:
        while not queue.empty():
            try:
                queue.get_nowait()
            except:
                pass

    # Recreează cozile pentru a ne asigura că nu există probleme de referință
    frame_queue = Queue(maxsize=10)
    sensor_queues = [Queue(maxsize=10) for _ in range(virtual_sensor_count)]

    # Adaugă un frame blank inițial în fiecare coadă
    blank_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
    cv2.putText(blank_frame, "În așteptare", (30, frame_height // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    frame_queue.put(blank_frame.copy())

    for i in range(virtual_sensor_count):
        sensor_width = frame_width // virtual_sensor_count
        sensor_blank = np.zeros((frame_height, sensor_width, 3), dtype=np.uint8)
        cv2.putText(sensor_blank, f"Senzor {i + 1}", (10, frame_height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        sensor_queues[i].put(sensor_blank)

    print("Toate cozile de streaming au fost resetate")


# Funcții îmbunătățite pentru procesarea imaginii
def create_binary_mask(input_frame):
    """Creează masca binară pentru detectarea liniei cu filtrare de zgomot"""
    hsv_frame = cv2.cvtColor(input_frame, cv2.COLOR_BGR2HSV)
    lower_bound = np.array([hsv_threshold_values[0], hsv_threshold_values[1], hsv_threshold_values[2]])
    upper_bound = np.array([hsv_threshold_values[3], hsv_threshold_values[4], hsv_threshold_values[5]])

    # Aplicăm un blur gaussian pentru a reduce zgomotul
    hsv_frame = cv2.GaussianBlur(hsv_frame, (5, 5), 0)

    binary_mask = cv2.inRange(hsv_frame, lower_bound, upper_bound)

    # Aplicăm operații morfologice pentru a îmbunătăți detectarea liniei
    kernel = np.ones((3, 3), np.uint8)
    binary_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, kernel)
    binary_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_OPEN, kernel)

    return binary_mask


def detect_line_position(binary_mask, display_frame):
    """Detectează poziția liniei în masca binară și o marchează pe frame-ul de afișare"""
    global line_positions_history

    center_x = frame_width // 2  # Valoare implicită dacă nu se detectează linie
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if len(contours) != 0:
        # Filtrăm contururile mici care pot fi zgomot
        valid_contours = [c for c in contours if cv2.contourArea(c) > 100]

        if valid_contours:
            largest_contour = max(valid_contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)

            center_x = x + w // 2
            center_y = y + h // 2

            # Desenăm conturul și centrul liniei
            cv2.drawContours(display_frame, [largest_contour], -1, (255, 0, 255), 7)
            cv2.circle(display_frame, (center_x, center_y), 10, (0, 255, 0), cv2.FILLED)

            # Desenăm o linie pentru a indica distanța față de centru
            cv2.line(display_frame, (frame_width // 2, frame_height // 2),
                     (center_x, center_y), (0, 255, 255), 2)

            # Actualizam istoricul pozițiilor
            line_positions_history.append(center_x)
            if len(line_positions_history) > max_history_length:
                line_positions_history.pop(0)

            # Dacă avem suficiente poziții, desenăm o predicție
            if len(line_positions_history) >= 3:
                trend = calculate_trend()
                prediction_x = center_x + trend
                prediction_x = max(0, min(frame_width - 1, prediction_x))  # Limitare la dimensiunile frame-ului

                cv2.circle(display_frame, (int(prediction_x), center_y), 5, (0, 0, 255), cv2.FILLED)

    # Adaugă informații despre poziția liniei pe imagine
    deviation = center_x - frame_width // 2
    cv2.putText(display_frame, f"Deviatie: {deviation}px", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

    return center_x


def calculate_trend():
    """Calculează tendința de mișcare a liniei bazată pe istoricul pozițiilor"""
    if len(line_positions_history) < 3:
        return 0

    # Calculăm tendința ca o medie ponderată a diferențelor
    # Dăm importanță mai mare schimbărilor recente
    weights = [0.2, 0.3, 0.5]  # Ponderi pentru ultimele 3 diferențe
    diffs = []

    for i in range(1, min(4, len(line_positions_history))):
        diffs.append(line_positions_history[-i] - line_positions_history[-(i + 1)])

    # Asigurăm că avem exact 3 diferențe
    while len(diffs) < 3:
        diffs.append(0)

    trend = sum(w * d for w, d in zip(weights, diffs))
    return int(trend)


def process_virtual_sensors(binary_mask, sensor_count):
    """Procesează masca binară și împarte-o în sectoare pentru senzorii virtuali cu sensibilitate ajustată"""
    global sensor_readings

    sensor_sections = np.hsplit(binary_mask, sensor_count)
    total_section_pixels = (binary_mask.shape[1] // sensor_count) * binary_mask.shape[0]
    readings = []
    sensor_frames_local = []

    for i, section in enumerate(sensor_sections):
        white_pixel_count = cv2.countNonZero(section)

        # Calculăm procentajul de pixeli albi pentru a-l afișa
        detection_percent = (white_pixel_count / total_section_pixels) * 100

        # Determină dacă senzorul detectează linia folosind threshold-ul ajustat
        if white_pixel_count > line_detection_threshold * total_section_pixels:
            readings.append(1)
        else:
            readings.append(0)

        # Convertim secțiunea în color pentru vizualizare mai bună
        section_color = cv2.cvtColor(section, cv2.COLOR_GRAY2BGR)

        # Adăugăm o nuanță verde pentru senzor activ sau roșie pentru inactiv
        if readings[-1] == 1:
            section_color = cv2.addWeighted(section_color, 0.7,
                                            np.full_like(section_color, (0, 255, 0)), 0.3, 0)
        else:
            section_color = cv2.addWeighted(section_color, 0.7,
                                            np.full_like(section_color, (0, 0, 200)), 0.3, 0)

        # Adăugăm text cu procentajul de detecție pentru debugging
        cv2.putText(section_color, f"{detection_percent:.1f}%", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(section_color, f"Prag: {line_detection_threshold * 100:.0f}%", (10, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        sensor_frames_local.append(section_color)

        # Adăugăm la coada pentru streaming
        if sensor_queues[i].full():
            try:
                sensor_queues[i].get_nowait()
            except:
                pass
        sensor_queues[i].put(section_color)

    sensor_readings = readings
    return readings


def calculate_drone_movement(sensor_readings, line_center_x):
    """Calculează mișcarea dronei cu adaptare a vitezei în funcție de curbe"""
    global current_rotation, drone_controller, last_rotations, rotation_index

    if not drone_controller or not is_flying or not is_autonomous:
        return

    # Calculăm deviația față de centru pentru controlul lateral
    lateral_movement = (line_center_x - frame_width // 2) // steering_sensitivity
    lateral_movement = int(np.clip(lateral_movement, -10, 10))

    if -2 < lateral_movement < 2:
        lateral_movement = 0

    # Determină rotația bazată pe citirile senzorilor
    if sensor_readings == [1, 0, 0]:
        current_rotation = rotation_weights[0]  # Virare puternică la stânga
    elif sensor_readings == [1, 1, 0]:
        current_rotation = rotation_weights[1]  # Virare ușoară la stânga
    elif sensor_readings == [0, 1, 0]:
        current_rotation = rotation_weights[2]  # Înainte
    elif sensor_readings == [0, 1, 1]:
        current_rotation = rotation_weights[3]  # Virare ușoară la dreapta
    elif sensor_readings == [0, 0, 1]:
        current_rotation = rotation_weights[4]  # Virare puternică la dreapta
    elif sensor_readings == [1, 1, 1]:
        current_rotation = rotation_weights[2]  # Înainte când toți senzorii detectează linia
    elif sensor_readings == [0, 0, 0]:
        # Când niciun senzor nu detectează linia, folosim istoricul pozițiilor
        if len(line_positions_history) >= 2:
            last_x = line_positions_history[-1]
            if last_x < frame_width // 3:  # Ultima poziție cunoscută era în stânga
                current_rotation = rotation_weights[0]  # Căutăm linia în stânga
            elif last_x > 2 * frame_width // 3:  # Ultima poziție cunoscută era în dreapta
                current_rotation = rotation_weights[4]  # Căutăm linia în dreapta
            else:
                current_rotation = rotation_weights[2]  # Mergem înainte
        else:
            current_rotation = rotation_weights[2]  # Înainte când nu avem informații
    elif sensor_readings == [1, 0, 1]:
        current_rotation = rotation_weights[2]  # Înainte pentru pattern neobișnuit
    else:
        current_rotation = 0

    # Stabilizare rotație pentru a evita miscări bruște
    last_rotations[rotation_index] = current_rotation
    rotation_index = (rotation_index + 1) % len(last_rotations)

    # Folosim media ultimelor rotații pentru o mișcare mai fluidă
    stabilized_rotation = sum(last_rotations) // len(last_rotations)

    # IMPORTANT: Adaptăm viteza în funcție de rotație
    # Reducem viteza în curbe pentru manevrabilitate mai bună
    adaptive_speed = base_forward_speed

    # Cu cât rotația este mai mare, cu atât reducem mai mult viteza
    if abs(stabilized_rotation) > 20:
        adaptive_speed = max(5, base_forward_speed - 5)  # Reducere majoră în curbe strânse
    elif abs(stabilized_rotation) > 10:
        adaptive_speed = max(7, base_forward_speed - 3)  # Reducere moderată

    # Trimite comenzile către dronă
    try:
        drone_controller.send_rc_control(lateral_movement, adaptive_speed, 0, stabilized_rotation)

        # Afișăm feedback despre comanda trimisă
        print(f"Control: lateral={lateral_movement}, forward={adaptive_speed}, rotation={stabilized_rotation}")
    except Exception as e:
        print(f"Eroare la trimiterea comenzilor către dronă: {e}")


# Funcție centralizată pentru procesarea frame-urilor
def process_frame(camera_frame):
    """Procesează un frame și actualizează toate cozile relevante"""
    if camera_frame is None:
        return None, None, None, []

    # Redimensionează și procesează frame-ul
    camera_frame = cv2.resize(camera_frame, (frame_width, frame_height))
    camera_frame = cv2.flip(camera_frame, 0)  # Flip vertical

    # Creează masca binară pentru detectarea liniei
    binary_mask = create_binary_mask(camera_frame)
    inverted_binary_mask = cv2.bitwise_not(binary_mask)

    # Adăugăm o grilă de referință pe imagine
    draw_reference_grid(camera_frame)

    # Detectează poziția liniei și marchează direct pe camera_frame
    line_center_x = detect_line_position(inverted_binary_mask, camera_frame)

    # Procesează senzorii virtuali
    readings = process_virtual_sensors(inverted_binary_mask, virtual_sensor_count)

    # Adăugăm informații despre starea de functionare
    add_status_overlay(camera_frame, readings)

    # Actualizează frame-ul pentru streaming după ce am desenat conturul și centrul
    if frame_queue.full():
        try:
            frame_queue.get_nowait()
        except:
            pass
    frame_queue.put(camera_frame.copy())

    return camera_frame, inverted_binary_mask, line_center_x, readings

    # Desenează linia centrală orizontală
    cv2.line(frame, (0, frame_height // 2), (frame_width, frame_height // 2),
             (100, 100, 100), 1)

    # Desenează diviziunile senzorilor
    for i in range(1, virtual_sensor_count):
        x = (frame_width // virtual_sensor_count) * i
        # În loc de LINE_DASH, vom folosi o linie punctată realizată manual
        for y in range(0, frame_height, 10):  # Desenăm segmente la fiecare 10 pixeli
            cv2.line(frame, (x, y), (x, min(y + 5, frame_height)), (50, 50, 50), 1)


def draw_reference_grid(frame):
    """Desenează o grilă de referință pe imagine"""
    # Desenează linia centrală verticală
    cv2.line(frame, (frame_width // 2, 0), (frame_width // 2, frame_height),
             (100, 100, 100), 1)

    # Desenează linia centrală orizontală
    cv2.line(frame, (0, frame_height // 2), (frame_width, frame_height // 2),
             (100, 100, 100), 1)

    # Desenează diviziunile senzorilor
    for i in range(1, virtual_sensor_count):
        x = (frame_width // virtual_sensor_count) * i
        # În loc de LINE_DASH, vom folosi o linie punctată realizată manual
        for y in range(0, frame_height, 10):  # Desenăm segmente la fiecare 10 pixeli
            cv2.line(frame, (x, y), (x, min(y + 5, frame_height)), (50, 50, 50), 1)


def add_status_overlay(frame, readings):
    """Adaugă un overlay cu informații de stare pe imagine, inclusiv viteza curentă"""
    global current_rotation

    # Calculăm viteza adaptivă curentă pentru afișare
    adaptive_speed = base_forward_speed
    if abs(current_rotation) > 20:
        adaptive_speed = max(5, base_forward_speed - 5)
    elif abs(current_rotation) > 10:
        adaptive_speed = max(7, base_forward_speed - 3)

    # Adăugăm o bară de stare în partea de jos a imaginii
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, frame_height - 40), (frame_width, frame_height),
                  (20, 20, 20), -1)

    # Adăugăm informații despre modul curent
    mode_text = "AUTONOM" if is_autonomous else "MANUAL"
    cv2.putText(overlay, f"Mod: {mode_text}", (10, frame_height - 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

    # Adăugăm informații despre rotația curentă
    cv2.putText(overlay, f"Rotatie: {current_rotation}", (160, frame_height - 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

    # Adăugăm informații despre viteza curentă
    cv2.putText(overlay, f"Viteza: {adaptive_speed}", (300, frame_height - 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

    sensor_text = ''.join(str(r) for r in readings)
    cv2.putText(overlay, f"Senzori: {sensor_text}", (10, frame_height - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

    # Aplicăm overlay-ul cu transparență
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

# Funcții de control dronă
def manual_control_mode():
    """Mod de control manual prin fereastra OpenCV"""
    global is_flying, is_autonomous, drone_controller

    print("Mod Control Manual")
    print("Folosiți următoarele taste:")
    print("W/S - înainte/înapoi")
    print("A/D - stânga/dreapta")
    print("Up/Down - sus/jos")
    print("Enter - pornește modul autonom")
    print("L - aterizează drona")

    cv2.namedWindow("Control Manual")

    # Inițializăm frame-urile pentru toate stream-urile
    blank_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)

    # Adăugăm un text pe frame-ul gol
    cv2.putText(blank_frame, "Asteptare frame de la drona...", (30, frame_height // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # Punem frame-ul în cozile de streaming
    frame_queue.put(blank_frame.copy())
    for i in range(virtual_sensor_count):
        # Pentru senzorii virtuali facem frame-uri mai înguste
        sensor_width = frame_width // virtual_sensor_count
        sensor_blank = np.zeros((frame_height, sensor_width, 3), dtype=np.uint8)
        cv2.putText(sensor_blank, f"Senzor {i + 1}", (10, frame_height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        sensor_queues[i].put(sensor_blank)

    while is_flying and not stop_event.is_set():
        # Verifică dacă s-a trecut la modul autonom
        if is_autonomous:
            try:
                cv2.destroyWindow("Control Manual")
            except:
                pass
            print("Am detectat tranziția la modul autonom, se termină bucla manuală")
            break

        # Procesează tastele pentru control
        if keyboard.is_pressed('w'):
            drone_controller.send_rc_control(0, 20, 0, 0)
        elif keyboard.is_pressed('s'):
            drone_controller.send_rc_control(0, -20, 0, 0)
        elif keyboard.is_pressed('a'):
            drone_controller.send_rc_control(-20, 0, 0, 0)
        elif keyboard.is_pressed('d'):
            drone_controller.send_rc_control(20, 0, 0, 0)
        elif keyboard.is_pressed('up'):
            drone_controller.send_rc_control(0, 0, 20, 0)
        elif keyboard.is_pressed('down'):
            drone_controller.send_rc_control(0, 0, -20, 0)
        elif keyboard.is_pressed('l'):  # Aterizare cu tasta 'l'
            print("Aterizare dronă cu tasta 'l'")
            is_flying = False
            try:
                drone_controller.land()
                drone_controller = None
            except:
                pass
            break
        else:
            if drone_controller:  # Verifică dacă controllerul există încă
                try:
                    drone_controller.send_rc_control(0, 0, 0, 0)
                except:
                    pass

        # Obține și procesează frame-ul
        try:
            if drone_controller:  # Verifică dacă controllerul există încă
                camera_frame = drone_controller.get_frame()
                if camera_frame is not None:
                    # Procesează frame-ul și actualizează toate cozile
                    process_frame(camera_frame)

                    # Afișează în fereastra OpenCV
                    if not is_autonomous:  # Verifică din nou pentru a evita erori în timpul tranziției
                        try:
                            camera_frame_display = cv2.resize(camera_frame, (frame_width, frame_height))
                            camera_frame_display = cv2.flip(camera_frame_display, 0)
                            cv2.imshow("Control Manual", camera_frame_display)
                            cv2.waitKey(1)
                        except Exception as e:
                            print(f"Eroare la afișarea ferestrei: {e}")
        except Exception as e:
            print(f"Eroare în bucla de control manual: {e}")

        # Verifică dacă trebuie să trecem în modul autonom
        if keyboard.is_pressed('enter') and is_flying:
            with mode_transition_lock:
                is_autonomous = True
                try:
                    cv2.destroyWindow("Control Manual")
                except:
                    pass
                print("Trecere la modul autonom...")
                # Pornește thread-ul pentru controlul autonom
                autonomous_thread = threading.Thread(target=autonomous_control_loop)
                autonomous_thread.daemon = True
                autonomous_thread.start()
                break

        time.sleep(0.03)  # Pauză mică pentru a nu suprasolicita CPU

    try:
        cv2.destroyWindow("Control Manual")
    except:
        pass
    print("Thread-ul de control manual s-a încheiat")


def autonomous_control_loop():
    global is_flying, is_autonomous, drone_controller, line_positions_history

    print("Pornire buclă control autonom")

    # Resetăm istoricul pozițiilor liniei
    line_positions_history = []

    # Resetăm istoricul rotațiilor
    for i in range(len(last_rotations)):
        last_rotations[i] = 0

    time.sleep(0.5)

    while is_flying and is_autonomous and not stop_event.is_set():
        try:
            # Obține frame-ul de la dronă
            if drone_controller:  # Verifică dacă controllerul există încă
                camera_frame = drone_controller.get_frame()
                if camera_frame is None:
                    time.sleep(0.03)
                    continue

                # Procesează frame-ul și obține toate informațiile necesare
                _, _, line_center_x, readings = process_frame(camera_frame)

                # Calculează mișcarea dronei cu adaptare a vitezei
                calculate_drone_movement(readings, line_center_x)

                if keyboard.is_pressed('l'):
                    print("Aterizare dronă cu tasta 'l' din modul autonom")
                    is_flying = False
                    is_autonomous = False
                    try:
                        drone_controller.land()
                        drone_controller = None
                    except:
                        pass
                    break
        except Exception as e:
            print(f"Eroare în bucla de control autonom: {e}")
            time.sleep(0.1)

        time.sleep(0.03)  # Pauză mică pentru a nu suprasolicita CPU

    print("Thread-ul de control autonom s-a încheiat")


# Funcții pentru streaming MJPEG
def generate_frames(queue):
    """Generator pentru stream MJPEG din coadă"""
    while not stop_event.is_set():
        try:
            if not queue.empty():
                try:
                    # Obține ultimul frame din coadă
                    img = list(queue.queue)[-1]
                    if img is not None:
                        # Asigură-te că imaginea este în format BGR
                        if len(img.shape) == 2:
                            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

                        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        frame = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n'
                               b'Access-Control-Allow-Origin: *\r\n\r\n' +
                               frame + b'\r\n')
                except Exception as e:
                    print(f"Eroare la generarea frame-ului: {e}")
            else:
                # Când coada este goală, generează un frame blank pentru a menține stream-ul activ
                blank_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
                cv2.putText(blank_frame, "In asteptare...", (30, frame_height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                _, buffer = cv2.imencode('.jpg', blank_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Access-Control-Allow-Origin: *\r\n\r\n' +
                       frame + b'\r\n')
        except Exception as e:
            print(f"Eroare generală în generate_frames: {e}")

        time.sleep(0.03)


def generate_sensor_frames(sensor_id):
    """Generator pentru stream MJPEG specific pentru senzori"""
    while not stop_event.is_set():
        try:
            if not sensor_queues[sensor_id].empty():
                try:
                    # Obține ultimul frame din coada senzorului
                    img = list(sensor_queues[sensor_id].queue)[-1]
                    if img is not None:
                        # Asigură-te că imaginea este în format BGR
                        if len(img.shape) == 2:
                            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

                        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        frame = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n'
                               b'Access-Control-Allow-Origin: *\r\n\r\n' +
                               frame + b'\r\n')
                except Exception as e:
                    print(f"Eroare la generarea frame-ului senzorului {sensor_id}: {e}")
            else:
                # Când coada este goală, generează un frame blank pentru a menține stream-ul activ
                sensor_width = frame_width // virtual_sensor_count
                blank_frame = np.zeros((frame_height, sensor_width, 3), dtype=np.uint8)
                cv2.putText(blank_frame, f"Senzor {sensor_id + 1}", (10, frame_height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                _, buffer = cv2.imencode('.jpg', blank_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Access-Control-Allow-Origin: *\r\n\r\n' +
                       frame + b'\r\n')
        except Exception as e:
            print(f"Eroare generală în generate_sensor_frames pentru senzorul {sensor_id}: {e}")

        time.sleep(0.03)


# Endpoint-uri FastAPI - Actualizate cu formatul /linefollower/...
@app.get("/")
def read_root():
    """Endpoint rădăcină"""
    return {
        "message": "Tello Drone Line Follower API",
        "status": "running",
        "endpoints": {
            "video_feed": "/linefollower/camera",
            "sensor_feeds": "/linefollower/sensor/{sensor_id}",
            "drone_stats": "/linefollower/stats",
            "start_drone": "/linefollower/start",
            "land_drone": "/linefollower/land",
            "switch_to_autonomous": "/linefollower/autonomous"
        }
    }


@app.get("/linefollower/camera")
async def video_feed():
    """Stream video principal"""
    return StreamingResponse(
        generate_frames(frame_queue),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache"
        }
    )


@app.get("/linefollower/sensor/{sensor_id}")
async def sensor_feed(sensor_id: int):
    """Stream pentru senzorii virtuali"""
    if 0 <= sensor_id < virtual_sensor_count:
        return StreamingResponse(
            generate_sensor_frames(sensor_id),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache"
            }
        )
    else:
        return {"error": "ID senzor invalid"}


@app.get("/linefollower/stats")
async def get_drone_stats():
    """Obține informații despre starea dronei"""
    global drone_controller, is_flying, is_autonomous, sensor_readings, current_rotation

    if not drone_controller:
        return {
            "success": True,
            "stats": {
                "active": False,
                "autonomous": False,
                "battery": None,
                "sensor_readings": [0, 0, 0],
                "rotation": 0,
                "speed": 0
            }
        }

    try:
        battery = None
        if is_flying and drone_controller:
            try:
                # Încearcă să obțină nivelul bateriei
                battery = drone_controller.get_battery()
            except Exception as e:
                print(f"Eroare la obținerea nivelului bateriei: {e}")

        # Calculăm viteza adaptivă curentă pentru a o raporta în statistici
        adaptive_speed = base_forward_speed
        if abs(current_rotation) > 20:
            adaptive_speed = max(5, base_forward_speed - 5)
        elif abs(current_rotation) > 10:
            adaptive_speed = max(7, base_forward_speed - 3)

        return {
            "success": True,
            "stats": {
                "active": is_flying,
                "autonomous": is_autonomous,
                "battery": battery,
                "sensor_readings": sensor_readings,
                "rotation": current_rotation,
                "speed": adaptive_speed  # Raportăm viteza adaptivă
            }
        }
    except Exception as e:
        print(f"Eroare la obținerea statisticilor: {e}")
        return {
            "success": False,
            "message": f"Eroare: {str(e)}"
        }


@app.post("/linefollower/start")
async def start_drone():
    """Pornește drona și modul de control manual"""
    global drone_controller, is_flying, is_autonomous, processing_thread

    if drone_controller and is_flying:
        return {"success": False, "message": "Drona este deja activă"}

    try:
        # Asigurăm oprirea oricărui controller vechi rămas
        if drone_controller:
            try:
                drone_controller = None
            except:
                pass

        # Resetăm toate variabilele de stare
        is_flying = False
        is_autonomous = False

        # Oprim orice thread-uri active
        stop_all_threads()

        # Resetăm toate cozile pentru a asigura stream-uri curate
        reset_queues()

        # Resetăm istoricul pozițiilor și rotațiilor
        global line_positions_history, last_rotations
        line_positions_history = []
        for i in range(len(last_rotations)):
            last_rotations[i] = 0

        # Acum inițializăm drona
        drone_controller = TelloController()
        drone_controller.takeoff()
        is_flying = True
        is_autonomous = False

        # Pornește thread-ul pentru controlul manual
        processing_thread = threading.Thread(target=manual_control_mode)
        processing_thread.daemon = True
        processing_thread.start()

        return {"success": True, "message": "Dronă pornită în modul manual"}
    except Exception as e:
        print(f"Eroare la pornirea dronei: {e}")
        is_flying = False
        drone_controller = None
        return {"success": False, "message": f"Eroare: {str(e)}"}


@app.post("/linefollower/autonomous")
async def switch_to_autonomous():
    """Comută la modul autonom de urmărire a liniei"""
    global is_autonomous, is_flying

    if not is_flying:
        return {"success": False, "message": "Drona nu este activă"}

    if is_autonomous:
        return {"success": False, "message": "Drona este deja în modul autonom"}

    try:
        with mode_transition_lock:
            is_autonomous = True

            # Pornește thread-ul pentru controlul autonom dacă nu este deja pornit
            if not any(t.name.startswith("autonomous") for t in threading.enumerate()):
                autonomous_thread = threading.Thread(
                    target=autonomous_control_loop,
                    name="autonomous_control"
                )
                autonomous_thread.daemon = True
                autonomous_thread.start()

        return {"success": True, "message": "Dronă comutată în modul autonom"}
    except Exception as e:
        print(f"Eroare la comutarea în modul autonom: {e}")
        return {"success": False, "message": f"Eroare: {str(e)}"}


@app.post("/linefollower/land")
async def land_drone():
    """Aterizează drona"""
    global drone_controller, is_flying, is_autonomous

    if not drone_controller or not is_flying:
        return {"success": False, "message": "Drona nu este activă"}

    try:
        # Setăm mai întâi flags-urile pentru a opri buclele
        is_autonomous = False
        is_flying = False

        # Oprim toate thread-urile active
        stop_all_threads()

        # Aterizăm drona
        if drone_controller:
            try:
                drone_controller.land()
            except Exception as e:
                print(f"Eroare la aterizare, dar continuăm procesul: {e}")

            # Eliberăm resursele controller-ului
            try:
                temp = drone_controller
                drone_controller = None
                del temp
            except:
                pass

        # Adăugăm frame-uri finale în cozi pentru a indica că drona a aterizat
        blank_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
        cv2.putText(blank_frame, "Drona a aterizat", (30, frame_height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        for _ in range(3):
            if not frame_queue.full():
                frame_queue.put(blank_frame.copy())

            for i in range(virtual_sensor_count):
                sensor_width = frame_width // virtual_sensor_count
                sensor_blank = np.zeros((frame_height, sensor_width, 3), dtype=np.uint8)
                cv2.putText(sensor_blank, "Aterizat", (10, frame_height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                if not sensor_queues[i].full():
                    sensor_queues[i].put(sensor_blank)

        return {"success": True, "message": "Dronă aterizată cu succes"}
    except Exception as e:
        print(f"Eroare la aterizarea dronei: {e}")
        is_flying = False
        is_autonomous = False
        drone_controller = None
        return {"success": True, "message": "Dronă aterizată (cu avertismente)"}


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("Pornire server FastAPI pe http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)