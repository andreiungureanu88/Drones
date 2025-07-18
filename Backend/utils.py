from djitellopy import Tello
import cv2
import numpy as np
from PIL import Image, ImageTk
from numpy import asarray, expand_dims
from keras_facenet import FaceNet
import tensorflow as tf
import firebase_admin
from firebase_admin import credentials, db
import threading
import queue
import tkinter as tk
import time
import os
import random
import datetime
from os import listdir
