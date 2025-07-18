from utils import *
from tello_controller import TelloController
from face_database import FaceDatabase
import threading



class FaceRecognizer:
    def __init__(self):
        self.detector = cv2.FaceDetectorYN.create(
            "./Configuration/face_detection_yunet_2023mar.onnx", "", [320, 320], 0.6, 0.3, 5000, 0, 0)
        self.face_net = FaceNet()
        self.tello = TelloController()
        self.databaseController= FaceDatabase()
        self.database = self.databaseController.load_database_from_firebase()
        self.unknown_faces_queue = queue.Queue()

        # Start the consumer thread
        self.consumer_thread = threading.Thread(target=self.consume_unknown_faces)
        self.consumer_thread.daemon = True
        self.consumer_thread.start()


    def is_image_clear(self, image, sharpness_threshold=6):
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
        sharpness = laplacian.var()

        min_val, max_val = gray_image.min(), gray_image.max()
        contrast = max_val - min_val

        print(f"Sharpness: {sharpness}")
        return sharpness >= sharpness_threshold

    def is_face_in_database(self, face_embedding):
        min_distance = float('inf')
        for key, value in self.database.items():
            stored_signature = np.array(value['signature'])
            dist = np.linalg.norm(stored_signature - face_embedding)
            if dist < min_distance:
                min_distance = dist

        return min_distance < 1

    def consume_unknown_faces(self):
        while True:
            face_image, face_embedding = self.unknown_faces_queue.get()

            if not self.is_face_in_database(face_embedding):
                self.add_new_face(face_image, face_embedding)

            self.unknown_faces_queue.task_done()

    def add_new_face(self, face_image, face_embedding):

        if not self.is_image_clear(np.array(face_image)):
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

                self.database[person_id] = new_entry
                db.reference('People').child(person_id).set(new_entry)

                print(f"Added new person: {name}")

            root.destroy()

        def on_cancel():
            root.destroy()

        face_image_pil = Image.fromarray(np.array(face_image))
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

    def recognize_faces(self):
        while True:
            frame = self.tello.get_frame()
            if frame is None:
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            img_width = int(frame_rgb.shape[1])
            img_height = int(frame_rgb.shape[0])
            self.detector.setInputSize((img_width, img_height))
            detections = self.detector.detect(frame_rgb)

            if detections[1] is not None and len(detections[1]) > 0:
                for detection in detections[1]:
                    x, y, w, h = detection[:4].astype(int)

                    x1, y1 = abs(x), abs(y)
                    x2, y2 = x1 + w, y1 + h

                    face_region = frame_rgb[y1:y2, x1:x2]
                    face_image = Image.fromarray(face_region)
                    face_image = face_image.resize((160, 160))
                    face_array = np.asarray(face_image)
                    face_array = expand_dims(face_array, axis=0)

                    with tf.device('/GPU:0'):
                        face_embedding = self.face_net.embeddings(face_array)[0]

                    min_distance = float('inf')
                    identity = 'UNKNOWN'

                    for key, value in self.database.items():
                        stored_signature = np.array(value['signature'])
                        dist = np.linalg.norm(stored_signature - face_embedding)
                        if dist < min_distance:
                            min_distance = dist
                            identity = value['name']

                    if min_distance < 1:
                        cv2.putText(frame, identity, (x1, y1 - 10), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 2, cv2.LINE_AA)
                    else:
                        cv2.putText(frame, "UNKNOWN", (x1, y1 - 10), cv2.FONT_HERSHEY_PLAIN, 1, (255, 0, 0), 2, cv2.LINE_AA)
                        self.unknown_faces_queue.put((face_image, face_embedding))

                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            cv2.imshow('Face Recognition', frame)

            if cv2.waitKey(1) & 0xFF == 27:
                break

        self.tello.streamoff()
        cv2.destroyAllWindows()
