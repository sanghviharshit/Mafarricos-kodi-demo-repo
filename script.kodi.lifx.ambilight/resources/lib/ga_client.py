import sys
import os
import traceback
import requests
import clientinfo
import hashlib
import xbmc
import time

# for info on the metrics that can be sent to Google Analytics
# https://developers.google.com/analytics/devguides/collection/protocol/v1/parameters#events

logEventHistory = {}
from tools import configs

# wrap a function to catch, log and then re throw an exception
def log_error(errors=(Exception, )):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except errors as error:
                if not (hasattr(error, 'quiet') and error.quiet):
                    ga = GoogleAnalytics()
                    errStrings = ga.formatException()
                    ga.sendEventData("Exception", errStrings[0], errStrings[1], True)
                log.exception(error)
                log.error("log_error: %s \n args: %s \n kwargs: %s",
                          func.__name__, args, kwargs)
                raise
        return wrapper
    return decorator

# main GA class
class GoogleAnalytics():

    testing = False

    def __init__(self):

        client_info = clientinfo.ClientInfo()
        self.version = client_info.get_version()
        self.device_id = client_info.get_device_id()

        # user agent string, used for OS and Kodi version identification
        kodi_ver = xbmc.getInfoLabel("System.BuildVersion")
        if(not kodi_ver):
            kodi_ver = "na"
        kodi_ver = kodi_ver.strip()
        if(kodi_ver.find(" ") > 0):
            kodi_ver = kodi_ver[0:kodi_ver.find(" ")]
        self.userAgent = "Kodi/" + kodi_ver + " (" + self.getUserAgentOS() + ")"

        # Use set user name
        # self.user_name = configs('username') or configs('connectUsername') or 'None'
        self.user_name = 'None'

        # use md5 for client and user for analytics
        self.device_id = hashlib.md5(self.device_id).hexdigest()
        self.user_name = hashlib.md5(self.user_name).hexdigest()

        # resolution
        self.screen_mode = xbmc.getInfoLabel("System.ScreenMode")
        self.screen_height = xbmc.getInfoLabel("System.ScreenHeight")
        self.screen_width = xbmc.getInfoLabel("System.ScreenWidth")

        self.lang = xbmc.getInfoLabel("System.Language")

    def getUserAgentOS(self):

        if xbmc.getCondVisibility('system.platform.osx'):
            return "Mac OS X"
        elif xbmc.getCondVisibility('system.platform.ios'):
            return "iOS"
        elif xbmc.getCondVisibility('system.platform.windows'):
            return "Windows NT"
        elif xbmc.getCondVisibility('system.platform.android'):
            return "Android"
        elif xbmc.getCondVisibility('system.platform.linux.raspberrypi'):
            return "Linux Rpi"
        elif xbmc.getCondVisibility('system.platform.linux'):
            return "Linux"
        else:
            return "Other"

    def formatException(self):

        stack = traceback.extract_stack()
        exc_type, exc_obj, exc_tb = sys.exc_info()
        tb = traceback.extract_tb(exc_tb)
        full_tb = stack[:-1] + tb
        #log.error(str(full_tb))

		# get last stack frame
        latestStackFrame = None
        if(len(tb) > 0):
            latestStackFrame = tb[-1]
        #log.error(str(tb))

        fileStackTrace = ""
        try:
            # get files from stack
            stackFileList = []
            for frame in full_tb:
                #log.error(str(frame))
                frameFile = (os.path.split(frame[0])[1])[:-3]
                frameLine = frame[1]
                if(len(stackFileList) == 0 or stackFileList[-1][0] != frameFile):
                    stackFileList.append([frameFile, [str(frameLine)]])
                else:
                    file = stackFileList[-1][0]
                    lines = stackFileList[-1][1]
                    lines.append(str(frameLine))
                    stackFileList[-1] = [file, lines]
            #log.error(str(stackFileList))

            for item in stackFileList:
                lines = ",".join(item[1])
                fileStackTrace += item[0] + "," + lines + ":"
            #log.error(str(fileStackTrace))
        except Exception as e:
            fileStackTrace = None
            log.error(e)

        errorType = "NA"
        errorFile = "NA"

        if latestStackFrame is not None:
            if fileStackTrace is None:
                fileStackTrace = os.path.split(latestStackFrame[0])[1] + ":" + str(latestStackFrame[1])

            codeLine = "NA"
            if(len(latestStackFrame) > 3 and latestStackFrame[3] != None):
                codeLine = latestStackFrame[3].strip()

            errorFile = "%s(%s)(%s)" % (fileStackTrace, exc_obj.message, codeLine)
            errorFile = errorFile[0:499]
            errorType = "%s" % (exc_type.__name__)
            #log.error(errorType + " - " + errorFile)

        del(exc_type, exc_obj, exc_tb)

        return errorType, errorFile

    def getBaseData(self):

        # all the data we can send to Google Analytics
        data = {}
        data['v'] = '1'
        data['tid'] = 'UA-83116503-2' # tracking id, this is the account ID

        data['ds'] = 'plugin' # data source

        data['an'] = 'Lifx4Kodi' # App Name
        data['aid'] = '1' # App ID
        data['av'] = self.version # App Version
        #data['aiid'] = '1.1' # App installer ID

        data['cid'] = self.device_id # Client ID
        #data['uid'] = self.user_name # User ID

        data['ua'] = self.userAgent # user agent string

        # add width and height, only add if full screen
        if(self.screen_mode.lower().find("window") == -1):
            data['sr'] = str(self.screen_width) + "x" + str(self.screen_height)

        data["ul"] = self.lang

        return data

    def sendScreenView(self, name):

        data = self.getBaseData()
        data['t'] = 'screenview' # action type
        data['cd'] = name

        self.sendData(data)

    def sendEventData(self, eventCategory, eventAction, eventLabel=None, throttle=False):

        # if throttling is enabled then only log the same event every 5 min
        if(throttle):
            throttleKey = eventCategory + "-" + eventAction + "-" + str(eventLabel)
            lastLogged = logEventHistory.get(throttleKey)
            if(lastLogged != None):
                timeSinceLastLog = time.time() - lastLogged
                if(timeSinceLastLog < 300):
                    #log.info("SKIPPING_LOG_EVENT : " + str(timeSinceLastLog) + " " + throttleKey)
                    return
            logEventHistory[throttleKey] = time.time()

        data = self.getBaseData()
        data['t'] = 'event' # action type
        data['ec'] = eventCategory # Event Category
        data['ea'] = eventAction # Event Action

        if(eventLabel != None):
            data['el'] = eventLabel # Event Label

        self.sendData(data)

    def sendData(self, data):

        if(configs('metric_logging') == "false"):
            return

        if (self.testing):
            xbmclog("GA: {}".format(str(data)))

        if(self.testing):
            url = "https://www.google-analytics.com/debug/collect" # test URL
        else:
            url = "https://www.google-analytics.com/collect" # prod URL

        try:
            r = requests.post(url, data)
        except Exception as error:
            log.error(error)
            r = None

        if(self.testing and r != None):
            xbmclog("GA: {}".format(r.text.encode('utf-8')))
