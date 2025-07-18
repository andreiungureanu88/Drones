from tello_controller import TelloController
from depth_estimator import DepthEstimator
from face_recognizer import FaceRecognizer
import threading
from time import sleep
import time
import math

class DroneAutoPilot:
    def __init__(self):
        self.controller = TelloController()
        self.depth_estimator = DepthEstimator()
        self.face_recognizer = FaceRecognizer()
        self.keep_flying = True
        self.face_recognition_thread = threading.Thread(target=self.face_recognizer.recognize_faces)
        self.face_recognition_thread.daemon = True
        self.right_distance = 0
        self.left_distance = 0

    def start_face_recognition(self):
        self.face_recognition_thread.start()

    def lift_and_rotate(self):
        self.start_face_recognition()
        self.takeoff()

        self.rotate_and_capture(90)
        sleep(2)
        self.rotate_and_capture(180)
        sleep(2)
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

        for i in range(3):
            self.controller.move_slow_clockwise(int(right_interval)+1)
            sleep(1)

        for i in range(3):
            self.controller.move_slow_counter_clockwise(int(return_interval)+1)
            sleep(1)

        for i in range(3):
            self.controller.move_slow_clockwise(int(left_interval)+1)
            sleep(1)

        sleep(10)
        self.controller.land()

    def takeoff(self):
        self.controller.takeoff()
        self.controller.send_rc_control(0, 0, 40, 0)
        threading.Event().wait(4)

    def rotate_and_capture(self, angle):
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
        depth_values = []
        for _ in range(num_frames):
            if not self.keep_flying:
                break

            try:
                frame = self.controller.get_frame()
                if frame is not None:
                    depth_value = self.depth_estimator.process_image(frame)
                    depth_values.append(depth_value)
                else:
                    print("Failed to capture image from drone.")
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

    def connect_and_stream(self, num_frames=5):
        self.controller.connect()
        self.controller.streamon()
        self.start_face_recognition()

        depth_values = []

        try:
            while True:
                frame = self.controller.get_frame()
                if frame is not None:
                    depth_value = self.depth_estimator.process_image(frame)
                    depth_values.append(depth_value)
                    if len(depth_values) >= num_frames:
                        average_depth = sum(depth_values) / len(depth_values)
                        print(f"Live Stream Average Depth: {average_depth:.2f} m")
                        depth_values.clear()
                else:
                    print("Failed to capture image from drone.")
                self.maintain_altitude()
                sleep(1)
        except KeyboardInterrupt:
            print("Streaming interrupted by user.")
        finally:
            self.controller.streamoff()
            self.controller.end()

if __name__ == '__main__':
    autopilot = DroneAutoPilot()
    autopilot.lift_and_rotate()
