# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link:
# https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from bs4 import BeautifulSoup
import configparser
import requests
import io, os, sys, re
from datetime import datetime
from collections import Counter, OrderedDict
from functools import lru_cache
import logging

# Make logging blocks for each SingleURI Validate
rsvLogger = logging.getLogger("rsv")
rsvLogger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
rsvLogger.addHandler(ch)

# Read config info from ini file placed in config folder of tool
config = configparser.ConfigParser()
config.read(os.path.join('.', 'config', 'config.ini'))
useSSL = config.getboolean('Options', 'UseSSL')

ConfigURI = ('https' if useSSL else 'http') + '://' + \
    config.get('SystemInformation', 'TargetIP')
User = config.get('SystemInformation', 'UserName')
Passwd = config.get('SystemInformation', 'Password')
sysDescription = config.get('SystemInformation', 'SystemInfo')

SchemaLocation = config.get('Options', 'MetadataFilePath')
chkCert = config.getboolean('Options', 'CertificateCheck') and useSSL
localOnly = config.getboolean('Options', 'LocalOnlyMode')

@lru_cache(maxsize=64)
def callResourceURI(URILink):
    """
    Makes a call to a given URI or URL

    param arg1: path to URI "/example/1", or URL "http://example.com"
    return: (success boolean, data)
    """ 
    # rs-assertions: 6.4.1, including accept, content-type and odata-versions
    # rs-assertion: handle redirects?  and target permissions
    # rs-assertion: require no auth for serviceroot calls
    nonService = 'http' in URILink[:8]
    statusCode = ''
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
                if '#' in URILink:
                    URILink, frag = tuple(URILink.rsplit('#',1))
                    fragNavigate = frag.split('/')[1:]
                    for item in fragNavigate:
                        if isinstance( decoded, dict ):
                            decoded = decoded.get(item)
                        elif isinstance( decoded, list ):
                            decoded = decoded[int(item)] if int(item) < len(decoded) else None
                    if not isinstance( decoded, dict ):
                        rsvLogger.warn(URILink + " decoded object no longer a dictionary")
            else:
                decoded = response.text
            return decoded is not None, decoded, statusCode
    except Exception as ex:
        rsvLogger.exception("Something went wrong")
    return False, None, statusCode


# note: Use some sort of re expression to parse SchemaAlias
# ex: #Power.1.1.1.Power , #Power.v1_0_0.Power
def getNamespace(string):
    return string.replace('#', '').rsplit('.', 1)[0]
def getType(string):
    return string.replace('#', '').rsplit('.', 1)[-1]


@lru_cache(maxsize=64)
def getSchemaDetails(SchemaAlias, SchemaURI=None, suffix='_v1.xml'):
    """
    Find Schema file for given Namespace.

    param arg1: Schema Namespace, such as ServiceRoot
    param SchemaURI: uri to grab schema, given localOnly is False
    return: (success boolean, a Soup object)
    """
    if SchemaAlias is None:
        return False, None, None
    
    # rs-assertion: parse frags
    if SchemaURI is not None and not localOnly:
        success, data, status = callResourceURI(SchemaURI)
        if success:
            soup = BeautifulSoup(data, "html.parser")
            if '#' in SchemaURI: 
                SchemaURI, frag = tuple(SchemaURI.rsplit('#',1))
                refType, refLink = getReferenceDetails(soup).get(getNamespace(frag))
                if refLink is not None:
                    success, data, status = callResourceURI(refLink)
                    if success:
                        soup = BeautifulSoup(data, "html.parser")
                        return True, soup, refLink
                    else:
                        rsvLogger.error("SchemaURI couldn't call reference link: %s %s", SchemaURI, frag)
                else:
                    rsvLogger.error("SchemaURI missing reference link: %s %s", SchemaURI, frag)
            else:
                return True, soup, SchemaURI
        rsvLogger.error("SchemaURI unsuccessful: %s", SchemaURI)
        return False, None, None
   
    # Use local if no URI or LocalOnly
    Alias = getNamespace(SchemaAlias).split('.')[0]
    try:
        filehandle = open(SchemaLocation + '/' + Alias + suffix, "r")
        filedata = filehandle.read()
        filehandle.close()
        soup = BeautifulSoup(filedata, "html.parser")
        parentTag = soup.find('edmx:dataservices')
        child = parentTag.find('schema')
        SchemaNamespace = child['namespace']
        FoundAlias = SchemaNamespace.split(".")[0]
        if FoundAlias == Alias:
            return True, soup, "local" + SchemaLocation + '/' + Alias + suffix
    except Exception as ex:
        rsvLogger.exception("Something went wrong")
    return False, None, None


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
                refDict[item['namespace'].split('.')[0]] = (item['namespace'], ref['uri'])
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
    propSchema = soup.find( 'schema', attrs={'namespace': getNamespace(currentType)})
    
    if propSchema is None:
        return False, None, None, None
    propEntity = propSchema.find( tagType, attrs={'name': getType(currentType)})
    
    if propEntity is None:
        return False, None, None, None

    currentType = propEntity.get('basetype')
    if currentType is None:
        return False, None, None, None
    
    currentType = currentType.replace('#','')
    SchemaNamespace, SchemaType = getNamespace(currentType), getType(currentType)
    propSchema = soup.find( 'schema', attrs={'namespace': SchemaNamespace})

    if propSchema is None:
        success, innerSoup, uri = getSchemaDetails(
            *refs.get(SchemaNamespace, (None,None)))
        if not success:
            return False, None, None, None
        innerRefs = getReferenceDetails(innerSoup)
        propSchema = innerSoup.find(
            'schema', attrs={'namespace': SchemaNamespace})
        if propSchema is None:
            return False, None, None, None
    else:
        innerSoup = soup
        innerRefs = refs

    return True, innerSoup, innerRefs, currentType 

def getTypeDetails(soup, refs, SchemaAlias, tagType):
    """
    Gets list of surface level properties for a given SchemaAlias,
    
    param arg1: soup
    param arg2: references
    param arg3: SchemaAlias string
    param arg4: tag of Type, which can be EntityType or ComplexType...
    return: list of (soup, ref, string PropertyName, tagType)
    """
    PropertyList = list()

    SchemaNamespace, SchemaType = getNamespace(SchemaAlias), getType(SchemaAlias)

    rsvLogger.debug("Schema is %s, %s, %s", SchemaAlias,
                    SchemaType, SchemaNamespace)

    innerschema = soup.find('schema', attrs={'namespace': SchemaNamespace})

    if innerschema is None:
        rsvLogger.error("Got XML, but schema still doesn't exist...? %s, %s" %
                            (getNamespace(SchemaAlias), SchemaAlias))
        raise Exception('exceptionType: Was not able to get type, is Schema in XML? '  + str(refs.get(getNamespace(SchemaAlias), (getNamespace(SchemaAlias), None))))

    for element in innerschema.find_all(tagType, attrs={'name': SchemaType}):
        rsvLogger.debug("___")
        rsvLogger.debug(element['name'])
        rsvLogger.debug(element.attrs)
        rsvLogger.debug(element.get('basetype'))
        
        usableProperties = element.find_all('property')
        usableNavProperties = element.find_all('navigationproperty')
       
        for innerelement in usableProperties + usableNavProperties:
            rsvLogger.debug(innerelement['name'])
            rsvLogger.debug(innerelement.get('type'))
            rsvLogger.debug(innerelement.attrs)
            newProp = innerelement['name']
            if SchemaAlias:
                newProp = SchemaAlias + ':' + newProp
            rsvLogger.debug("ADDING :::: %s", newProp)
            if newProp not in PropertyList:
                PropertyList.append((soup,refs,newProp,tagType))
        
    return PropertyList 


def getPropertyDetails(soup, refs, PropertyItem, tagType='entitytype'):
    """
    Get dictionary of tag attributes for properties given, including basetypes.

    param arg1: soup data
    param arg2: references
    param arg3: a property string
    """
    propEntry = dict()

    propOwner, propChild = PropertyItem.split(':')[0].replace('#',''), PropertyItem.split(':')[-1]
    SchemaNamespace, SchemaType = getNamespace(propOwner), getType(propOwner)
    rsvLogger.debug('___')
    rsvLogger.debug('%s, %s', SchemaNamespace, PropertyItem)

    propSchema = soup.find('schema', attrs={'namespace': SchemaNamespace})
    if propSchema is None:
        rsvLogger.error("innerSoup doesn't exist...? %s", SchemaNamespace)
        return None
    else:
        innerSoup = soup
        innerRefs = refs

    # get type tag and tag of property in type
    propEntity = propSchema.find(tagType, attrs={'name': SchemaType})
    propTag = propEntity.find('property', attrs={'name': propChild})

    # check if this property is a nav property
    # Checks if this prop is an annotation
    propEntry['isNav'] = False
    if '@' not in propChild:
        if propTag is None:
            propTag = propEntity.find(
                'navigationproperty', attrs={'name': propChild})
            propEntry['isNav'] = True
        # start adding attrs and props together
        propAll = propTag.find_all()
        for tag in propAll:
            propEntry[tag['term']] = tag.attrs 
    else:
        propTag = propEntity

    propEntry['attrs'] = propTag.attrs
    rsvLogger.debug(propEntry)

    success, typeSoup, typeRefs, propType = getParentType(innerSoup, innerRefs, SchemaType, tagType)
    propType = propTag.get('type')
    
    # find the real type of this, by inheritance
    while propType is not None:
        rsvLogger.debug("HASTYPE")
        TypeNamespace, TypeSpec = getNamespace(propType), getType(propType)

        rsvLogger.debug('%s, %s', TypeNamespace, propType)
        # Type='Collection(Edm.String)'
        # If collection, check its inside type
        if re.match('Collection(.*)', propType) is not None:
            propType = propType.replace('Collection(', "").replace(')', "")
            propEntry['isCollection'] = propType
            continue
        if 'Edm' in propType:
            propEntry['realtype'] = propType
            break
        
        # get proper soup
        if TypeNamespace.split('.')[0] != SchemaNamespace.split('.')[0]:
            success, typeSoup, uri = getSchemaDetails(*refs.get(TypeNamespace,(None,None)))
        else:
            success, typeSoup = True, innerSoup

        if not success:
            rsvLogger.error("innerSoup doesn't exist...? %s", SchemaNamespace)
            return None

        propEntry['soup'] = typeSoup
        
        # traverse tags to find the type
        typeRefs = getReferenceDetails(typeSoup)
        # traverse tags to find the type
        typeSchema = typeSoup.find( 'schema', attrs={'namespace': TypeNamespace})
        typeSimpleTag = typeSchema.find( 'typedefinition', attrs={'name': TypeSpec})
        typeComplexTag = typeSchema.find( 'complextype', attrs={'name': TypeSpec})
        typeEnumTag = typeSchema.find('enumtype', attrs={'name': TypeSpec})
        typeEntityTag = typeSchema.find('entitytype', attrs={'name': TypeSpec})

        # perform more logic for each type
        if typeSimpleTag is not None:
            propType = typeSimpleTag.get('underlyingtype')
            isEnum = typeSimpleTag.find('annotation', attrs={'term':'Redfish.Enumeration'})
            if propType == 'Edm.String' and isEnum is not None:
                propEntry['realtype'] = 'deprecatedEnum'
                propEntry['typeprops'] = list()
                memberList = isEnum.find('collection').find_all('propertyvalue')

                for member in memberList:
                    propEntry['typeprops'].append( member.get('string'))
                rsvLogger.debug("%s", str(propEntry['typeprops']))
                break
            else:
                continue
        elif typeComplexTag is not None:
            rsvLogger.debug("go deeper in type")
            propertyList = list()
            success, baseSoup, baseRefs, baseType = True, typeSoup, typeRefs, propType
            while success:
                propertyList.extend(getTypeDetails(
                    baseSoup, baseRefs, baseType, 'complextype'))
                success, baseSoup, baseRefs, baseType = getParentType(baseSoup, baseRefs, baseType, 'complextype')
            propDict = {item[2]: getPropertyDetails( *item) for item in propertyList}
            rsvLogger.debug(key for key in propDict)
            propEntry['realtype'] = 'complex'
            propEntry['typeprops'] = propDict
            break
        elif typeEnumTag is not None:
            propEntry['realtype'] = 'enum'
            propEntry['typeprops'] = list()
            for MemberName in typeEnumTag.find_all('member'):
                propEntry['typeprops'].append(MemberName['name'])
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


def checkPropertyCompliance(soup, PropertyName, PropertyItem, decoded, refs):
    """
    Given a dictionary of properties, check the validitiy of each item, and return a
    list of counted properties

    param arg1: property name
    param arg2: property item dictionary
    param arg3: json payload
    param arg4: refs
    """
    resultList = OrderedDict()
    counts = Counter()

    rsvLogger.info(PropertyName)
    item = PropertyName.split(':')[-1]

    propValue = decoded.get(item, 'n/a')
    rsvLogger.info("\tvalue: %s %s", propValue, type(propValue))

    propExists = not (propValue == 'n/a')
    propNotNull = propExists and propValue is not None and propValue is not 'None'

    if PropertyItem is None:
        if propExists:
            rsvLogger.info('\tItem is skipped, no schema')
            counts['skipNoSchema'] += 1
            return {item: ('-', '-',
                                'Exists' if propExists else 'DNE', 'skipNoSchema')}, counts 
        else:
            rsvLogger.error('\tItem is present, no schema found')
            counts['failNoSchema'] += 1
            return {item: ('-', '-',
                                'Exists' if propExists else 'DNE', 'failNoSchema')}, counts 

    propAttr = PropertyItem['attrs']

    propType = propAttr.get('type')
    propRealType = PropertyItem.get('realtype')
    rsvLogger.info("\thas Type: %s %s", propType, propRealType)

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
            return  {item: ('-', (propType, propRealType),
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

    # Note: consider http://docs.oasis-open.org/odata/odata-csdl-xml/v4.01/csprd01/odata-csdl-xml-v4.01-csprd01.html#_Toc472333112
    # Note: make sure it checks each one
    propCollectionType = PropertyItem.get('isCollection')
    isCollection = propCollectionType is not None
    if propCollectionType is not None and propNotNull:
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
    for cnt, val in enumerate(propValueList):
        appendStr = (('#' + str(cnt)) if isCollection else '')
        if propRealType is not None and propExists and propNotNull:
            paramPass = False
            if propRealType == 'Edm.Boolean':
                paramPass = isinstance( val, bool )
                if not paramPass:
                    rsvLogger.error("%s: Not a boolean" % PropertyName)

            elif propRealType == 'Edm.DateTimeOffset':
                # note: find out why this might be wrong 
                if isinstance(val, str):
                    match = re.match(
                        '.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])', str(val))
                    paramPass = match is not None
                    if not paramPass:
                        rsvLogger.error("%s: Malformed DateTimeOffset" % PropertyName)
                else:
                    rsvLogger.error("%s: Expected string value for DateTimeOffset" % PropertyName)


            elif propRealType == 'Edm.Int16' or propRealType == 'Edm.Int32' or\
                    propRealType == 'Edm.Int64' or propRealType == 'Edm.Int' or\
                    propRealType == 'Edm.Decimal' or propRealType == 'Edm.Double':
                rsvLogger.debug("intcheck: %s %s %s", propRealType, val, (validMinAttr, validMaxAttr))
                paramPass = isinstance( val, (int, float) ) 
                if paramPass:
                    if 'Int' in propRealType:
                        paramPass = isinstance( val, int )
                        if not paramPass:
                            rsvLogger.error("%s: Expected int" % PropertyName)
                    if validMinAttr is not None:
                        paramPass = paramPass and int(
                            validMinAttr['int']) <= val
                        if not paramPass:
                            rsvLogger.error("%s: Value out of assigned min range" % PropertyName)
                    if validMaxAttr is not None:
                        paramPass = paramPass and int(
                            validMaxAttr['int']) >= val
                        if not paramPass:
                            rsvLogger.error("%s: Value out of assigned max range" % PropertyName)
                else:
                    rsvLogger.error("%s: Expected numeric type" % PropertyName)


            elif propRealType == 'Edm.Guid':
                if isinstance(val, str):
                    match = re.match(
                        "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", str(val))
                    paramPass = match is not None
                    if not paramPass:
                        rsvLogger.error("%s: Malformed Guid" % PropertyName)
                else:
                    rsvLogger.error("%s: Expected string value for Guid" % PropertyName)
                    
            elif propRealType == 'Edm.String':
                if isinstance(val, str):
                    if validPatternAttr is not None:
                        pattern = validPatternAttr.get('string', '')
                        match = re.fullmatch(pattern, val)
                        paramPass = match is not None
                        if not paramPass:
                            rsvLogger.error("%s: Malformed String" % PropertyName)
                    else:
                        paramPass = True
                else:
                    rsvLogger.error("%s: Expected string value" % PropertyName)

            else:
                if propRealType == 'complex':
                    rsvLogger.info('\t***going into Complex')
                    if not isinstance( val, dict ):
                        resultList[item + appendStr]\
                                = ('ComplexDictionary' + appendStr, (propType, propRealType),\
                                            'Exists' if propExists else 'DNE',\
                                            'complexFAIL')
                        rsvLogger.error(item + ' : Complex item not a dictionary')
                        counts['complex'] += 1
                        counts['failComplex'] += 1
                        continue
                        
                    complexMessages = OrderedDict()
                    complexCounts = Counter()
                    innerPropDict = PropertyItem['typeprops']
                    innerPropSoup = PropertyItem['soup']
                    successService, serviceSchemaSoup, SchemaServiceURI = getSchemaDetails('metadata','/redfish/v1/$metadata','.xml')
                    if successService:
                        serviceRefs = getReferenceDetails(serviceSchemaSoup)
                        successService, additionalProps = getAnnotations(serviceSchemaSoup, serviceRefs, val)
                        for prop in additionalProps:
                            innerPropDict[prop[2]] = getPropertyDetails(*prop)
                    for prop in innerPropDict:
                        propMessages, propCounts = checkPropertyCompliance(innerPropSoup, prop, innerPropDict[prop], val, refs)
                        complexMessages.update(propMessages)
                        complexCounts.update(propCounts)
                    successPayload, odataMessages = checkPayloadCompliance('',val)
                    complexMessages.update(odataMessages)
                    rsvLogger.info('\t***out of Complex')
                    rsvLogger.info('complex %s', complexCounts)
                    counts.update(complexCounts)
                    resultList[item + appendStr]\
                            = ('ComplexDictionary' + appendStr, (propType, propRealType),\
                                        'Exists' if propExists else 'DNE',\
                                        'complex')
                    if item == "Actions":
                        success, baseSoup, baseRefs, baseType = True, innerPropSoup, getReferenceDetails(innerPropSoup), decoded.get('@odata.type')
                        actionsDict = dict()

                        while success:
                            SchemaNamespace, SchemaType = getNamespace(baseType), getType(baseType)
                            innerschema = baseSoup.find('schema', attrs={'namespace': SchemaNamespace})
                            actions = innerschema.find_all('action')
                            for act in actions:
                                keyname = '#%s.%s' % (SchemaNamespace, act['name'])
                                actionsDict[keyname] = act
                            success, baseSoup, baseRefs, baseType = getParentType(baseSoup, baseRefs, baseType, 'entitytype')
                        
                        for k in actionsDict:
                            actionDecoded = val.get(k, 'n/a')
                            actPass = False
                            if actionDecoded != 'n/a':
                                target = actionDecoded.get('target')
                                if target is not None and isinstance( target, str ):
                                    actPass = True
                                else:
                                    rsvLogger.error(k + ': target for action is malformed')
                            else:
                                rsvLogger.error(k + ': action not Found')
                            complexMessages[k] = ('Action', '-',\
                                        'Exists' if actionDecoded != 'n/a'  else 'DNE',\
                                        'PASS' if actPass else 'FAIL') 
                            counts['pass'] += 1
                    
                    for complexKey in complexMessages:
                        resultList[item + '.' + complexKey + appendStr] = complexMessages[complexKey]

                    for key in val:
                        if key not in complexMessages:
                            rsvLogger.error('%s: Appears to be an extra property (check inheritance or casing?)', item + '.' + key + appendStr)
                            counts['failAdditional'] += 1
                            resultList[item + '.' + key + appendStr] = (val[key], '-',
                                                                 'Exists',
                                                                 '-')
                    continue

                elif propRealType == 'enum':
                    if isinstance(val, str):
                        paramPass = val in PropertyItem['typeprops']
                        if not paramPass:
                            rsvLogger.error("%s: Invalid enum found (check casing?)" % PropertyName)
                    else:
                        rsvLogger.error("%s: Expected string value for Enum" % PropertyName)
                    
                elif propRealType == 'deprecatedEnum':
                    if isinstance(val, list):
                        paramPass = True
                        for enumItem in val:
                            for k,v in enumItem.items():
                                rsvLogger.debug('%s, %s' % (k,v))
                                paramPass = paramPass and str(v) in PropertyItem['typeprops']
                        if not paramPass:
                            rsvLogger.error("%s: Invalid DeprecatedEnum found (check casing?)" % PropertyName)
                    elif isinstance(val, str):
                        rsvLogger.debug('%s' % val)
                        paramPass = str(val) in PropertyItem['typeprops']
                        if not paramPass:
                            rsvLogger.error("%s: Invalid DeprecatedEnum found (check casing?)" % PropertyName)
                    else:
                        rsvLogger.error("%s: Expected list/str value for DeprecatedEnum? (" % PropertyName) 

                elif propRealType == 'entity':
                    # check if the entity is truly what it's supposed to be
                    autoExpand = PropertyItem.get('OData.AutoExpand',None) is not None or\
                    PropertyItem.get('OData.AutoExpand'.lower(),None) is not None
                    uri = val['@odata.id']
                    if not autoExpand:
                        success, data, status = callResourceURI(uri)
                    else:
                        success, data, status = True, val, 200
                    rsvLogger.debug('%s, %s, %s', success, (propType, propCollectionType), data)
                    if propCollectionType == 'Resource.Item' or propType == 'Resource.Item' and success: 
                        paramPass = success 
                    elif success:
                        currentType = data.get('@odata.type', propCollectionType)
                        if currentType is None:
                            currentType = propType
                        baseLink = refs.get(getNamespace(propCollectionType if propCollectionType is not None else propType))
                        baseLinkObj = refs.get(getNamespace(currentType.split('.')[0]))
                        if soup.find('schema',attrs={'namespace': getNamespace(currentType)}) is not None:
                            success, baseSoup = True, soup
                        elif baseLink is not None:
                            success, baseSoup, uri = getSchemaDetails(*baseLink)
                        else:
                            success = False

                        rsvLogger.debug('success: %s %s %s',success, currentType, baseLink)        
                        if currentType is not None and success:
                            currentType = currentType.replace('#','')
                            baseRefs = getReferenceDetails(baseSoup)
                            allTypes = []
                            while currentType not in allTypes and success: 
                                allTypes.append(currentType)
                                success, baseSoup, baseRefs, currentType = getParentType(baseSoup, baseRefs, currentType, 'entitytype')
                                rsvLogger.debug('success: %s %s',success, currentType)

                            rsvLogger.debug('%s, %s, %s', propType, propCollectionType, allTypes)
                            paramPass = propType in allTypes or propCollectionType in allTypes
                            if not paramPass:
                                rsvLogger.error("%s: Expected Entity type %s, but not found in type inheritance %s" % (PropertyName, (propType, propCollectionType), allTypes))
                        else:
                            rsvLogger.error("%s: Could not get schema file for Entity check" % PropertyName)
                    else:
                        rsvLogger.error("%s: Could not get resource for Entity check" % PropertyName)


        resultList[item + appendStr] = (val, (propType, propRealType),
                                         'Exists' if propExists else 'DNE',
                                         'PASS' if paramPass and propMandatoryPass and propNullablePass else 'FAIL')
        if paramPass and propNullablePass and propMandatoryPass:
            counts['pass'] += 1
            rsvLogger.info("\tSuccess")
        else:
            counts[propType] += 1
            if not paramPass:
                if propMandatory:
                    rsvLogger.error("%s: Mandatory prop has failed to check" % PropertyName)
                    counts['failMandatoryProp'] += 1
                else:
                    counts['failProp'] += 1
            elif not propMandatoryPass:
                rsvLogger.error("%s: Mandatory prop does not exist" % PropertyName)
                counts['failMandatoryExist'] += 1
            elif not propNullablePass:
                rsvLogger.error("%s: This property is not nullable" % PropertyName)
                counts['failNull'] += 1
            rsvLogger.info("\tFAIL")

    return resultList, counts

# Function to collect all links in current resource schema


def getAllLinks(jsonData, propDict, refDict, prefix='', context=''):
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
                cType = propDict[key].get('isCollection') 
                autoExpand = propDict[key].get('OData.AutoExpand',None) is not None or\
                    propDict[key].get('OData.AutoExpand'.lower(),None) is not None
                if cType is not None:
                    cSchema = refDict.get(getNamespace(cType),(None,None))[1]
                    if cSchema is None:
                        cSchema = context 
                    for cnt, listItem in enumerate(insideItem):
                        linkList[prefix+str(item)+'.'+getType(propDict[key]['isCollection']) +
                                 '#' + str(cnt)] = (listItem.get('@odata.id'), autoExpand, cType, cSchema, listItem)
                else:
                    cType = propDict[key]['attrs'].get('type')
                    cSchema = refDict.get(getNamespace(cType),(None,None))[1]
                    if cSchema is None:
                        cSchema = context 
                    linkList[prefix+str(item)+'.'+getType(propDict[key]['attrs']['name'])] = (\
                            insideItem.get('@odata.id'), autoExpand, cType, cSchema, insideItem)
    for key in propDict:
        item = getType(key).split(':')[-1]
        if propDict[key]['realtype'] == 'complex':
            if jsonData.get(item) is not None:
                if propDict[key].get('isCollection') is not None:
                    for listItem in jsonData[item]:
                        linkList.update(getAllLinks(
                            listItem, propDict[key]['typeprops'], refDict, prefix+item+'.', context))
                else:
                    linkList.update(getAllLinks(
                        jsonData[item], propDict[key]['typeprops'], refDict, prefix+item+'.', context))
    rsvLogger.debug(str(linkList))
    return linkList

def getAnnotations(soup, refs, decoded, prefix=''):
    additionalProps = list() 
    for key in [k for k in decoded if prefix+'@' in k]:
        splitKey = key.split('@',1)
        fullItem = splitKey[1]
        realType, refLink = refs.get(getNamespace(fullItem),(None,None))
        success, annotationSoup, uri = getSchemaDetails(realType, refLink)
        rsvLogger.debug('%s, %s, %s, %s, %s', str(success), key, splitKey, decoded[key], realType)
        if success:
            realItem = realType + '.' + fullItem.split('.',1)[1]
            annotationRefs = getReferenceDetails(annotationSoup)
            additionalProps.append( (annotationSoup, annotationRefs, realItem+':'+key, 'term') )

    return True, additionalProps 

def checkPayloadCompliance(uri, decoded):
    messages = dict()
    success = True
    for key in [k for k in decoded if '@odata' in k]:
        itemType = key.split('.',1)[-1]
        itemTarget = key.split('.',1)[0]
        paramPass = False
        if key == 'id':
            paramPass = isinstance( decoded[key], str)
            pass
        elif key == 'count':
            paramPass = isinstance( decoded[key], int)
            pass
        elif key == 'context':
            paramPass = isinstance( decoded[key], str)
            pass
        elif key == 'type':
            paramPass = isinstance( decoded[key], str)
            pass
        else:
            paramPass = True
        if not paramPass:
            rsvLogger.error(key + "@odata item not compliant: " + decoded[key])
            success = False
        messages[key] = (decoded[key], 'odata',
                                         'Exists',
                                         'PASS' if paramPass else 'FAIL')
    return success, messages


def validateURITree(URI, uriName, expectedType=None, expectedSchema=None, expectedJson=None, allLinks=set()):
    allLinks.add(URI)
    
    validateSuccess, counts, results, links = \
            validateSingleURI(URI, uriName, expectedType, expectedSchema, expectedJson)
    if validateSuccess:
        refLinks = OrderedDict()
        for linkName in links:
            if 'Links' in linkName.split('.',1)[0] or 'RelatedItem' in linkName.split('.',1)[0] or 'Redundancy' in linkName.split('.',1)[0]:
                refLinks[linkName] = links[linkName]
                continue
            if links[linkName][0] in allLinks:
                counts['repeat'] += 1
                continue

            allLinks.add(links[linkName][0])
            linkURI, autoExpand, linkType, linkSchema, innerJson = links[linkName]
            rsvLogger.debug('%s', links[linkName])

            if linkType is not None and autoExpand:
                success, linkCounts, linkResults, xlinks = validateURITree(
                        linkURI, uriName + ' -> ' + linkName, linkType, linkSchema, innerJson, allLinks)
            else:
                success, linkCounts, linkResults, xlinks = validateURITree(
                        linkURI, uriName + ' -> ' + linkName, allLinks=allLinks)
            if not success:
                counts['unvalidated'] += 1
            rsvLogger.info('%s, %s', linkName, linkCounts)
            results.update(linkResults)
    
    return validateSuccess, counts, results, allLinks


def validateSingleURI(URI, uriName='', expectedType=None, expectedSchema=None, expectedJson=None):
    # rs-assertion: 9.4.1
    # Initial startup here
    errorMessages = io.StringIO()
    fmt = logging.Formatter('%(levelname)s - %(message)s')
    errh = logging.StreamHandler(errorMessages)
    errh.setLevel(logging.ERROR)
    errh.setFormatter(fmt)
    rsvLogger.addHandler(errh)
    
    # Start 
    rsvLogger.info("\n*** %s, %s", uriName, URI)
    rsvLogger.debug("\n*** %s, %s, %s", expectedType, expectedSchema is not None, expectedJson is not None)
    counts = Counter()
    propertyDict = OrderedDict()
    results = OrderedDict()
    messages = OrderedDict()
    success = False

    results[uriName] = (URI, success, counts, messages, errorMessages, '-', '-')

    # Get from service by URI, ex: "/redfish/v1"
    if expectedJson is None:
        success, jsonData, status = callResourceURI(URI)
        rsvLogger.debug('%s, %s, %s', success, jsonData, status)
        if not success:
            rsvLogger.error('%s:  URI could not be acquired: %s' % (URI, status))
            counts['failGet'] += 1
            rsvLogger.removeHandler(errh) 
            return False, counts, results, None
        counts['passGet'] += 1
    else:
        jsonData = expectedJson

    # check for @odata mandatory stuff
    # check for version numbering problems
    # check id if its the same as URI
    # check @odata.context instead of local.  Realize that @odata is NOT a "property"
    successPayload, odataMessages = checkPayloadCompliance(URI,jsonData)
    messages.update(odataMessages)
    
    if not successPayload:
        counts['failPayloadError'] += 1
        rsvLogger.error(str(URI) + ':  payload error, @odata property noncompliant',)
        rsvLogger.removeHandler(errh) 
        return False, counts, results, None
    
    if expectedType is None:
        SchemaFullType = jsonData.get('@odata.type')
        if SchemaFullType is None:
            rsvLogger.error(str(URI) + ':  Json does not contain @odata.type',)
            counts['failJsonError'] += 1
            rsvLogger.removeHandler(errh) 
            return False, counts, results, None
    else:
        SchemaFullType = jsonData.get('@odata.type', expectedType) 
    rsvLogger.info(SchemaFullType)

    # Parse @odata.type, get schema XML and its references from its namespace
    SchemaNamespace, SchemaType = getNamespace(SchemaFullType), getType(SchemaFullType)
    if expectedSchema is None:
        SchemaURI = jsonData.get('@odata.context',None)
    else:
        SchemaURI = expectedSchema
    rsvLogger.debug("%s %s", SchemaType, SchemaURI)
       
    success, SchemaSoup, SchemaURI = getSchemaDetails( SchemaNamespace, SchemaURI=SchemaURI)

    if not success:
        rsvLogger.error("validateURI: No schema XML for %s %s",
                        SchemaFullType, SchemaType)
        counts['failSchema'] += 1
        rsvLogger.removeHandler(errh) 
        return False, counts, results, None

    refDict = getReferenceDetails(SchemaSoup)

    rsvLogger.debug(jsonData)
    rsvLogger.debug(SchemaSoup)
    
    successService, serviceSchemaSoup, SchemaServiceURI = getSchemaDetails('metadata','/redfish/v1/$metadata','.xml')
    if successService:
        serviceRefs = getReferenceDetails(serviceSchemaSoup)
        successService, additionalProps = getAnnotations(serviceSchemaSoup, serviceRefs, jsonData)
    
    results[uriName] = (URI, success, counts, messages, errorMessages, SchemaURI, ('assuming ' if expectedType is SchemaFullType else '') + str(SchemaFullType))

    # Fallback typing for properties without types
    # Use string comprehension to get highest type
    if expectedType is SchemaFullType:
        for schema in SchemaSoup.find_all('schema'):
            newNamespace = schema.get('namespace')
            if schema.find('entitytype',attrs={'name': SchemaType}):
                SchemaNamespace = newNamespace
                SchemaFullType = newNamespace + '.' + SchemaType
        rsvLogger.warn('No @odata.type present, assuming highest type %s', SchemaFullType)

    # Attempt to get a list of properties
    propertyList = list()
    success, baseSoup, baseRefs, baseType = True, SchemaSoup, refDict, SchemaFullType
    while success:
        try:
            propertyList.extend(getTypeDetails(
                baseSoup, baseRefs, baseType, 'entitytype'))
            success, baseSoup, baseRefs, baseType = getParentType(baseSoup, baseRefs, baseType, 'entitytype')
        except Exception as ex:
            rsvLogger.exception("Something went wrong")
            rsvLogger.error(URI + ':  Getting type failed for ' + SchemaFullType,)
            counts['exceptionGetType'] += 1
            rsvLogger.removeHandler(errh) 
    for item in propertyList:
        rsvLogger.debug(item[2])
    
    if successService:
        propertyList.extend(additionalProps)

    # Generate dictionary of property info
    for prop in propertyList:
        try:
            propertyDict[prop[2]] = getPropertyDetails(*prop)
        except Exception as ex:
            rsvLogger.exception("Something went wrong")
            rsvLogger.error('%s:  Could not get details on this property' % (prop[2]))
            counts['exceptionGetDict'] += 1
    for key in propertyDict:
        rsvLogger.debug(key)

    # With dictionary of property details, check json against those details
    # rs-assertion: test for AdditionalProperties
    for prop in propertyDict:
        try:
            propMessages, propCounts = checkPropertyCompliance(SchemaSoup, prop, propertyDict[prop], jsonData, refDict)
            messages.update(propMessages)
            counts.update(propCounts)
        except Exception as ex:
            rsvLogger.exception("Something went wrong")
            rsvLogger.error('%s:  Could not finish compliance check on this property: %s, %s' % (prop))
            counts['exceptionPropCompliance'] += 1

    # List all items checked and unchecked
    # current logic does not check inside complex types
    fmt = '%-30s%30s'
    rsvLogger.info('%s, %s', uriName, SchemaType)

    for key in jsonData:
        item = jsonData[key]
        rsvLogger.info(fmt % (
            key, messages[key][3] if key in messages else 'Exists, no schema check'))
        if key not in messages:
            # note: extra messages for "unchecked" properties
            rsvLogger.error('%s: Appears to be an extra property (check inheritance or casing?)', key)
            counts['failAdditional'] += 1
            messages[key] = (item, '-',
                             'Exists',
                             '-')
    for key in messages:
        if key not in jsonData:
            rsvLogger.info(fmt % (key, messages[key][3]))

    rsvLogger.info('%s, %s, %s', SchemaFullType, counts, len(propertyList))
    
    # Get all links available
    links = getAllLinks(jsonData, propertyDict, refDict, context=SchemaURI)

    rsvLogger.debug(links)
    rsvLogger.removeHandler(errh) 
    return True, counts, results, links

##########################################################################
######################          Script starts here              ##########
##########################################################################


if __name__ == '__main__':
    # Logging config
    # logging
    startTick = datetime.now()
    if not os.path.isdir('logs'):
           os.makedirs('logs')
    fmt = logging.Formatter('%(levelname)s - %(message)s')
    fh = logging.FileHandler(datetime.strftime(startTick, "logs/ComplianceLog_%m_%d_%Y_%H%M%S.txt"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    rsvLogger.addHandler(fh)
    rsvLogger.info('System Info: ' + sysDescription)
    rsvLogger.info("RedfishServiceValidator Config details: %s", str(
        (ConfigURI, 'user:' + str(User), SchemaLocation, 'CheckCert' if chkCert else 'no CheckCert', 'localOnly' if localOnly else 'Attempt for Online Schema')))
    rsvLogger.info('Start time: ' + startTick.strftime('%x - %X'))

    # Start main
    status_code = 1
    success, counts, results, xlinks = validateURITree('/redfish/v1', 'ServiceRoot')
    finalCounts = Counter()
    nowTick = datetime.now()
    rsvLogger.info('Elapsed time: ' + str(nowTick-startTick).rsplit('.',1)[0])
    
    # Render html
    htmlStrTop = '<html><head><title>Compliance Test Summary</title>\
            <style>\
            .pass {background-color:#99EE99}\
            .fail {background-color:#EE9999}\
            .warn {background-color:#EEEE99}\
            .button {padding: 12px; display: inline-block}\
            .center {text-align:center;}\
            .log {text-align:left; white-space:pre-wrap; font-size:smaller}\
            .title {background-color:#DDDDDD; border: 1pt solid; font-height: 30px; padding: 8px}\
            .titlesub {padding: 8px}\
            .titlerow {border: 2pt solid}\
            .results {transition: visibility 0s, opacity 0.5s linear; display: none; opacity: 0}\
            .resultsShow {display: block; opacity: 1}\
            body {background-color:lightgrey; border: 1pt solid; text-align:center; margin-left:auto; margin-right:auto}\
            th {text-align:center; background-color:beige; border: 1pt solid}\
            td {text-align:left; background-color:white; border: 1pt solid}\
            table {width:90%; margin: 0px auto;}\
            .titletable {width:100%}\
            </style>\
            </head>'
    htmlStrBodyHeader = '<body><table>\
                <tr><th>##### Redfish Compliance Test Report #####</th></tr>\
                <tr><th>System: ' + ConfigURI + '</th></tr>\
                <tr><th>Description: ' + sysDescription + '</th></tr>\
                <tr><th>User: ' + User + ' ###  \
                SSL Cert Check: ' + str(chkCert) + ' ###  \n\
                Local Only Schema:' + str(localOnly) + ' ###  Local Schema Location :' + SchemaLocation + '</th></tr>\
                <tr><th>Start time: ' + (startTick).strftime('%x - %X') + '</th></tr>\
                <tr><th>Run time: ' + str(nowTick-startTick).rsplit('.',1)[0] + '</th></tr>\
                <tr><th></th></tr>'

    htmlStr = '' 

    rsvLogger.info(len(results))
    for cnt, item in enumerate(results):
        htmlStr += '<tr><td class="titlerow"><table class="titletable"><tr>'
        htmlStr += '<td class="title" style="width:40%"><div>{}</div>\
                <div class="button warn" onClick="document.getElementById(\'resNum{}\').classList.toggle(\'resultsShow\');">Show results</div>\
                </td>'.format(item, cnt, cnt)
        htmlStr += '<td class="titlesub log" style="width:30%"><div><b>URI:</b> {}</div><div><b>XML:</b> {}</div><div><b>type:</b> {}</div></td>'.format(results[item][0],results[item][5],results[item][6])
        htmlStr += '<td style="width:10%"' + \
            ('class="pass"> GET Success' if results[item]
             [1] else 'class="fail"> GET Failure') + '</td>'
        htmlStr += '<td style="width:10%">'

        innerCounts = results[item][2]
        finalCounts.update(innerCounts)
        for countType in innerCounts:
            innerCounts[countType] += 0
            htmlStr += '<div {style}>{p}: {q}</div>'.format(p=countType,
                                             q=innerCounts.get(countType, 0),
                                             style='class="fail log"' if 'fail' in countType or 'exception' in countType else 'class=log')
        htmlStr += '</td></tr>'
        htmlStr += '</table></td></tr>'
        htmlStr += '<tr><td class="results" id=\'resNum{}\'><table><tr><td><table><tr><th> Name</th> <th> Value</th> <th>Type</th> <th>Exists?</th> <th>Success</th> <tr>'.format(cnt)
        if results[item][3] is not None:
            for i in results[item][3]:
                htmlStr += '<tr>'
                htmlStr += '<td>' + str(i) + '</td>'
                for j in results[item][3][i]:
                    if 'PASS' in str(j):
                        htmlStr += '<td class="pass center">' + str(j) + '</td>'
                    elif 'FAIL' in str(j):
                        htmlStr += '<td class="fail center">' + str(j) + '</td>'
                    else:
                        htmlStr += '<td >' + str(j) + '</td>'
                htmlStr += '</tr>'
        htmlStr += '</table></td></tr>'
        if results[item][4] is not None:
            htmlStr += '<tr><td class="fail log">' + str(results[item][4].getvalue()).replace('\n','<br />') + '</td></tr>'
            results[item][4].close()
        htmlStr += '<tr><td>---</td></tr></table></td></tr>'
    htmlStr += '</table></body></html>'

    htmlStrTotal = '<tr><td><div>Final counts: '
    for countType in finalCounts:
        htmlStrTotal += '{p}: {q},   '.format(p=countType, q=finalCounts.get(countType, 0))
    htmlStrTotal += '</div><div class="button warn" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results resultsShow\'};">Expand All</div>'
    htmlStrTotal += '</div><div class="button fail" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results\'};">Collapse All</div>'

    htmlPage = htmlStrTop + htmlStrBodyHeader + htmlStrTotal + htmlStr

    with open(datetime.strftime(startTick, "logs/ComplianceHtmlLog_%m_%d_%Y_%H%M%S.html"), 'w') as f:
        f.write(htmlPage)
    
    fails = 0
    for key in finalCounts:
        if 'fail' in key or 'exception' in key:
            fails += finalCounts[key]

    success = success and not (fails > 0)
    rsvLogger.info(finalCounts)

    if not success:
        rsvLogger.info("Validation has failed: %d problems found", fails)
    else:
        rsvLogger.info("Validation has succeeded.")
        status_code = 0

    sys.exit(status_code)
