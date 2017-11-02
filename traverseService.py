
# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link:
# https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from bs4 import BeautifulSoup
import requests
import sys
import re
import os
import json
from collections import OrderedDict
from functools import lru_cache
import logging
from rfSession import rfSession
from requests.packages.urllib3.exceptions import InsecureRequestWarning


traverseLogger = logging.getLogger(__name__)
traverseLogger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
traverseLogger.addHandler(ch)

commonHeader = {'OData-Version': '4.0'}
proxies = {'http': None, 'https': None}

currentSession = rfSession()
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
 
def getLogger():
    """
    Grab logger for tools that might use this lib
    """
    return traverseLogger

# default config
configset = {
        "targetip": type(""), "username": type(""), "password": type(""), "authtype": type(""), "usessl": type(True), "certificatecheck": type(True), "certificatebundle": type(""),
        "metadatafilepath": type(""), "cachemode": (type(False),type("")), "cachefilepath": type(""), "schemasuffix": type(""), "timeout": type(0), "httpproxy": type(""), "httpsproxy": type(""),
        "systeminfo": type(""), "localonlymode": type(True), "servicemode": type(True), "token": type(""), 'linklimit': dict
        }
config = {
        'authtype': 'basic', 'username': "", 'password': "", 'token': '',
        'certificatecheck': True, 'certificatebundle': "", 'metadatafilepath': './SchemaFiles/metadata',
        'cachemode': 'Off', 'cachefilepath': './cache', 'schemasuffix': '_v1.xml', 'httpproxy': "", 'httpsproxy': "",
        'localonlymode': False, 'servicemode': False, 'linklimit': {'LogEntry':20}
        }

def setConfig(cdict):
    """
    Set config based on configurable dictionary
    """
    for item in cdict:
        if item not in configset:
            traverseLogger.error('Unsupported {}'.format(item))
        elif not isinstance(cdict[item], configset[item]):
            traverseLogger.error('Unsupported {}, expected type {}'.format(item, configset[item]))
    
    # Always keep LogEntry: 20
    defaultlinklimit = config['linklimit']

    config.update(cdict)
    
    defaultlinklimit.update(config['linklimit'])
    config['linklimit'] = defaultlinklimit

    User, Passwd, Ip, ChkCert, UseSSL = config['username'], config['password'], config['targetip'], config['certificatecheck'], config['usessl']
    
    config['configuri'] = ('https' if UseSSL else 'http') + '://' + Ip

    config['certificatecheck'] = ChkCert and UseSSL

    # Convert list of strings to dict
    chkcertbundle = config['certificatebundle']
    if chkcertbundle not in [None, ""] and config['certificatecheck']:
        if not os.path.isfile(chkcertbundle):
            chkcertbundle = None
            traverseLogger.error('ChkCertBundle is not found, defaulting to None')
    else:
        config['certificatebundle'] = None

    httpprox = config['httpproxy']
    httpsprox = config['httpsproxy']
    proxies['http'] = httpprox if httpprox != "" else None
    proxies['https'] = httpsprox if httpsprox != "" else None

    if config['cachemode'] not in ['Off', 'Fallback', 'Prefer']:
        if config['cachemode'] is not False:
            traverseLogger.error('CacheMode or path invalid, defaulting to Off')
        config['cachemode'] = 'Off'

    AuthType = config['authtype']
    if AuthType not in ['None', 'Basic', 'Session', 'Token']:
        config['authtype'] = 'Basic'
        traverseLogger.error('AuthType invalid, defaulting to Basic')

    if AuthType == 'Session':
        certVal = chkcertbundle if ChkCert and chkcertbundle is not None else ChkCert
        success = currentSession.startSession(User, Passwd, config['configuri'], certVal, proxies)
        if not success:
            raise RuntimeError("Session could not start")

def isNonService(uri):
    """
    Checks if a uri is within the service
    """
    return 'http' in uri[:8]


def navigateJsonFragment(decoded, URILink):
    if '#' in URILink:
        URILink, frag = tuple(URILink.rsplit('#', 1))
        fragNavigate = frag.split('/')
        for item in fragNavigate:
            if item == '':
                continue
            if isinstance(decoded, dict):
                decoded = decoded.get(item)
            elif isinstance(decoded, list):
                decoded = decoded[int(item)] if int(
                    item) < len(decoded) else None
        if not isinstance(decoded, dict):
            traverseLogger.warn(
                "Decoded object no longer a dictionary {}".format(URILink))
    return decoded


@lru_cache(maxsize=64)
def callResourceURI(URILink):
    """
    Makes a call to a given URI or URL

    param arg1: path to URI "/example/1", or URL "http://example.com"
    return: (success boolean, data, request status code)
    """
    # rs-assertions: 6.4.1, including accept, content-type and odata-versions
    # rs-assertion: handle redirects?  and target permissions
    # rs-assertion: require no auth for serviceroot calls
    ConfigURI, UseSSL, AuthType, ChkCert, ChkCertBundle, timeout, Token = config['configuri'], config['usessl'], config['authtype'], \
            config['certificatecheck'], config['certificatebundle'], config['timeout'], config['token']
    CacheMode, CacheDir = config['cachemode'], config['cachefilepath']

    if URILink is None:
        traverseLogger.debug("This URI is empty!")
        return False, None, -1, 0
    nonService = isNonService(URILink)
    payload = None
    statusCode = ''
    elapsed = 0

    # determine if we need to Auth...
    if not nonService:
        noauthchk = \
            ('/redfish' in URILink and '/redfish/v1' not in URILink) or\
            URILink in ['/redfish/v1', '/redfish/v1/', '/redfish/v1/odata', 'redfish/v1/odata/'] or\
            '/redfish/v1/$metadata' in URILink
        if noauthchk:
            traverseLogger.debug('dont chkauth')
            auth = None
        else:
            auth = (config['username'], config['password'])
        if CacheMode in ["Fallback", "Prefer"]:
            CacheDir = os.path.join(CacheDir + URILink)
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
    if nonService and config['servicemode']:
        traverseLogger.debug('Disallowed out of service URI')
        return False, None, -1, 0

    # rs-assertion: do not send auth over http
    # remove UseSSL if necessary if you require unsecure auth
    if not UseSSL or nonService or AuthType != 'Basic':
        auth = None

    # only send token when we're required to chkauth, during a Session, and on Service and Secure
    if UseSSL and not nonService and AuthType == 'Session' and not noauthchk:
        headers = {"X-Auth-Token": currentSession.getSessionKey()}
        headers.update(commonHeader)
    elif UseSSL and not nonService and AuthType == 'Token' and not noauthchk:
        headers = {"Authorization": "Bearer "+Token}
        headers.update(commonHeader)
    else:
        headers = commonHeader

    certVal = ChkCertBundle if ChkCert and ChkCertBundle not in [None, ""] else ChkCert

    # rs-assertion: must have application/json or application/xml
    traverseLogger.debug('callingResourceURI{}with authtype {} and ssl {}: {}'.format(
        ' out of service ' if nonService else ' ', AuthType, UseSSL, URILink))
    try:
        if payload is not None and CacheMode == 'Prefer':
            return True, payload, -1, 0
        response = requests.get(ConfigURI + URILink if not nonService else URILink,
                                headers=headers, auth=auth, verify=certVal, timeout=timeout, proxies=proxies)
        expCode = [200]
        elapsed = response.elapsed.total_seconds()
        statusCode = response.status_code
        traverseLogger.debug('{}, {}, {},\nTIME ELAPSED: {}'.format(statusCode,
                             expCode, response.headers, elapsed))
        if statusCode in expCode:
            contenttype = response.headers.get('content-type')
            if contenttype is not None and 'application/json' in contenttype:
                traverseLogger.debug("This is a JSON response")
                decoded = response.json(object_pairs_hook=OrderedDict)
                # navigate fragment
                decoded = navigateJsonFragment(decoded, URILink)
            elif contenttype is not None and 'application/xml' in contenttype:
                decoded = response.text
            else:
                traverseLogger.error(
                        "This URI did NOT return XML or Json, this is not a Redfish resource (is this redirected?): {}".format(URILink))
                return False, response.text, statusCode, elapsed
            return decoded is not None, decoded, statusCode, elapsed

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
        traverseLogger.warn("output: ", exc_info=True)
    except Exception as ex:
        traverseLogger.error("A problem when getting resource has occurred {}".format(URILink))
        traverseLogger.warn("output: ", exc_info=True)

    if payload is not None and CacheMode == 'Fallback':
        return True, payload, -1, 0
    return False, None, statusCode, elapsed


# note: Use some sort of re expression to parse SchemaType
# ex: #Power.1.1.1.Power , #Power.v1_0_0.Power
def getNamespace(string):
    return string.replace('#', '').rsplit('.', 1)[0]


def getType(string):
    return string.replace('#', '').rsplit('.', 1)[-1]


@lru_cache(maxsize=64)
def getSchemaDetails(SchemaType, SchemaURI):
    """
    Find Schema file for given Namespace.

    param arg1: Schema Namespace, such as ServiceRoot
    param SchemaURI: uri to grab schema, given LocalOnly is False
    return: (success boolean, a Soup object)
    """
    traverseLogger.debug('getting Schema of {} {}'.format(SchemaType, SchemaURI))

    if SchemaType is None:
        return False, None, None

    LocalOnly, SchemaLocation, ServiceOnly = config['localonlymode'], config['metadatafilepath'], config['servicemode']

    if SchemaURI is not None and not LocalOnly or '/redfish/v1/$metadata' in SchemaURI:
        # Get our expected Schema file here
        # if success, generate Soup, then check for frags to parse
        #   start by parsing references, then check for the refLink
        if '#' in SchemaURI:
            SchemaURI, frag = tuple(SchemaURI.rsplit('#', 1))
        else:
            frag = None
        success, data, status, elapsed = callResourceURI(SchemaURI)
        if success:
            soup = BeautifulSoup(data, "xml")
            # if frag, look inside xml for real target as a reference
            if frag is not None:
                # prefer type over frag, truncated down
                # using frag, check references
                frag = getNamespace(SchemaType)
                frag = frag.split('.', 1)[0]
                refType, refLink = getReferenceDetails(
                    soup, name=SchemaURI).get(frag, (None, None))
                if refLink is not None:
                    success, linksoup, newlink = getSchemaDetails(refType, refLink)
                    if success:
                        return True, linksoup, newlink
                    else:
                        traverseLogger.error(
                            "SchemaURI couldn't call reference link {} inside {}".format(frag, SchemaURI))
                else:
                    traverseLogger.error(
                        "SchemaURI missing reference link {} inside {}".format(frag, SchemaURI))
            else:
                return True, soup, SchemaURI
        if isNonService(SchemaURI) and ServiceOnly:
            traverseLogger.info("Nonservice URI skipped: {}".format(SchemaURI))
        else:
            traverseLogger.debug("SchemaURI called unsuccessfully: {}".format(SchemaURI))
    if LocalOnly:
        traverseLogger.debug("This program is currently LOCAL ONLY")
    if ServiceOnly:
        traverseLogger.debug("This program is currently SERVICE ONLY")
    if not LocalOnly and not ServiceOnly and isNonService(SchemaURI):
        traverseLogger.warn("SchemaURI {} was unable to be called, defaulting to local storage in {}".format(SchemaURI, SchemaLocation))
    return getSchemaDetailsLocal(SchemaType, SchemaURI)


def getSchemaDetailsLocal(SchemaType, SchemaURI):
    # Use local if no URI or LocalOnly
    # What are we looking for?  Parse from URI
    # if we're not able to use URI to get suffix, work with option fallback
    Alias = getNamespace(SchemaType).split('.')[0]
    SchemaLocation, SchemaSuffix = config['metadatafilepath'], config['schemasuffix']
    if SchemaURI is not None:
        uriparse = SchemaURI.split('/')[-1].split('#')
        xml = uriparse[0]
    else:
        traverseLogger.warn("SchemaURI was empty, must generate xml name from type {}".format(SchemaType)),
        return getSchemaDetailsLocal(SchemaType, SchemaType + SchemaSuffix)
    traverseLogger.debug((SchemaType, SchemaURI, SchemaLocation + '/' + xml))
    pout = Alias + SchemaSuffix if xml is None else xml
    try:
        # get file
        filehandle = open(SchemaLocation + '/' + xml, "r")
        data = filehandle.read()
        filehandle.close()
        # get tags
        soup = BeautifulSoup(data, "xml")
        edmxTag = soup.find('edmx:Edmx', recursive=False)
        parentTag = edmxTag.find('edmx:DataServices', recursive=False)
        child = parentTag.find('Schema', recursive=False)
        SchemaNamespace = child['Namespace']
        FoundAlias = SchemaNamespace.split(".")[0]
        traverseLogger.debug(FoundAlias)
        if '/redfish/v1/$metadata' in SchemaURI:
            if len(uriparse) > 1:
                frag = getNamespace(SchemaType)
                frag = frag.split('.', 1)[0]
                refType, refLink = getReferenceDetails(
                    soup, name=SchemaLocation+'/'+pout).get(frag, (None, None))
                if refLink is not None:
                    traverseLogger.debug('Entering {} inside {}, pulled from $metadata'.format(refType, refLink))
                    return getSchemaDetails(refType, refLink)
                else:
                    traverseLogger.error('Could not find item in $metadata {}'.format(frag))
                    return False, None, None
            else:
                return True, soup, "local" + SchemaLocation + '/' + pout
        if FoundAlias in Alias:
            return True, soup, "local" + SchemaLocation + '/' + pout
    except FileNotFoundError as ex:
        # if we're looking for $metadata locally... ditch looking for it, go straight to file
        if '/redfish/v1/$metadata' in SchemaURI and Alias != '$metadata':
            traverseLogger.error("Unable to find a harddrive stored $metadata at {}, defaulting to {}".format(SchemaLocation, Alias + SchemaSuffix))
            return getSchemaDetailsLocal(SchemaType, Alias + SchemaSuffix)
        else:
            traverseLogger.error(
                "File not found in {} for {}: ".format(SchemaLocation, pout))
            if Alias == '$metadata':
                traverseLogger.error(
                    "If $metadata cannot be found, Annotations may be unverifiable")
    except Exception as ex:
        traverseLogger.error("A problem when getting a local schema has occurred {}".format(SchemaURI))
        traverseLogger.warn("output: ", exc_info=True)
    return False, None, None


def check_redfish_extensions_alias(name, item):
    """
    Check that edmx:Include for Namespace RedfishExtensions has the expected 'Redfish' Alias attribute
    :param name: the name of the resource
    :param item: the edmx:Include item for RedfishExtensions
    :return:
    """
    alias = item.get('Alias')
    if alias is None or alias != 'Redfish':
        msg = ("In the resource {}, the {} namespace must have an alias of 'Redfish'. The alias is {}. " +
               "This may cause properties of the form [PropertyName]@Redfish.TermName to be unrecognized.")
        traverseLogger.error(msg.format(name, item.get('Namespace'),
                             'missing' if alias is None else "'" + str(alias) + "'"))


def getReferenceDetails(soup, metadata_dict=None, name='xml'):
    """
    Create a reference dictionary from a soup file

    param arg1: soup
    param metadata_dict: dictionary of service metadata, compare with
    return: dictionary
    """
    refDict = {}
    ServiceOnly = config['servicemode']

    maintag = soup.find("edmx:Edmx", recursive=False)
    refs = maintag.find_all('edmx:Reference', recursive=False)
    for ref in refs:
        includes = ref.find_all('edmx:Include', recursive=False)
        for item in includes:
            if item.get('Namespace') is None or ref.get('Uri') is None:
                traverseLogger.error("Reference incorrect for: {}".format(item))
                continue
            if item.get('Alias') is not None:
                refDict[item['Alias']] = (item['Namespace'], ref['Uri'])
            else:
                refDict[item['Namespace']] = (item['Namespace'], ref['Uri'])
            # Check for proper Alias for RedfishExtensions
            if name == '$metadata' and item.get('Namespace').startswith('RedfishExtensions.'):
                check_redfish_extensions_alias(name, item)

    cntref = len(refDict)
    if metadata_dict is not None:
        refDict.update(metadata_dict)
        if len(refDict.keys()) > len(metadata_dict.keys()):
            diff_keys = [key for key in refDict if key not in metadata_dict]
            traverseLogger.log(
                    logging.ERROR if ServiceOnly else logging.DEBUG,
                    "Reference in a Schema {} not in metadata, this may not be compatible with ServiceMode".format(name))
            traverseLogger.log(
                    logging.ERROR if ServiceOnly else logging.DEBUG,
                    "References missing in metadata: {}".format(str(diff_keys)))
    traverseLogger.debug("References generated from {}: {} out of {}".format(name, cntref, len(refDict)))
    return refDict


def getParentType(soup, refs, currentType, tagType='EntityType'):
    # overhauling needed: deprecated function that should be realigned with the current type function
    # debug: what are we working towards?  did we get it?  it's fine if we didn't
    # error: none, should lend that to whatever calls it
    """
    Get parent type of given type.

    param arg1: soup
    param arg2: refs
    param arg3: current type
    param tagType: the type of tag for inheritance, default 'EntityType'
    return: success, associated soup, associated ref, new type
    """
    pnamespace, ptype = getNamespace(currentType), getType(currentType)

    propSchema = soup.find(  # BS4 line
        'Schema', attrs={'Namespace': pnamespace})

    if propSchema is None:
        return False, None, None, None

    propEntity = propSchema.find(tagType, attrs={'Name': ptype}, recursive=False)  # BS4 line

    if propEntity is None:
        return False, None, None, None

    currentType = propEntity.get('BaseType')

    if currentType is None:
        return False, None, None, None

    currentType = currentType.replace('#', '')
    SchemaNamespace, SchemaType = getNamespace(
        currentType), getType(currentType)
    propSchema = soup.find('Schema', attrs={'Namespace': SchemaNamespace})  # BS4 line

    if propSchema is None:
        success, innerSoup, uri = getSchemaDetails(
            *refs.get(SchemaNamespace, (None, None)))
        if not success:
            return False, None, None, None
        innerRefs = getReferenceDetails(innerSoup, refs, uri)
        propSchema = innerSoup.find(  
            'Schema', attrs={'Namespace': SchemaNamespace})
        if propSchema is None:
            return False, None, None, None
    else:
        innerSoup = soup
        innerRefs = refs

    return True, innerSoup, innerRefs, currentType


class ResourceObj:
    robjcache = {}
    
    def __init__(self, name, uri, expectedType=None, expectedSchema=None, expectedJson=None, parent=None):
        self.initiated = False
        self.parent = parent
        self.uri, self.name = uri, name
        self.rtime = 0

        # Check if we provide a json
        if expectedJson is None:
            success, self.jsondata, status, self.rtime = callResourceURI(self.uri)
            traverseLogger.debug('{}, {}, {}'.format(success, self.jsondata, status))
            if not success:
                traverseLogger.error(
                    '{}:  URI could not be acquired: {}'.format(self.uri, status))
                return
        else:
            self.jsondata = expectedJson
        
        traverseLogger.debug("payload: {}".format(json.dumps(self.jsondata, indent=4, sort_keys=True)))
        if not isinstance(self.jsondata, dict):
            traverseLogger.error("Resource no longer a dictionary...")
            return

        # Check if we provide a type besides json's
        if expectedType is None:
            fullType = self.jsondata.get('@odata.type')
            if fullType is None:
                traverseLogger.error(
                    '{}:  Json does not contain @odata.type'.format(self.uri))
                return
        else:
            fullType = self.jsondata.get('@odata.type', expectedType)

        # Provide a context for this
        if expectedSchema is None:
            self.context = self.jsondata.get('@odata.context')
            expectedSchema = self.context
            if expectedSchema is None:
                traverseLogger.error(
                    '{}:  Json does not contain @odata.context'.format(self.uri))
        else:
            self.context = expectedSchema

        success, typesoup, self.context = getSchemaDetails(
            fullType, SchemaURI=self.context)

        if not success:
            traverseLogger.error("validateURI: No schema XML for {}".format(fullType))
            return

        # Use string comprehension to get highest type
        if fullType is expectedType:
            typelist = list()
            schlist = list()
            for schema in typesoup.find_all('Schema'):
                newNamespace = schema.get('Namespace')
                typelist.append(newNamespace)
                schlist.append(schema)
            for item, schema in reversed(sorted(zip(typelist, schlist))):
                traverseLogger.debug(
                    "{}   {}".format(item, getType(fullType)))
                if schema.find('EntityType', attrs={'Name': getType(fullType)}, recursive=False):
                    fullType = item + '.' + getType(fullType)
                    break
            traverseLogger.warn(
                'No @odata.type present, assuming highest type {}'.format(fullType))

        self.additionalList = []
        self.initiated = True
        idtag = (fullType, self.context)  # 🔫

        serviceRefs = None
        successService, serviceSchemaSoup, SchemaServiceURI = getSchemaDetails(
            '$metadata', '/redfish/v1/$metadata')
        if successService:
            serviceRefs = getReferenceDetails(serviceSchemaSoup, name=SchemaServiceURI)
            successService, additionalProps = getAnnotations(
                serviceSchemaSoup, serviceRefs, self.jsondata)
            for prop in additionalProps:
                self.additionalList.append(prop)

        # if we've generated this type, use it, else generate type
        if idtag in ResourceObj.robjcache:
            self.typeobj = ResourceObj.robjcache[idtag]
        else:
            typerefs = getReferenceDetails(typesoup, serviceRefs, self.context)
            self.typeobj = PropType(
                fullType, typesoup, typerefs, 'EntityType', topVersion=getNamespace(fullType))
            ResourceObj.robjcache[idtag] = self.typeobj

        self.links = OrderedDict()
        node = self.typeobj
        while node is not None:
            self.links.update(getAllLinks(
                self.jsondata, node.propList, node.refs, context=expectedSchema, linklimits=config['linklimit']))
            node = node.parent


class PropItem:
    def __init__(self, soup, refs, propOwner, propChild, tagType, topVersion):
        try:
            self.name = propOwner + ':' + propChild
            self.propOwner, self.propChild = propOwner, propChild
            self.propDict = getPropertyDetails(
                soup, refs, propOwner, propChild, tagType, topVersion)
            self.attr = self.propDict['attrs']
        except Exception as ex:
            traverseLogger.exception("Something went wrong")
            traverseLogger.error(
                    '{}:{} :  Could not get details on this property'.format(str(propOwner),str(propChild)))
            self.propDict = None
            return
        pass


class PropType:
    def __init__(self, fulltype, soup, refs, tagType, topVersion=None):
        self.initiated = False
        self.fulltype = fulltype
        self.soup, self.refs = soup, refs
        self.snamespace, self.stype = getNamespace(
            self.fulltype), getType(self.fulltype)
        self.additional = False

        self.tagType = tagType
        self.isNav = False
        self.propList = []
        self.parent = None

        propertyList = self.propList
        success, baseSoup, baseRefs, baseType = True, self.soup, self.refs, self.fulltype
        try:
            self.additional, newList = getTypeDetails(
                baseSoup, baseRefs, baseType, self.tagType, topVersion)
            propertyList.extend(newList)
            success, baseSoup, baseRefs, baseType = getParentType(
                baseSoup, baseRefs, baseType, self.tagType)
            if success:
                self.parent = PropType(
                    baseType, baseSoup, baseRefs, self.tagType, topVersion=topVersion)
                if not self.additional:
                    self.additional = self.parent.additional
            self.initiated = True
        except Exception as ex:
            traverseLogger.exception("Something went wrong")
            traverseLogger.error(
                '{}:  Getting type failed for {}'.format(str(self.fulltype), str(baseType)))
            return


def getTypeDetails(soup, refs, SchemaAlias, tagType, topVersion=None):
    # spits out information on the type we have, prone to issues if references/soup is ungettable, this shouldn't be ran without it 
    #   has been prone to a lot of confusing errors: rehaul information that user expects to know before this point is reached
    # info: works undercover, but maybe can point out what type was generated and how many properties were found, if additional props allowed...
    # debug: all typegen info
    # error: if we're missing something, otherwise should be find getting all properties and letting them handle their own generation.
    #   if something can't be genned, let that particular property (PropItem) handle itself, no catches
    """
    Gets list of surface level properties for a given SchemaType,
    """
    PropertyList = list()
    additional = False

    SchemaNamespace, SchemaType = getNamespace(
        SchemaAlias), getType(SchemaAlias)

    traverseLogger.debug("Generating type: {} of tagType {}".format(SchemaAlias, tagType))
    traverseLogger.debug("Schema is {}, {}".format(
                        SchemaType, SchemaNamespace))

    innerschema = soup.find('Schema', attrs={'Namespace': SchemaNamespace})

    if innerschema is None:
        traverseLogger.error("Got XML, but expected schema doesn't exist...? {}, {}\n... we will be unable to generate properties".format(
                             SchemaNamespace, SchemaType))
        return False, PropertyList

    element = innerschema.find(tagType, attrs={'Name': SchemaType}, recursive=False)
    traverseLogger.debug("___")
    traverseLogger.debug(element['Name'])
    traverseLogger.debug(element.attrs)
    traverseLogger.debug(element.get('BaseType'))

    usableProperties = element.find_all(['NavigationProperty', 'Property'], recursive=False)
    additionalElement = element.find(
        'Annotation', attrs={'Term': 'OData.AdditionalProperties'})
    additionalElementOther = element.find(
        'Annotation', attrs={'Term': 'Redfish.DynamicPropertyPatterns'})
    if additionalElement is not None:
        additional = additionalElement.get('Bool', False)
        if additional in ['false', 'False', False]:
            additional = False
        if additional in ['true', 'True']:
            additional = True
    else:
        additional = False
    if additionalElementOther is not None:
        additional = True

    for innerelement in usableProperties:
        traverseLogger.debug(innerelement['Name'])
        traverseLogger.debug(innerelement.get('Type'))
        traverseLogger.debug(innerelement.attrs)
        newPropOwner = SchemaAlias if SchemaAlias is not None else 'SomeSchema'
        newProp = innerelement['Name']
        traverseLogger.debug("ADDING :::: {}:{}".format(newPropOwner, newProp))
        if newProp not in PropertyList:
            PropertyList.append(
                PropItem(soup, refs, newPropOwner, newProp, tagType=tagType, topVersion=topVersion))

    return additional, PropertyList


def getPropertyDetails(soup, refs, propOwner, propChild, tagType='EntityType', topVersion=None):
    # gets an individual property's details, can be prone to problems if info does not exist in soup or is bad
    #   HOWEVER, this will rarely be the case: a property that does not exist in soup would never be expected to generate
    #   info: under the hood, too much info to be worth showing
    #   debug: however, individual property concerns can go here
    #   error: much like above function, what if we can't find the type we need?  should not happen...
    #       if this happens, is it necessarily an error?  could be an outbound referenced type that isn't needed or stored
    #       example-- if we have a type for StorageXxx but don't have it stored on our system, why bother?  we don't use it
    #       the above is not technically error, pass it on?
    """
    Get dictionary of tag attributes for properties given, including basetypes.

    param arg1: soup data
    param arg2: references
    param arg3: a property string
    """

    propEntry = dict()

    SchemaNamespace, SchemaType = getNamespace(propOwner), getType(propOwner)
    traverseLogger.debug('___') 
    traverseLogger.debug('{}, {}:{}, {}'.format(SchemaNamespace, propOwner, propChild, tagType))

    propSchema = soup.find('Schema', attrs={'Namespace': SchemaNamespace})
    if propSchema is None:
        traverseLogger.warn(
            "getPropertyDetails: Schema could not be acquired,  {}".format(SchemaNamespace))
        return None

    # get type tag and tag of property in type
    propEntity = propSchema.find(tagType, attrs={'Name': SchemaType}, recursive=False)  # BS4 line
    propTag = propEntity.find(['NavigationProperty', 'Property'], attrs={'Name': propChild}, recursive=False)  # BS4 line

    # check if this property is a nav property
    # Checks if this prop is an annotation
    success, typeSoup, typeRefs, propType = getParentType(
        soup, refs, SchemaType, tagType)
    if '@' not in propChild:
        propEntry['isTerm'] = False
        # start adding attrs and props together
        propAll = propTag.find_all()  # BS4 line
        for tag in propAll:
            propEntry[tag['Term']] = tag.attrs
        propType = propTag.get('Type')
    else:
        propEntry['isTerm'] = True
        propTag = propEntity
        propType = propTag.get('Type', propOwner)

    propEntry['isNav'] = propTag.name == 'NavigationProperty'
    propEntry['attrs'] = propTag.attrs
    traverseLogger.debug(propEntry)

    propEntry['realtype'] = 'none'

    # find the real type of this, by inheritance
    while propType is not None:
        traverseLogger.debug("HASTYPE")
        TypeNamespace, TypeSpec = getNamespace(propType), getType(propType)

        traverseLogger.debug('{}, {}'.format(TypeNamespace, propType))
        # Type='Collection(Edm.String)'
        # If collection, check its inside type
        if re.match('Collection\(.*\)', propType) is not None:
            propType = propType.replace('Collection(', "").replace(')', "")
            propEntry['isCollection'] = propType
            continue
        if 'Edm' in propType:
            propEntry['realtype'] = propType
            break

        # get proper soup
        if TypeNamespace.split('.')[0] != SchemaNamespace.split('.')[0]:
            success, typeSoup, uri = getSchemaDetails(
                *refs.get(TypeNamespace, (None, None)))
        else:
            success, typeSoup, uri = True, soup, 'of parent'

        if not success:
            traverseLogger.error(
                "getPropertyDetails: InnerType could not be acquired, {} {} {}".format(propOwner, propChild ,uri))
            return propEntry

        # traverse tags to find the type
        typeRefs = getReferenceDetails(typeSoup, refs, name=uri)
        typeSchema = typeSoup.find(  # BS4 line
            'Schema', attrs={'Namespace': TypeNamespace})
        typeTag = typeSchema.find(  # BS4 line
            ['EnumType', 'ComplexType', 'EntityType', 'TypeDefinition'], attrs={'Name': TypeSpec}, recursive=False)
        nameOfTag = typeTag.name if typeTag is not None else 'None'
        # perform more logic for each type
        if nameOfTag == 'TypeDefinition':
            propType = typeTag.get('UnderlyingType')
            # This piece of code is rather simple UNLESS this is an "enumeration"
            #   this is a unique deprecated enum, labeled as Edm.String
            isEnum = typeTag.find(  # BS4 line
                'Annotation', attrs={'Term': 'Redfish.Enumeration'}, recursive=False)
            if propType == 'Edm.String' and isEnum is not None:
                propEntry['realtype'] = 'deprecatedEnum'
                propEntry['typeprops'] = list()
                memberList = isEnum.find(  # BS4 line
                    'Collection').find_all('PropertyValue')  # BS4 line

                for member in memberList:
                    propEntry['typeprops'].append(member.get('String'))
                traverseLogger.debug("{}".format(propEntry['typeprops']))
                break
            else:
                continue

        elif nameOfTag == 'ComplexType':
            traverseLogger.debug("go deeper in type")
            # We need to find the highest existence of this type vs topVersion schema
            # not ideal, but works for this solution
            success, baseSoup, baseRefs, baseType = True, typeSoup, typeRefs, propType
            if topVersion is not None and topVersion != SchemaNamespace:
                currentVersion = topVersion
                currentSchema = baseSoup.find(  # BS4 line
                    'Schema', attrs={'Namespace': currentVersion})
                # Working backwards from topVersion schematag,
                #   created expectedType, check if currentTypeTag exists
                #   if it does, use our new expectedType, else continue down parent types
                #   until we exhaust all schematags in file
                while currentSchema is not None:
                    expectedType = currentVersion + '.' + getType(propType)
                    currentTypeTag = currentSchema.find(  # BS4 line
                        'ComplexType', attrs={'Name': getType(propType)})
                    if currentTypeTag is not None:
                        baseType = expectedType
                        traverseLogger.debug('new type: ' + baseType)  # Printout FORMAT
                        break
                    else:
                        nextEntity = currentSchema.find(  # BS4 line
                            'EntityType', attrs={'Name': SchemaType})
                        nextType = nextEntity.get('BaseType')
                        currentVersion = getNamespace(nextType)
                        currentSchema = baseSoup.find(  # BS4 line
                            'Schema', attrs={'Namespace': currentVersion})
                        continue
            propEntry['realtype'] = 'complex'
            propEntry['typeprops'] = PropType(
                baseType, baseSoup, baseRefs, 'ComplexType')
            break

        elif nameOfTag == 'EnumType':
            # If enum, get all members
            propEntry['realtype'] = 'enum'
            propEntry['typeprops'] = list()
            for MemberName in typeTag.find_all('Member'):  # BS4 line
                propEntry['typeprops'].append(MemberName['Name'])
            break

        elif nameOfTag == 'EntityType':
            # If entity, do nothing special (it's a reference link)
            propEntry['realtype'] = 'entity'
            propEntry['typeprops'] = dict()
            traverseLogger.debug("typeEntityTag found {}".format(propTag['Name']))
            break

        else:
            traverseLogger.error("type doesn't exist? {}".format(propType))
            raise Exception(
                "getPropertyDetails: problem grabbing type: " + propType)
            break

    return propEntry


def getAllLinks(jsonData, propList, refDict, prefix='', context='', linklimits=None):
    # gets all links, this can miss something if it is not designated navigatable or properly autoextended, collections, etc
    # info: works underneath, can maybe report how many links it has gotten or leave that to whatever calls it?
    # debug: should be reported by what calls it?  not much debug is neede besides what is already generated earlier, 
    # error: it really depends on what type generation has done: if done correctly, this should have no problem, if propList is empty, it does nothing
    #       cannot think of errors that would be neccesary to know
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
    try:
        for propx in propList:
            propDict = propx.propDict
            key = propx.name
            item = getType(key).split(':')[-1]
            ownerNS = propx.propOwner.split('.')[0]
            ownerType = propx.propOwner.split('.')[-1]
            if propDict['isNav']:
                insideItem = jsonData.get(item)
                if insideItem is not None:
                    cType = propDict.get('isCollection')
                    autoExpand = propDict.get('OData.AutoExpand', None) is not None or\
                        propDict.get('OData.AutoExpand'.lower(), None) is not None
                    if cType is not None:
                        cTypeName = getType(cType)
                        cSchema = refDict.get(getNamespace(cType), (None, None))[1]
                        if cSchema is None:
                            cSchema = context
                        for cnt, listItem in enumerate(insideItem):
                            # starts at 0...
                            if cTypeName in linklimits:
                                if cnt >= linklimits[cTypeName]:
                                    traverseLogger.debug("Truncating Links of {}".format(cTypeName))
                                    break
                            linkList[prefix + str(item) + '.' + getType(propDict['isCollection']) +
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
                insideItem = jsonData.get(item)
                uriItem = {'@odata.id': insideItem}
                cType = ownerNS + '.' + ownerNS
                autoExpand = propDict.get('OData.AutoExpand', None) is not None or \
                             propDict.get('OData.AutoExpand'.lower(), None) is not None
                cSchema = refDict.get(getNamespace(cType), (None, None))[1]
                if cSchema is None:
                    cSchema = context
                traverseLogger.debug('Registry Location Uri: resource = {}, type = {}, schema = {}'
                                     .format(insideItem, cType, cSchema))
                linkList[prefix + str(item) + '.' + getType(propDict['attrs']['Name'])] = (
                    uriItem.get('@odata.id'), autoExpand, cType, cSchema, uriItem)
        for propx in propList:
            propDict = propx.propDict
            key = propx.name
            item = getType(key).split(':')[-1]
            if propDict['realtype'] == 'complex':
                if jsonData.get(item) is not None:
                    cType = propDict.get('isCollection')
                    if cType is not None:
                        cTypeName = getType(cType)
                        for cnt, listItem in enumerate(jsonData[item]):
                            # starts at 0...
                            if cTypeName in linklimits:
                                if cnt >= linklimits[cTypeName]:
                                    traverseLogger.debug("Truncating Links of {}".format(cTypeName))
                                    break
                            linkList.update(getAllLinks(
                                listItem, propDict['typeprops'].propList, refDict, prefix + item + '.', context))
                    else:
                        linkList.update(getAllLinks(
                            jsonData[item], propDict['typeprops'].propList, refDict, prefix + item + '.', context))
        traverseLogger.debug(str(linkList))
    except Exception as ex:
        traverseLogger.exception("Something went wrong")
    return linkList


def getAnnotations(soup, refs, decoded, prefix=''):
    """
    Function to gather @ additional props in a payload
    """
    additionalProps = list()
    # For every ...@ in decoded, check for its presence in refs
    #   get the schema file for it
    #   concat type info together
    annotationsFound = 0
    for key in [k for k in decoded if prefix + '@' in k and '@odata' not in k]:
        annotationsFound += 1
        splitKey = key.split('@', 1)
        fullItem = splitKey[1]
        realType, refLink = refs.get(getNamespace(fullItem), (None, None))
        success, annotationSoup, uri = getSchemaDetails(realType, refLink)
        traverseLogger.debug('{}, {}, {}, {}, {}'.format(
            str(success), key, splitKey, decoded[key], realType))
        if success:
            annotationRefs = getReferenceDetails(annotationSoup, refs, uri)
            if isinstance(decoded[key], dict) and decoded[key].get('@odata.type') is not None:
                payloadType = decoded[key].get('@odata.type').replace('#', '')
                realType, refLink = annotationRefs.get(getNamespace(payloadType).split('.')[0], (None, None))
                success, annotationSoup, uri = getSchemaDetails(realType, refLink)
                realItem = payloadType
                tagtype = 'ComplexType'
            else:
                realItem = realType + '.' + fullItem.split('.', 1)[1]
                tagtype = 'Term'
            additionalProps.append(
                PropItem(annotationSoup, annotationRefs, realItem, key, tagtype, None))
    traverseLogger.info("Annotations generated: {} out of {}".format(len(additionalProps), annotationsFound))
    return True, additionalProps
