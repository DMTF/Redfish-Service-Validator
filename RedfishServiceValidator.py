# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link:
# https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from bs4 import BeautifulSoup
import configparser
import requests
import re
import os
import sys
from datetime import datetime
from collections import Counter, OrderedDict
from functools import lru_cache
import logging
import traceback

# Logging config
startTick = datetime.now()
fmt = logging.Formatter('%(levelname)s - %(message)s')

if not os.path.isdir('logs'):
       os.makedirs('logs')

rsvLogger = logging.getLogger()
rsvLogger.setLevel(logging.DEBUG)

fh = logging.FileHandler(datetime.strftime(startTick, "logs/ComplianceLog_%m_%d_%Y_%H%M%S.txt"))
fh.setLevel(logging.DEBUG)
fh.setFormatter(fmt)
rsvLogger.addHandler(fh)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
rsvLogger.addHandler(ch)

errh = logging.StreamHandler(sys.stderr)
errh.setLevel(logging.ERROR)
rsvLogger.addHandler(errh)

# Read config info from ini file placed in config folder of tool
config = configparser.ConfigParser()
config.read(os.path.join('.', 'config', 'config.ini'))
useSSL = config.getboolean('Options', 'UseSSL')
ConfigURI = ('https' if useSSL else 'http') + '://' + \
    config.get('SystemInformation', 'TargetIP')
User = config.get('SystemInformation', 'UserName')
Passwd = config.get('SystemInformation', 'Password')
SchemaLocation = config.get('Options', 'MetadataFilePath')
chkCert = config.getboolean('Options', 'CertificateCheck') and useSSL
localOnly = config.getboolean('Options', 'LocalOnlyMode')

rsvLogger.info("RedfishServiceValidator Config details: %s", str(
    (useSSL, ConfigURI, User, SchemaLocation, chkCert, localOnly)))

@lru_cache(maxsize=64)
def callResourceURI(URILink):
    """
    Makes a call to a given URI or URL

    param arg1: path to URI "/example/1", or URL "http://example.com"
    return: (success boolean, data)
    """
    
    # rs-assertions: 6.4.1, including accept, content-type and odata-versions
    # rs-assertion: URIs and URLs
    # rs-assertion: clients cannot make assumptions about URIs
    # rs-assertion: handle redirects?  and target permissions
    nonService = 'http' in URILink[:8]

    # rs-assertion: uris may contain '?' queries and '#' frags
    # what about $metadata?  frags are for clients...
    URILink = URILink.replace("#", "%23")
    statusCode = ''

    # rs-assertion: require no auth for serviceroot calls
    if not nonService:
        # feel free to make this into a regex
        noauthchk = \
            ('/redfish' in URILink and '/redfish/v1' not in URILink) or\
            URILink in ['/redfish/v1', '/redfish/v1/', '/redfish/v1/odata', 'redfish/v1/odata/'] or\
            '/redfish/v1/$metadata' in URILink
        if noauthchk:
            rsvLogger.debug('dont chkauth')
            auth = None
        else:
            auth = (User, Passwd)

    # rs-assertion: do not send auth over http
    if not useSSL or nonService:
        auth = None
    
    # suppress logging from requests
    # rs-assertion: must have application/json or application/xml
    rsvLogger.debug('callingResourceURI: %s', URILink)
    try:
        response = requests.get(ConfigURI + URILink if not nonService else URILink,
                                auth=auth, verify=chkCert)
        expCode = [200]
        statusCode = response.status_code
        rsvLogger.debug('%s, %s, %s', statusCode, expCode, response.headers)
        if statusCode in expCode:
            contenttype = response.headers.get('content-type')
            if contenttype is not None and 'application/json' in contenttype:
                decoded = response.json(object_pairs_hook=OrderedDict)
            else:
                decoded = response.text
            return True, decoded, statusCode
    except Exception as ex:
        rsvLogger.error("Something went wrong: %s", str(ex))
        rsvLogger.error(traceback.format_exc())
    return False, None, statusCode

# note: Use some sort of re expression to parse SchemaAlias
# ex: #Power.1.1.1.Power , #Power.v1_0_0.Power

def getNamespace(string):
    ret = string.replace('#', '').rsplit('.', 1)[0]
    return ret
def getType(string):
    return string.replace('#', '').rsplit('.', 1)[-1]

def getSchemaDetails(SchemaAlias, SchemaURI=None):
    """
    Find Schema file for given Namespace.

    param arg1: Schema Namespace, such as ServiceRoot
    param SchemaURI: uri to grab schema, given localOnly is False
    return: (success boolean, a Soup object)
    """
    if SchemaURI is not None and not localOnly:
        success, data, status = callResourceURI(SchemaURI)
        if success:
            soup = BeautifulSoup(data, "html.parser")
            return True, soup
        rsvLogger.debug("Fallback to local Schema")

    Alias = getNamespace(SchemaAlias).split('.')[0]
    try:
        filehandle = open(SchemaLocation + '/' + Alias + '_v1.xml', "r")
        filedata = filehandle.read()
        filehandle.close()
        soup = BeautifulSoup(filedata, "html.parser")
        parentTag = soup.find('edmx:dataservices')
        child = parentTag.find('schema')
        SchemaNamespace = child['namespace']
        FoundAlias = SchemaNamespace.split(".")[0]
        if FoundAlias == Alias:
            return True, soup
    except Exception as ex:
        rsvLogger.error("Something went wrong: %s", str(ex))
        rsvLogger.error(traceback.format_exc())
    return False, None


def getReferenceDetails(soup):
    """
    Create a reference dictionary from a soup file

    param arg1: soup
    return: dictionary
    """
    refDict = {}
    refs = soup.find_all('edmx:reference')
    for ref in refs:
        includes = ref.find_all('edmx:include')
        for item in includes:
            if item.get('namespace') is None or ref.get('uri') is None:
                rsvLogger.error("Reference incorrect for: ", item)
                continue
            if item.get('alias') is not None:
                refDict[item['alias']] = (item['namespace'], ref['uri'])
            else:
                refDict[item['namespace']] = (item['namespace'], ref['uri'])
                refDict[item['namespace'].split('.')[0]] = (
                    item['namespace'], ref['uri'])
    return refDict


# Function to search for all Property attributes in any target schema
# Schema XML may be the initial file for local properties or referenced
# schema for foreign properties
def getTypeDetails(soup, refs, SchemaAlias, tagType):
    """
    Gets list of surface level properties for a given SchemaAlias,
    including base type inheritance.

    param arg1: soup
    param arg2: references
    param arg3: SchemaAlias string
    param arg4: tag of Type, which can be EntityType or ComplexType...
    return: list of properties as strings
    """
    PropertyList = list()

    SchemaType = getType(SchemaAlias)
    SchemaNamespace = getNamespace(SchemaAlias)

    rsvLogger.debug("Schema is %s, %s, %s", SchemaAlias,
                    SchemaType, SchemaNamespace)

    innerschema = soup.find('schema', attrs={'namespace': SchemaNamespace})

    if innerschema is None:
        Alias = SchemaAlias.split('.')[0] # why only get this part?
        rsvLogger.debug(refs.get(Alias))
        success, soup = getSchemaDetails(
            *refs.get(getNamespace(Alias), (getNamespace(Alias), None)))
        if not success:
            rsvLogger.error("xml for schema doesn't exist...? %s, %s",
                            getNamespace(SchemaAlias), Alias)
            raise Exception('exceptionType: Was not able to get XML... check if it exists locally or as: ' + refs.get(getNamespace(Alias), (getNamespace(Alias), None)))
        refs = getReferenceDetails(soup)
        innerschema = soup.find('schema', attrs={'namespace': SchemaNamespace})
        if innerschema is None:
            rsvLogger.error("Got XML, but schema still doesn't exist...? %s, %s",
                            getNamespace(SchemaAlias), Alias)
            raise Exception('exceptionType: Was not able to get types, is Schema in XML? '  + refs.get(getNamespace(Alias), (getNamespace(Alias), None)))

    for element in innerschema.find_all(tagType, attrs={'name': SchemaType}):
        rsvLogger.debug("___")
        rsvLogger.debug(element['name'])
        rsvLogger.debug(element.attrs)
        rsvLogger.debug(element.get('basetype'))
        # note: Factor in navigationproperties
        #       what about EntityContainers?
        usableProperties = element.find_all('property')
        usableNavProperties = element.find_all('navigationproperty')
        baseType = element.get('basetype')

        if baseType is not None:
            PropertyList.extend(getTypeDetails(soup, refs, baseType, tagType))

        for innerelement in usableProperties + usableNavProperties:
            rsvLogger.debug(innerelement['name'])
            rsvLogger.debug(innerelement['type'])
            rsvLogger.debug(innerelement.attrs)
            newProp = innerelement['name']
            if SchemaAlias:
                newProp = SchemaAlias + ':' + newProp
            rsvLogger.debug("ADDING :::: %s", newProp)
            if newProp not in PropertyList:
                PropertyList.append(newProp)

    return PropertyList

# Function to retrieve the detailed Property attributes and store in a dictionary format
# The attributes for each property are referenced through various other
# methods for compliance check

def getPropertyDetails(soup, refs, PropertyItem, tagType='entitytype'):
    """
    Get dictionary of tag attributes for properties given, including basetypes.

    param arg1: soup data
    param arg2: references
    param arg3: a property string
    param tagtype: type of Tag, such as EntityType or ComplexType
    """
    propEntry = dict()

    propOwner, propChild = PropertyItem.split(
        ':')[0], PropertyItem.split(':')[-1]

    SchemaNamespace = getNamespace(propOwner)
    SchemaType = getType(propOwner)

    rsvLogger.debug('___')
    rsvLogger.debug('%s, %s', SchemaNamespace, PropertyItem)

    propSchema = soup.find('schema', attrs={'namespace': SchemaNamespace})
    
    # get another csdl xml if the given namespace does not exist
    if propSchema is None:
        success, innerSoup = getSchemaDetails(
            *refs[SchemaNamespace.split('.')[0]])
        if not success:
            rsvLogger.error("innerSoup doesn't exist...? %s", SchemaNamespace)
            raise Exception('getPropertyDetails: no such xml at ' + refs[SchemaNamespace.split('.')[0]])
        innerRefs = getReferenceDetails(innerSoup)
        propSchema = innerSoup.find(
            'schema', attrs={'namespace': SchemaNamespace})
        if propSchema is None:
            rsvLogger.error("innerSoup doesn't exist...? %s", SchemaNamespace)
            raise Exception('getPropertyDetails: no such schema at ' + refs[SchemaNamespace.split('.')[0]])
    else:
        innerSoup = soup
        innerRefs = refs

    # get type tag and tag of property in type
    propEntity = propSchema.find(tagType, attrs={'name': SchemaType})
    propTag = propEntity.find('property', attrs={'name': propChild})

    # check if this property is a nav property
    propEntry['isNav'] = False

    if propTag is None:
        propTag = propEntity.find(
            'navigationproperty', attrs={'name': propChild})
        propEntry['isNav'] = True

    # start adding attrs and props together
    propAll = propTag.find_all()
    propEntry['attrs'] = propTag.attrs

    for tag in propAll:
        propEntry[tag['term']] = tag.attrs
    rsvLogger.debug(propEntry)

    propType = propTag.get('type')

    # find the real type of this, by inheritance
    while propType is not None:
        rsvLogger.debug("HASTYPE")
        TypeNamespace = getNamespace(propType)
        typeSpec = getType(propType)

        rsvLogger.debug('%s, %s', TypeNamespace, propType)
        # Type='Collection(Edm.String)'
        # If collection, check its inside type
        if re.match('Collection(.*)', propType) is not None:
            propType = propType.replace('Collection(', "")
            propType = propType.replace(')', "")
            propEntry['isCollection'] = propType
            continue
        if 'Edm' in propType:
            propEntry['realtype'] = propType
            break
        
        # Check if type exist in this schema xml, else get new xml
        if TypeNamespace.split('.')[0] != SchemaNamespace.split('.')[0]:
            success, typeSoup = getSchemaDetails(*refs[TypeNamespace])
        else:
            success, typeSoup = True, innerSoup

        if not success:
            rsvLogger.error("innerSoup doesn't exist...? %s", SchemaNamespace)
            raise Exception("getPropertyDetails: no such soup for" +
                            SchemaNamespace + TypeNamespace)

        # traverse tags to find the type
        typeRefs = getReferenceDetails(typeSoup)
        typeSchema = typeSoup.find(
            'schema', attrs={'namespace': TypeNamespace})
        typeSimpleTag = typeSchema.find(
            'typedefinition', attrs={'name': typeSpec})
        typeComplexTag = typeSchema.find(
            'complextype', attrs={'name': typeSpec})
        typeEnumTag = typeSchema.find('enumtype', attrs={'name': typeSpec})
        typeEntityTag = typeSchema.find('entitytype', attrs={'name': typeSpec})

        # perform more logic for each type
        if typeSimpleTag is not None:
            propType = typeSimpleTag.get('underlyingtype')
            continue
        elif typeComplexTag is not None:
            rsvLogger.debug("go DEEP")
            propList = getTypeDetails(
                typeSoup, typeRefs, propType, tagType='complextype')
            rsvLogger.debug(propList)
            propDict = {item: getPropertyDetails(
                typeSoup, typeRefs, item, tagType='complextype') for item in propList}
            rsvLogger.debug(propDict)
            propEntry['realtype'] = 'complex'
            propEntry['typeprops'] = propDict
            break
        elif typeEnumTag is not None:
            propEntry['realtype'] = 'enum'
            propEntry['typeprops'] = list()
            for MemberName in typeEnumTag.find_all('member'):
                propEntry['typeprops'].append(MemberName['name'].lower())
            break
        elif typeEntityTag is not None:
            propEntry['realtype'] = 'entity'
            propEntry['typeprops'] = dict()
            rsvLogger.debug("typeEntityTag found %s", propTag['name'])
            break
        else:
            rsvLogger.error("type doesn't exist? %s", propType)
            raise Exception("getPropertyDetails: problem grabbing type: " + propType)
            break

    return propEntry


# Function to check compliance of individual Properties based on the
# attributes retrieved from the schema xml
def checkPropertyCompliance(PropertyName, PropertyItem, decoded):
    """
    Given a dictionary of properties, check the validitiy of each item, and return a
    list of counted properties

    param arg1: property dictionary
    param arg2: json payload
    """
    def getTypeInheritance(decoded, tagType='entitytype'):
        schType = decoded.get('@odata.type')
        schContext = decoded.get('@odata.context')
        success, sch = getSchemaDetails(schType, schContext)
        if not success:
            return []
        schRefs = getReferenceDetails(sch)
        currentType = schType.replace('#', '')
        allTypes = list()
        while currentType not in allTypes and currentType is not None:
            propSchema = sch.find(
                'schema', attrs={'namespace': getNamespace(currentType)})
            if propSchema is None:
                success, sch = getSchemaDetails(
                    *schRefs[getNamespace(currentType)])
                continue
            propEntity = propSchema.find(
                tagType, attrs={'name': getType(currentType)})
            allTypes.append(currentType)
            if propEntity is None:
                break
            currentType = propEntity.get('basetype')
        return allTypes

    resultList = OrderedDict()
    counts = Counter()

    rsvLogger.info(PropertyName)
    item = PropertyName.split(':')[-1]

    propValue = decoded.get(item, 'xxDoesNotExist')

    rsvLogger.info("\tvalue: %s %s", propValue, type(propValue))

    propAttr = PropertyItem['attrs']

    propType = propAttr.get('type')
    propRealType = PropertyItem.get('realtype')

    rsvLogger.info("\thas Type: %s %s", propType, propRealType)

    propExists = not (propValue == 'xxDoesNotExist')
    propNotNull = propExists and propValue is not '' and propValue is not None and propValue is not 'None'

    # why not actually check oem
    # rs-assertion: 7.4.7.2
    if 'Oem' in PropertyName:
        rsvLogger.info('\tOem is skipped')
        counts['skipOem'] += 1
        return {item: ('-', '-',
                            'Exists' if propExists else 'DNE', 'SkipOEM')}, counts

    propMandatory = False
    propMandatoryPass = True
    if 'Redfish.Required' in PropertyItem:
        propMandatory = True
        propMandatoryPass = True if propExists else False
        rsvLogger.info("\tMandatory Test: %s",
                       'OK' if propMandatoryPass else 'FAIL')
    else:
        rsvLogger.info("\tis Optional")
        if not propExists:
            rsvLogger.info("\tprop Does not exist, skip...")
            counts['skipOptional'] += 1
            return  {item: (propValue, (propType, propRealType),
                                'Exists' if propExists else 'DNE',
                                'SkipOptional')}, counts

    propNullable = propAttr.get('nullable')
    propNullablePass = True

    if propNullable is not None:
        propNullablePass = (
            propNullable == 'true') or not propExists or propNotNull
        rsvLogger.info("\tis Nullable: %s %s", propNullable, propNotNull)
        rsvLogger.info("\tNullability test: %s",
                       'OK' if propNullablePass else 'FAIL')

    # rs-assertion: Check for permission change
    propPermissions = propAttr.get('Odata.Permissions')
    if propPermissions is not None:
        propPermissionsValue = propPermissions['enummember']
        rsvLogger.info("\tpermission %s", propPermissionsValue)

    validPatternAttr = PropertyItem.get(
        'Validation.Pattern')
    validMinAttr = PropertyItem.get('Validation.Minimum')
    validMaxAttr = PropertyItem.get('Validation.Maximum')

    paramPass = True
    propValue = None if propValue == 'xxDoesNotExist' else propValue

    # Note: consider http://docs.oasis-open.org/odata/odata-csdl-xml/v4.01/csprd01/odata-csdl-xml-v4.01-csprd01.html#_Toc472333112
    # Note: make sure it checks each one
    propCollectionType = PropertyItem.get('isCollection')
    if propCollectionType is not None:
        # note: handle collections correctly, this needs a nicer printout
        # rs-assumption: do not assume URIs for collections
        # rs-assumption: check @odata.count property
        # rs-assumption: check @odata.link property
        rsvLogger.info("\tis Collection")
        resultList[item] = ('Collection, size: ' + str(len(propValue)), (propType, propRealType),
                            'Exists' if propExists else 'DNE',
                            '...')
        propValueList = propValue
    else:
        propValueList = [propValue]
    # note: make sure we don't enter this on null values, some of which are
    # OK!
    if propRealType is not None and propExists and propNotNull:
        cnt = 0
        for val in propValueList:
            paramPass = False
            if propRealType == 'Edm.Boolean':
                if str(val).lower() == "true" or str(val).lower() == "false":
                    paramPass = True

            elif propRealType == 'Edm.DateTimeOffset':
                # note: find out why this might be wrong
                match = re.match(
                    '.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])', str(val))
                if match:
                    paramPass = True

            elif propRealType == 'Edm.Int16' or propRealType == 'Edm.Int32' or\
                    propRealType == 'Edm.Int64' or propRealType == 'Edm.Int' or\
                    propRealType == 'Edm.Decimal' or propRealType == 'Edm.Double':
                paramPass = str(val).isnumeric()
                # note: check if val can be string, if it can't this might
                # have trouble
                if 'Int' in propRealType:
                    paramPass = paramPass and '.' not in str(val)
                if validMinAttr is not None:
                    paramPass = paramPass and int(
                        validMinAttr['int']) <= int(val)
                if validMaxAttr is not None:
                    paramPass = paramPass and int(
                        validMaxAttr['int']) >= int(val)

            elif propRealType == 'Edm.Guid':
                match = re.match(
                    "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", str(val))
                if match:
                    paramPass = True

            elif propRealType == 'Edm.String':
                if validPatternAttr is not None:
                    pattern = validPatternAttr.get('string', '')
                    match = re.fullmatch(pattern, val)
                    paramPass = match is not None
                else:
                    paramPass = True

            else:
                if propRealType == 'complex':
                    rsvLogger.info('\t***going into Complex')
                    complexMessages = OrderedDict()
                    complexCounts = Counter()
                    innerPropDict = PropertyItem['typeprops']
                    for prop in innerPropDict:
                        propMessages, propCounts = checkPropertyCompliance(prop, innerPropDict[prop], val)
                        complexMessages.update(propMessages)
                        complexCounts.update(propCounts)
                    rsvLogger.info('\t***out of Complex')
                    rsvLogger.info('complex %s', complexCounts)
                    counts.update(complexCounts)
                    counts['complex'] += 1
                    resultList[item] = ('ComplexDictionary' + (('#' + str(cnt)) if len(propValueList) > 1 else ''), (propType, propRealType),
                                        'Exists' if propExists else 'DNE',
                                        'complex')
                    for complexKey in complexMessages:
                        resultList[item + '.' + complexKey + (('#' + str(cnt)) if len(
                            propValueList) > 1 else '')] = complexMessages[complexKey]
                    continue

                elif propRealType == 'enum':
                    # note: Make sure to check lowercase
                    if val.lower() in PropertyItem['typeprops']:
                        paramPass = True

                elif propRealType == 'entity':
                    success, data, status = callResourceURI(val['@odata.id'])
                    rsvLogger.debug('%s, %s, %s', success, propType, data)
                    if success:
                        paramPass = success

                        listType = getTypeInheritance(data)
                        #paramPass = propType in listType or propCollectionType in listType
                    else:
                        paramPass = '#' in val['@odata.id']
                # Note: Actually check if this is correct

            resultList[item + (('#' + str(cnt)) if len(propValueList) > 1 else '')] = (val, (propType, propRealType),
                                                                                       'Exists' if propExists else 'DNE',
                                                                                       'PASS' if paramPass and propMandatoryPass and propNullablePass else 'FAIL')
            cnt += 1
            if paramPass and propNullablePass and propMandatoryPass:
                counts['pass'] += 1
                rsvLogger.info("\tSuccess")
            else:
                counts[propType] += 1
                if not paramPass:
                    if propMandatory:
                        counts['failMandatoryProp'] += 1
                    else:
                        counts['failProp'] += 1
                elif not propMandatoryPass:
                    counts['failMandatoryExist'] += 1
                elif not propNullablePass:
                    counts['failNull'] += 1
                rsvLogger.info("\tFAIL")

    return resultList, counts

# Function to collect all links in current resource schema


def getAllLinks(jsonData, propDict):
    """
    Function that returns all links provided in a given JSON response.
    This result will include a link to itself.

    :param arg1: json dict
    :param arg2: property dict
    :param linkName: json dict
    :return: list of links
    """
    linkList = OrderedDict()
    # check keys in propertyDictionary
    # if it is a Nav property, check that it exists
    #   if it is not a Nav Collection, add it to list
    #   otherwise, add everything IN Nav collection
    # if it is a Complex property, check that it exists
    #   if it is, recurse on collection or individual item
    for key in propDict:
        item = getType(key).split(':')[-1]
        if propDict[key]['isNav']:
            insideItem = jsonData.get(item)
            if insideItem is not None:
                if propDict[key].get('isCollection') is not None:
                    cnt = 0
                    for listItem in insideItem:
                        linkList[getType(propDict[key]['isCollection']) +
                                 '#' + str(cnt)] = listItem.get('@odata.id')
                        cnt += 1
                else:
                    linkList[getType(propDict[key]['attrs']['name'])] = insideItem.get(
                        '@odata.id')
    for key in propDict:
        item = getType(key).split(':')[-1]
        if propDict[key]['realtype'] == 'complex':
            if jsonData.get(item) is not None:
                if propDict[key].get('isCollection') is not None:
                    for listItem in jsonData[item]:
                        linkList.update(getAllLinks(
                            listItem, propDict[key]['typeprops']))
                else:
                    linkList.update(getAllLinks(
                        jsonData[item], propDict[key]['typeprops']))
    return linkList


def checkAnnotationCompliance(decoded):
    for key in [k for k in decoded if '@' in k]:
        rsvLogger.info(key)


# Consider removing this as a global
allLinks = set()


def validateURI(URI, uriName=''):
    # rs-assertion: 9.4.1
    # Initial startup here
    rsvLogger.info("\n*** %s, %s", uriName, URI)
    counts = Counter()
    results = OrderedDict()
    messages = OrderedDict()
    errorMessages = list()

    results[uriName] = (URI, False, counts, messages, errorMessages)

    # Get from service by URI, ex: "/redfish/v1"
    success, jsonData, status = callResourceURI(URI)

    rsvLogger.debug('%s, %s, %s', success, jsonData, status)

    if not success:
        rsvLogger.error("validateURI: Get URI failed.")
        counts['failGet'] += 1
        errorMessages += ('%s:  URI could not be acquired: %s' % (URI, status),)
        return False, counts, results

    counts['passGet'] += 1

    checkAnnotationCompliance(jsonData)
    # check for @odata mandatory stuff
    # check for version numbering problems
    # check id if its the same as URI
    # check @odata.context instead of local

    SchemaFullType = jsonData.get('@odata.type')
    if SchemaFullType is None:
        rsvLogger.error("validateURI: Json does not contain type, is error?")
        counts['failJsonError'] += 1
        errorMessages += (URI + ':  Json does not contain @odata.type',)
        return False, counts, results

    rsvLogger.info(SchemaFullType)

    # Parse @odata.type, get schema XML and its references from its namespace

    SchemaType = getType(SchemaFullType)
    SchemaNamespace = getNamespace(SchemaFullType)
    SchemaURI = jsonData.get('@odata.context')

    SchemaURI = SchemaURI.split('#')[0]

    rsvLogger.debug("%s %s", SchemaType, SchemaURI)

    success, SchemaSoup = getSchemaDetails(
        SchemaNamespace, SchemaURI=SchemaURI)

    if success:
        refDict = getReferenceDetails(SchemaSoup)
        if SchemaType in refDict:
            success, SchemaSoup = getSchemaDetails(
                SchemaNamespace, SchemaURI=refDict[getNamespace(SchemaType)][1])
    else:
        success, SchemaSoup = getSchemaDetails(SchemaNamespace)
        if not success:
            success, SchemaSoup = getSchemaDetails(SchemaType)
        if success:
            refDict = getReferenceDetails(SchemaSoup)

    if not success:
        rsvLogger.error("validateURI: No schema XML for %s %s",
                        SchemaFullType, SchemaType)
        counts['failSchema'] += 1
        errorMessages += (URI + ':  No such XML for ' + SchemaFullType,)
        return False, counts, results

    refDict = getReferenceDetails(SchemaSoup)

    rsvLogger.debug(jsonData)
    rsvLogger.debug(SchemaSoup)

    # Attempt to get a list of properties
    try:
        propertyList = getTypeDetails(
            SchemaSoup, refDict, SchemaFullType, 'entitytype')
    except Exception as ex:
        rsvLogger.error(traceback.format_exc())
        counts['exceptionGetType'] += 1
        errorMessages += (URI + ':  Getting type failed for ' + SchemaFullType,)
        rsvLogger.error(errorMessages)
        return False, counts, results

    rsvLogger.debug(propertyList)
    propertyDict = OrderedDict()

    # Generate dictionary of property info
    for prop in propertyList:
        try:
            propertyDict[prop] = getPropertyDetails(SchemaSoup, refDict, prop)
        except Exception as ex:
            rsvLogger.error(traceback.format_exc())
            errorMessages += ('%s:  Could not get details on this property: %s, %s' % (prop, str(type(ex).__name__), str(ex)),)
            counts['exceptionGetDict'] += 1

    rsvLogger.debug(propertyDict)

    # With dictionary of property details, check json against those details
    # rs-assertion: test for AdditionalProperties
    for prop in propertyDict:
        try:
            propMessages, propCounts = checkPropertyCompliance(prop, propertyDict[prop], jsonData)
            messages.update(propMessages)
            counts.update(propCounts)
        except Exception as ex:
            rsvLogger.error(traceback.format_exc())
            errorMessages += ('%s:  Could not finish compliance check on this property: %s, %s' % (prop, str(type(ex).__name__), str(ex)),)
            counts['exceptionPropCompliance'] += 1

    # List all items checked and uncheckedi
    # current logic does not check inside complex types
    fmt = '%-20s%20s'
    rsvLogger.info('%s, %s', uriName, SchemaType)

    for key in jsonData:
        item = jsonData[key]
        rsvLogger.info(fmt % (
            key, 'Exists And Checks' if key in messages else 'Exists, no schema check'))
        if key not in messages:
            # note: extra messages for "unchecked" properties
            messages[key] = (item, '-',
                             'Exists',
                             '-')
    for key in messages:
        if key not in jsonData:
            rsvLogger.info("Checking: %s %s", key, messages[key][3])

    rsvLogger.info('%s, %s, %s', SchemaFullType, counts, len(propertyList))

    results[uriName] = (URI, success, counts, messages, errorMessages)

    # Get all links available
    links = getAllLinks(jsonData, propertyDict)

    rsvLogger.debug(links)

    for linkName in links:
        if links[linkName] in allLinks:
            counts['repeat'] += 1
            continue

        allLinks.add(links[linkName])

        success, linkCounts, linkResults = validateURI(
            links[linkName], uriName + ' -> ' + linkName)
        if not success:
            counts['unvalidated'] += 1
        rsvLogger.info('%s, %s', linkName, linkCounts)
        results.update(linkResults)

    return True, counts, results

##########################################################################
######################          Script starts here              ##########
##########################################################################


if __name__ == '__main__':
    # Rewrite here
    status_code = 1
    success, counts, results = validateURI('/redfish/v1', 'ServiceRoot')

    finalCounts = Counter()

    nowTick = datetime.now()
 
    # Render html
    htmlStr = '<html><head><title>Compliance Test Summary</title>\
            <style>\
            .pass {background-color:#99EE99; text-align:center}\
            .fail {background-color:#EE9999; text-align:center}\
            .title {background-color:#DDDDDD; border: 1pt solid; padding: 8px}\
            .titlerow {border: 2pt solid}\
            body {background-color:lightgrey; border: 1pt solid; text-align:center; margin-left:auto; margin-right:auto}\
            th {text-align:center; background-color:beige; border: 1pt solid}\
            td {text-align:left; background-color:white; border: 1pt solid}\
            table {width:90%; margin: 0px auto;}\
            .titletable {width:100%}\
            </style>\
            </head><body>'
    htmlStr += '<table>\
                <tr><th>##### Redfish Compliance Test Report #####</th></tr>\
                <tr><th>System: ' + ConfigURI + '</th></tr>\
                <tr><th>User: ' + User + '</th></tr>\
                <tr><th>Start time: ' + str(startTick) + '</th></tr>\
                <tr><th>Run time: ' + str(nowTick - startTick) + '</th></tr>\
                <tr><th></th></tr>'

    htmlStr2 = '' + htmlStr

    cnt = 1
    rsvLogger.info(len(results))
    for item in results:
        cnt += 1
        htmlStr += '<tr><td class="titlerow"><table class="titletable"><tr>'
        htmlStr += '<td class="title" style="width:40%">' + item + '</td>'
        htmlStr += '<td style="width:20%">' + str(results[item][0]) + '</td>'
        htmlStr += '<td style="width:10%"' + \
            ('class="pass"> PASS' if results[item]
             [1] else 'class="fail"> FAIL') + '</td>'
        htmlStr += '<td>'
        innerCounts = results[item][2]
        finalCounts.update(innerCounts)
        for countType in innerCounts:
            innerCounts[countType] += 0
            htmlStr += '{p}: {q},   '.format(p=countType,
                                             q=innerCounts.get(countType, 0))
        htmlStr += '</td></tr>'
        htmlStr += '</table></td></tr>'
        htmlStr += '<tr><td><table><tr><th> Name</th> <th> Value</th> <th>Type</th> <th>Exists?</th> <th>Success</th> <tr>'
        if results[item][3] is not None:
            for i in results[item][3]:
                htmlStr += '<tr>'
                htmlStr += '<td>' + str(i) + '</td>'
                for j in results[item][3][i]:
                    if 'PASS' in str(j):
                        htmlStr += '<td class="pass">' + str(j) + '</td>'
                    elif 'FAIL' in str(j):
                        htmlStr += '<td class="fail">' + str(j) + '</td>'
                    else:
                        htmlStr += '<td >' + str(j) + '</td>'
                htmlStr += '</tr>'
        htmlStr += '</table></td></tr>'
        if results[item][4] is not None:
            for i in results[item][4]:
                htmlStr += '<tr><td class="fail">' + str(i) + '</td></tr>'
        htmlStr += '<tr><td>---</td></tr>'
    htmlStr += '</table></body></html>'
    htmlStr += '</table></body></html>'

    with open(datetime.strftime(startTick, "logs/ComplianceHtmlLog_%m_%d_%Y_%H%M%S.html"), 'w') as f:
        f.write(htmlStr)
    
    fails = 0
    for key in finalCounts:
        if 'fail' in key or 'exception' in key:
            fails += finalCounts[key]

    success = success and not (fails > 0)
    rsvLogger.info(finalCounts)

    if not success:
        rsvLogger.info("Validation has failed: %d problems found", fails)
        sys.exit(1)
    
    rsvLogger.info("Validation has succeeded.")
    sys.exit(0)
