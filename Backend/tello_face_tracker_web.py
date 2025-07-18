from utils import *
from tello_controller import *


class TelloFaceTracker:
    def __init__(self, w=360, h=240, fbRange=[6200, 6800], pid=[0.4, 0.4, 0]):
        self.w = w
        self.h = h
        self.fbRange = fbRange
        self.pid = pid
        self.pError = 0
        self.startCounter = 0
        self.mydrone = None
        self.is_tracking = False

    def initialize(self):
        mytello = TelloController()
        mytello.streamon()
        mytello.takeoff()
        mytello.move_up(50)
        return mytello

    def telloGetFrame(self):
        img = self.mydrone.get_frame()
        if img is None:
            print("Nu am primit niciun cadru video.")
            return None
        else:
            img = cv2.resize(img, (self.w, self.h))
        return img

    def findFace(self, img):
        detector = cv2.FaceDetectorYN.create("./Configuration/face_detection_yunet_2023mar.onnx", "", [320, 320], 0.6, 0.3, 5000, 0, 0)
        img_W = int(img.shape[1])
        img_H = int(img.shape[0])
        detector.setInputSize((img_W, img_H))

        detections = detector.detect(img)

        myFaceList = []
        myFaceListArea = []

        if detections[1] is not None and len(detections[1]) > 0:
            for detection in detections[1]:
                x, y, w, h = detection[:4].astype(int)
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cx = x + w // 2
                cy = y + h // 2
                area = w * h
                cv2.circle(img, [cx, cy], 5, (0, 255, 0), cv2.FILLED)
                myFaceListArea.append(area)
                myFaceList.append([cx, cy])

        if len(myFaceListArea) != 0:
            i = myFaceListArea.index(max(myFaceListArea))
            return img, [myFaceList[i], myFaceListArea[i]]
        else:
            return img, [[0, 0], 0]

    def trackFace(self, info):
        fb = 0
        ud = 0
        area = info[1]
        cx, cy = info[0]


        if area == 0:
            self.mydrone.send_rc_control(0, 0, 0, 0)
            return 0

        error = cx - self.w // 2
        speed = self.pid[0] * error + self.pid[1] * (error - self.pError)
        speed = int(np.clip(speed, -100, 100))

        if self.fbRange[0] < area < self.fbRange[1]:
            fb = 0
        elif area > self.fbRange[1]:
            fb = -30
        elif area < self.fbRange[0] and area != 0:
            fb = 30

        if cy < self.h // 3:
            ud = 30
        elif cy > self.h * 2 // 3:
            ud = -30
        else:
            ud = 0

        print(f"Control - Speed: {speed}, FB: {fb}, UD: {ud}, Error: {error}")
        self.mydrone.send_rc_control(0, fb, ud, speed)
        return error

    def run(self):
        while True:
            img = self.telloGetFrame()
            if img is None:
                continue

            img, info = self.findFace(img)
            print("Center", info[0], "Area", info[1])

            self.pError = self.trackFace(info)
            #img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = cv2.resize(img, (640, 380))

            cv2.imshow('Image', img)

            if cv2.waitKey(1) & 0xFF == 27:
                self.mydrone.land()
                break

        self.mydrone.streamoff()
        cv2.destroyAllWindows()

    def start_tracking(self):
        self.is_tracking = True

    def start_face_tracking(self):
        try:
            if self.mydrone:
                self.disconnect()
                time.sleep(2)

            self.mydrone = self.initialize()
            self.is_tracking = True
            return True
        except Exception as e:
            print(f"Error in start_face_tracking: {e}")
            return False

    def stop_tracking(self):
        self.is_tracking = False
        if self.mydrone:
            self.mydrone.send_rc_control(0, 0, 0, 0)

    def get_stats(self):
        if self.mydrone:
            return {
                "battery": self.mydrone.get_battery(),
                "height": 0,
            }
        return None

    def disconnect(self):
        if self.mydrone:
            try:
                self.stop_tracking()
                self.mydrone.land()
                time.sleep(1)
                self.mydrone.streamoff()
                self.mydrone = None
            except Exception as e:
                print(f"Error disconnecting: {e}")
                self.mydrone = None


    def get_drone_battery(self):
        if self.mydrone:
            return self.mydrone.get_battery()
        else:
            return 0

if __name__ == '__main__':
    print("Starting face tracking...")
    tracker = TelloFaceTracker()
    tracker.run()