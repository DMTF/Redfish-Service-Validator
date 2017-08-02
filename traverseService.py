
# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link:
# https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from bs4 import BeautifulSoup
import bs4
import configparser
import requests
import sys
import re
from collections import OrderedDict
from functools import lru_cache
import logging
from distutils.version import LooseVersion
from datetime import datetime, timedelta
from rfSession import rfSession

expectedVersion = '4.5.3'


def versionCheck(actual, target):
    if not LooseVersion(actual) <= LooseVersion(target):
        raise RuntimeError("Your version of bs4 is not <= {}, please install the appropriate library".format(expectedVersion))
    return True


traverseLogger = logging.getLogger(__name__)
traverseLogger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
traverseLogger.addHandler(ch)
config = configparser.ConfigParser()
config['DEFAULT'] = {'LogPath': './logs', 'SchemaSuffix': '_v1.xml', 'timeout': 30, 'AuthType': 'Basic'}
config['internal'] = {'configSet': '0'}
commonHeader = {'OData-Version': '4.0'}
SchemaSuffix = UseSSL = ConfigURI = User = Passwd = SysDescription = SchemaLocation\
        = ChkCert = LocalOnly = AuthType = ServiceOnly = timeout = LogPath = None

currentSession = rfSession()


def getLogger():
    """
    Grab logger for tools that might use this lib
    """
    return traverseLogger


def setConfigNamespace(args):
    """
    Provided a namespace, modify args based on it
    """
    global SchemaSuffix, UseSSL, ConfigURI, User, Passwd, SysDescription, SchemaLocation,\
        ChkCert, LocalOnly, ServiceOnly, timeout, LogPath, AuthType
    User = args.user
    Passwd = args.passwd
    AuthType = args.authtype
    SysDescription = args.desc
    SchemaLocation = args.dir
    timeout = args.timeout
    ChkCert = not args.nochkcert
    UseSSL = not args.nossl
    LogPath = args.logdir
    ConfigURI = ('https' if UseSSL else 'http') + '://' + \
        args.ip
    LocalOnly = args.localonly
    ServiceOnly = args.service
    SchemaSuffix = args.suffix

    versionCheck(bs4.__version__, expectedVersion)

    if AuthType == 'Session':
        currentSession.startSession(User, Passwd, ConfigURI, ChkCert)

    config['internal']['configSet'] = '1'


def setConfig(filename):
    """
    Set config based on config file read from location filename
    """
    global SchemaSuffix, UseSSL, ConfigURI, User, Passwd, SysDescription, SchemaLocation,\
        ChkCert, LocalOnly, ServiceOnly, timeout, LogPath, AuthType
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
    SchemaSuffix = config.get('Options', 'SchemaSuffix')
    timeout = config.getint('Options', 'timeout')
    LocalOnly = config.getboolean('Options', 'LocalOnlyMode')
    ServiceOnly = config.getboolean('Options', 'ServiceMode')

    versionCheck(bs4.__version__, expectedVersion)

    if AuthType == 'Session':
        currentSession.startSession(User, Passwd, ConfigURI, ChkCert)

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
            traverseLogger.debug('dont chkauth')
            auth = None
        else:
            auth = (User, Passwd)

    if nonService and ServiceOnly:
        traverseLogger.debug('Disallowed out of service URI')
        return False, None, -1, 0

    # rs-assertion: do not send auth over http
    if not UseSSL or nonService or AuthType != 'Basic':
        auth = None

    if UseSSL and not nonService and AuthType == 'Session' and not noauthchk:
        headers = {"X-Auth-Token": currentSession.getSessionKey()}
        headers.update(commonHeader)
    else:
        headers = commonHeader

    # rs-assertion: must have application/json or application/xml
    traverseLogger.debug('callingResourceURI: %s', URILink)
    try:
        response = requests.get(ConfigURI + URILink if not nonService else URILink,
                                headers=headers, auth=auth, verify=ChkCert, timeout=timeout)
        expCode = [200]
        elapsed = response.elapsed.total_seconds()
        statusCode = response.status_code
        traverseLogger.debug('%s, %s, %s,\nTIME ELAPSED: %s', statusCode,
                             expCode, response.headers, elapsed)
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
                            URILink + " decoded object no longer a dictionary")
            else:
                decoded = response.text
            return decoded is not None, decoded, statusCode, elapsed
    except Exception as ex:
        traverseLogger.exception("Something went wrong")
    return False, None, statusCode, elapsed


# note: Use some sort of re expression to parse SchemaAlias
# ex: #Power.1.1.1.Power , #Power.v1_0_0.Power
def getNamespace(string):
    return string.replace('#', '').rsplit('.', 1)[0]


def getType(string):
    return string.replace('#', '').rsplit('.', 1)[-1]


@lru_cache(maxsize=64)
def getSchemaDetails(SchemaAlias, SchemaURI):
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
        success, data, status, elapsed = callResourceURI(SchemaURI)
        # if success, generate Soup, then check for frags to parse
        #   start by parsing references, then check for the refLink
        if success:
            soup = BeautifulSoup(data, "html.parser")
            if '#' in SchemaURI:
                SchemaURI, frag = tuple(SchemaURI.rsplit('#', 1))
                refType, refLink = getReferenceDetails(
                    soup).get(getNamespace(frag), (None, None))
                if refLink is not None:
                    success, linksoup, newlink = getSchemaDetails(refType, refLink)
                    if success:
                        return True, linksoup, newlink
                    else:
                        traverseLogger.error(
                            "SchemaURI couldn't call reference link: %s %s", SchemaURI, frag)
                else:
                    traverseLogger.error(
                        "SchemaURI missing reference link: %s %s", SchemaURI, frag)
            else:
                return True, soup, SchemaURI
        if isNonService(SchemaURI) and ServiceOnly:
            traverseLogger.info("Nonservice URI skipped " + SchemaURI)
        else:
            traverseLogger.debug("SchemaURI unsuccessful: %s", SchemaURI)
    return getSchemaDetailsLocal(SchemaAlias, SchemaURI)


def getSchemaDetailsLocal(SchemaAlias, SchemaURI):
    # Use local if no URI or LocalOnly
    if SchemaURI is not None:
        uriparse = SchemaURI.split('/')[-1].split('#')
        xml = uriparse[0]
    else:        
        return getSchemaDetailsLocal(SchemaAlias, SchemaAlias + SchemaSuffix)
    Alias = getNamespace(SchemaAlias)
    traverseLogger.debug((SchemaAlias, SchemaURI, SchemaLocation + '/' + xml))
    try:
        filehandle = open(SchemaLocation + '/' + xml, "r")
        filedata = filehandle.read()
        filehandle.close()
        soup = BeautifulSoup(filedata, "html.parser")
        edmxTag = soup.find('edmx:edmx', recursive=False)
        parentTag = edmxTag.find('edmx:dataservices', recursive=False)
        child = parentTag.find('schema', recursive=False)
        SchemaNamespace = child['namespace']
        FoundAlias = SchemaNamespace.split(".")[0]
        traverseLogger.debug(FoundAlias)
        if '/redfish/v1/$metadata' in SchemaURI:
            if len(uriparse) > 1:
                frag = uriparse[1]
                refType, refLink = getReferenceDetails(
                    soup).get(getNamespace(frag), (None, None))
                if refLink is not None:
                    return getSchemaDetailsLocal(refType, refLink)
                else:
                    traverseLogger.error('Could not find item in $metadata {}'.format(frag))
                    return False, None, None
            else:
                return True, soup, "local" + SchemaLocation + '/' + Alias
        if FoundAlias in Alias:
            return True, soup, "local" + SchemaLocation + '/' + Alias
    except FileNotFoundError as ex:
        if '/redfish/v1/$metadata' in SchemaURI:
            return getSchemaDetailsLocal(SchemaAlias, SchemaAlias + SchemaSuffix)
        else:
            traverseLogger.error(
                "File not found in {} for {}: ".format(SchemaLocation, Alias))
    except Exception as ex:
        traverseLogger.exception("Something went wrong")
    return False, None, None


def getReferenceDetails(soup, metadata_dict=None):
    """
    Create a reference dictionary from a soup file

    param arg1: soup
    param metadata_dict: dictionary of service metadata, compare with
    return: dictionary
    """
    refDict = {}
    maintag = soup.find('edmx:edmx', recursive=False)
    refs = maintag.find_all('edmx:reference', recursive=False)
    for ref in refs:
        includes = ref.find_all('edmx:include', recursive=False)
        for item in includes:
            if item.get('namespace') is None or ref.get('uri') is None:
                traverseLogger.error("Reference incorrect for: ", item)
                continue
            traverseLogger.debug("Reference {} as {}, {}".format(
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
            propSchema = soup.find('schema')
            nameOfSchema = propSchema.get('namespace', '?')
            diff_keys = [key for key in refDict if key not in metadata_dict]
            traverseLogger.log(
                    logging.ERROR if ServiceOnly else logging.WARN,
                    "Reference in a Schema containing {} not in metadata, this may not be compatible with ServiceMode".format(nameOfSchema))
            traverseLogger.log(
                    logging.ERROR if ServiceOnly else logging.WARN,
                    "References missing in metadata: {}".format(str(diff_keys)))
    return refDict


def getParentType(soup, refs, currentType, tagType='entitytype'):
    """
    Get parent type of given type.

    param arg1: soup
    param arg2: refs
    param arg3: current type
    param tagType: the type of tag for inheritance, default 'entitytype'
    return: success, associated soup, associated ref, new type
    """
    pnamespace, ptype = getNamespace(currentType), getType(currentType)

    propSchema = soup.find(
        'schema', attrs={'namespace': pnamespace})

    if propSchema is None:
        return False, None, None, None

    propEntity = propSchema.find(tagType, attrs={'name': ptype}, recursive=False)

    if propEntity is None:
        return False, None, None, None

    currentType = propEntity.get('basetype')

    if currentType is None:
        return False, None, None, None

    currentType = currentType.replace('#', '')
    SchemaNamespace, SchemaType = getNamespace(
        currentType), getType(currentType)
    propSchema = soup.find('schema', attrs={'namespace': SchemaNamespace})

    if propSchema is None:
        success, innerSoup, uri = getSchemaDetails(
            *refs.get(SchemaNamespace, (None, None)))
        if not success:
            return False, None, None, None
        innerRefs = getReferenceDetails(innerSoup, refs)
        propSchema = innerSoup.find(
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
            traverseLogger.debug('%s, %s, %s', success, self.jsondata, status)
            if not success:
                traverseLogger.error(
                    '%s:  URI could not be acquired: %s' % (self.uri, status))
                return
        else:
            self.jsondata = expectedJson

        # Check if we provide a type besides json's
        if expectedType is None:
            fullType = self.jsondata.get('@odata.type')
            if fullType is None:
                traverseLogger.error(
                    str(self.uri) + ':  Json does not contain @odata.type',)
                return
        else:
            fullType = self.jsondata.get('@odata.type', expectedType)

        # Provide a context for this
        if expectedSchema is None:
            self.context = self.jsondata.get('@odata.context')
            expectedSchema = self.context
            if expectedSchema is None:
                traverseLogger.error(
                    str(self.uri) + ':  Json does not contain @odata.context',)
                return
        else:
            self.context = expectedSchema

        success, typesoup, self.context = getSchemaDetails(
            fullType, SchemaURI=self.context)

        if not success:
            traverseLogger.error("validateURI: No schema XML for " + fullType)
            return

        # Use string comprehension to get highest type
        if fullType is expectedType:
            typelist = list()
            schlist = list()
            for schema in typesoup.find_all('schema'):
                newNamespace = schema.get('namespace')
                typelist.append(newNamespace)
                schlist.append(schema)
            for item, schema in reversed(sorted(zip(typelist, schlist))):
                traverseLogger.debug(
                    item + ' ' + str('') + ' ' + getType(fullType))
                if schema.find('entitytype', attrs={'name': getType(fullType)}, recursive=False):
                    fullType = item + '.' + getType(fullType)
                    break
            traverseLogger.warn(
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
    def __init__(self, soup, refs, name, tagType, topVersion):
        try:
            self.name = name
            self.propDict = getPropertyDetails(
                soup, refs, name, tagType, topVersion)
            self.attr = self.propDict['attrs']
        except Exception as ex:
            traverseLogger.exception("Something went wrong")
            traverseLogger.error(
                '%s:  Could not get details on this property' % name)
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
                ':  Getting type failed for ' + str(self.fulltype) + " " + str(baseType))
            return


def getTypeDetails(soup, refs, SchemaAlias, tagType, topVersion=None):
    """
    Gets list of surface level properties for a given SchemaAlias,

    param arg1: soup
    param arg2: references
    param arg3: SchemaAlias string
    param arg4: tag of Type, which can be EntityType or ComplexType...
    return: list of (soup, ref, string PropertyName, tagType)
    """
    PropertyList = list()
    additional = False

    SchemaNamespace, SchemaType = getNamespace(
        SchemaAlias), getType(SchemaAlias)

    traverseLogger.debug("Schema is %s, %s, %s", SchemaAlias,
                         SchemaType, SchemaNamespace)

    innerschema = soup.find('schema', attrs={'namespace': SchemaNamespace})

    if innerschema is None:
        traverseLogger.error("Got XML, but schema still doesn't exist...? %s, %s" %
                             (getNamespace(SchemaAlias), SchemaAlias))
        raise Exception('exceptionType: Was not able to get type, is Schema in XML? ' +
                        str(refs.get(getNamespace(SchemaAlias), (getNamespace(SchemaAlias), None))))

    element = innerschema.find(tagType, attrs={'name': SchemaType}, recursive=False)
    traverseLogger.debug("___")
    traverseLogger.debug(element['name'])
    traverseLogger.debug(element.attrs)
    traverseLogger.debug(element.get('basetype'))

    usableProperties = element.find_all(['navigationproperty', 'property'], recursive=False)
    additionalElement = element.find(
        'annotation', attrs={'term': 'OData.AdditionalProperties'})
    if additionalElement is not None:
        additional = additionalElement.get('bool', False)
    else:
        additional = False

    for innerelement in usableProperties:
        traverseLogger.debug(innerelement['name'])
        traverseLogger.debug(innerelement.get('type'))
        traverseLogger.debug(innerelement.attrs)
        newProp = innerelement['name']
        traverseLogger.debug("ADDING :::: %s", newProp)
        if SchemaAlias:
            newProp = SchemaAlias + ':' + newProp
        if newProp not in PropertyList:
            PropertyList.append(
                PropItem(soup, refs, newProp, tagType=tagType, topVersion=topVersion))

    return additional, PropertyList


def getPropertyDetails(soup, refs, PropertyItem, tagType='entitytype', topVersion=None):
    """
    Get dictionary of tag attributes for properties given, including basetypes.

    param arg1: soup data
    param arg2: references
    param arg3: a property string
    """

    propEntry = dict()

    propOwner, propChild = PropertyItem.split(
        ':')[0].replace('#', ''), PropertyItem.split(':')[-1]
    SchemaNamespace, SchemaType = getNamespace(propOwner), getType(propOwner)
    traverseLogger.debug('___')
    traverseLogger.debug('%s, %s', SchemaNamespace, PropertyItem)

    propSchema = soup.find('schema', attrs={'namespace': SchemaNamespace})
    if propSchema is None:
        traverseLogger.error(
            "getPropertyDetails: Schema could not be acquired,  %s", SchemaNamespace)
        return None
    else:
        innerSoup = soup
        innerRefs = refs

    # get type tag and tag of property in type
    propEntity = propSchema.find(tagType, attrs={'name': SchemaType}, recursive=False)
    propTag = propEntity.find(['navigationproperty', 'property'], attrs={'name': propChild}, recursive=False)

    # check if this property is a nav property
    # Checks if this prop is an annotation
    success, typeSoup, typeRefs, propType = getParentType(
        innerSoup, innerRefs, SchemaType, tagType)
    if '@' not in propChild:
        propEntry['isTerm'] = False
        # start adding attrs and props together
        propAll = propTag.find_all()
        for tag in propAll:
            propEntry[tag['term']] = tag.attrs
        propType = propTag.get('type')
    else:
        propEntry['isTerm'] = True
        propTag = propEntity
        propType = propTag.get('type', propOwner)

    propEntry['isNav'] = propTag.name == 'navigationproperty'
    propEntry['attrs'] = propTag.attrs
    traverseLogger.debug(propEntry)

    propEntry['realtype'] = 'none'

    # find the real type of this, by inheritance
    while propType is not None:
        traverseLogger.debug("HASTYPE")
        TypeNamespace, TypeSpec = getNamespace(propType), getType(propType)

        traverseLogger.debug('%s, %s', TypeNamespace, propType)
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
            traverseLogger.error(
                "getPropertyDetails: InnerType could not be acquired,  %s", TypeNamespace)
            return propEntry

        # traverse tags to find the type
        typeRefs = getReferenceDetails(typeSoup, refs)
        typeSchema = typeSoup.find(
            'schema', attrs={'namespace': TypeNamespace})
        typeTag = typeSchema.find(
            ['enumtype', 'complextype', 'entitytype', 'typedefinition'], attrs={'name': TypeSpec}, recursive=False)

        # perform more logic for each type
        if typeTag.name == 'typedefinition':
            propType = typeTag.get('underlyingtype')
            # This piece of code is rather simple UNLESS this is an "enumeration"
            #   this is a unique deprecated enum, labeled as Edm.String
            isEnum = typeTag.find(
                'annotation', attrs={'term': 'Redfish.Enumeration'}, recursive=False)
            if propType == 'Edm.String' and isEnum is not None:
                propEntry['realtype'] = 'deprecatedEnum'
                propEntry['typeprops'] = list()
                memberList = isEnum.find(
                    'collection').find_all('propertyvalue')

                for member in memberList:
                    propEntry['typeprops'].append(member.get('string'))
                traverseLogger.debug("%s", str(propEntry['typeprops']))
                break
            else:
                continue

        elif typeTag.name == 'complextype':
            traverseLogger.debug("go deeper in type")
            # We need to find the highest existence of this type vs topVersion schema
            # not ideal, but works for this solution
            success, baseSoup, baseRefs, baseType = True, typeSoup, typeRefs, propType
            if topVersion is not None and topVersion != SchemaNamespace:
                currentVersion = topVersion
                currentSchema = baseSoup.find(
                    'schema', attrs={'namespace': currentVersion})
                # Working backwards from topVersion schematag,
                #   created expectedType, check if currentTypeTag exists
                #   if it does, use our new expectedType, else continue down parent types
                #   until we exhaust all schematags in file
                while currentSchema is not None:
                    expectedType = currentVersion + '.' + getType(propType)
                    currentTypeTag = currentSchema.find(
                        'complextype', attrs={'name': getType(propType)})
                    if currentTypeTag is not None:
                        baseType = expectedType
                        traverseLogger.debug('new type: ' + baseType)
                        break
                    else:
                        nextEntity = currentSchema.find(
                            'entitytype', attrs={'name': SchemaType})
                        nextType = nextEntity.get('basetype')
                        currentVersion = getNamespace(nextType)
                        currentSchema = baseSoup.find(
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
            for MemberName in typeTag.find_all('member'):
                propEntry['typeprops'].append(MemberName['name'])
            break

        elif typeTag.name == 'entitytype':
            # If entity, do nothing special (it's a reference link)
            propEntry['realtype'] = 'entity'
            propEntry['typeprops'] = dict()
            traverseLogger.debug("typeEntityTag found %s", propTag['name'])
            break

        else:
            traverseLogger.error("type doesn't exist? %s", propType)
            raise Exception(
                "getPropertyDetails: problem grabbing type: " + propType)
            break

    return propEntry


def getAllLinks(jsonData, propList, refDict, prefix='', context=''):
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
    traverseLogger.debug(str(linkList))
    return linkList


def getAnnotations(soup, refs, decoded, prefix=''):
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
        traverseLogger.debug('%s, %s, %s, %s, %s', str(
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
                PropItem(annotationSoup, annotationRefs, realItem + ':' + key, tagtype, None))

    return True, additionalProps
