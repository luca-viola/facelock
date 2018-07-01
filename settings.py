import configparser
from appdirs import *
from shutil import copyfile

class Settings:
    appname = ''
    appauthor = ''
    fileName = ''
    filePath = ''

    config = configparser.ConfigParser()
    
    def firstStart(self):
        if(os.path.isdir(self.filePath)!=True):
          os.mkdir(self.filePath)
        if(os.path.isfile(self.filePath+"/"+self.fileName)!=True):
          copyfile(os.getcwd()+"/"+self.fileName,self.filePath+"/"+self.fileName)

    def __init__(self,appname,appauthor=''):
        self.appname=appname
        self.appauthor=appauthor
        self.fileName=appname+".conf"        
        self.filePath=user_config_dir(self.appname,self.appauthor)
        self.firstStart()
        self.config.read(self.filePath+"/"+self.fileName)

    def saveSettings(self):
        with open(self.filePath+"/"+self.fileName, 'w') as configfile:
            self.config.write(configfile)

    def getTimeout(self):
        return int(self.config['facelock']['timeout'])     
    
    def getExecuteCommand(self):
        return self.config['facelock']['executeCommand']

    def isTrackingOnStart(self):
        if self.config['facelock']['trackOnStart'] == "True":
          return True
        else:
          return False
        
    def getImagePath(self):
        return self.config['facelock']['imagePath']     

    def isLockingOnUnknownFacesOnly(self):
        if self.config['facelock']['lockOnUnknownFacesOnly'] == "True":
          return True
        else:
          return False     

    def getCameraIndex(self):
        return int(self.config['facelock']['cameraIndex'])    

    def getProcessCountsPerFps(self):
        return int(self.config['facelock']['processCountsPerFps'])     
            
    def getTargetFaceName(self):
        return self.config['facelock']['targetFaceName']

    def getSettingsDialogSize(self):
        size = self.config['facelock']['settingsDialogSize'].split("x")
        return list(map(int,size))

    def setTimeout(self,timeout):
        self.config['facelock']['timeout']=str(timeout)     

    def setExecuteCommand(self,executeCommand):
        self.config['facelock']['executeCommand']=executeCommand

    def setTrackingOnStart(self,isTrackingOnStart):
        self.config['facelock']['trackOnStart']=str(isTrackingOnStart)     

    def setLockOnUnknownFacesOnly(self,lockOnUnknowFacesOnly):
        self.config['facelock']['lockOnUnknownFacesOnly']=str(lockOnUnknowFacesOnly)

    def setImagePath(self,imagePath):
        self.config['facelock']['imagePath']=imagePath     

    def setCameraIndex(self,cameraIndex):
        self.config['facelock']['cameraIndex']=str(cameraIndex)     
        
    def setProcessCountsPerFps(self,processCountsPerFps):
        self.config['facelock']['processCountsPerFps']=str(processCountsPerFps)

    def setTargetFaceName(self,targetFaceName):
        self.config['facelock']['targetFaceName']=targetFaceName     
    
    def setSettingsDialogSize(self,width,height):
        self.config['facelock']['settingsDialogSize'] = str(width)+"x"+str(height)
