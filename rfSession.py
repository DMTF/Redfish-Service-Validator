# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

from datetime import datetime, timedelta
import requests
import logging
import sys
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from http.client import responses

commonHeader = {'OData-Version': '4.0'}

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class rfSession:
    def __init__(self, user, password, server, logger=None, chkCert=True, proxies=None):
        self.user = user
        self.pwd = password
        self.server = server
        self.chkCert = chkCert
        self.proxies = {} if proxies is None else proxies
        self.key = None
        self.loc = None
        self.timeout = None
        self.tick = None
        self.started = False
        self.chkCert = False

        if logger is None:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.DEBUG)
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.INFO)
            self.logger.addHandler(ch)
        else:
            self.logger = logger

    def startSession(self):
        payload = {
                'UserName': self.user,
                'Password': self.pwd
        }
        sr = requests.get(self.server + '/redfish/v1/', verify=self.chkCert, headers=commonHeader, proxies=self.proxies)
        success = sr.status_code in [200, 204] and sr.json() is not None
        if not success:
            self.logger.error('Could not retrieve service root to start Session')
            return False
        links = sr.json().get('Links')
        if links is not None:
            sessionsObj = links.get('Sessions')
            if sessionsObj is None:
                sessionsURI = '/redfish/v1/SessionService/Sessions'
                self.logger.info('using default URI {}'.format(sessionsURI))
            else:
                sessionsURI = sessionsObj.get('@odata.id', '/redfish/v1/SessionService/Sessions')
        else:
            self.logger.error('Could not retrieve service root link to start Session')
            return False

        response = requests.post(self.server + sessionsURI, json=payload, verify=self.chkCert,
                                 headers=commonHeader, proxies=self.proxies)
        statusCode = response.status_code
        ourSessionKey = response.headers.get('X-Auth-Token')
        ourSessionLocation = response.headers.get('Location', '/None')
        if ourSessionLocation.startswith('/'):
            ourSessionLocation = self.server + ourSessionLocation
        success = statusCode in range(200, 204) and ourSessionKey is not None

        self.key = ourSessionKey
        self.loc = ourSessionLocation
        self.timeout = timedelta(minutes=30)
        self.tick = datetime.now()
        self.started = success

        if success:
            self.logger.info('Session successfully created')
        else:
            if response.text is not None:
                self.logger.info('Response body from session creation:')
                self.logger.info('{}'.format(response.text))
            self.logger.info('Headers: {}'.format(response.headers))
            if statusCode in [400, 401]:
                self.logger.error('Error creating session. Status code "{} {}". Check supplied username and password.'
                                  .format(statusCode, responses[statusCode]))
                raise ValueError('Bad Username or Password')
            else:
                self.logger.error('Error creating session. Status code "{} {}".'
                                  .format(statusCode, responses[statusCode]))
                raise ValueError('Bad response from service')

        return success

    def isSessionOld(self):
        return datetime.now() - self.tick > self.timeout

    def getSessionKey(self):
        if not self.started:
            self.logger.error('This session is not started')
            return None
        if self.isSessionOld():
            self.logger.warning('This session is old')
        self.tick = datetime.now()
        return self.key

    def killSession(self):
        if self.started and not self.isSessionOld():
            headers = {'X-Auth-Token': self.getSessionKey()}
            headers.update(commonHeader)
            try:
                requests.delete(self.loc, verify=self.chkCert, headers=headers, proxies=self.proxies)
            except Exception as e:
                self.logger.warning('Error deleting current session: {}'.format(e))
        self.started = False
        return True

    def getLogger(self):
        """
        Grab logger for tools that might use this lib
        """
        return self.logger
