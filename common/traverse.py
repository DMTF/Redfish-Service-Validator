# Copyright Notice:
# Copyright 2016-2020 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import json
from datetime import datetime
from functools import lru_cache
from urllib.parse import urlparse, urlunparse
from http.client import responses

import redfish as rf
import common.catalog as catalog
from common.helper import navigateJsonFragment
from common.metadata import Metadata

import logging
my_logger = logging.getLogger(__name__)
traverseLogger = my_logger

# dictionary to hold sampling notation strings for URIs
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
    newService = rfService(config)
    return newService

class rfService():
    def __init__(self, config):
        traverseLogger.info('Setting up service...')
        self.active, self.config = False, config
        self.logger = getLogger()

        self.config['configuri'] = self.config['ip']
        self.config['metadatafilepath'] = self.config['schema_directory']
        self.config['usessl'] = urlparse(self.config['configuri']).scheme in ['https']
        self.config['certificatecheck'] = False
        self.config['certificatebundle'] = None
        self.config['timeout'] = 10

        self.catalog = catalog.SchemaCatalog(self.config['metadatafilepath'])

        if not self.config['usessl'] and not self.config['forceauth']:
            if self.config['username'] not in ['', None] or self.config['password'] not in ['', None]:
                traverseLogger.warning('Attempting to authenticate on unchecked http/https protocol is insecure, if necessary please use ForceAuth option.  Clearing auth credentials...')
                self.config['username'] = ''
                self.config['password'] = ''
        
        rhost, user, passwd = self.config['configuri'], self.config['username'], self.config['password']
        self.context = rf.redfish_client( base_url = rhost, username = user, password = passwd )
        self.context.login( auth = self.config['authtype'].lower() )

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
        success, data, status, delay = self.callResourceURI(Metadata.metadata_uri)

        if success and data is not None and status in range(200,210):
            self.metadata = Metadata(data, self, my_logger)
        else:
            self.metadata = Metadata(None, self, my_logger)

        self.active = True


    def close(self):
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
            URLDest = urlunparse((scheme, netloc, path, '', '', '')) #URILink
        else:
            URLDest = urlunparse((scheme, netloc, path, params, query, fragment))

        payload, statusCode, elapsed, auth, noauthchk = None, '', 0, None, True

        isXML = False
        if "$metadata" in path or ".xml" in path[:-5]:
            isXML = True
            traverseLogger.debug('Should be XML')

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

        certVal = ChkCertBundle if ChkCert and ChkCertBundle not in [None, ""] else ChkCert

        # rs-assertion: must have application/json or application/xml
        traverseLogger.debug('callingResourceURI {}with authtype {} and ssl {}: {} {}'.format(
            'out of service ' if not inService else '', AuthType, UseSSL, URILink, headers))
        response = None
        try:
            if payload is not None: # and CacheMode == 'Prefer':
                return True, payload, -1, 0
            startTick = datetime.now()
            response = self.context.get(URLDest)  # only proxy non-service
            elapsed = datetime.now() - startTick
            statusCode = response.status

            traverseLogger.debug('{}, {},\nTIME ELAPSED: {}'.format(statusCode, response.getheaders(), elapsed))
            if statusCode in [200]:
                contenttype = response.getheader('content-type')
                if contenttype is None:
                    traverseLogger.error("Content-type not found in header: {}".format(URILink))
                    contenttype = ''
                if 'application/json' in contenttype:
                    traverseLogger.debug("This is a JSON response")
                    decoded = response.dict
                            
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
                            decoded = response.dict
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

        # except requests.exceptions.SSLError as e:
        #     traverseLogger.error("SSLError on {}: {}".format(URILink, repr(e)))
        #     traverseLogger.debug("output: ", exc_info=True)
        # except requests.exceptions.ConnectionError as e:
        #     traverseLogger.error("ConnectionError on {}: {}".format(URILink, repr(e)))
        #     traverseLogger.debug("output: ", exc_info=True)
        # except requests.exceptions.Timeout as e:
        #     traverseLogger.error("Request has timed out ({}s) on resource {}".format(timeout, URILink))
        #     traverseLogger.debug("output: ", exc_info=True)
        # except requests.exceptions.RequestException as e:
        #     traverseLogger.error("Request has encounted a problem when getting resource {}: {}".format(URILink, repr(e)))
        #     traverseLogger.debug("output: ", exc_info=True)
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
