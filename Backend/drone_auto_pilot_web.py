from tello_controller import TelloController
from depth_estimator import DepthEstimator
import threading
from time import sleep
import time
import math
import cv2
import queue
import numpy as np


class DroneAutoPilot:
    def __init__(self):
        self.controller = TelloController()
        self.depth_estimator = DepthEstimator()
        self.keep_flying = True

        self.movement_thread = threading.Thread(target=self.movement_routine)
        self.movement_thread.daemon = True

        self.right_distance = 0
        self.left_distance = 0

        self.current_frame = None
        self.frame_lock = threading.Lock()

        self.frame_queue = queue.Queue(maxsize=10)

        self.debug_mode = True

    def start_movement_thread(self):
        self.movement_thread.start()
        if self.debug_mode:
            print("Movement thread started")

    def movement_routine(self):
        sleep(2)
        self.lift_and_rotate()
        print("Movement routine completed")

    def get_next_frame(self):
        try:
            frame_data = self.frame_queue.get(timeout=1.0)
            self.frame_queue.task_done()
            return frame_data
        except queue.Empty:
            blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank_frame, "Waiting for drone frames...", (50, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            _, buffer = cv2.imencode('.jpg', blank_frame)
            return buffer.tobytes()

    def start_frame_processing(self):
        self.controller.streamon()

        if self.debug_mode:
            print("Starting frame processing")

        print("Starting movement thread")
        self.start_movement_thread()

        print("Starting frame processing loop")
        frame_count = 0
        last_frame_time = time.time()

        while self.keep_flying:
            try:
                frame = self.controller.get_frame()
                current_time = time.time()

                if frame is not None:
                    frame_count += 1
                    if current_time - last_frame_time >= 5:
                        fps = frame_count / (current_time - last_frame_time)
                        if self.debug_mode:
                            print(f"Frame processing FPS: {fps:.2f}, Frame shape: {frame.shape}")
                        frame_count = 0
                        last_frame_time = current_time

                    with self.frame_lock:
                        self.current_frame = frame.copy()

                    annotated_frame = frame.copy()
                    cv2.putText(annotated_frame, "Drone View", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                    try:
                        _, buffer = cv2.imencode('.jpg', annotated_frame)
                        frame_bytes = buffer.tobytes()

                        self.frame_queue.put_nowait(frame_bytes)
                    except queue.Full:
                        pass


                else:
                    if self.debug_mode and time.time() - last_frame_time >= 3:
                        print("No frame received from drone")
                        last_frame_time = time.time()

                    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(blank_frame, "No drone feed available", (50, 240),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

                    _, buffer = cv2.imencode('.jpg', blank_frame)
                    try:
                        self.frame_queue.put_nowait(buffer.tobytes())
                    except queue.Full:
                        pass

                sleep(0.01)

            except Exception as e:
                print(f"Error in frame processing: {e}")
                sleep(0.5)

        print("Stopping frame processing")
        self.controller.streamoff()

    def lift_and_rotate(self):
        try:
            print("Starting lift and rotate sequence")
            self.takeoff()

            print("Rotating for measurement - 90 degrees")
            self.rotate_and_capture(90)
            sleep(2)
            print("Rotating for measurement - 180 degrees")
            self.rotate_and_capture(180)
            sleep(2)
            print("Returning to starting position")
            self.return_to_starting_position()

            print(f"Distanța la dreapta este {self.right_distance * 100} cm")
            print(f"Distanța la stânga este {self.left_distance * 100} cm")

            right_sweep_angle = self.calculate_sweep_angle(self.right_distance)
            left_sweep_angle = self.calculate_sweep_angle(self.left_distance)

            print(f"Unghiul de baleiaj la dreapta: {right_sweep_angle:.2f} grade")
            print(f"Unghiul de baleiaj la stânga: {left_sweep_angle:.2f} grade")

            right_interval = right_sweep_angle / 3
            left_interval = left_sweep_angle / 3
            return_interval = (right_sweep_angle + left_sweep_angle) / 3

            print("Starting right sweep")
            for i in range(3):
                self.controller.move_slow_clockwise(int(right_interval) + 1)
                sleep(1)

            print("Starting left sweep")
            for i in range(3):
                self.controller.move_slow_counter_clockwise(int(return_interval) + 1)
                sleep(1)

            print("Returning to starting position")
            for i in range(3):
                self.controller.move_slow_clockwise(int(left_interval) + 1)
                sleep(1)

            sleep(10)
            print("Landing")
            self.controller.land()
        except Exception as e:
            print(f"Error in movement routine: {e}")
            try:
                self.controller.land()
            except:
                pass

    def takeoff(self):
        print("Taking off")
        self.controller.takeoff()
        self.controller.send_rc_control(0, 0, 40, 0)
        threading.Event().wait(4)
        print("Takeoff complete")

    def rotate_and_capture(self, angle):
        print(f"Rotating {angle} degrees")
        if angle == 180:
            self.controller.move_counter_clockwise(180)
        elif angle == 90:
            self.controller.move_clockwise(90)

        threading.Event().wait(1)
        self.controller.send_rc_control(0, 0, 0, 0)
        sleep(4)
        self.capture_and_print_depth(angle)

    def return_to_starting_position(self):
        self.controller.move_clockwise(90)
        threading.Event().wait(1)
        self.controller.send_rc_control(0, 0, 0, 0)
        sleep(1)

    def maintain_altitude(self):
        self.controller.send_rc_control(0, 0, 0, 0)

    def land(self):
        self.controller.send_rc_control(0, 0, -20, 0)
        threading.Event().wait(3)
        self.controller.land()

    def capture_and_print_depth(self, angle, num_frames=5):
        print(f"Capturing depth at {angle} degrees")
        depth_values = []
        for i in range(num_frames):
            if not self.keep_flying:
                break

            try:
                with self.frame_lock:
                    if self.current_frame is not None:
                        frame = self.current_frame.copy()
                    else:
                        print(f"No current frame available (attempt {i + 1}/{num_frames}).")
                        sleep(0.5)
                        continue

                print(f"Processing frame {i + 1}/{num_frames} for depth estimation")
                depth_value = self.depth_estimator.process_image(frame)
                depth_values.append(depth_value)
                print(f"Depth value: {depth_value:.2f} m")

            except Exception as e:
                print(f"Error capturing image: {e}")
                self.keep_flying = False

            self.maintain_altitude()
            sleep(1)

        if depth_values:
            average_depth = sum(depth_values) / len(depth_values)
            if angle == 90:
                self.right_distance = average_depth
                print(f"Calculated Average Depth to the right: {self.right_distance:.2f} m")
            elif angle == 180:
                self.left_distance = average_depth
                print(f"Calculated Average Depth to the left: {self.left_distance:.2f} m")
        else:
            print("No depth values calculated.")

    def calculate_sweep_angle(self, distance, depth=4.0):
        angle = 2 * math.degrees(math.atan(distance / (2 * depth)))
        return angle

    def connect_and_stream(self):
        self.start_frame_processing()

    def stop(self):
        print("Stopping all operations")
        self.keep_flying = False
        try:
            self.controller.streamoff()
        except Exception as e:
            print(f"Error stopping stream: {e}")


if __name__ == '__main__':
    autopilot = DroneAutoPilot()
    try:
        autopilot.connect_and_stream()
    except KeyboardInterrupt:
        print("Operation interrupted by user")
    finally:
        autopilot.stop()