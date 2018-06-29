#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
from settings import Settings
from CameraProbe import CameraProbe
from FaceRecognitionBuilder import FaceRecognitionBuilder

from nohup import nohup


def main():
  settings=Settings('facelock')

  cameraProbe = CameraProbe()

  faceRecognition=FaceRecognitionBuilder().\
    withSettings(settings).\
    withCameraProperties(cameraProbe.getFps(),
                          cameraProbe.getWidth(),
                          cameraProbe.getHeight()).\
    build()

  faceRecognition.toggle()
  faceRecognition.run()
  
if __name__ == '__main__':
    nohup(main)