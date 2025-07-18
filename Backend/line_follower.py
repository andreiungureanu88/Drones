from time import sleep
import cv2
import numpy as np
from utils import *
import keyboard
from tello_controller import TelloController

drone_controller = TelloController()
drone_controller.takeoff()
sleep(1)

hsv_threshold_values = [0, 0, 109, 179, 255, 255]
virtual_sensor_count = 3
line_detection_threshold = 0.2
frame_width, frame_height = 480, 360
steering_sensitivity = 3
rotation_weights = [-25, -15, 0, 15, 25]
current_rotation = 0
forward_speed = 10
is_flying = True


def manual_control_mode():

    global is_flying
    print("Manual Control Mode")
    print("Use following keys:")
    print("W/S - forward/backward")
    print("A/D - left/right")
    print("Up/Down arrows - altitude up/down")
    print("Enter - start autonomous mode")
    print("L - land the drone")

    cv2.namedWindow("Manual Control View")

    while is_flying:
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
        elif keyboard.is_pressed('l'):  # Landing with 'l' key
            print("Landing drone with 'l' key")
            is_flying = False
            drone_controller.land()
            break
        else:
            drone_controller.send_rc_control(0, 0, 0, 0)

        camera_frame = drone_controller.get_frame()
        if camera_frame is not None:
            camera_frame = cv2.resize(camera_frame, (frame_width, frame_height))
            camera_frame = cv2.flip(camera_frame, 0)
            cv2.imshow("Manual Control View", camera_frame)
            cv2.waitKey(1)

        if keyboard.is_pressed('enter') and is_flying:
            cv2.destroyWindow("Manual Control View")
            print("Starting autonomous mode...")
            return


def create_binary_mask(input_frame):

    hsv_frame = cv2.cvtColor(input_frame, cv2.COLOR_RGB2HSV)
    lower_bound = np.array([hsv_threshold_values[0], hsv_threshold_values[1], hsv_threshold_values[2]])
    upper_bound = np.array([hsv_threshold_values[3], hsv_threshold_values[4], hsv_threshold_values[5]])

    binary_mask = cv2.inRange(hsv_frame, lower_bound, upper_bound)
    return binary_mask


def detect_line_position(binary_mask, display_frame):
    center_x = 0
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    if len(contours) != 0:
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)

        center_x = x + w // 2
        center_y = y + h // 2

        cv2.drawContours(display_frame, largest_contour, -1, (255, 0, 255), 7)
        cv2.circle(display_frame, (center_x, center_y), 10, (0, 255, 0), cv2.FILLED)
        return center_x
    else:
        print("No line detected")
        return center_x


def process_virtual_sensors(binary_mask, sensor_count):

    sensor_sections = np.hsplit(binary_mask, sensor_count)
    total_section_pixels = (binary_mask.shape[1] // sensor_count) * binary_mask.shape[0]
    sensor_readings = []

    for i, section in enumerate(sensor_sections):
        white_pixel_count = cv2.countNonZero(section)

        if white_pixel_count > line_detection_threshold * total_section_pixels:
            sensor_readings.append(1)
        else:
            sensor_readings.append(0)

        cv2.imshow(f"Sensor {i}", section)

    print(f"Sensor readings: {sensor_readings}")
    return sensor_readings


def calculate_drone_movement(sensor_readings, line_center_x):

    global current_rotation

    lateral_movement = (line_center_x - frame_width // 2) // steering_sensitivity
    lateral_movement = int(np.clip(lateral_movement, -10, 10))

    if -2 < lateral_movement < 2:
        lateral_movement = 0

    if sensor_readings == [1, 0, 0]:
        current_rotation = rotation_weights[0]
    elif sensor_readings == [1, 1, 0]:
        current_rotation = rotation_weights[1]
    elif sensor_readings == [0, 1, 0]:
        current_rotation = rotation_weights[2]
    elif sensor_readings == [0, 1, 1]:
        current_rotation = rotation_weights[3]
    elif sensor_readings == [0, 0, 1]:
        current_rotation = rotation_weights[4]
    elif sensor_readings == [1, 1, 1]:
        current_rotation = rotation_weights[2]
    elif sensor_readings == [0, 0, 0]:
        current_rotation = rotation_weights[2]
    elif sensor_readings == [1, 0, 1]:
        current_rotation = rotation_weights[2]
    else:
        current_rotation = 0

    drone_controller.send_rc_control(lateral_movement, forward_speed, 0, current_rotation)


manual_control_mode()

cv2.namedWindow("Camera View")

while is_flying:
    camera_frame = drone_controller.get_frame()
    if camera_frame is None:
        continue

    camera_frame = cv2.resize(camera_frame, (frame_width, frame_height))
    camera_frame = cv2.flip(camera_frame, 0)

    binary_mask = create_binary_mask(camera_frame)
    inverted_binary_mask = cv2.bitwise_not(binary_mask)

    line_center_x = detect_line_position(inverted_binary_mask, camera_frame)
    sensor_readings = process_virtual_sensors(inverted_binary_mask, virtual_sensor_count)

    calculate_drone_movement(sensor_readings, line_center_x)

    if keyboard.is_pressed('l'):
        print("Landing drone with 'l' key")
        is_flying = False
        drone_controller.land()
        break

    cv2.imshow("Camera View", camera_frame)
    cv2.imshow("Line Detection", inverted_binary_mask)
    cv2.waitKey(1)

cv2.destroyAllWindows()
print("Program ended")