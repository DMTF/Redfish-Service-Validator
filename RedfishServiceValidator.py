# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from bs4 import BeautifulSoup
import configparser, glob, requests
import random, string, re
import time, os, sys
from datetime import datetime
from collections import Counter,OrderedDict
from functools import lru_cache
import logging, traceback

# Logging config
startTick = datetime.now()
fmt = logging.Formatter('%(levelname)s - %(message)s')

rsvLogger = logging.getLogger()
rsvLogger.setLevel(logging.DEBUG)

fh = logging.FileHandler(datetime.strftime(startTick,"logs/ComplianceLog_%m_%d_%Y_%H%M%S.txt"))
fh.setLevel(logging.DEBUG)
fh.setFormatter(fmt)
rsvLogger.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
rsvLogger.addHandler(ch)

# Read config info from ini file placed in config folder of tool
config = configparser.ConfigParser()
config.read(os.path.join('.', 'config', 'config.ini'))
useSSL = config.getboolean('Options', 'UseSSL')
ConfigURI = ( 'https' if useSSL else 'http' ) + '://'+config.get('SystemInformation', 'TargetIP')
User = config.get('SystemInformation', 'UserName')
Passwd = config.get('SystemInformation', 'Password')
SchemaLocation = config.get('Options', 'MetadataFilePath')
chkCert = config.getboolean('Options', 'CertificateCheck') and useSSL
localOnly = config.getboolean('Options', 'LocalOnlyMode')

rsvLogger.debug("Config details: %s", str((useSSL,ConfigURI,User,Passwd,SchemaLocation,chkCert,localOnly)))

# Function to GET/PATCH/POST resource URI
# Certificate check is conditional based on input from config ini file
# 
@lru_cache(maxsize=64)
def callResourceURI(URILink):
        """
        Makes a call to a given URI or URL
        
        param arg1: path to URI "/example/1", or URL "http://example.com"
        return: (success boolean, data)
        """
        statusCode = ""
        nonService = 'http' in URILink
        
        URILink = URILink.replace("#", "%23")

        # redfish spec requires no auth for serviceroot calls
        if not nonService:
            noauthchk = \
                    ('/redfish' in URILink and '/redfish/v1' not in URILink) or\
                    URILink in ['/redfish/v1','/redfish/v1/'] or\
                    '/redfish/v1/$metadata' in URILink
            if noauthchk:
                rsvLogger.debug('dont chkauth')
                auth = None
            else:
                auth = (User, Passwd)
        rsvLogger.debug('callingResourceURI: %s', URILink)
        try:
                rsvLogger.propagate = False
                expCode = []
                response = requests.get(ConfigURI+URILink if not nonService else URILink,\
                        auth = auth if not nonService else None, verify=chkCert)
                rsvLogger.propagate = True
                expCode = [200, 204]
                statusCode = response.status_code
                rsvLogger.debug('%s, %s, %s',statusCode, expCode, response.headers)
                if statusCode in expCode:
                    if 'application/json' in response.headers['content-type']:
                        decoded = response.json(object_pairs_hook=OrderedDict)
                    else:
                        decoded = response.text
                    return True, decoded
        except Exception as ex:
                rsvLogger.propagate = True
                rsvLogger.error("Something went wrong: %s", str(ex))
                rsvLogger.error(traceback.format_exc())
        return False, None

# note: Use some sort of re expression to parse SchemaAlias
# ex: #Power.1.1.1.Power , #Power.v1_0_0.Power
def getNamespace(string):
    ret = string.replace('#','').rsplit('.',1)[0]
    return ret
def getType(string):
    return string.replace('#','').rsplit('.',1)[-1]

# Function to parse individual Schema xml file and search for the Alias string
# Returns the content of the xml file on successfully matching the Alias
def getSchemaDetails(SchemaAlias, SchemaURI=None):
        """
        Find Schema file for given Namespace.
        
        param arg1: Schema Namespace, such as ServiceRoot
        param SchemaURI: uri to grab schema, given localOnly is False
        return: a Soup object
        """
        # Note: Add in calls to $metadata, references and URIs, instead of just locally
        if SchemaURI is not None and not localOnly:
            success, data = callResourceURI(SchemaURI)
            if success:
                soup = BeautifulSoup(data, "html.parser")
                return True, soup
            rsvLogger.debug("Fallback to local Schema")

        Alias = getNamespace(SchemaAlias).split('.')[0]
        try:
                filehandle = open(SchemaLocation+'/'+Alias+'_v1.xml', "r")
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
            if item.get('alias', None) is not None:
                refDict[item['alias']] = (item['namespace'], ref['uri'] )
            else:
                refDict[item['namespace']] = (item['namespace'], ref['uri'] )
                refDict[item['namespace'].split('.')[0]] = (item['namespace'], ref['uri'] )
    return refDict
    

# Function to search for all Property attributes in any target schema
# Schema XML may be the initial file for local properties or referenced schema for foreign properties
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
        
        rsvLogger.debug("Schema is %s, %s, %s", SchemaAlias, SchemaType, SchemaNamespace)

        innerschema = soup.find('schema',attrs={'namespace':SchemaNamespace})
          
        if innerschema is None:
            Alias = SchemaAlias.split('.')[0]
            rsvLogger.debug ( refs.get(Alias,None ))
            success, soup = getSchemaDetails(*refs.get(getNamespace(Alias),(Alias,None)))
            if not success:
                rsvLogger.error("innerSchemaSoup doesn't exist...? %s, %s", getNamespace(SchemaAlias), Alias)
                raise Exception('getTypeDetails: ' + SchemaNamespace + ' ' + SchemaAlias)
            refs = getReferenceDetails(soup)
            innerschema = soup.find('schema',attrs={'namespace':SchemaNamespace})
            
        for element in innerschema.find_all(tagType,attrs={'name': SchemaType}):
            rsvLogger.debug("___")
            rsvLogger.debug(element['name'])
            rsvLogger.debug(element.attrs)
            rsvLogger.debug(element.get('basetype',None))
            # note: Factor in navigationproperties properly
            #       what about EntityContainers?
            usableProperties = element.find_all('property')
            usableNavProperties = element.find_all('navigationproperty')
            baseType = element.get('basetype',None)
            
            if baseType is not None:
                PropertyList.extend( getTypeDetails(soup, refs, baseType, tagType) )

            for innerelement in usableProperties + usableNavProperties:
                rsvLogger.debug(innerelement['name'])
                rsvLogger.debug(innerelement['type'])
                rsvLogger.debug(innerelement.attrs)
                newProp = innerelement['name']
                if SchemaAlias:
                    newProp = SchemaAlias + ':' + newProp
                rsvLogger.debug("ADDING :::: %s", newProp) 
                if newProp not in PropertyList: 
                    PropertyList.append( newProp )

        return PropertyList

# Function to retrieve the detailed Property attributes and store in a dictionary format
# The attributes for each property are referenced through various other methods for compliance check
def getPropertyDetails(soup, refs, PropertyItem, tagType = 'entitytype'):
        """
        Get dictionary of tag attributes for properties given, including basetypes.

        param arg1: soup data
        param arg2: list of properties as strings
        param tagtype: type of Tag, such as EntityType or ComplexType
        """
        propEntry = dict()

        propOwner, propChild = PropertyItem.split(':')[0], PropertyItem.split(':')[-1]

        SchemaNamespace = getNamespace(propOwner)
        SchemaType = getType(propOwner)
         
        rsvLogger.debug('___')
        rsvLogger.debug('%s, %s', SchemaNamespace, PropertyItem)
        
        propSchema = soup.find('schema',attrs={'namespace':SchemaNamespace})

        if propSchema is None:
            success, innerSoup = getSchemaDetails(*refs[SchemaNamespace.split('.')[0]]) 
            if not success:
                rsvLogger.error("innerSoup doesn't exist...? %s", SchemaNamespace)
                raise Exception('getPropertyDetails')
            innerRefs = getReferenceDetails(innerSoup)
            propSchema = innerSoup.find('schema',attrs={'namespace':SchemaNamespace})
        else:
            innerSoup = soup
            innerRefs = refs

        propEntity = propSchema.find(tagType,attrs={'name':SchemaType})
        propTag = propEntity.find('property',attrs={'name':propChild})
        
        propEntry['isNav'] = False
        
        if propTag is None:
            propTag = propEntity.find('navigationproperty',attrs={'name':propChild})
            propEntry['isNav'] = True
        propAll = propTag.find_all()

        propEntry['attrs'] = propTag.attrs
        
        for tag in propAll:
            propEntry[tag['term']] = tag.attrs
        rsvLogger.debug(propEntry)
        
        propType = propTag.get('type',None)

        while propType is not None:
            rsvLogger.debug("HASTYPE")
            TypeNamespace = getNamespace(propType)
            typeSpec = getType(propType)

            rsvLogger.debug('%s, %s', TypeNamespace, propType)
            # Type='Collection(Edm.String)'
            if re.match('Collection(.*)',propType) is not None:
                propType = propType.replace('Collection(', "")
                propType = propType.replace(')', "")
                propEntry['isCollection'] = propType
                # Note : this needs work
                continue
            if 'Edm' in propType:
                propEntry['realtype'] = propType
                break
            
            if TypeNamespace.split('.')[0] != SchemaNamespace.split('.')[0]:
                success, typeSoup = getSchemaDetails(*refs[TypeNamespace])
            else:
                success, typeSoup = True, innerSoup
            
            if not success:
                rsvLogger.error("innerSoup doesn't exist...? %s", SchemaNamespace)
                raise Exception("getPropertyDetails: no such soup for" + SchemaNamespace + TypeNamespace)
                continue

            typeRefs = getReferenceDetails(typeSoup) 
            typeSchema = typeSoup.find('schema',attrs={'namespace':TypeNamespace})
            typeSimpleTag = typeSchema.find('typedefinition',attrs={'name':typeSpec})
            typeComplexTag = typeSchema.find('complextype',attrs={'name':typeSpec}) 
            typeEnumTag = typeSchema.find('enumtype',attrs={'name':typeSpec}) 
            typeEntityTag = typeSchema.find('entitytype',attrs={'name':typeSpec})
            
            if typeSimpleTag is not None:
                propType = typeSimpleTag.get('underlyingtype',None)
                continue
            elif typeComplexTag is not None:
                rsvLogger.debug("go DEEP")
                propList = getTypeDetails(typeSoup, typeRefs, propType, tagType='complextype') 
                rsvLogger.debug(propList)
                propDict = { item: getPropertyDetails(typeSoup, typeRefs, item, tagType='complextype' ) for item in propList }
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
                # consider this, is this only for navigation checking?
                propEntry['realtype'] = 'entity'
                propEntry['typeprops'] = dict()
                rsvLogger.debug ("typeEntityTag found %s",propTag['name'])
                break
            else:
                rsvLogger.error("type doesn't exist? %s", propType)
                raise Exception("problem")
                break 
                
        return propEntry


# Function to check compliance of individual Properties based on the attributes retrieved from the schema xml
def checkPropertyCompliance(PropertyDictionary, decoded):
                """
                Given a dictionary of properties, check the validitiy of each item, and return a
                list of counted properties

                param arg1: property dictionary
                param arg2: json payload
                """
                def getTypeInheritance(decoded,tagType='entitytype'):
                    schType = decoded.get('@odata.type', None)
                    schContext = decoded.get('@odata.context', None)
                    success, sch = getSchemaDetails( schType, schContext )
                    if not success:
                        return []
                    schRefs = getReferenceDetails(sch)
                    currentType = schType.replace('#','')
                    allTypes = list()
                    while currentType not in allTypes and currentType is not None:
                        propSchema = sch.find('schema',attrs={'namespace':getNamespace(currentType)})
                        if propSchema is None:
                            success, sch = getSchemaDetails(*schRefs[getNamespace(currentType)])
                            continue
                        propEntity = propSchema.find(tagType,attrs={'name':getType(currentType)})
                        allTypes.append(currentType)
                        if propEntity is None:
                            break
                        currentType = propEntity.get('basetype',None) 
                    return allTypes
                
                resultList = OrderedDict()
                counts = Counter()

                for key in PropertyDictionary:
                     
                    rsvLogger.info(key)
                    item = key.split(':')[-1]
                    
                    propValue = decoded.get(item, 'xxDoesNotExist') 

                    rsvLogger.info("\tvalue: %s", propValue)

                    propAttr = PropertyDictionary[key]['attrs']

                    propType = propAttr.get('type',None)
                    propRealType = PropertyDictionary[key].get('realtype',None) 

                    rsvLogger.info("\thas Type: %s %s", propType, propRealType)
                    
                    propExists = not (propValue == 'xxDoesNotExist')
                    propNotNull = propExists and propValue is not '' and propValue is not None and propValue is not 'None'
                    
                    if 'Oem' in key:
                        rsvLogger.info('\tOem is skipped')
                        counts['skipOem'] += 1
                        resultList[item] = ('-', '-',\
                                'Exists' if propExists else 'DNE', 'SkipOEM')
                        continue
                
                    propMandatory = False                    
                    propMandatoryPass = True
                    if 'Redfish.Required' in PropertyDictionary[key]:
                        propMandatory = True
                        propMandatoryPass = True if propExists else False
                        rsvLogger.info("\tMandatory Test: %s", 'OK' if propMandatoryPass else 'FAIL')
                    else:
                        rsvLogger.info("\tis Optional")
                        if not propExists:
                            rsvLogger.info("\tprop Does not exist, skip...")
                            counts['skipOptional'] += 1
                            resultList[item] = (propValue, (propType, propRealType),\
                                    'Exists' if propExists else 'DNE',\
                                    'SkipOptional')
                            continue

                    propNullable = propAttr.get('nullable',None)
                    propNullablePass = True
                    
                    if propNullable is not None:
                        propNullablePass = (propNullable == 'true') or not propExists or propNotNull
                        rsvLogger.info("\tis Nullable: %s %s", propNullable, propNotNull)
                        rsvLogger.info("\tNullability test: %s", 'OK' if propNullablePass else 'FAIL')

                    propPermissions = propAttr.get('Odata.Permissions',None)
                    if propPermissions is not None:
                        propPermissionsValue = propPermissions['enummember']
                        rsvLogger.info("\tpermission %s", propPermissionsValue)

                    validPatternAttr = PropertyDictionary[key].get('Validation.Pattern',None)  
                    validMinAttr = PropertyDictionary[key].get('Validation.Minimum',None)  
                    validMaxAttr = PropertyDictionary[key].get('Validation.Maximum',None)   
                    
                    paramPass = True
                    propValue = None if propValue == 'xxDoesNotExist' else propValue
                    
                    # Note: consider http://docs.oasis-open.org/odata/odata-csdl-xml/v4.01/csprd01/odata-csdl-xml-v4.01-csprd01.html#_Toc472333112
                    # Note: make sure it checks each one
                    propCollectionType = PropertyDictionary[key].get('isCollection',None)  
                    if propCollectionType is not None:
                        # note: handle collections correctly, this needs a nicer printout
                        rsvLogger.info("\tis Collection")
                        resultList[item] = ('Collection, size: ' + str(len(propValue)), (propType, propRealType),\
                                'Exists' if propExists else 'DNE',\
                                '...')
                        propValueList = propValue
                    else:
                        propValueList = [propValue]
                    # note: make sure we don't enter this on null values, some of which are OK!
                    if propRealType is not None and propExists and propNotNull:
                        cnt = 0
                        for val in propValueList: 
                            paramPass = False
                            if propRealType == 'Edm.Boolean':
                                if str(val).lower() == "true" or str(val).lower() == "false":
                                     paramPass = True       

                            elif propRealType == 'Edm.DateTimeOffset':
                                # note: find out why this might be wrong
                                match = re.match('.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])',str(val))
                                if match:
                                    paramPass = True

                            elif propRealType == 'Edm.Int16' or propRealType == 'Edm.Int32' or\
                                    propRealType == 'Edm.Int64' or propRealType == 'Edm.Int' or\
                                    propRealType == 'Edm.Decimal' or propRealType == 'Edm.Double':
                                paramPass = str(val).isnumeric()
                                # note: check if val can be string, if it can't this might have trouble
                                if 'Int' in propRealType:
                                    paramPass = paramPass and '.' not in str(val)
                                if validMinAttr is not None:
                                    paramPass = paramPass and int(validMinAttr['int']) <= int(val)
                                if validMaxAttr is not None:
                                    paramPass = paramPass and int(validMaxAttr['int']) >= int(val)

                            elif propRealType == 'Edm.Guid':
                                match = re.match("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",str(val))
                                if match:
                                    paramPass = True

                            elif propRealType == 'Edm.String':
                                if validPatternAttr is not None:
                                    pattern = validPatternAttr.get('string','')
                                    match = re.fullmatch(pattern,val)
                                    paramPass = match is not None
                                else:
                                    paramPass = True 

                            else:
                                if propRealType == 'complex':                           
                                    rsvLogger.info('\t***going into Complex %s', PropertyDictionary[key]['typeprops'])
                                    complexResultList, complexCounts = checkPropertyCompliance( PropertyDictionary[key]['typeprops'], val)
                                    rsvLogger.info('\t***out of Complex')
                                    rsvLogger.info('complex %s',complexCounts)
                                    counts.update(complexCounts)
                                    counts['complex'] += 1
                                    resultList[item] = ('ComplexDictionary' + (('#'+str(cnt)) if len(propValueList) > 1 else ''), (propType, propRealType),\
                                            'Exists' if propExists else 'DNE',\
                                            'complex')
                                    for complexKey in complexResultList:
                                        resultList[item + '.'  + complexKey + (('#'+str(cnt)) if len(propValueList) > 1 else '')]  = complexResultList[complexKey]
                                    continue

                                elif propRealType == 'enum':
                                    # note: Make sure to check lowercase
                                    if val.lower() in PropertyDictionary[key]['typeprops']:
                                        paramPass = True        

                                elif propRealType == 'entity':
                                    success, data = callResourceURI(val['@odata.id'])
                                    rsvLogger.debug('%s, %s, %s', success, propType, data)
                                    if success:
                                        paramPass = success

                                        listType = getTypeInheritance(data)
                                        #paramPass = propType in listType or propCollectionType in listType
                                    else:
                                        paramPass = '#' in val['@odata.id']
                                # Note: Actually check if this is correct

                            resultList[item + (('#'+str(cnt)) if len(propValueList) > 1 else '')] = (val, (propType, propRealType),\
                                    'Exists' if propExists else 'DNE',\
                                    'PASS' if paramPass and propMandatoryPass and propNullablePass else 'FAIL')
                            cnt += 1
                            if paramPass and propNullablePass and propMandatoryPass:
                                counts['pass'] += 1
                                rsvLogger.info ("\tSuccess")
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
                                rsvLogger.info ("\tFAIL")
                
                return resultList, counts

# Function to collect all links in current resource schema
def     getAllLinks(jsonData, propDict):
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
                insideItem = jsonData.get(item, None)
                if insideItem is not None:
                    if propDict[key].get('isCollection',None) is not None:
                        cnt = 0
                        for listItem in insideItem:
                            linkList[getType(propDict[key]['isCollection'])+'#'+str(cnt)] = listItem.get('@odata.id', None)
                            cnt += 1
                    else:
                        linkList[getType(propDict[key]['attrs']['name'])] = insideItem.get('@odata.id', None)
        for key in propDict:
            item = getType(key).split(':')[-1]
            if propDict[key]['realtype'] == 'complex':
                if jsonData.get(item,None) is not None:
                    if propDict[key].get('isCollection',None) is not None:
                        for listItem in jsonData[item]:
                            linkList.update( getAllLinks(listItem, propDict[key]['typeprops']))
                    else: 
                        linkList.update( getAllLinks(jsonData[item], propDict[key]['typeprops']))
        return linkList

def checkAnnotationCompliance(decoded):
    for key in [k for k in decoded if '@' in k]:
        rsvLogger.info(key)

# get rid of AllLinks
allLinks = set()
def validateURI (URI, uriName=''):
    
    # Initial startup here
    rsvLogger.info("\n*** %s, %s", uriName, URI)
    counts = Counter()
    results = OrderedDict()
    
    results[uriName] = (URI, False, counts, None)

    # Get from service by URI, ex: "/redfish/v1"
    success, jsonData = callResourceURI(URI)

    if not success:
        rsvLogger.error("validateURI: Get URI failed.")
        counts['failGet'] += 1
        return False, counts, results
    
    counts['passGet'] += 1

    checkAnnotationCompliance(jsonData) 
    # check for @odata mandatory stuff
    # check for version numbering problems
    # check id if its the same as URI
    # check @odata.context instead of local 

    SchemaFullType = jsonData.get('@odata.type',None)
    if SchemaFullType is None:
        rsvLogger.error("validateURI: Json does not contain type, is error?")
        counts['failJsonError'] += 1
        return False, counts, results

    rsvLogger.info(SchemaFullType) 

    # Parse @odata.type, get schema XML and its references from its namespace

    SchemaType = getType(SchemaFullType)
    SchemaNamespace = getNamespace(SchemaFullType)
    SchemaURI = jsonData.get('@odata.context', None)
    
    SchemaURI = SchemaURI.split('#')[0]

    rsvLogger.debug("%s %s", SchemaType, SchemaURI)
    
    success, SchemaSoup = getSchemaDetails(SchemaNamespace, SchemaURI=SchemaURI)
        
    if success:
        refDict = getReferenceDetails(SchemaSoup)
        if SchemaType in refDict:
            success, SchemaSoup = getSchemaDetails(SchemaNamespace, SchemaURI=refDict[getNamespace(SchemaType)][1])
    else:
        success, SchemaSoup = getSchemaDetails(SchemaNamespace) 
        if not success:
            success, SchemaSoup = getSchemaDetails(SchemaType)
        if success:
            refDict = getReferenceDetails(SchemaSoup)
    
    if not success: 
        rsvLogger.error("validateURI: No schema XML for %s %s", SchemaFullType, SchemaType)
        counts['failSchema'] += 1
        return False, counts, results
    
    refDict = getReferenceDetails(SchemaSoup)
        
    rsvLogger.debug(jsonData)
    rsvLogger.debug(SchemaSoup)
   
    # Attempt to get a list of properties
    try:
        propertyList = getTypeDetails(SchemaSoup, refDict, SchemaFullType, 'entitytype')
    except Exception as ex:
        rsvLogger.error(traceback.format_exc())
        counts['exceptionGetType'] += 1
        return False, counts, results
    
    rsvLogger.debug(propertyList)

    # Generate dictionary of property info
    try:
        propertyDict = OrderedDict(( item, getPropertyDetails(SchemaSoup, refDict, item)) for item in propertyList )
    except Exception as ex:
        rsvLogger.error(traceback.format_exc())
        counts['exceptionGetDict'] += 1
        return False, counts, results
    
    rsvLogger.debug(propertyDict)
   
    # With dictionary of property details, check json against those details
    try:
        messages, checkCounts = checkPropertyCompliance(propertyDict, jsonData)
    except Exception as ex:
        rsvLogger.error(traceback.format_exc())
        counts['exceptionPropCompliance'] += 1
        return False, counts, results
   
    # List all items checked and uncheckedi
    # current logic does not check inside complex types
    fmt = '%-20s%20s'
    rsvLogger.info('%s, %s', uriName, SchemaType)

    for key in jsonData:
        item = jsonData[key]
        rsvLogger.info(fmt % (key, 'Exists And Checks' if key in messages else 'Exists, no schema check'))
        if key not in messages:
            # note: extra messages for "unchecked" properties
            messages[key] = (item, '-',\
                    'Exists',\
                    '-')
    for key in messages:
        if key not in jsonData:
            rsvLogger.info("Checking: %s %s", key, messages[key][3])

    # Update counts, then commit results
    counts.update(checkCounts)

    rsvLogger.info('%s, %s, %s', SchemaFullType, counts, len(propertyList))
    
    results[uriName] = (URI, success, counts, messages)

    # Get all links available
    links = getAllLinks(jsonData, propertyDict)
    
    rsvLogger.debug(links)
    
    for linkName in links:
        if links[linkName] in allLinks:
            counts['repeat'] += 1
            continue
        
        allLinks.add(links[linkName])
        
        success, linkCounts, linkResults = validateURI(links[linkName], uriName + ' -> ' + linkName)
        if not success:
            counts['unvalidated'] += 1
        rsvLogger.info('%s, %s', linkName, linkCounts)
        results.update(linkResults)

    return True, counts, results

##########################################################################
######################          Script starts here              ######################
##########################################################################

if __name__ == '__main__':
    # Rewrite here
    status_code = 1
    success, counts, results = validateURI ('/redfish/v1','ServiceRoot')
   
    finalCounts = Counter()

    nowTick = datetime.now()

    if not success:
        rsvLogger.info("Validation has failed.")
        sys.exit(1)    

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
                <tr><th>User: '+ User +'</th></tr>\
                <tr><th>Start time: ' + str(startTick) + '</th></tr>\
                <tr><th>Run time: ' + str(nowTick - startTick) +'</th></tr>\
                <tr><th></th></tr>'

    htmlStr2 = '' + htmlStr

    cnt = 1
    rsvLogger.info (len(results))
    for item in results:
        cnt += 1    
        htmlStr += '<tr><td class="titlerow"><table class="titletable"><tr>'
        htmlStr += '<td class="title" style="width:40%">' + item + '</td>'
        htmlStr += '<td style="width:20%">' + str(results[item][0]) + '</td>'
        htmlStr += '<td style="width:10%"' + ('class="pass"> PASS' if results[item][1] else 'class="fail"> FAIL') + '</td>'
        htmlStr += '<td>'
        innerCounts = results[item][2]
        finalCounts.update(innerCounts)
        for countType in innerCounts:
            innerCounts[countType] += 0 
            htmlStr += '{p}: {q},   '.format(p=countType,q=innerCounts.get(countType,0))
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
        htmlStr += '<tr><td>---</td></tr>'
    htmlStr += '</table></body></html>'
    htmlStr += '</table></body></html>'

    with open(datetime.strftime(startTick,"logs/ComplianceHtmlLog_%m_%d_%Y_%H%M%S.html"),'w') as f:
        f.write(htmlStr)
    
    rsvLogger.info(finalCounts)
    sys.exit(0)

