# Copyright Notice:
# Copyright 2016-2018 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import requests
import sys
import re
import os
import json
import random
from collections import OrderedDict
from functools import lru_cache
import logging
from rfSession import rfSession
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from http.client import responses
import configparser
from urllib.parse import urlparse, urlunparse

import metadata as md
from commonRedfish import createContext, getNamespace, getNamespaceUnversioned, getType, getVersion, navigateJsonFragment
import rfSchema

traverseLogger = logging.getLogger(__name__)
traverseLogger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
traverseLogger.addHandler(ch)

commonHeader = {'OData-Version': '4.0'}
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# dictionary to hold sampling notation strings for URIs
uri_sample_map = dict()

currentService = None


class AuthenticationError(Exception):
    """Exception used for failed basic auth or token auth"""
    def __init__(self, msg=None):
        super(AuthenticationError, self).__init__(msg)


def getLogger():
    """
    Grab logger for tools that might use this lib
    """
    return traverseLogger


# default config
argparse2configparser = {
        'user': 'username', 'nochkcert': '!certificatecheck', 'ca_bundle': 'certificatebundle', 'schemamode': 'schemamode',
        'suffix': 'schemasuffix', 'schemadir': 'metadatafilepath', 'nossl': '!usessl', 'timeout': 'timeout', 'service': 'servicemode',
        'http_proxy': 'httpproxy', 'localonly': 'localonlymode', 'https_proxy': 'httpsproxy', 'passwd': 'password',
        'ip': 'targetip', 'logdir': 'logpath', 'desc': 'systeminfo', 'authtype': 'authtype',
        'payload': 'payloadmode+payloadfilepath', 'cache': 'cachemode+cachefilepath', 'token': 'token',
        'linklimit': 'linklimit', 'sample': 'sample', 'nooemcheck': '!oemcheck', 'preferonline': 'preferonline',
        'uri_check': 'uricheck', 'version_check': 'versioncheck'
        }

configset = {
        "targetip": str, "username": str, "password": str, "authtype": str, "usessl": bool, "certificatecheck": bool, "certificatebundle": str,
        "metadatafilepath": str, "cachemode": (bool, str), "cachefilepath": str, "schemasuffix": str, "timeout": int, "httpproxy": str, "httpsproxy": str,
        "systeminfo": str, "localonlymode": bool, "servicemode": bool, "token": str, 'linklimit': dict, 'sample': int, 'extrajsonheaders': str, 'extraxmlheaders': str, "schema_pack": str,
        "forceauth": bool, "oemcheck": bool, 'preferonline': bool, 'uricheck': bool, 'versioncheck': str
        }

defaultconfig = {
        'authtype': 'Basic',
        'username': "",
        'password': "",
        'token': "",
        'oemcheck': True,
        'certificatecheck': True,
        'certificatebundle': "",
        'metadatafilepath': './SchemaFiles/metadata',
        'cachemode': 'Off',
        'cachefilepath': './cache',
        'schemasuffix': '_v1.xml',
        'httpproxy': "",
        'httpsproxy': "",
        'localonlymode': False,
        'servicemode': False,
        'preferonline': False,
        'linklimit': {'LogEntry': 20},
        'sample': 0,
        'timeout': 30,
        'schema_pack': None,
        'forceauth': False,
        'uricheck': False,
        'versioncheck': '',
        }

defaultconfig_by_version = {
        '1.0.0': {'schemasuffix': '.xml'},
        '1.0.6': {'uricheck': True}
        }

customval = {
        'linklimit': lambda v: re.findall('[A-Za-z_]+:[0-9]+', v)
        }

configSet = False

config = dict(defaultconfig)

def startService(config, defaulted=[]):
    """startService

    Begin service to use, sets as global

    Notes: Strip globals, turn into normal factory

    :param config: configuration of service
    :param defaulted: config options not specified by the user
    """
    global currentService
    if currentService is not None:
        currentService.close()
    currentService = rfService(config, defaulted)
    return currentService


def convertConfigParserToDict(configpsr):
    """convertConfigParserToDict

    Takes a raw config parser and strips out its options
    Used to circumvent normal config parser calls

    Notes: make function independent of tool

    :param configpsr: config parser
    """
    cdict = {}
    for category in configpsr:
        for option in configpsr[category]:
            val = configpsr[category][option]
            if option not in configset.keys() and category not in ['Information', 'Validator']:
                traverseLogger.error('Config option {} in {} unsupported!'.format(option, category))
            if val in ['', None]:
                continue
            if val.isdigit():
                val = int(val)
            elif option in customval:
                val = customval[option](val)
            elif str(val).lower() in ['on', 'true', 'yes']:
                val = True
            elif str(val).lower() in ['off', 'false', 'no']:
                val = False
            cdict[option] = val
    return cdict


def setByArgparse(args):
    """setByArgparse

    Set config via args namespace parsed by argsparse

    :param args: arg namespace
    """
    if args.config is not None:
        configpsr = configparser.ConfigParser()
        configpsr.read(args.config)
        cdict = convertConfigParserToDict(configpsr)
    else:
        cdict = {}
    for param in args.__dict__:
        if args.__dict__[param] is not None:
            if param in argparse2configparser:
                if isinstance(args.__dict__[param], list):
                    for cnt, item in enumerate(argparse2configparser[param].split('+')):
                        cdict[item] = args.__dict__[param][cnt]
                elif '+' not in argparse2configparser[param]:
                    if '!' in argparse2configparser[param]:
                        cdict[argparse2configparser[param].replace('!', '')] = not args.__dict__[param]
                    else:
                        cdict[argparse2configparser[param]] = args.__dict__[param]
            else:
                cdict[param] = args.__dict__[param]
    return setConfig(cdict)


def setConfig(cdict):
    """
    Set config based on configurable dictionary
    """
    # Send config only with keys supported by program
    linklimitdict = {}
    if cdict.get('linklimit') is not None:
        for item in cdict.get('linklimit'):
            if re.match('[A-Za-z_]+:[0-9]+', item) is not None:
                typename, count = tuple(item.split(':')[:2])
                if typename not in linklimitdict:
                    linklimitdict[typename] = int(count)
                else:
                    traverseLogger.error('Limit already exists for {}'.format(typename))
    cdict['linklimit'] = linklimitdict

    for item in cdict:
        if item not in configset:
            traverseLogger.debug('Unsupported {}'.format(item))
        elif cdict[item] is None and configset[item] is str:
            cdict[item] = ''
        elif not isinstance(cdict[item], configset[item]):
            traverseLogger.error('Unsupported {}, expected type {}'.format(item, configset[item]))

    global config
    config = dict()

    # set linklimit
    defaultlinklimit = defaultconfig['linklimit']

    config.update(cdict)

    config['certificatecheck'] = config.get('certificatecheck', True) and config.get('usessl', True)

    if 'extrajsonheaders' in config:
        config['extrajsonheaders'] = json.loads(config['extrajsonheaders'])
    if 'extraxmlheaders' in config:
        config['extraxmlheaders'] = json.loads(config['extraxmlheaders'])

    defaultlinklimit.update(config['linklimit'])
    config['linklimit'] = defaultlinklimit

    if 'cachemode' in config and config['cachemode'] not in ['Off', 'Fallback', 'Prefer']:
        if config['cachemode'] is not False:
            traverseLogger.error('CacheMode or path invalid, defaulting to Off')
        config['cachemode'] = 'Off'

    if 'authtype' in config and config['authtype'] not in ['None', 'Basic', 'Session', 'Token']:
        config['authtype'] = 'Basic'
        traverseLogger.error('AuthType invalid, defaulting to Basic')

    # report keys not explicitly set in config
    defaultkeys = [key for key in defaultconfig if key not in config]
    config.update({key: defaultconfig[key] for key in defaultkeys})

    return config, defaultkeys


class rfService():
    def __init__(self, config, default_entries=[]):
        traverseLogger.info('Setting up service...')
        global currentService
        currentService = self
        self.config = config
        self.proxies = dict()
        self.active = False

        config['configuri'] = ('https' if config.get('usessl', True) else 'http') + '://' + config['targetip']
        httpprox = config['httpproxy']
        httpsprox = config['httpsproxy']
        self.proxies['http'] = httpprox if httpprox != "" else None
        self.proxies['https'] = httpsprox if httpsprox != "" else None

        # Convert list of strings to dict
        self.chkcertbundle = config['certificatebundle']
        chkcertbundle = self.chkcertbundle
        if chkcertbundle not in [None, ""] and config['certificatecheck']:
            if not os.path.isfile(chkcertbundle) and not os.path.isdir(chkcertbundle):
                self.chkcertbundle = None
                traverseLogger.error('ChkCertBundle is not found, defaulting to None')
        else:
            config['certificatebundle'] = None

        ChkCert = config['certificatecheck']
        AuthType = config['authtype']

        self.currentSession = None
        if not config.get('usessl', True) and not config['forceauth']:
            if config['username'] not in ['', None] or config['password'] not in ['', None]:
                traverseLogger.warning('Attempting to authenticate on unchecked http/https protocol is insecure, if necessary please use ForceAuth option.  Clearing auth credentials...')
                config['username'] = ''
                config['password'] = ''
        if AuthType == 'Session':
            certVal = chkcertbundle if ChkCert and chkcertbundle is not None else ChkCert
            # no proxy for system under test
            self.currentSession = rfSession(config['username'], config['password'], config['configuri'], None, certVal, self.proxies)
            self.currentSession.startSession()
        self.metadata = md.Metadata(traverseLogger)

        target_version = self.config.get('versioncheck')

        # get Version
        success, data, status, delay = self.callResourceURI('/redfish/v1')
        if not success:
            traverseLogger.warn('Could not get ServiceRoot')
        elif target_version in [None, '']:
            if 'RedfishVersion' not in data:
                traverseLogger.warn('Could not get RedfishVersion from ServiceRoot')
            else:
                traverseLogger.info('Redfish Version of Service: {}'.format(data['RedfishVersion']))
                target_version = data['RedfishVersion']

        # with Version, get default and compare to user defined values
        default_config_target = defaultconfig_by_version.get(target_version, dict())
        override_with = {k: default_config_target[k] for k in default_config_target if k in default_entries}
        self.config.update(override_with)

        self.active = True

    def close(self):
        if self.currentSession is not None and self.currentSession.started:
            self.currentSession.killSession()
        self.active = False

    def getFromCache(URILink, CacheDir):
        CacheDir = os.path.join(CacheDir + URILink)
        payload = None
        if os.path.isfile(CacheDir):
            with open(CacheDir) as f:
                payload = f.read()
        if os.path.isfile(os.path.join(CacheDir, 'index.xml')):
            with open(os.path.join(CacheDir, 'index.xml')) as f:
                payload = f.read()
        if os.path.isfile(os.path.join(CacheDir, 'index.json')):
            with open(os.path.join(CacheDir, 'index.json')) as f:
                payload = json.loads(f.read())
            payload = navigateJsonFragment(payload, URILink)
        return payload

    @lru_cache(maxsize=128)
    def callResourceURI(self, URILink):
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

        URILink = URILink.rstrip('/')
        config = currentService.config
        proxies = currentService.proxies
        ConfigIP, UseSSL, AuthType, ChkCert, ChkCertBundle, timeout, Token = config['targetip'], config['usessl'], config['authtype'], \
                config['certificatecheck'], config['certificatebundle'], config['timeout'], config['token']
        CacheMode, CacheDir = config['cachemode'], config['cachefilepath']

        scheme, netloc, path, params, query, fragment = urlparse(URILink)
        inService = scheme is '' and netloc is ''
        scheme = ('https' if UseSSL else 'http') if scheme is '' else scheme
        netloc = ConfigIP if netloc is '' else netloc
        URLDest = urlunparse((scheme, netloc, path, params, query, fragment))

        payload, statusCode, elapsed, auth, noauthchk = None, '', 0, None, True

        isXML = False
        if "$metadata" in URILink or ".xml" in URILink[:-5]:
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

            auth = None if noauthchk else (config['username'], config['password'])
            traverseLogger.debug('dont chkauth' if noauthchk else 'chkauth')

            if CacheMode in ["Fallback", "Prefer"]:
                payload = rfService.getFromCache(URILink, CacheDir)

        if not inService and config['servicemode']:
            traverseLogger.debug('Disallowed out of service URI ' + URILink)
            return False, None, -1, 0

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
        try:
            if payload is not None and CacheMode == 'Prefer':
                return True, payload, -1, 0
            response = requests.get(URLDest,
                                    headers=headers, auth=auth, verify=certVal, timeout=timeout,
                                    proxies=proxies if not inService else None)  # only proxy non-service
            expCode = [200]
            elapsed = response.elapsed.total_seconds()
            statusCode = response.status_code
            traverseLogger.debug('{}, {}, {},\nTIME ELAPSED: {}'.format(statusCode,
                                 expCode, response.headers, elapsed))
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
                                "Incorrect content type 'text/xml' for file within service".format(URILink))
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
            traverseLogger.error("SSLError on {}".format(URILink))
            traverseLogger.debug("output: ", exc_info=True)
        except requests.exceptions.ConnectionError as e:
            traverseLogger.error("ConnectionError on {}".format(URILink))
            traverseLogger.debug("output: ", exc_info=True)
        except requests.exceptions.Timeout as e:
            traverseLogger.error("Request has timed out ({}s) on resource {}".format(timeout, URILink))
            traverseLogger.debug("output: ", exc_info=True)
        except requests.exceptions.RequestException as e:
            traverseLogger.error("Request has encounted a problem when getting resource {}".format(URILink))
            traverseLogger.warning("output: ", exc_info=True)
        except AuthenticationError as e:
            raise e  # re-raise exception
        except Exception:
            traverseLogger.error("A problem when getting resource has occurred {}".format(URILink))
            traverseLogger.warning("output: ", exc_info=True)

        if payload is not None and CacheMode == 'Fallback':
            return True, payload, -1, 0
        return False, None, statusCode, elapsed


def callResourceURI(URILink):
    if currentService is None:
        traverseLogger.warn("The current service is not setup!  Program must configure the service before contacting URIs")
        raise RuntimeError
    else:
        return currentService.callResourceURI(URILink)


def createResourceObject(name, uri, jsondata=None, typename=None, context=None, parent=None, isComplex=False):
    """
    Factory for resource object, move certain work here
    """
    traverseLogger.debug(
        'Creating ResourceObject {} {} {}'.format(name, uri, typename))
    oem = config.get('oemcheck', True)

    # Create json from service or from given
    original_jsondata = jsondata
    if jsondata is None and not isComplex:
        success, jsondata, status, rtime = callResourceURI(uri)
        traverseLogger.debug('{}, {}, {}'.format(success, jsondata, status))
        if not success:
            traverseLogger.error(
                '{}:  URI could not be acquired: {}'.format(uri, status))
            return None
    else:
        jsondata, rtime = jsondata, 0

    if not isinstance(jsondata, dict):
        if not isComplex:
            traverseLogger.error("Resource no longer a dictionary...")
        else:
            traverseLogger.debug("ComplexType does not have val")
        return None

    acquiredtype = jsondata.get('@odata.type', typename)
    if acquiredtype is None:
        traverseLogger.error(
            '{}:  Json does not contain @odata.type or NavType'.format(uri))
        return None

    if typename is not None:
        if not oem and 'OemObject' in typename:
            acquiredtype = typename

    original_context = context
    if context is None:
        context = jsondata.get('@odata.context')
        if context is None:
            context = createContext(acquiredtype)

    # Get Schema object
    schemaObj = rfSchema.getSchemaObject(acquiredtype, context)
    if schemaObj is None:
        traverseLogger.error("ResourceObject creation: No schema XML for {} {} {}".format(typename, acquiredtype, context))
        return None

    forceType = False
    # Check if this is a Registry resource
    parent_type = parent.typename if parent is not None and parent.typeobj is not None else None

    # get highest type if type is invalid
    if schemaObj.getTypeTagInSchema(acquiredtype) is None:
        if schemaObj.getTypeTagInSchema(getNamespaceUnversioned(acquiredtype)) is not None:
            traverseLogger.error("Namespace version of type appears missing from SchemaXML, attempting highest type: {}".format(acquiredtype))
            acquiredtype = schemaObj.getHighestType(acquiredtype, parent_type)
            typename = acquiredtype
            traverseLogger.error("New namespace: {}".format(typename))
            forceType = True
        else:
            traverseLogger.error("getResourceObject: Namespace appears nonexistent in SchemaXML: {} {}".format(acquiredtype, context))
            return None

    # check odata.id if it corresponds
    odata_id = jsondata.get('@odata.id', '')

    currentType = acquiredtype
    baseObj = schemaObj
    success = True
    allTypes = []
    while currentType not in allTypes and success:
        allTypes.append(currentType)
        success, baseObj, currentType = baseObj.getParentType(currentType, 'EntityType')
        traverseLogger.debug('success = {}, currentType = {}'.format(success, currentType))

    uri_item = uri
    scheme, netloc, path, params, query, fragment = urlparse(uri_item)
    scheme, netloc, path, params, query, fragment_odata = urlparse(odata_id)

    if 'Resource.Resource' in allTypes:
        if fragment is '':
            if original_jsondata is None:
                traverseLogger.debug('Acquired resource OK {}'.format(uri_item))
            else:
                traverseLogger.debug('Acquired resource thru AutoExpanded means {}'.format(uri_item))
                traverseLogger.info('Regetting resource from URI {}'.format(uri_item))
                return createResourceObject(name, uri_item, None, typename, context, parent, isComplex)
        else:
            if original_jsondata is None:
                traverseLogger.warn('Acquired Resource.Resource type with fragment, could cause issues  {}'.format(uri_item))
            else:
                traverseLogger.warn('Found uri with fragment, which Resource.Resource types do not use {}'.format(uri_item))
        if fragment_odata is '':
            pass
        else:
            traverseLogger.warn('@odata.id should not have a fragment'.format(odata_id))


    elif 'Resource.ReferenceableMember' in allTypes:
        if fragment is not '':
            pass
        else:
            traverseLogger.warn('No fragment, but ReferenceableMembers require it {}'.format(uri_item))
        if fragment_odata is not '':
            pass
        else:
            traverseLogger.warn('@odata.id should have a fragment'.format(odata_id))


    newResource = ResourceObj(name, uri, jsondata, typename, original_context, parent, isComplex, forceType=forceType)
    newResource.rtime = rtime

    return newResource


class ResourceObj:
    def __init__(self, name: str, uri: str, jsondata: dict, typename: str, context: str, parent=None, isComplex=False, forceType=False):
        self.initiated = False
        self.parent = parent
        self.uri, self.name = uri, name
        self.rtime = 0
        self.isRegistry = False
        self.errorIndex = {
        }

        oem = config.get('oemcheck', True)

        # Check if this is a Registry resource
        parent_type = parent.typename if parent is not None and parent is not None else None
        if parent_type is not None and getType(parent_type) == 'MessageRegistryFile':
            traverseLogger.debug('{} is a Registry resource'.format(self.uri))
            self.isRegistry = True

        # Check if we provide a valid json
        self.jsondata = jsondata

        traverseLogger.debug("payload: {}".format(json.dumps(self.jsondata, indent=4, sort_keys=True)))

        if not isinstance(self.jsondata, dict):
            traverseLogger.error("Resource no longer a dictionary...")
            raise ValueError('This Resource is no longer a Dictionary')

        # Check for @odata.id (todo: regex)
        odata_id = self.jsondata.get('@odata.id')
        if odata_id is None and not isComplex:
            if self.isRegistry:
                traverseLogger.debug('{}: @odata.id missing, but not required for Registry resource'
                                     .format(self.uri))
            else:
                traverseLogger.error('{}: Json does not contain @odata.id'.format(self.uri))

        # Get our real type (check for version)
        acquiredtype = typename if forceType else jsondata.get('@odata.type', typename)
        if acquiredtype is None:
            traverseLogger.error(
                '{}:  Json does not contain @odata.type or NavType'.format(uri))
            raise ValueError
        if acquiredtype is not typename and isComplex:
            context = None

        if typename is not None:
            if not oem and 'OemObject' in typename:
                acquiredtype = typename

        if currentService:
            if not oem and 'OemObject' in acquiredtype:
                pass
            else:
                if jsondata.get('@odata.type') is not None:
                    currentService.metadata.add_service_namespace(getNamespace(jsondata.get('@odata.type')))
                if jsondata.get('@odata.context') is not None:
                    # add the namespace to the set of namespaces referenced by this service
                    ns = getNamespace(jsondata.get('@odata.context').split('#')[-1])
                    if '/' not in ns and not ns.endswith('$entity'):
                        currentService.metadata.add_service_namespace(ns)

        # Provide a context for this (todo: regex)
        if context is None:
            context = self.jsondata.get('@odata.context')
            if context is None:
                context = createContext(acquiredtype)
                if self.isRegistry:
                    # If this is a Registry resource, @odata.context is not required; do our best to construct one
                    traverseLogger.debug('{}: @odata.context missing from Registry resource; constructed context {}'
                                         .format(acquiredtype, context))
                elif isComplex:
                    pass
                else:
                    traverseLogger.error('{}:  Json does not contain @odata.context'.format(uri))

        self.context = context

        # Get Schema object
        self.schemaObj = rfSchema.getSchemaObject(acquiredtype, self.context)

        if self.schemaObj is None:
            traverseLogger.error("ResourceObject creation: No schema XML for {} {} {}".format(typename, acquiredtype, self.context))
            raise ValueError

        # Use string comprehension to get highest type
        if acquiredtype is typename and not forceType:
            acquiredtype = self.schemaObj.getHighestType(typename, parent_type)
            if not isComplex:
                traverseLogger.warning(
                    'No @odata.type present, assuming highest type {} {}'.format(typename, acquiredtype))

        # Check if we provide a valid type (todo: regex)
        self.typename = acquiredtype
        typename = self.typename

        self.initiated = True

        # get our metadata
        metadata = currentService.metadata if currentService else None

        self.typeobj = rfSchema.getTypeObject(typename, self.schemaObj)

        self.propertyList = self.typeobj.getProperties(self.jsondata, topVersion=getNamespace(typename))
        propertyList = [prop.payloadName for prop in self.propertyList]

        # get additional
        self.additionalList = []
        propTypeObj = self.typeobj
        if propTypeObj.propPattern is not None and len(propTypeObj.propPattern) > 0:
            prop_pattern = propTypeObj.propPattern.get('Pattern', '.*')
            prop_type = propTypeObj.propPattern.get('Type', 'Resource.OemObject')

            regex = re.compile(prop_pattern)
            for key in [k for k in self.jsondata if k not in propertyList and regex.match(k)]:
                val = self.jsondata.get(key)
                value_obj = rfSchema.PropItem(propTypeObj.schemaObj, propTypeObj.fulltype, key, val, customType=prop_type)
                self.additionalList.append(value_obj)

        if config['uricheck'] and self.typeobj.expectedURI is not None:
            my_id = self.jsondata.get('Id')
            self.errorIndex['bad_uri_schema_uri'] = not self.typeobj.compareURI(uri, my_id)
            self.errorIndex['bad_uri_schema_odata'] = not self.typeobj.compareURI(odata_id, my_id)

            if self.errorIndex['bad_uri_schema_uri']:
                traverseLogger.error('{}: URI not in Redfish.Uris: {}'.format(uri, self.typename))
            else:
                traverseLogger.debug('{} in Redfish.Uris: {}'.format(uri, self.typename))

            if self.errorIndex['bad_uri_schema_odata']:
                traverseLogger.error('{}: odata_id not in Redfish.Uris: {}'.format(odata_id, self.typename))
            else:
                traverseLogger.debug('{} in Redfish.Uris: {}'.format(odata_id, self.typename))

        # get annotation
        successService, annotationProps = getAnnotations(metadata, self.jsondata)
        if successService:
            self.additionalList.extend(annotationProps)

        # list illegitimate properties together
        self.unknownProperties = [k for k in self.jsondata if k not in propertyList +
                [prop.payloadName for prop in self.additionalList] and '@odata' not in k]

        self.links = OrderedDict()

        sample = config.get('sample')
        linklimits = config.get('linklimits', {})
        self.links.update(self.typeobj.getLinksFromType(self.jsondata, self.context, self.propertyList, oem, linklimits, sample))

        self.links.update(getAllLinks(
            self.jsondata, self.additionalList, self.schemaObj, context=context, linklimits=linklimits,
            sample_size=sample, oemCheck=oem))

    def getResourceProperties(self):
        allprops = self.propertyList + self.additionalList[:min(len(self.additionalList), 100)]
        return allprops


def enumerate_collection(items, cTypeName, linklimits, sample_size):
    """
    Generator function to enumerate the items in a collection, applying the link limit or sample size if applicable.
    If a link limit is specified for this cTypeName, return the first N items as specified by the limit value.
    If a sample size greater than zero is specified, return a random sample of items specified by the sample_size.
    In both the above cases, if the limit value or sample size is greater than or equal to the number of items in the
    collection, return all the items.
    If a limit value for this cTypeName and a sample size are both provided, the limit value takes precedence.
    :param items: the collection of items to enumerate
    :param cTypeName: the type name of this collection
    :param linklimits: a dictionary mapping type names to their limit values
    :param sample_size: the number of items to sample from large collections
    :return: enumeration of the items to be processed
    """
    if cTypeName in linklimits:
        # "link limit" case
        limit = min(linklimits[cTypeName], len(items))
        traverseLogger.debug('Limiting "{}" to first {} links'.format(cTypeName, limit))
        for i in range(limit):
            if linklimits[cTypeName] < len(items):
                uri = items[i].get('@odata.id')
                if uri is not None:
                    uri_sample_map[uri] = 'Collection limit {} of {}'.format(i + 1, limit)
            yield i, items[i]
    elif 0 < sample_size < len(items):
        # "sample size" case
        traverseLogger.debug('Limiting "{}" to sample of {} links'.format(cTypeName, sample_size))
        sample = 0
        for i in sorted(random.sample(range(len(items)), sample_size)):
            sample += 1
            uri = items[i].get('@odata.id')
            if uri is not None:
                uri_sample_map[uri] = 'Collection sample {} of {}'.format(sample, sample_size)
            yield i, items[i]
    else:
        # "all" case
        traverseLogger.debug('Processing all links for "{}"'.format(cTypeName))
        yield from enumerate(items)


def getAllLinks(jsonData, propList, schemaObj, prefix='', context='', linklimits=None, sample_size=0, oemCheck=True):
    """
    Function that returns all links provided in a given JSON response.
    This result will include a link to itself.

    :param arg1: json dict
    :param arg2: property dict
    :param arg3: reference dict
    :param prefix: default blank, for deeper links
    :param context: default blank, for AutoExpanded types
    :return: list of links
    """
    linkList = OrderedDict()
    if linklimits is None:
        linklimits = {}
    # check keys in propertyDictionary
    # if it is a Nav property, check that it exists
    #   if it is not a Nav Collection, add it to list
    #   otherwise, add everything IN Nav collection
    # if it is a Complex property, check that it exists
    #   if it is, recurse on collection or individual item
    if not isinstance(jsonData, dict):
        traverseLogger.error("Generating links requires a dict")
    refDict = schemaObj.refs
    try:
        for propx in propList:
            propDict = propx.propDict
            if propDict is None:
                continue

            isNav = propDict.get('isNav', False)
            key = propx.name
            item = getType(key).split(':')[-1]

            insideItem = propx.val if propx.exists else None
            autoExpand = propDict.get('OData.AutoExpand', None) is not None or\
                propDict.get('OData.AutoExpand'.lower(), None) is not None
            cType = propDict.get('isCollection')
            ownerNS = propx.propOwner.split('.')[0]
            ownerType = propx.propOwner.split('.')[-1]

            if isNav:
                if insideItem is not None:
                    if cType is not None:
                        cTypeName = getType(cType)
                        cSchema = refDict.get(getNamespace(cType), (None, None))[1]
                        if cSchema is None:
                            cSchema = context
                        for cnt, listItem in enumerate_collection(insideItem, cTypeName, linklimits, sample_size):
                            linkList[prefix + str(item) + '.' + cTypeName +
                                     '#' + str(cnt)] = (listItem.get('@odata.id'), autoExpand, cType, cSchema, listItem)
                    else:
                        cType = propDict['attrs'].get('Type')
                        cSchema = refDict.get(getNamespace(cType), (None, None))[1]
                        if cSchema is None:
                            cSchema = context
                        linkList[prefix + str(item) + '.' + getType(propDict['attrs']['Name'])] = (
                            insideItem.get('@odata.id'), autoExpand, cType, cSchema, insideItem)
            elif item == 'Uri' and ownerNS == 'MessageRegistryFile' and ownerType == 'Location':
                # special handling for MessageRegistryFile Location Uri
                if insideItem is not None and isinstance(insideItem, str) and len(insideItem) > 0:
                    uriItem = {'@odata.id': insideItem}
                    cType = ownerNS + '.' + ownerNS
                    cSchema = refDict.get(getNamespace(cType), (None, None))[1]
                    if cSchema is None:
                        cSchema = context
                    traverseLogger.debug('Registry Location Uri: resource = {}, type = {}, schema = {}'
                                         .format(insideItem, cType, cSchema))
                    linkList[prefix + str(item) + '.' + getType(propDict['attrs']['Name'])] = (
                        uriItem.get('@odata.id'), autoExpand, cType, cSchema, uriItem)
            elif item == 'Actions':
                # special handling for @Redfish.ActionInfo payload annotations
                if isinstance(insideItem, dict):
                    cType = 'ActionInfo.ActionInfo'
                    cSchema = refDict.get(getNamespace(cType), (None, None))[1]
                    for k, v in insideItem.items():
                        if not isinstance(v, dict):
                            continue
                        uri = v.get('@Redfish.ActionInfo')
                        if isinstance(uri, str):
                            uriItem = {'@odata.id': uri}
                            traverseLogger.debug('{}{}: @Redfish.ActionInfo annotation uri = {}'.format(item, k, uri))
                            linkList[prefix + str(item) + k + '.' + cType] = (
                                uriItem.get('@odata.id'), autoExpand, cType, cSchema, uriItem)

        for propx in propList:
            propDict = propx.propDict
            if propDict is None:
                continue
            propDict = propx.propDict
            key = propx.name
            item = getType(key).split(':')[-1]
            if 'Oem' in item and not oemCheck:
                continue
            cType = propDict.get('isCollection')
            if propDict is None:
                continue
            elif propDict['realtype'] == 'complex':
                tp = propDict['typeprops']
                if jsonData.get(item) is not None and tp is not None:
                    if cType is not None:
                        cTypeName = getType(cType)
                        for item in tp:
                            linkList.update(item.links)
                    else:
                        linkList.update(tp.links)
        traverseLogger.debug(str(linkList))
    except Exception as e:
        traverseLogger.debug('Exception caught while getting all links', exc_info=1)
        traverseLogger.error('Unexpected error while extracting links from payload: {}'.format(repr(e)))
    # contents of Registries may be needed to validate other resources (like Bios), so move to front of linkList
    if 'Registries.Registries' in linkList:
        linkList.move_to_end('Registries.Registries', last=False)
        traverseLogger.debug('getAllLinks: Moved Registries.Registries to front of list')
    return linkList


def getAnnotations(metadata, decoded, prefix=''):
    """
    Function to gather @ additional props in a payload
    """
    allowed_annotations = ['odata', 'Redfish', 'Privileges', 'Message']
    if metadata is not None:
        schemaObj = metadata.schema_obj
    else:
        traverseLogger.warn("Cannot work on annotations without a service or metadata")
        return False, []
    additionalProps = list()
    # For every ...@ in decoded, check for its presence in refs
    #   get the schema file for it
    #   concat type info together
    annotationsFound = 0
    for key in [k for k in decoded if prefix + '@' in k and '@odata' not in k]:
        annotationsFound += 1
        splitKey = key.split('@', 1)
        fullItem = splitKey[1]
        if getNamespace(fullItem) not in allowed_annotations:
            traverseLogger.error("getAnnotations: {} is not an allowed annotation namespace, please check spelling/capitalization.".format(fullItem))
            continue
        elif metadata is not None:
            # add the namespace to the set of namespaces referenced by this service
            metadata.add_service_namespace(getNamespace(fullItem))
        annotationSchemaObj = schemaObj.getSchemaFromReference(getNamespace(fullItem))
        traverseLogger.debug('{}, {}, {}'.format(key, splitKey, decoded[key]))
        if annotationSchemaObj is not None:
            realType = annotationSchemaObj.name
            realItem = realType + '.' + fullItem.split('.', 1)[1]
            additionalProps.append(
                rfSchema.PropItem(annotationSchemaObj, realItem, key, decoded[key]))
    traverseLogger.debug("Annotations generated: {} out of {}".format(len(additionalProps), annotationsFound))
    return True, additionalProps
