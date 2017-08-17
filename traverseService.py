
# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link:
# https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from bs4 import BeautifulSoup
import configparser
import requests
import sys
import re
import os
from collections import OrderedDict
from functools import lru_cache
import logging
from rfSession import rfSession
from requests.packages.urllib3.exceptions import InsecureRequestWarning


traverseLogger = logging.getLogger(__name__)
traverseLogger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
traverseLogger.addHandler(ch)  # Printout FORMAT, consider allowing debug to be piped here
config = configparser.ConfigParser()
config['DEFAULT'] = {'LogPath': './logs', 'SchemaSuffix': '_v1.xml', 'timeout': 30, 'AuthType': 'Basic', 'CertificateBundle': "",
                        'HttpProxy': "", 'HttpsProxy': ""}
config['internal'] = {'configSet': '0'}
commonHeader = {'OData-Version': '4.0'}
proxies = {}
SchemaSuffix = UseSSL = ConfigURI = User = Passwd = SysDescription = SchemaLocation = \
        ChkCertBundle = ChkCert = LocalOnly = AuthType = ServiceOnly = timeout = LogPath = None

currentSession = rfSession()
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


def getLogger():
    """
    Grab logger for tools that might use this lib
    """
    return traverseLogger


def setConfigNamespace(args):
    # both config functions should conflate no extra info to log, unless it errors out or defaultsi
    #   any printouts should go to RSV, it's responsible for most logging initiative to file
    #   consider this: traverse has its own logging, rsv has its own logging
    # info: xxx
    """
    Provided a namespace, modify args based on it
    """
    global SchemaSuffix, UseSSL, ConfigURI, User, Passwd, SysDescription, SchemaLocation,\
        ChkCert, LocalOnly, ServiceOnly, timeout, LogPath, AuthType, ChkCertBundle
    User = args.user
    Passwd = args.passwd
    AuthType = args.authtype
    SysDescription = args.desc
    SchemaLocation = args.dir
    timeout = args.timeout
    UseSSL = not args.nossl
    ChkCert = not args.nochkcert and UseSSL
    ChkCertBundle = args.ca_bundle
    if ChkCertBundle not in [None, ""] and ChkCert:
        if not os.path.isfile(ChkCertBundle):
            ChkCertBundle = None
            traverseLogger.error('ChkCertBundle is not found, defaulting to None')
    else:
        ChkCertBundle = None
    LogPath = args.logdir
    ConfigURI = ('https' if UseSSL else 'http') + '://' + \
        args.ip
    LocalOnly = args.localonly
    ServiceOnly = args.service
    SchemaSuffix = args.suffix
    httpprox = args.http_proxy
    httpsprox = args.https_proxy
    proxies['http'] = httpprox
    proxies['https'] = httpsprox

    if AuthType not in ['None', 'Basic', 'Session']:
        AuthType = 'Basic'
        traverseLogger.error('AuthType invalid, defaulting to Basic') 

    if AuthType == 'Session':
        certVal = ChkCertBundle if ChkCert and ChkCertBundle is not None else ChkCert
        success = currentSession.startSession(User, Passwd, ConfigURI, certVal, proxies)
        if not success:
            raise RuntimeError("Session could not start")

    config['internal']['configSet'] = '1'


def setConfig(filename):
    """
    Set config based on config file read from location filename
    """
    global SchemaSuffix, UseSSL, ConfigURI, User, Passwd, SysDescription, SchemaLocation,\
        ChkCert, LocalOnly, ServiceOnly, timeout, LogPath, AuthType, ChkCertBundle
    config.read(filename)
    UseSSL = config.getboolean('Options', 'UseSSL')

    ConfigURI = ('https' if UseSSL else 'http') + '://' + \
        config.get('SystemInformation', 'TargetIP')

    User = config.get('SystemInformation', 'UserName')
    Passwd = config.get('SystemInformation', 'Password')
    SysDescription = config.get('SystemInformation', 'SystemInfo')
    AuthType = config.get('SystemInformation', 'AuthType')

    SchemaLocation = config.get('Options', 'MetadataFilePath')
    LogPath = config.get('Options', 'LogPath')
    ChkCert = config.getboolean('Options', 'CertificateCheck') and UseSSL
    ChkCertBundle = config.get('Options', 'CertificateBundle')
    if ChkCertBundle not in [None, ""] and ChkCert:
        if not os.path.isfile(ChkCertBundle):
            ChkCertBundle = None
            traverseLogger.error('ChkCertBundle is not found, defaulting to None')  # Printout FORMAT
    else:
        ChkCertBundle = None
    SchemaSuffix = config.get('Options', 'SchemaSuffix')
    timeout = config.getint('Options', 'timeout')
    LocalOnly = config.getboolean('Options', 'LocalOnlyMode')
    ServiceOnly = config.getboolean('Options', 'ServiceMode')
    httpprox = config.get('Options', 'HttpProxy')
    httpsprox = config.get('Options', 'HttpsProxy')
    proxies['http'] = httpprox if httpprox != "" else None
    proxies['https'] = httpsprox if httpsprox != "" else None

    if AuthType not in ['None', 'Basic', 'Session']:
        AuthType = 'Basic'
        traverseLogger.error('AuthType invalid, defaulting to Basic')  # Printout FORMAT

    if AuthType == 'Session':
        certVal = ChkCertBundle if ChkCert and ChkCertBundle is not None else ChkCert
        success = currentSession.startSession(User, Passwd, ConfigURI, certVal, proxies)
        if not success:
            raise RuntimeError("Session could not start")

    config['internal']['configSet'] = '1'

def isConfigSet():
    """
    Check if the library is configured
    """
    if config['internal']['configSet'] == '1':
        return True
    else:
        raise RuntimeError("Configuration is not set")


def isNonService(uri):
    """
    Checks if a uri is within the service
    """
    return 'http' in uri[:8]


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
    if URILink is None:
        traverseLogger.debug("This URI is empty!")
        return False, None, -1, 0
    nonService = isNonService(URILink)
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
            auth = (User, Passwd)

    if nonService and ServiceOnly:
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
    else:
        headers = commonHeader

    certVal = ChkCertBundle if ChkCert and ChkCertBundle is not None else ChkCert

    # rs-assertion: must have application/json or application/xml
    traverseLogger.debug('callingResourceURI with authtype {} and ssl {}: {}'.format(AuthType, UseSSL, URILink)) 
    try:
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
                if '#' in URILink:
                    URILink, frag = tuple(URILink.rsplit('#', 1))
                    fragNavigate = frag.split('/')[1:]
                    for item in fragNavigate:
                        if isinstance(decoded, dict):
                            decoded = decoded.get(item)
                        elif isinstance(decoded, list):
                            decoded = decoded[int(item)] if int(
                                item) < len(decoded) else None
                    if not isinstance(decoded, dict):
                        traverseLogger.warn(
                            "Decoded object no longer a dictionary {}".format(URILink))
            elif contenttype is not None and 'application/xml' in contenttype:
                decoded = response.text
            else:
                traverseLogger.error(
                        "This URI did NOT return XML or Json, this is not a Redfish resource (is this redirected?): {}".format(URILink))
                return False, response.text, statusCode, elapsed
            return decoded is not None, decoded, statusCode, elapsed

    except requests.exceptions.ConnectionError as e:
        traverseLogger.error("ConnectionError on {}".format(URILink))
    except requests.exceptions.Timeout as e:
        traverseLogger.error("Request has timed out ({}s) on resource {}".format(timeout, URILink))
    except requests.exceptions.RequestException as e:
        traverseLogger.error("Request has encounted a problem when getting resource {}".format(URILink))
        traverseLogger.warn("output: ", exc_info=True)
    except Exception as ex:
        traverseLogger.error("A problem when getting resource has occurred {}".format(URILink))
        traverseLogger.warn("output: ", exc_info=True)

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

    if SchemaURI is not None and not LocalOnly:
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
    if not LocalOnly:
        traverseLogger.warn("SchemaURI {} was unable to be called, defaulting to local storage in {}".format(SchemaURI, SchemaLocation))
    return getSchemaDetailsLocal(SchemaType, SchemaURI)


def getSchemaDetailsLocal(SchemaType, SchemaURI):
    # Use local if no URI or LocalOnly
    # What are we looking for?  Parse from URI
    # if we're not able to use URI to get suffix, work with option fallback
    Alias = getNamespace(SchemaType).split('.')[0]
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


def getReferenceDetails(soup, metadata_dict=None, name='xml'):
    """
    Create a reference dictionary from a soup file

    param arg1: soup
    param metadata_dict: dictionary of service metadata, compare with
    return: dictionary
    """
    refDict = {}

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

    cntref = len(refDict)
    if metadata_dict is not None:
        refDict.update(metadata_dict)
        if len(refDict.keys()) > len(metadata_dict.keys()):
            diff_keys = [key for key in refDict if key not in metadata_dict]
            traverseLogger.log(
                    logging.ERROR if ServiceOnly else logging.WARN,
                    "Reference in a Schema {} not in metadata, this may not be compatible with ServiceMode".format(name))
            traverseLogger.log(
                    logging.ERROR if ServiceOnly else logging.WARN,
                    "References missing in metadata: {}".format(str(diff_keys)))
    traverseLogger.debug(str(refDict))
    traverseLogger.debug("References generated from {}: {}".format(name, cntref))
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
        innerRefs = getReferenceDetails(innerSoup, refs, )
        propSchema = innerSoup.find(  # BS4 line
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

        # Check if we provide a type besides json's
        if expectedType is None:
            fullType = self.jsondata.get('@odata.type')
            if fullType is None:
                traverseLogger.error(  # Printout FORMAT
                    str(self.uri) + ':  Json does not contain @odata.type',)
                return
        else:
            fullType = self.jsondata.get('@odata.type', expectedType)

        # Provide a context for this
        if expectedSchema is None:
            self.context = self.jsondata.get('@odata.context')
            expectedSchema = self.context
            if expectedSchema is None:
                traverseLogger.error(  # Printout FORMAT
                    str(self.uri) + ':  Json does not contain @odata.context',)
        else:
            self.context = expectedSchema

        success, typesoup, self.context = getSchemaDetails(
            fullType, SchemaURI=self.context)

        if not success:
            traverseLogger.error("validateURI: No schema XML for " + fullType)  # Printout FORMAT
            return

        # Use string comprehension to get highest type
        if fullType is expectedType:
            typelist = list()
            schlist = list()
            for schema in typesoup.find_all('Schema'):  # BS4 line
                newNamespace = schema.get('Namespace')
                typelist.append(newNamespace)
                schlist.append(schema)
            for item, schema in reversed(sorted(zip(typelist, schlist))):
                traverseLogger.debug(  # Printout FORMAT
                    item + ' ' + str('') + ' ' + getType(fullType))
                if schema.find('EntityType', attrs={'Name': getType(fullType)}, recursive=False):  # BS4 line
                    fullType = item + '.' + getType(fullType)
                    break
            traverseLogger.warn(  # Printout FORMAT
                'No @odata.type present, assuming highest type %s', fullType)

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
            typerefs = getReferenceDetails(typesoup, serviceRefs)
            self.typeobj = PropType(
                fullType, typesoup, typerefs, 'EntityType', topVersion=getNamespace(fullType))
            ResourceObj.robjcache[idtag] = self.typeobj

        self.links = OrderedDict()
        node = self.typeobj
        while node is not None:
            self.links.update(getAllLinks(
                self.jsondata, node.propList, node.refs, context=expectedSchema))
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
            traverseLogger.exception("Something went wrong")  # Printout FORMAT
            traverseLogger.error(  # Printout FORMAT
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
            traverseLogger.exception("Something went wrong")  # Printout FORMAT
            traverseLogger.error(  # Printout FORMAT
                ':  Getting type failed for ' + str(self.fulltype) + " " + str(baseType))
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

    traverseLogger.debug("Schema is %s, %s, %s", SchemaType,  # Printout FORMAT
                         SchemaType, SchemaNamespace)

    innerschema = soup.find('Schema', attrs={'Namespace': SchemaNamespace})  # BS4 line

    if innerschema is None:
        traverseLogger.error("Got XML, but schema still doesn't exist...? %s, %s" %  # Printout FORMAT
                             (getNamespace(SchemaType), SchemaType))
        raise Exception('exceptionType: Was not able to get type, is Schema in XML? ' +
                        str(refs.get(getNamespace(SchemaType), (getNamespace(SchemaType), None))))

    element = innerschema.find(tagType, attrs={'Name': SchemaType}, recursive=False)  # BS4 line
    traverseLogger.debug("___")  # Printout FORMAT
    traverseLogger.debug(element['Name'])  # Printout FORMAT
    traverseLogger.debug(element.attrs)  # Printout FORMAT
    traverseLogger.debug(element.get('BaseType'))  # Printout FORMAT

    usableProperties = element.find_all(['NavigationProperty', 'Property'], recursive=False)  # BS4 line
    additionalElement = element.find(  # BS4 line
        'Annotation', attrs={'Term': 'OData.AdditionalProperties'})
    if additionalElement is not None:
        additional = additionalElement.get('Bool', False)
        if additional in ['false', 'False', False]:
            additional = False
        if additional in ['true', 'True']:
            additional = True
    else:
        additional = False

    for innerelement in usableProperties:
        traverseLogger.debug(innerelement['Name'])  # Printout FORMAT
        traverseLogger.debug(innerelement.get('Type'))  # Printout FORMAT
        traverseLogger.debug(innerelement.attrs)  # Printout FORMAT
        newPropOwner = SchemaAlias if SchemaAlias is not None else 'SomeSchema'
        newProp = innerelement['Name']
        traverseLogger.debug("ADDING :::: {}:{}".format(newPropOwner, newProp))  # Printout FORMAT
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
        traverseLogger.error( 
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
    traverseLogger.debug(propEntry)  # Printout FORMAT

    propEntry['realtype'] = 'none'

    # find the real type of this, by inheritance
    while propType is not None:
        traverseLogger.debug("HASTYPE")  # Printout FORMAT
        TypeNamespace, TypeSpec = getNamespace(propType), getType(propType)

        traverseLogger.debug('%s, %s', TypeNamespace, propType)  # Printout FORMAT
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
            success, typeSoup = True, soup

        if not success:
            traverseLogger.error(  # Printout FORMAT
                "getPropertyDetails: InnerType could not be acquired,  %s", TypeNamespace)
            return propEntry

        # traverse tags to find the type
        typeRefs = getReferenceDetails(typeSoup, refs)
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
                traverseLogger.debug("{}".format(propEntry['typeprops']))  # Printout FORMAT
                break
            else:
                continue

        elif nameOfTag == 'ComplexType':
            traverseLogger.debug("go deeper in type")  # Printout FORMAT
            # We need to find the highest existence of this type vs topVersion schema
            # not ideal, but works for this solution
            success, baseSoup, baseRefs, baseType = True, typeSoup, typeRefs, propType
            if topVersion is not None and topVersion != SchemaNamespace:
                currentVersion = topVersion
                currentSchema = baseSoup.find(  # BS4 line
                    'schema', attrs={'Namespace': currentVersion})
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
                            'schema', attrs={'Namespace': currentVersion})
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
            traverseLogger.debug("typeEntityTag found %s", propTag['Name'])  # Printout FORMAT
            break

        else:
            traverseLogger.error("type doesn't exist? %s", propType)  # Printout FORMAT
            raise Exception(
                "getPropertyDetails: problem grabbing type: " + propType)
            break

    return propEntry


def getAllLinks(jsonData, propList, refDict, prefix='', context=''):
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
    # check keys in propertyDictionary
    # if it is a Nav property, check that it exists
    #   if it is not a Nav Collection, add it to list
    #   otherwise, add everything IN Nav collection
    # if it is a Complex property, check that it exists
    #   if it is, recurse on collection or individual item
    for propx in propList:
        propDict = propx.propDict
        key = propx.name
        item = getType(key).split(':')[-1]
        if propDict['isNav']:
            insideItem = jsonData.get(item)
            if insideItem is not None:
                cType = propDict.get('isCollection')
                autoExpand = propDict.get('OData.AutoExpand', None) is not None or\
                    propDict.get('OData.AutoExpand'.lower(), None) is not None
                if cType is not None:
                    cSchema = refDict.get(getNamespace(cType), (None, None))[1]
                    if cSchema is None:
                        cSchema = context
                    for cnt, listItem in enumerate(insideItem):
                        linkList[prefix + str(item) + '.' + getType(propDict['isCollection']) +
                                 '#' + str(cnt)] = (listItem.get('@odata.id'), autoExpand, cType, cSchema, listItem)
                else:
                    cType = propDict['attrs'].get('Type')
                    cSchema = refDict.get(getNamespace(cType), (None, None))[1]
                    if cSchema is None:
                        cSchema = context
                    linkList[prefix + str(item) + '.' + getType(propDict['attrs']['Name'])] = (
                        insideItem.get('@odata.id'), autoExpand, cType, cSchema, insideItem)
    for propx in propList:
        propDict = propx.propDict
        key = propx.name
        item = getType(key).split(':')[-1]
        if propDict['realtype'] == 'complex':
            if jsonData.get(item) is not None:
                if propDict.get('isCollection') is not None:
                    for listItem in jsonData[item]:
                        linkList.update(getAllLinks(
                            listItem, propDict['typeprops'].propList, refDict, prefix + item + '.', context))
                else:
                    linkList.update(getAllLinks(
                        jsonData[item], propDict['typeprops'].propList, refDict, prefix + item + '.', context))
    traverseLogger.debug(str(linkList))  # Printout FORMAT
    return linkList


def getAnnotations(soup, refs, decoded, prefix=''):
    # function that gets annotations, calls a lot of other functions for info:
    #   info: what annotations have been found?  A lot of this can be considered here as debug or outside as info...
    
    """
    Function to gather @ additional props in a payload
    """
    additionalProps = list()
    # For every ...@ in decoded, check for its presence in refs
    #   get the schema file for it
    #   concat type info together
    for key in [k for k in decoded if prefix + '@' in k]:
        splitKey = key.split('@', 1)
        fullItem = splitKey[1]
        realType, refLink = refs.get(getNamespace(fullItem), (None, None))
        success, annotationSoup, uri = getSchemaDetails(realType, refLink)
        traverseLogger.debug('%s, %s, %s, %s, %s', str(  # Printout FORMAT
            success), key, splitKey, decoded[key], realType)
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

    return True, additionalProps
