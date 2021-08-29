# Copyright Notice:
# Copyright 2016-2020 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import json, requests
from collections import OrderedDict
from functools import lru_cache
from urllib.parse import urlparse, urlunparse
from http.client import responses

from common.redfish import navigateJsonFragment
from common.session import rfSession
import common.schema as schema
from common.metadata import Metadata

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

import logging
my_logger = logging.getLogger(__name__)
traverseLogger = my_logger

# dictionary to hold sampling notation strings for URIs
commonHeader = {'OData-Version': '4.0'}

uri_sample_map = dict()
currentService = None
config = {}


class AuthenticationError(Exception):
    """Exception used for failed basic auth or token auth"""
    def __init__(self, msg=None):
        super(AuthenticationError, self).__init__(msg)

def getLogger():
    """
    Grab logger for tools that might use this lib
    """
    return my_logger

def startService(config):
    """startService

    Begin service to use, sets as global

    Notes: Strip globals, turn into normal factory

    :param config: configuration of service
    :param defaulted: config options not specified by the user
    """
    global currentService
    if currentService is not None:
        currentService.close()
    newService = rfService(config)
    currentService = newService
    config = newService.config
    return newService

class rfService():
    def __init__(self, my_config):
        traverseLogger.info('Setting up service...')
        global config
        config = my_config
        self.config = my_config
        # self.proxies = dict()
        self.active = False
        # Create a Session to optimize connection times
        self.session = requests.Session()

        # setup URI
        self.config['configuri'] = self.config['ip']
        self.config['metadatafilepath'] = self.config['schema_directory']
        self.config['usessl'] = urlparse(self.config['configuri']).scheme in ['https']
        self.config['certificatecheck'] = False
        self.config['certificatebundle'] = None
        self.config['timeout'] = 10

        self.currentSession = None
        if not self.config['usessl'] and not self.config['forceauth']:
            if config['username'] not in ['', None] or config['password'] not in ['', None]:
                traverseLogger.warning('Attempting to authenticate on unchecked http/https protocol is insecure, if necessary please use ForceAuth option.  Clearing auth credentials...')
                config['username'] = ''
                config['password'] = ''
        if config['authtype'].lower() == 'session':
            # certVal = chkcertbundle if ChkCert and chkcertbundle is not None else ChkCert
            # no proxy for system under test
            # self.currentSession = rfSession(config['username'], config['password'], config['configuri'], None, certVal, self.proxies)
            self.currentSession = rfSession(config['username'], config['password'], config['configuri'], None)
            self.currentSession.startSession()

        global currentService # TODO: This is still not ideal programming practice
        currentService = self
        success, data, status, delay = self.callResourceURI(Metadata.metadata_uri)
        if success:
            soup = schema.BeautifulSoup(data, "xml")
            schema_obj = schema.rfSchema(soup, '$metadata', 'service')
            self.metadata = Metadata(schema_obj, my_logger)
        else:
            pass
            self.metadata = Metadata(None, my_logger)

        target_version = 'n/a'

        # get Version
        success, data, status, delay = self.callResourceURI('/redfish/v1')
        if not success:
            traverseLogger.warn('Could not get ServiceRoot')
        else:
            if 'RedfishVersion' not in data:
                traverseLogger.warn('Could not get RedfishVersion from ServiceRoot')
            else:
                traverseLogger.info('Redfish Version of Service: {}'.format(data['RedfishVersion']))
                target_version = data['RedfishVersion']
        if target_version in ['1.0.0', 'n/a']:
            traverseLogger.warning('!!Version of target may produce issues!!')
        
        self.service_root = data
        self.active = True

    def close(self):
        if self.currentSession is not None and self.currentSession.started:
            self.currentSession.killSession()
        self.active = False

    @lru_cache(maxsize=128)
    def callResourceURI(self, URILink):
        traverseLogger = my_logger
        """
        Makes a call to a given URI or URL

        param arg1: path to URI "/example/1", or URL "http://example.com"
        return: (success boolean, data, request status code)
        """
        # rs-assertions: 6.4.1, including accept, content-type and odata-versions
        # rs-assertion: handle redirects?  and target permissions
        # rs-assertion: require no auth for serviceroot calls
        if URILink is None:
            traverseLogger.warn("This URI is empty!")
            return False, None, -1, 0

        config = self.config
        # proxies = self.proxies
        ConfigIP, UseSSL, AuthType, ChkCert, ChkCertBundle, timeout, Token = config['configuri'], config['usessl'], config['authtype'], \
                config['certificatecheck'], config['certificatebundle'], config['timeout'], config['token']

        scheme, netloc, path, params, query, fragment = urlparse(URILink)
        inService = scheme == '' and netloc == ''
        if inService:
            scheme, netloc, _path, __params, ___query, ____fragment = urlparse(ConfigIP)
            URLDest = urlunparse((scheme, netloc, path, params, query, fragment))
        else:
            URLDest = urlunparse((scheme, netloc, path, params, query, fragment))

        payload, statusCode, elapsed, auth, noauthchk = None, '', 0, None, True

        isXML = False
        if "$metadata" in path or ".xml" in path[:-5]:
            isXML = True
            traverseLogger.debug('Should be XML')

        ExtraHeaders = None
        if 'extrajsonheaders' in config and not isXML:
            ExtraHeaders = config['extrajsonheaders']
        elif 'extraxmlheaders' in config and isXML:
            ExtraHeaders = config['extraxmlheaders']

        # determine if we need to Auth...
        if inService:
            noauthchk =  URILink in ['/redfish', '/redfish/v1', '/redfish/v1/odata'] or\
                '/redfish/v1/$metadata' in URILink

            auth = None if noauthchk else (config.get('username'), config.get('password'))
            traverseLogger.debug('dont chkauth' if noauthchk else 'chkauth')


        # rs-assertion: do not send auth over http
        # remove UseSSL if necessary if you require unsecure auth
        if (not UseSSL and not config['forceauth']) or not inService or AuthType != 'Basic':
            auth = None

        # only send token when we're required to chkauth, during a Session, and on Service and Secure
        headers = {}
        headers.update(commonHeader)
        if not noauthchk and inService and UseSSL:
            traverseLogger.debug('successauthchk')
            if AuthType == 'Session':
                currentSession = currentService.currentSession
                headers.update({"X-Auth-Token": currentSession.getSessionKey()})
            elif AuthType == 'Token':
                headers.update({"Authorization": "Bearer " + Token})

        if ExtraHeaders is not None:
            headers.update(ExtraHeaders)

        certVal = ChkCertBundle if ChkCert and ChkCertBundle not in [None, ""] else ChkCert

        # rs-assertion: must have application/json or application/xml
        traverseLogger.debug('callingResourceURI {}with authtype {} and ssl {}: {} {}'.format(
            'out of service ' if not inService else '', AuthType, UseSSL, URILink, headers))
        response = None
        try:
            if payload is not None: # and CacheMode == 'Prefer':
                return True, payload, -1, 0
            response = self.session.get(URLDest, headers=headers, auth=auth, verify=certVal, timeout=timeout)  # only proxy non-service
            expCode = [200]
            elapsed = response.elapsed.total_seconds()
            statusCode = response.status_code
            traverseLogger.debug('{}, {}, {},\nTIME ELAPSED: {}'.format(statusCode, expCode, response.headers, elapsed))
            if statusCode in expCode:
                contenttype = response.headers.get('content-type')
                if contenttype is None:
                    traverseLogger.error("Content-type not found in header: {}".format(URILink))
                    contenttype = ''
                if 'application/json' in contenttype:
                    traverseLogger.debug("This is a JSON response")
                    decoded = response.json(object_pairs_hook=OrderedDict)
                    # navigate fragment
                    decoded = navigateJsonFragment(decoded, URILink)
                    if decoded is None:
                        traverseLogger.error(
                                "The JSON pointer in the fragment of this URI is not constructed properly: {}".format(URILink))
                elif 'application/xml' in contenttype:
                    decoded = response.text
                elif 'text/xml' in contenttype:
                    # non-service schemas can use "text/xml" Content-Type
                    if inService:
                        traverseLogger.warn(
                                "Incorrect content type 'text/xml' for file within service {}".format(URILink))
                    decoded = response.text
                else:
                    traverseLogger.error(
                            "This URI did NOT return XML or Json contenttype, is this not a Redfish resource (is this redirected?): {}".format(URILink))
                    decoded = None
                    if isXML:
                        traverseLogger.info('Attempting to interpret as XML')
                        decoded = response.text
                    else:
                        try:
                            json.loads(response.text)
                            traverseLogger.info('Attempting to interpret as JSON')
                            decoded = response.json(object_pairs_hook=OrderedDict)
                        except ValueError:
                            pass

                return decoded is not None, decoded, statusCode, elapsed
            elif statusCode == 401:
                if inService and AuthType in ['Basic', 'Token']:
                    if AuthType == 'Token':
                        cred_type = 'token'
                    else:
                        cred_type = 'username and password'
                    raise AuthenticationError('Error accessing URI {}. Status code "{} {}". Check {} supplied for "{}" authentication.'
                                              .format(URILink, statusCode, responses[statusCode], cred_type, AuthType))

        except requests.exceptions.SSLError as e:
            traverseLogger.error("SSLError on {}: {}".format(URILink, repr(e)))
            traverseLogger.debug("output: ", exc_info=True)
        except requests.exceptions.ConnectionError as e:
            traverseLogger.error("ConnectionError on {}: {}".format(URILink, repr(e)))
            traverseLogger.debug("output: ", exc_info=True)
        except requests.exceptions.Timeout as e:
            traverseLogger.error("Request has timed out ({}s) on resource {}".format(timeout, URILink))
            traverseLogger.debug("output: ", exc_info=True)
        except requests.exceptions.RequestException as e:
            traverseLogger.error("Request has encounted a problem when getting resource {}: {}".format(URILink, repr(e)))
            traverseLogger.debug("output: ", exc_info=True)
        except AuthenticationError as e:
            raise e  # re-raise exception
        except Exception as e:
            traverseLogger.error("A problem when getting resource {} has occurred: {}".format(URILink, repr(e)))
            traverseLogger.debug("output: ", exc_info=True)
            if response and response.text:
                traverseLogger.debug("payload: {}".format(response.text))

        if payload is not None:
            return True, payload, -1, 0
        return False, None, statusCode, elapsed


def callResourceURI(URILink):
    traverseLogger = my_logger
    if currentService is None:
        traverseLogger.warn("The current service is not setup!  Program must configure the service before contacting URIs")
        raise RuntimeError
    else:
        return currentService.callResourceURI(URILink)

