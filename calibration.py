#!/usr/bin/env python3
from settings import Settings
from CameraProbe import CameraProbe
from FaceRecognitionBuilder import FaceRecognitionBuilder

from nohup import nohup


def main():
  settings = Settings('facelock')

  cameraProbe = CameraProbe()

  faceRecognition = FaceRecognitionBuilder(). \
    withSettings(settings). \
    withCameraProperties(cameraProbe.getFps(),
                         cameraProbe.getWidth(),
                         cameraProbe.getHeight()). \
    build()
  faceRecognition.hasWindow = True
  faceRecognition.run()


if __name__ == '__main__':
  nohup(main)

