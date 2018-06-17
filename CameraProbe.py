import cv2

class CameraProbe():
  fps = 0
  width = 0
  height = 0

  def __init__(self,cameraIndex=0):
    video_capture = cv2.VideoCapture(cameraIndex)

    (major_ver, minor_ver, subminor_ver) = (cv2.__version__).split('.')
    if int(major_ver)  < 3 :
        self.fps = video_capture.get(cv2.cv.CV_CAP_PROP_FPS)
        self.width = video_capture.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH)
        self.height = video_capture.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT)
    else :
        self.fps = video_capture.get(cv2.CAP_PROP_FPS)
        self.width = video_capture.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.height = video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
    
    video_capture.release()
    
  def getFps(self):
    return self.fps

  def getWidth(self):
    return self.width

  def getHeight(self):
    return self.height

    