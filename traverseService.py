
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
traverseLogger.setLevel(logging.DEBUG)  # Printout FORMAT
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
            traverseLogger.error('ChkCertBundle is not found, defaulting to None')  # Printout FORMAT
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
        traverseLogger.error('AuthType invalid, defaulting to Basic')  # Printout FORMAT

    if AuthType == 'Session':
        certVal = ChkCertBundle if ChkCert and ChkCertBundle is not None else ChkCert
        success = currentSession.startSession(User, Passwd, ConfigURI, certVal, proxies)
        if not success:
            raise RuntimeError("Session could not start")

    config['internal']['configSet'] = '1'
    input(config['internal'])


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
    # critical code, gets URI
    # debug: where are we going, is it on the service, is it blocked, what auth, 
    # error: we should know if a something was ungettable, but should this be in this function?  Also if its not json/xml, and GENERAL requests errors
    """
    Makes a call to a given URI or URL

    param arg1: path to URI "/example/1", or URL "http://example.com"
    return: (success boolean, data, request status code)
    """
    # rs-assertions: 6.4.1, including accept, content-type and odata-versions
    # rs-assertion: handle redirects?  and target permissions
    # rs-assertion: require no auth for serviceroot calls
    if URILink is None:
        return False, None, -1, 0
    nonService = isNonService(URILink)
    statusCode = ''
    elapsed = 0
    if not nonService:
        # feel free to make this into a regex
        noauthchk = \
            ('/redfish' in URILink and '/redfish/v1' not in URILink) or\
            URILink in ['/redfish/v1', '/redfish/v1/', '/redfish/v1/odata', 'redfish/v1/odata/'] or\
            '/redfish/v1/$metadata' in URILink
        if noauthchk:
            traverseLogger.debug('dont chkauth')  # Printout FORMAT
            auth = None
        else:
            auth = (User, Passwd)

    if nonService and ServiceOnly:
        traverseLogger.debug('Disallowed out of service URI')  # Printout FORMAT
        return False, None, -1, 0

    # rs-assertion: do not send auth over http
    if not UseSSL or nonService or AuthType != 'Basic':
        auth = None

    if UseSSL and not nonService and AuthType == 'Session' and not noauthchk:
        headers = {"X-Auth-Token": currentSession.getSessionKey()}
        headers.update(commonHeader)
    else:
        headers = commonHeader

    certVal = ChkCertBundle if ChkCert and ChkCertBundle is not None else ChkCert

    # rs-assertion: must have application/json or application/xml
    traverseLogger.debug('callingResourceURI: %s', URILink)  # Printout FORMAT
    try:
        response = requests.get(ConfigURI + URILink if not nonService else URILink,
                                headers=headers, auth=auth, verify=certVal, timeout=timeout, proxies=proxies)
        expCode = [200]
        elapsed = response.elapsed.total_seconds()
        statusCode = response.status_code
        traverseLogger.debug('%s, %s, %s,\nTIME ELAPSED: %s', statusCode,  # Printout FORMAT
                             expCode, response.headers, elapsed)
        if statusCode in expCode:
            contenttype = response.headers.get('content-type')
            if contenttype is not None and 'application/json' in contenttype:
                traverseLogger.debug("This is a JSON response")  # Printout FORMAT
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
                        traverseLogger.warn(  # Printout FORMAT
                            URILink + " decoded object no longer a dictionary")
            elif contenttype is not None and 'application/xml' in contenttype:
                decoded = response.text
            else:
                traverseLogger.error(  # Printout FORMAT
                        "This URI did NOT return XML or Json, this is not a Redfish resource (is this redirected?): {}".format(URILink))
                return False, response.text, statusCode, elapsed
            return decoded is not None, decoded, statusCode, elapsed
    except Exception as ex:
        traverseLogger.exception("Something went wrong")  # Printout FORMAT
    return False, None, statusCode, elapsed


# note: Use some sort of re expression to parse SchemaAlias
# ex: #Power.1.1.1.Power , #Power.v1_0_0.Power
def getNamespace(string):
    return string.replace('#', '').rsplit('.', 1)[0]


def getType(string):
    return string.replace('#', '').rsplit('.', 1)[-1]


@lru_cache(maxsize=64)
def getSchemaDetails(SchemaAlias, SchemaURI):
    # a big mess of misinformation: intention is to find a schema xml and return its soup, local or service or online
    #   however, does not warn adequately what its doing or why, such as references and the like, fragment usage or type usage
    #   change: add a setting for specifically adding metadata, or have a glob so we can personally find it in a directory
    #   info: a lot of under the hood, should not deliberate unless its necessary to know (fallbacks, service denial, $metadata usage)
    #   warn: conflate above with a warn label instead of info
    #   debug: what is under the hood, knowing when we get a schema, the name and destination, fragment + type
    #   error: we couldn't find what we were looking for at ALL, however this always happens in finding local fallback
    """
    Find Schema file for given Namespace.

    param arg1: Schema Namespace, such as ServiceRoot
    param SchemaURI: uri to grab schema, given LocalOnly is False
    return: (success boolean, a Soup object)
    """
    if SchemaAlias is None:
        return False, None, None

    # rs-assertion: parse frags
    if SchemaURI is not None and not LocalOnly:
        # Get our expected Schema file here
        frag = None
        if '#' in SchemaURI:
            SchemaURI, frag = tuple(SchemaURI.rsplit('#', 1))
        success, data, status, elapsed = callResourceURI(SchemaURI)
        # if success, generate Soup, then check for frags to parse
        #   start by parsing references, then check for the refLink
        if success:
            soup = BeautifulSoup(data, "html.parser")
            # if frag, look inside xml for real target
            if frag is not None:
                # prefer type over frag
                frag = getNamespace(SchemaAlias)
                frag = frag.split('.', 1)[0]
                # using frag, check references
                refType, refLink = getReferenceDetails(
                    soup).get(frag, (None, None))
                if refLink is not None:
                    success, linksoup, newlink = getSchemaDetails(refType, refLink)
                    if success:
                        return True, linksoup, newlink
                    else:
                        traverseLogger.error(  # Printout FORMAT
                            "SchemaURI couldn't call reference link: {} {}".format(SchemaURI, frag))
                else:
                    traverseLogger.error(  # Printout FORMAT
                        "SchemaURI missing reference link: {} {}".format(SchemaURI, frag))
            else:
                return True, soup, SchemaURI
        if isNonService(SchemaURI) and ServiceOnly:
            traverseLogger.info("Nonservice URI skipped " + SchemaURI)  # Printout FORMAT
        else:
            traverseLogger.debug("SchemaURI unsuccessful: %s", SchemaURI)  # Printout FORMAT
    return getSchemaDetailsLocal(SchemaAlias, SchemaURI)


def getSchemaDetailsLocal(SchemaAlias, SchemaURI):
    # Use local if no URI or LocalOnly
    # What are we looking for?  Parse from URI
    xml = None
    # if we're not able to use URI to get suffix, work with option fallback
    if SchemaURI is not None:
        uriparse = SchemaURI.split('/')[-1].split('#')
        xml = uriparse[0]
    else:
        return getSchemaDetailsLocal(SchemaAlias, SchemaAlias + SchemaSuffix)
    Alias = getNamespace(SchemaAlias)
    traverseLogger.debug((SchemaAlias, SchemaURI, SchemaLocation + '/' + xml))  # Printout FORM
    try:
        filehandle = open(SchemaLocation + '/' + xml, "r")
        filedata = filehandle.read()
        filehandle.close()
        soup = BeautifulSoup(filedata, "html.parser")
        edmxTag = soup.find('edmx:edmx', recursive=False)  # BS4 line
        parentTag = edmxTag.find('edmx:dataservices', recursive=False)  # BS4 line
        child = parentTag.find('schema', recursive=False)  # BS4 line
        SchemaNamespace = child['namespace']
        FoundAlias = SchemaNamespace.split(".")[0]
        traverseLogger.debug(FoundAlias)
        pout = SchemaAlias + SchemaSuffix if xml is None else xml
        if '/redfish/v1/$metadata' in SchemaURI:
            if len(uriparse) > 1:
                frag = uriparse[1]
                refType, refLink = getReferenceDetails(
                    soup).get(getNamespace(frag), (None, None))
                if refLink is not None:
                    return getSchemaDetailsLocal(refType, refLink)
                else:
                    traverseLogger.error('Could not find item in $metadata {}'.format(frag))  # Printout FORMAT
                    return False, None, None
            else:
                return True, soup, "local" + SchemaLocation + '/' + pout
        if FoundAlias in Alias:
            return True, soup, "local" + SchemaLocation + '/' + pout
    except FileNotFoundError as ex:
        # if we're looking for $metadata locally... ditch looking for it, go straight to file
        if '/redfish/v1/$metadata' in SchemaURI:
            return getSchemaDetailsLocal(SchemaAlias, pout)
        else:
            traverseLogger.error(  # Printout FORMAT
                "File not found in {} for {}: ".format(SchemaLocation, pout))
    except Exception as ex:
        traverseLogger.exception("Something went wrong")  # Printout FORMAT
    return False, None, None


def getReferenceDetails(soup, metadata_dict=None):
    # One of several info spitting functions, information here is critical for later functionality
    #   intended to generate references with a given xml and previously calculated metadata dict
    #   prone to a LOT of early issues if whatever this function is used on IS NOT correct
    #   info: Tell us: what references did we generate when this was called, maybe have a name associated
    #   debug: what total references did we get from this soup: problem is this function is called a LOT, cannot be cached reliably?
    #   warn: it'd be best to have all refs on service if able
    #   error: we must have all refs on service if able, or malformed references (this should not happen if we can verify xml before using it)
    """
    Create a reference dictionary from a soup file

    param arg1: soup
    param metadata_dict: dictionary of service metadata, compare with
    return: dictionary
    """
    refDict = {}
    maintag = soup.find('edmx:edmx', recursive=False)  # BS4 line
    refs = maintag.find_all('edmx:reference', recursive=False)  # BS4 line
    for ref in refs:
        includes = ref.find_all('edmx:include', recursive=False)  # BS4 line
        for item in includes:
            if item.get('namespace') is None or ref.get('uri') is None:
                traverseLogger.error("Reference incorrect for: ", item)  # Printout FORMAT
                continue
            traverseLogger.debug("Reference {} as {}, {}".format(  # Printout FORMAT
                item.get('namespace'), item.get('alias', 'itself'), ref.get('uri')))
            if item.get('alias') is not None:
                refDict[item['alias']] = (item['namespace'], ref['uri'])
            else:
                refDict[item['namespace']] = (item['namespace'], ref['uri'])
                refDict[item['namespace'].split('.')[0]] = (
                    item['namespace'], ref['uri'])

    if metadata_dict is not None:
        refDict.update(metadata_dict)
        if len(refDict.keys()) > len(metadata_dict.keys()):
            propSchema = soup.find('schema')  # BS4 line
            nameOfSchema = propSchema.get('namespace', '?')
            diff_keys = [key for key in refDict if key not in metadata_dict]
            traverseLogger.log(  # Printout FORMAT
                    logging.ERROR if ServiceOnly else logging.WARN,
                    "Reference in a Schema containing {} not in metadata, this may not be compatible with ServiceMode".format(nameOfSchema))
            traverseLogger.log(  # Printout FORMAT
                    logging.ERROR if ServiceOnly else logging.WARN,
                    "References missing in metadata: {}".format(str(diff_keys)))
    return refDict


def getParentType(soup, refs, currentType, tagType='entitytype'):
    # overhauling needed: deprecated function that should be realigned with the current type function
    # info: none, works under the covers
    # debug: what are we working towards?  did we get it?  it's fine if we didn't
    # error: none, should lend that to whatever calls it
    """
    Get parent type of given type.

    param arg1: soup
    param arg2: refs
    param arg3: current type
    param tagType: the type of tag for inheritance, default 'entitytype'
    return: success, associated soup, associated ref, new type
    """
    pnamespace, ptype = getNamespace(currentType), getType(currentType)

    propSchema = soup.find(  # BS4 line
        'schema', attrs={'namespace': pnamespace})

    if propSchema is None:
        return False, None, None, None

    propEntity = propSchema.find(tagType, attrs={'name': ptype}, recursive=False)  # BS4 line

    if propEntity is None:
        return False, None, None, None

    currentType = propEntity.get('basetype')

    if currentType is None:
        return False, None, None, None

    currentType = currentType.replace('#', '')
    SchemaNamespace, SchemaType = getNamespace(
        currentType), getType(currentType)
    propSchema = soup.find('schema', attrs={'namespace': SchemaNamespace})  # BS4 line

    if propSchema is None:
        success, innerSoup, uri = getSchemaDetails(
            *refs.get(SchemaNamespace, (None, None)))
        if not success:
            return False, None, None, None
        innerRefs = getReferenceDetails(innerSoup, refs)
        propSchema = innerSoup.find(  # BS4 line
            'schema', attrs={'namespace': SchemaNamespace})
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
            traverseLogger.debug('%s, %s, %s', success, self.jsondata, status)  # Printout FORMAT
            if not success:
                traverseLogger.error(  # Printout FORMAT
                    '%s:  URI could not be acquired: %s' % (self.uri, status))
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
            for schema in typesoup.find_all('schema'):  # BS4 line
                newNamespace = schema.get('namespace')
                typelist.append(newNamespace)
                schlist.append(schema)
            for item, schema in reversed(sorted(zip(typelist, schlist))):
                traverseLogger.debug(  # Printout FORMAT
                    item + ' ' + str('') + ' ' + getType(fullType))
                if schema.find('entitytype', attrs={'name': getType(fullType)}, recursive=False):  # BS4 line
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
            serviceRefs = getReferenceDetails(serviceSchemaSoup)
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
                fullType, typesoup, typerefs, 'entitytype', topVersion=getNamespace(fullType))
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
    Gets list of surface level properties for a given SchemaAlias,
    """
    PropertyList = list()
    additional = False

    SchemaNamespace, SchemaType = getNamespace(
        SchemaAlias), getType(SchemaAlias)

    traverseLogger.debug("Schema is %s, %s, %s", SchemaAlias,  # Printout FORMAT
                         SchemaType, SchemaNamespace)

    innerschema = soup.find('schema', attrs={'namespace': SchemaNamespace})  # BS4 line

    if innerschema is None:
        traverseLogger.error("Got XML, but schema still doesn't exist...? %s, %s" %  # Printout FORMAT
                             (getNamespace(SchemaAlias), SchemaAlias))
        raise Exception('exceptionType: Was not able to get type, is Schema in XML? ' +
                        str(refs.get(getNamespace(SchemaAlias), (getNamespace(SchemaAlias), None))))

    element = innerschema.find(tagType, attrs={'name': SchemaType}, recursive=False)  # BS4 line
    traverseLogger.debug("___")  # Printout FORMAT
    traverseLogger.debug(element['name'])  # Printout FORMAT
    traverseLogger.debug(element.attrs)  # Printout FORMAT
    traverseLogger.debug(element.get('basetype'))  # Printout FORMAT

    usableProperties = element.find_all(['navigationproperty', 'property'], recursive=False)  # BS4 line
    additionalElement = element.find(  # BS4 line
        'annotation', attrs={'term': 'OData.AdditionalProperties'})
    if additionalElement is not None:
        additional = additionalElement.get('bool', False)
        if additional in ['false', 'False', False]:
            additional = False
        if additional in ['true', 'True']:
            additional = True
    else:
        additional = False

    for innerelement in usableProperties:
        traverseLogger.debug(innerelement['name'])  # Printout FORMAT
        traverseLogger.debug(innerelement.get('type'))  # Printout FORMAT
        traverseLogger.debug(innerelement.attrs)  # Printout FORMAT
        newPropOwner = SchemaAlias if SchemaAlias is not None else 'SomeSchema'
        newProp = innerelement['name']
        traverseLogger.debug("ADDING :::: %s", newProp)  # Printout FORMAT
        if newProp not in PropertyList:
            PropertyList.append(
                PropItem(soup, refs, newPropOwner, newProp, tagType=tagType, topVersion=topVersion))

    return additional, PropertyList


def getPropertyDetails(soup, refs, propOwner, propChild, tagType='entitytype', topVersion=None):
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
    traverseLogger.debug('___')  # Printout FORMAT
    traverseLogger.debug('{}, {}:{}'.format(SchemaNamespace, propOwner, propChild))  # Printout FORMAT

    propSchema = soup.find('schema', attrs={'namespace': SchemaNamespace})  # BS4 line
    if propSchema is None:
        traverseLogger.error(  # Printout FORMAT
            "getPropertyDetails: Schema could not be acquired,  %s", SchemaNamespace)
        return None
    else:
        innerSoup = soup
        innerRefs = refs

    # get type tag and tag of property in type
    propEntity = propSchema.find(tagType, attrs={'name': SchemaType}, recursive=False)  # BS4 line
    propTag = propEntity.find(['navigationproperty', 'property'], attrs={'name': propChild}, recursive=False)  # BS4 line

    # check if this property is a nav property
    # Checks if this prop is an annotation
    success, typeSoup, typeRefs, propType = getParentType(
        innerSoup, innerRefs, SchemaType, tagType)
    if '@' not in propChild:
        propEntry['isTerm'] = False
        # start adding attrs and props together
        propAll = propTag.find_all()  # BS4 line
        for tag in propAll:
            propEntry[tag['term']] = tag.attrs
        propType = propTag.get('type')
    else:
        propEntry['isTerm'] = True
        propTag = propEntity
        propType = propTag.get('type', propOwner)

    propEntry['isNav'] = propTag.name == 'navigationproperty'
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
            success, typeSoup = True, innerSoup

        if not success:
            traverseLogger.error(  # Printout FORMAT
                "getPropertyDetails: InnerType could not be acquired,  %s", TypeNamespace)
            return propEntry

        # traverse tags to find the type
        typeRefs = getReferenceDetails(typeSoup, refs)
        typeSchema = typeSoup.find(  # BS4 line
            'schema', attrs={'namespace': TypeNamespace})
        typeTag = typeSchema.find(  # BS4 line
            ['enumtype', 'complextype', 'entitytype', 'typedefinition'], attrs={'name': TypeSpec}, recursive=False)

        # perform more logic for each type
        if typeTag.name == 'typedefinition':
            propType = typeTag.get('underlyingtype')
            # This piece of code is rather simple UNLESS this is an "enumeration"
            #   this is a unique deprecated enum, labeled as Edm.String
            isEnum = typeTag.find(  # BS4 line
                'annotation', attrs={'term': 'Redfish.Enumeration'}, recursive=False)
            if propType == 'Edm.String' and isEnum is not None:
                propEntry['realtype'] = 'deprecatedEnum'
                propEntry['typeprops'] = list()
                memberList = isEnum.find(  # BS4 line
                    'collection').find_all('propertyvalue')  # BS4 line

                for member in memberList:
                    propEntry['typeprops'].append(member.get('string'))
                traverseLogger.debug("%s", str(propEntry['typeprops']))  # Printout FORMAT
                break
            else:
                continue

        elif typeTag.name == 'complextype':
            traverseLogger.debug("go deeper in type")  # Printout FORMAT
            # We need to find the highest existence of this type vs topVersion schema
            # not ideal, but works for this solution
            success, baseSoup, baseRefs, baseType = True, typeSoup, typeRefs, propType
            if topVersion is not None and topVersion != SchemaNamespace:
                currentVersion = topVersion
                currentSchema = baseSoup.find(  # BS4 line
                    'schema', attrs={'namespace': currentVersion})
                # Working backwards from topVersion schematag,
                #   created expectedType, check if currentTypeTag exists
                #   if it does, use our new expectedType, else continue down parent types
                #   until we exhaust all schematags in file
                while currentSchema is not None:
                    expectedType = currentVersion + '.' + getType(propType)
                    currentTypeTag = currentSchema.find(  # BS4 line
                        'complextype', attrs={'name': getType(propType)})
                    if currentTypeTag is not None:
                        baseType = expectedType
                        traverseLogger.debug('new type: ' + baseType)  # Printout FORMAT
                        break
                    else:
                        nextEntity = currentSchema.find(  # BS4 line
                            'entitytype', attrs={'name': SchemaType})
                        nextType = nextEntity.get('basetype')
                        currentVersion = getNamespace(nextType)
                        currentSchema = baseSoup.find(  # BS4 line
                            'schema', attrs={'namespace': currentVersion})
                        continue
            propEntry['realtype'] = 'complex'
            propEntry['typeprops'] = PropType(
                baseType, baseSoup, baseRefs, 'complextype')
            break

        elif typeTag.name == 'enumtype':
            # If enum, get all members
            propEntry['realtype'] = 'enum'
            propEntry['typeprops'] = list()
            for MemberName in typeTag.find_all('member'):  # BS4 line
                propEntry['typeprops'].append(MemberName['name'])
            break

        elif typeTag.name == 'entitytype':
            # If entity, do nothing special (it's a reference link)
            propEntry['realtype'] = 'entity'
            propEntry['typeprops'] = dict()
            traverseLogger.debug("typeEntityTag found %s", propTag['name'])  # Printout FORMAT
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
                    cType = propDict['attrs'].get('type')
                    cSchema = refDict.get(getNamespace(cType), (None, None))[1]
                    if cSchema is None:
                        cSchema = context
                    linkList[prefix + str(item) + '.' + getType(propDict['attrs']['name'])] = (
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
            annotationRefs = getReferenceDetails(annotationSoup, refs)
            if isinstance(decoded[key], dict) and decoded[key].get('@odata.type') is not None:
                payloadType = decoded[key].get('@odata.type').replace('#', '')
                realType, refLink = annotationRefs.get(getNamespace(payloadType).split('.')[0], (None, None))
                success, annotationSoup, uri = getSchemaDetails(realType, refLink)
                realItem = payloadType
                tagtype = 'complextype'
            else:
                realItem = realType + '.' + fullItem.split('.', 1)[1]
                tagtype = 'term'
            additionalProps.append(
                PropItem(annotationSoup, annotationRefs, realItem, key, tagtype, None))

    return True, additionalProps
