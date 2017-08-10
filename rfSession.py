
# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link:
# https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from datetime import datetime, timedelta
import requests
import logging
import sys
from requests.packages.urllib3.exceptions import InsecureRequestWarning

commonHeader = {'OData-Version': '4.0'}

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

sessionLogger = logging.getLogger(__name__)
sessionLogger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
sessionLogger.addHandler(ch)


def getLogger():
    """
    Grab logger for tools that might use this lib
    """
    return sessionLogger


class rfSession:
    def __init__(self):
        self.user, self.pwd, self.server = None, None, None
        self.key, self.loc = None, None
        self.timeout, self.tick = 0, 0
        self.started, self.chkCert = False, False

    def startSession(self, user, password, server, chkCert=True, proxies=None):
        payload = {
                "UserName": user,
                "Password": password
        }
        if proxies is None:
            proxies = {}
        sr = requests.get(server + '/redfish/v1/', verify=chkCert, headers=commonHeader, proxies=proxies)
        success = sr.status_code in [200, 204] and sr.json() is not None
        if not success:
            sessionLogger.error("Could not retrieve serviceroot to start Session")
            return False
        links = sr.json().get('Links')
        if links is not None:
            sessionsObj = links.get('Sessions')
            if sessionsObj is None:
                sessionsURI = '/redfish/v1/SessionService/Sessions'
                sessionLogger.info('using default URI', sessionsURI)
            else:
                sessionsURI = sessionsObj.get('@odata.id', '/redfish/v1/SessionService/Sessions')
        else:
            sessionLogger.error("Could not retrieve serviceroot.links to start Session")
            return False

        response = requests.post(server + sessionsURI, json=payload, verify=chkCert, headers=commonHeader, proxies=proxies)
        statusCode = response.status_code
        ourSessionKey = response.headers.get("X-Auth-Token")
        ourSessionLocation = response.headers.get("Location", "/None")
        success = statusCode in range(200, 204) and ourSessionKey is not None

        self.user, self.pwd, self.server = user, None, server
        self.key, self.loc = ourSessionKey, ourSessionLocation
        self.timeout, self.tick = timedelta(minutes=30), datetime.now()
        self.started, self.chkCert = success, chkCert
        self.proxies = proxies

        if success:
            sessionLogger.info("Session successfully started")
        else:
            sessionLogger.info("Session failed to start {}".format(statusCode))

        return success

    def isSessionOld(self):
        return datetime.now() - self.tick > self.timeout

    def getSessionKey(self):
        if not self.started:
            sessionLogger.error("This session is not started")
            return None
        if self.isSessionOld():
            sessionLogger.error("This session is old")
        self.tick = datetime.now()
        return self.key

    def killSession(self):
        if self.started and not self.isSessionOld():
            headers = {"X-Auth-Token": self.getSessionKey()}
            headers.update(commonHeader)
            response = requests.delete(str(self.server) + str(self.loc), verify=self.chkCert, headers=headers, proxies=self.proxies)
        self.started = False
        return True
