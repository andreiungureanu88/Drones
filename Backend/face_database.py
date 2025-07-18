from utils import *
import datetime
import os
import random
from os import listdir
from numpy import expand_dims
import cv2
from PIL import Image
import tensorflow as tf
import numpy as np
import firebase_admin
from firebase_admin import credentials, db
from keras_facenet import FaceNet

cred = credentials.Certificate('./Configuration/tellodrone-baebd-firebase-adminsdk-v09bs-1b7c673b01.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': "https://tellodrone-baebd-default-rtdb.europe-west1.firebasedatabase.app/"
})

class FaceDatabase:
    def __init__(self, folder='Images'):
        self.folder = folder
        self.detector = cv2.FaceDetectorYN.create(
            "./Configuration/face_detection_yunet_2023mar.onnx", "", [320, 320], 0.6, 0.3, 5000, 0, 0)
        self.face_net = FaceNet()
        self.database = {}
        self.ref = db.reference('People')

    @staticmethod
    def generate_unique_id():
        now = datetime.datetime.now()
        random_number = random.randint(1000, 9999)
        return now.strftime("%Y%m%d%H%M%S") + str(random_number)

    def build_database(self):
        for filename in listdir(self.folder):
            path = os.path.join(self.folder, filename)
            image = cv2.imread(path)

            img_width = int(image.shape[1])
            img_height = int(image.shape[0])
            self.detector.setInputSize((img_width, img_height))

            detections = self.detector.detect(image)

            if detections[1] is not None and len(detections[1]) > 0:
                x, y, w, h = detections[1][0][:4].astype(int)
            else:
                x, y, w, h = 1, 1, 10, 10

            x1, y1 = abs(x), abs(y)
            x2, y2 = x1 + w, y1 + h

            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            rgb_image = Image.fromarray(rgb_image)
            rgb_array = np.asarray(rgb_image)

            face_region = rgb_array[y1:y2, x1:x2]
            face_image = Image.fromarray(face_region)
            face_image = face_image.resize((160, 160))
            face_array = np.asarray(face_image)
            face_array = expand_dims(face_array, axis=0)

            with tf.device('/GPU:0'):
                face_embedding = self.face_net.embeddings(face_array)[0]

            person_id = self.generate_unique_id()
            name = os.path.splitext(filename)[0]
            date_added = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.database[person_id] = {
                "name": name,
                "date_added": date_added,
                "last_recognition": date_added,
                "total_recognition": 1,
                "signature": face_embedding.tolist()
            }

            self.ref.child(person_id).set(self.database[person_id])

    def load_database_from_firebase(self):
        data = self.ref.get()
        return {key: value for key, value in data.items()} if data else {}
