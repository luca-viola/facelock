import face_recognition
import cv2
import os
import time
from threading import Thread
from time import sleep

class FaceRecognitionBuilder(object):
  faceLock = None
  cam_fps = 0
  cam_width = 0
  cam_height = 0
  settings = None
  visualFeedback = None

  def __init__(self):
    self.faceLock = None

  def withSettings(self, settings):
    self.settings = settings
    return self

  def withVisualFeedback(self, trayIconVisualFeedback):
    self.visualFeedback = trayIconVisualFeedback
    return self

  def withCameraProperties(self, cam_fps, cam_width, cam_height):
    self.cam_fps = cam_fps
    self.cam_width = cam_width
    self.cam_height = cam_height
    return self

  def build(self):
    self.faceLock = _FaceRecognition(self.settings)
    self.faceLock.setCamResolution(self.cam_fps, self.cam_width, self.cam_height)
    self.faceLock.setVisualFeedback(self.visualFeedback)
    return self.faceLock

class _FaceRecognition(Thread):
  video_capture = None
  hasWindow = False
  target_face = None
  target_face_enconding = None
  targetFaceName = ''
  running = True
  visualFeedback = None
  timeout = 0
  processFrameCount = 0
  imagePath = ''
  settings = None
  cam_fps = 0
  cam_width = 0
  cam_height = 0
  
  def __init__(self, settings):
    Thread.__init__(self)
    self.setName("FACE_RECOGNITION")
    self.settings = settings
    self.timeout = self.settings.getTimeout()
    self.processFrameCount = self.settings.getProcessCountsPerFps()
    self.imagePath = self.settings.getImagePath()
    self.targetFaceName = self.settings.getTargetFaceName()
    self.target_face = face_recognition.load_image_file(self.imagePath)
    self.target_face_enconding = face_recognition.face_encodings(self.target_face)[0]
    self.video_capture = cv2.VideoCapture(0)
  
  def run(self):
    self.running = True
    self.probeFaces()

  def isRunning(self):
    return self.running

  def quit(self):
    self.running = False
  
  def setVisualFeedback(self, visualFeedback):
    self.visualFeedback = visualFeedback
  
  def setCamResolution(self, cam_fps, cam_width, cam_height):
    self.cam_fps = cam_fps
    self.cam_width = cam_width
    self.cam_height = cam_height
  
  def probeFaces(self):
    known_face_encodings = [
      self.target_face_enconding
    ]
    known_face_names = [
      self.targetFaceName
    ]
    
    face_locations = []
    face_encodings = []
    face_names = []
    process_this_frame = True
    counter = time.time()
    
    while self.running == True:
      try:
        ret, frame = self.video_capture.read()
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        # small_frame = frame
      except cv2.error as e:
        counter = time.time()
        print("Exception caught!")
        video_capture = cv2.VideoCapture(0)
        continue
      rgb_small_frame = small_frame[:, :, ::-1]
      
      if process_this_frame == 0:
        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
        
        face_names = []
        for face_encoding in face_encodings:
          matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
          name = "Unknown"
          
          if True in matches:
            first_match_index = matches.index(True)
            name = known_face_names[first_match_index]
            counter = time.time()
          face_names.append(name)
     
      process_this_frame = (process_this_frame + 1) % int((self.cam_fps / self.processFrameCount))
      font = cv2.FONT_HERSHEY_DUPLEX
      
      if self.targetFaceName not in face_names:
        lapse = int(time.time() - counter)
        cv2.putText(small_frame, str(lapse), (10, 90), font, 4.0, (0, 0, 255), 0)
        if self.visualFeedback != None:
          self.visualFeedback.ko()
      else:
        if self.visualFeedback != None:
          self.visualFeedback.ok()
      
      if (lapse >= self.timeout and self.hasWindow == False) or  \
                    ((self.targetFaceName not in face_names) and
                                   ('Unknown' in face_names) and
                    self.settings.isLockingOnUnknownFacesOnly()):
        os.system(self.settings.getExecuteCommand())
        counter = time.time()
        continue
      
      if self.hasWindow == True:
        for (top, right, bottom, left), name in zip(face_locations, face_names):
          cv2.rectangle(small_frame, (left, top), (right, bottom), (0, 0, 255), 2)
          cv2.rectangle(small_frame, (left, bottom - 9), (right, bottom), (0, 0, 255), cv2.FILLED)
          cv2.putText(small_frame, name, (left + 6, bottom - 2), font, 0.33, (255, 255, 255), 1)
          
        cv2.namedWindow('Face Lock', cv2.WINDOW_NORMAL)
        cv2.imshow('Face Lock', small_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
          break
  
  def toggle(self):
    if self.hasWindow == False:
      self.hasWindow = True
    else:
      self.hasWindow = False
  
  def freeResources(self):
    if self.video_capture != None:
      while self.running == True:
        sleep(0.1)
      self.video_capture.release()
    cv2.destroyAllWindows()
