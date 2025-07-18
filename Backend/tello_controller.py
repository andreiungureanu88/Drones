import threading
from djitellopy import Tello
from utils import *
from time import sleep

class TelloController:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TelloController, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.tello = Tello()
        self.tello.connect()
        self.tello.streamon()
        print(f"Connected to Tello. Battery: {self.tello.get_battery()}%")

    def calibrate(self):
        self.tello.send_control_command("imu_calibrate")

    def get_frame(self):
        frame_read = self.tello.get_frame_read()
        frame = frame_read.frame
        if frame is not None and frame.size > 0:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return frame
        else:
            print("Invalid frame received.")
            return None

    def send_rc_control(self, left_right_velocity, for_back_velocity, up_down_velocity, yaw_velocity):
        self.tello.send_rc_control(left_right_velocity, for_back_velocity, up_down_velocity, yaw_velocity)

    def takeoff(self):
        self.tello.takeoff()

    def land(self):
        self.tello.land()

    def streamoff(self):
        self.tello.streamoff()

    def streamon(self):
        self.tello.streamon()

    def calculate_movement_time(self, distance_cm, speed_cms):
        return distance_cm / speed_cms


    def _handle_error(self):
        print("Handling error... Returning to safe state.")
        self.tello.land()
        sleep(5)

    def move_up(self,distance_up):
        self.tello.move_up(distance_up)

    def move_clockwise(self,degrees):
        self.tello.rotate_clockwise(degrees)

    def move_counter_clockwise(self,degrees):
        self.tello.rotate_counter_clockwise(degrees)

    def move_slow_clockwise(self, degrees, speed=9):

        self.tello.set_speed(speed)
        self.tello.rotate_clockwise(degrees)

    def move_slow_counter_clockwise(self, degrees, speed=9):

        self.tello.set_speed(speed)
        self.tello.rotate_counter_clockwise(degrees)

    def get_battery(self):
        try:
            return self.tello.get_battery()
        except:
            return 0