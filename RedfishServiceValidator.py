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

# Read config info from ini file placed in config folder of tool
config = configparser.ConfigParser()
config.read(os.path.join('.', 'config', 'config.ini'))
useSSL = config.getboolean('Options', 'UseSSL')
ConfigURI = ( 'https' if useSSL else 'http' ) + '://'+config.get('SystemInformation', 'TargetIP')
User = config.get('SystemInformation', 'UserName')
Passwd = config.get('SystemInformation', 'Password')
SchemaLocation = config.get('Options', 'MetadataFilePath')
chkCert = config.getboolean('Options', 'CertificateCheck') and useSSL
getOnly = config.getboolean('Options', 'GetOnlyMode')
debug = 0

if debug:
    print("Config details:" + str((useSSL,ConfigURI,User,Passwd,SchemaLocation,chkCert,getOnly)))

# Function to GET/PATCH/POST resource URI
# Certificate check is conditional based on input from config ini file
# 
def callResourceURI(URILink, Method = 'GET', payload = None ):
        """
        Makes a call to a given URI
        
        param arg1: path to URI "/example/1"
        param Method: http message type, default 'GET'
        param payload: data for PATCH
        return: (success boolean, data)
        """

        URILink = URILink.replace("#", "%23")
        statusCode = ""

        noauthchk = \
                ('/redfish' in URILink and '/redfish/v1' not in URILink) or\
                URILink in ['/redfish/v1','/redfish/v1/'] or\
                '/redfish/v1/$metadata' in URILink
        if noauthchk:
            print('dont chkauth')
            auth = None
        try:
                expCode = []
                if Method == 'GET' or Method == 'ReGET':
                        response = requests.get(ConfigURI+URILink, auth = (User, Passwd), verify=chkCert)
                        expCode = [200, 204]
                elif Method == 'PATCH':
                        response = requests.patch(ConfigURI+URILink, data = payload, auth = (User, Passwd),verify=chkCert)
                        expCode = [200, 204, 400, 405]
                statusCode = response.status_code
                if debug:
                    print(Method, statusCode, expCode, response.headers)
                if statusCode in expCode:
                    if 'application/json' in response.headers['content-type']:
                        decoded = response.json(object_pairs_hook=OrderedDict)
                    else:
                        decoded = response.text
                    return True, decoded
        except Exception as ex:
                print("Something went wrong: ", ex)
        return False, None

# note: Use some sort of re expression to parse SchemaAlias
# ex: #Power.1.1.1.Power , #Power.v1_0_0.Power
def getNamespace(string):
    ret = string.rsplit('.',1)[0].replace('#','')
    retTo = ret.split('.')
    if len(retTo) <= 3:
        return ret
    return retTo[0] + '.' + 'v' + retTo[1] + '_' + retTo[2] + '_' + retTo[3]
def getType(string):
    return string.rsplit('.',1)[-1].replace('#','')

# Function to parse individual Schema xml file and search for the Alias string
# Returns the content of the xml file on successfully matching the Alias
@lru_cache(maxsize=64)
def getSchemaDetails(SchemaAlias, SchemaURI=None):
        """
        Find Schema file for given Namespace.
        
        param arg1: Schema Namespace, such as ServiceRoot
        param SchemaURI: uri to grab schema
        return: a Soup object
        """
        # Note: Add in calls to $metadata, references and URIs, instead of just locally
        if SchemaURI is not None:
            success, data = callResourceURI(SchemaURI)
            if success:
                soup = BeautifulSoup(data, "html.parser")
                return True, soup
            else:
                return False, None

        Alias = getNamespace(SchemaAlias).split('.')[0]
        try:
                filehandle = open(SchemaLocation+'/'+Alias+'_v1.xml', "r")
                filedata = filehandle.read()
                filehandle.close()
                soup = BeautifulSoup(filedata, "html.parser")
                parentTag = soup.find('edmx:dataservices')
                for child in parentTag.find_all('schema', limit=1):
                        SchemaNamespace = child['namespace']
                        FoundAlias = SchemaNamespace.split(".")[0]
                        if FoundAlias == Alias:
                                return True, soup
        except Exception as ex:
                print("Something went wrong: ", ex)
        return False, None 

# Function to search for all Property attributes in any target schema
# Schema XML may be the initial file for local properties or referenced schema for foreign properties
def getTypeDetails(soup, SchemaAlias, tagType):
        """
        Gets list of surface level properties for a given SchemaAlias,
        including base type inheritance.
        
        param arg1: soup
        param arg2: SchemaAlias string
        param arg3: tag of Type, which can be EntityType or ComplexType...
        return: list of properties as strings
        """
        PropertyList = list()

        SchemaType = getType(SchemaAlias)
        SchemaNamespace = getNamespace(SchemaAlias)

        if debug:
            print("Schema is", SchemaAlias, SchemaType, SchemaNamespace)

        innerschema = soup.find('schema',attrs={'namespace':SchemaNamespace})
          
        if innerschema is None:
            print("innerSchema doesn't exist...?", SchemaNamespace)
            raise Exception('getTypeDetails: no such soup for:' + SchemaNamespace)

        for element in innerschema.find_all(tagType,attrs={'name': SchemaType}):
            if debug:
                print("___")
                print(element['name'])
                print(element.attrs)
                print(element.get('basetype',None))
            # note: Factor in navigationproperties properly
            #       what about EntityContainers?
            usableProperties = element.find_all('property')
            usableNavProperties = element.find_all('navigationproperty')
            baseType = element.get('basetype',None)
            
            if baseType is not None:
                if getNamespace(baseType) != SchemaNamespace.split('.')[0]:
                    success, InnerSchemaSoup = getSchemaDetails(getNamespace(baseType))
                    if not success:
                        raise Exception('getTypeDetails: ' + SchemaNamespace + ' ' + baseType)
                    PropertyList.extend( getTypeDetails(InnerSchemaSoup, baseType, tagType)  )
                else: 
                    PropertyList.extend( getTypeDetails(soup, baseType, tagType ) )

            for innerelement in usableProperties + usableNavProperties:
                if debug:
                    print(innerelement['name'])
                    print(innerelement['type'])
                    print(innerelement.attrs)
                newProp = innerelement['name']
                if SchemaAlias:
                    newProp = SchemaAlias + ':' + newProp
                if debug:
                    print("ADDING ::::", newProp) 
                if newProp not in PropertyList: 
                    PropertyList.append( newProp )

        return PropertyList

# Function to retrieve the detailed Property attributes and store in a dictionary format
# The attributes for each property are referenced through various other methods for compliance check
def getPropertyDetails(soup, PropertyList, tagType = 'entitytype'):
        """
        Get dictionary of tag attributes for properties given, including basetypes.

        param arg1: soup data
        param arg2: list of properties as strings
        param tagtype: type of Tag, such as EntityType or ComplexType
        """
        PropertyDictionary = OrderedDict() 
         
        for prop in PropertyList:
            PropertyDictionary[prop] = dict()
            
            propOwner, propChild = prop.split(':')[0], prop.split(':')[-1]

            SchemaNamespace = getNamespace(propOwner)
            SchemaType = getType(propOwner)
             
            if debug:
                print('___')
                print(SchemaNamespace, prop)
            
            propSchema = soup.find('schema',attrs={'namespace':SchemaNamespace})

            if propSchema is None:
                refs=soup.find_all('edmx:reference')
                success, innerSoup = getSchemaDetails(SchemaNamespace) 
                if not success:
                    raise Exception('getPropertyDetails')
                propSchema = innerSoup.find('schema',attrs={'namespace':SchemaNamespace})

            propEntity = propSchema.find(tagType,attrs={'name':SchemaType})
            propTag = propEntity.find('property',attrs={'name':propChild})
            
            PropertyDictionary[prop]['isNav'] = False
            
            if propTag is None:
                propTag = propEntity.find('navigationproperty',attrs={'name':propChild})
                PropertyDictionary[prop]['isNav'] = True
            propAll = propTag.find_all()

            PropertyDictionary[prop]['attrs'] = propTag.attrs
            
            for tag in propAll:
                PropertyDictionary[prop][tag['term']] = tag.attrs
            if debug:
                print(PropertyDictionary[prop])
            
            propType = propTag.get('type',None)

            while propType is not None:
                if debug:
                    print("HASTYPE")
                TypeNamespace = getNamespace(propType)
                typeSpec = getType(propType)

                if debug:
                    print(TypeNamespace, propType)
                # Type='Collection(Edm.String)'
                if re.match('Collection(.*)',propType) is not None:
                    propType = propType.replace('Collection(', "")
                    propType = propType.replace(')', "")
                    PropertyDictionary[prop]['isCollection'] = propType
                    # Note : this needs work
                    continue
                if 'Edm' in propType:
                    PropertyDictionary[prop]['realtype'] = propType
                    break
                
                success, typeSoup = getSchemaDetails(TypeNamespace)
                
                if not success:
                    raise Exception("getPropertyDetails: no such soup for" + SchemaNamespace + TypeNamespace)
                    continue
                
                typeSchema = typeSoup.find('schema',attrs={'namespace':TypeNamespace})
                typeSimpleTag = typeSchema.find('typedefinition',attrs={'name':typeSpec})
                typeComplexTag = typeSchema.find('complextype',attrs={'name':typeSpec}) 
                typeEnumTag = typeSchema.find('enumtype',attrs={'name':typeSpec}) 
                typeEntityTag = typeSchema.find('entitytype',attrs={'name':typeSpec})
                
                if typeSimpleTag is not None:
                    propType = typeSimpleTag.get('underlyingtype',None)
                    continue
                elif typeComplexTag is not None:
                    if debug:
                        print("go DEEP")
                    propList = getTypeDetails(typeSoup, propType, tagType='complextype') 
                    if debug:
                        print(propList)
                    propDict = getPropertyDetails(typeSoup, propList, tagType='complextype' ) 
                    if debug:
                        print(propDict)
                    PropertyDictionary[prop]['realtype'] = 'complex'
                    PropertyDictionary[prop]['typeprops'] = propDict
                    break
                elif typeEnumTag is not None:
                    PropertyDictionary[prop]['realtype'] = 'enum'
                    PropertyDictionary[prop]['typeprops'] = list() 
                    for MemberName in typeEnumTag.find_all('member'):
                        PropertyDictionary[prop]['typeprops'].append(MemberName['name'].lower())
                    break
                elif typeEntityTag is not None:
                    # consider this, is this only for navigation checking?
                    PropertyDictionary[prop]['realtype'] = 'entity'
                    PropertyDictionary[prop]['typeprops'] = dict()
                    if debug:
                        print ("typeEntityTag found",propTag['name'])
                    break
                else:
                    raise Exception("problem")
                    break 
                
        return PropertyDictionary

# Function to check compliance of individual Properties based on the attributes retrieved from the schema xml
def checkPropertyCompliance(PropertyDictionary, decoded):
                """
                Given a dictionary of properties, check the validitiy of each item, and return a
                list of counted properties

                param arg1: property dictionary
                param arg2: json payload
                """
                def getTypeInheritance(SchemaAlias,tagType='entitytype'):
                    success, sch = getSchemaDetails(SchemaAlias)
                    currentType = SchemaAlias.replace('#','')
                    allTypes = list()
                    while currentType not in allTypes and currentType is not None:
                        sNameSpace = getNamespace(currentType)
                        sType = getType(currentType)
                        propSchema = sch.find('schema',attrs={'namespace':getNamespace(currentType)})
                        if propSchema is None:
                            success, sch = getSchemaDetails(currentType)
                            continue
                        propEntity = propSchema.find(tagType,attrs={'name':getType(currentType)})
                        allTypes.append(currentType)
                        currentType = propEntity.get('basetype',None) 
                    return allTypes

                
                resultList = OrderedDict()
                counts = Counter()

                for key in PropertyDictionary:
                     
                    print(key)
                    item = key.split(':')[-1]
                    
                    if 'Oem' in key:
                        print('\tOem is skipped')
                        counts['skipOem'] += 1
                        resultList[item] = (key, '-', '-', '-','-','SkipOEM')
                        continue
                    
                    propValue = decoded.get(item, 'xxDoesNotExist') 

                    print("\tvalue:", propValue)

                    propAttr = PropertyDictionary[key]['attrs']

                    propType = propAttr.get('type',None)
                    propRealType = PropertyDictionary[key].get('realtype',None) 

                    print("\thas Type:", propType, propRealType)
                    
                    propExists = not (propValue == 'xxDoesNotExist')
                    propNotNull = propExists and (propValue is not '' or propValue is not None)
                
                    propMandatory = False                    
                    propMandatoryPass = True
                    if 'Redfish.Required' in PropertyDictionary[key]:
                        propMandatory = True
                        propMandatoryPass = True if propExists else False
                        print("\tMandatory Test:", 'OK' if propMandatoryPass else 'FAIL')
                    else:
                        print("\tis Optional")
                        if not propExists:
                            print("\tprop Does not exist, skip...")
                            counts['skipOptional'] += 1
                            resultList[item] = (key, propValue, propType, propRealType,\
                                    'Exists' if propExists else 'Missing',\
                                    'SkipOptional')
                            continue

                    propNullable = propAttr.get('nullable',None)
                    propNullablePass = True
                    
                    if propNullable is not None:
                        propNullablePass = (propNullable == 'true') or not propExists or propNotNull
                        print("\tis Nullable:", propNullable, propNotNull)
                        print("\tNullability test:", 'OK' if propNullablePass else 'FAIL')

                    propPermissions = propAttr.get('Odata.Permissions',None)
                    if propPermissions is not None:
                        propPermissionsValue = propPermissions['enummember']
                        print("\tpermission", propPermissionsValue)

                    validPatternAttr = PropertyDictionary[key].get('Validation.Pattern',None)  
                    validMinAttr = PropertyDictionary[key].get('Validation.Minimum',None)  
                    validMaxAttr = PropertyDictionary[key].get('Validation.Maximum',None)   
                    
                    paramPass = True
                    propValue = None if propValue == 'xxDoesNotExist' else propValue
                    
                    # Note: consider http://docs.oasis-open.org/odata/odata-csdl-xml/v4.01/csprd01/odata-csdl-xml-v4.01-csprd01.html#_Toc472333112
                    # Note: make sure it checks each one
                    propCollectionType = PropertyDictionary[key].get('isCollection',None)  
                    if propCollectionType is not None:
                        print("\tis Collection")
                        propValueList = propValue
                    else:
                        propValueList = [propValue]
                    if propRealType is not None and propExists:
                        for val in propValueList: 
                            paramPass = False
                            if propRealType == 'Edm.Boolean':
                                if str(val).lower() == "true" or str(val).lower() == "false":
                                     paramPass = True       

                            elif propRealType == 'Edm.DateTimeOffset':
                                match = re.match('.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])',str(val))
                                if match:
                                    paramPass = True

                            elif propRealType == 'Edm.Int16' or propRealType == 'Edm.Int32' or\
                                    propRealType == 'Edm.Int64' or propRealType == 'Edm.Int' or\
                                    propRealType == 'Edm.Decimal' or propRealType == 'Edm.Double':
                                paramPass = str(val).isnumeric()
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
                                    print('going into Complex')
                                    complexResultList, complexCounts = checkPropertyCompliance( PropertyDictionary[key]['typeprops'], val)
                                    print('out of Complex')
                                    print('complex',complexCounts)
                                    counts.update(complexCounts)
                                    counts['complex'] += 1
                                    resultList[item] = (key, val, propType, propRealType,\
                                            'Exists' if propExists else 'Missing',\
                                            'complex')
                                    for complexKey in complexResultList:
                                        resultList[item + '.'  + complexKey] = complexResultList[complexKey]
                                    continue

                                elif propRealType == 'enum':
                                    # note: Make sure to check lowercase
                                    if val.lower() in PropertyDictionary[key]['typeprops']:
                                        paramPass = True        

                                elif propRealType == 'entity':
                                    success, data = callResourceURI(val['@odata.id'])
                                    if debug:
                                        print (success, propType, data)
                                    if success:
                                        listType = getTypeInheritance(data.get('@odata.type',None))
                                        paramPass = propType in listType or propCollectionType in listType
                                    else:
                                        paramPass = '#' in val['@odata.id']
                                # Note: Actually check if this is correct

                            resultList[item] = (key, val, propType, propRealType,\
                                    'Exists' if propExists else 'Missing',\
                                    paramPass and propMandatoryPass and propNullablePass)

                            if paramPass and propNullablePass and propMandatoryPass:
                                counts['pass'] += 1
                                print ("\tSuccess")
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
                                print ("\tFAIL")
                                input()
                
                return resultList, counts

# Function to collect all links in current resource schema
def     getAllLinks(jsonData, propDict, linkName=''):
        """
        Function that returns all links provided in a given JSON response.
        This result will include a link to itself.

        :param jsonData: json dict
        :return: list of links, including itself
        """
        linkList = OrderedDict()
        for key in propDict:
            item = getType(key).split(':')[-1]
            if propDict[key]['isNav']:
                insideItem = jsonData.get(item, None)
                if insideItem is not None:
                    print(item, insideItem)
                    if propDict[key].get('isCollection',None) is not None:
                        cnt = 0
                        for listItem in insideItem:
                            linkList[getType(key)+'#'+str(cnt)] = listItem.get('@odata.id', None)
                            cnt += 1
                    else:
                        linkList[getType(key)] = insideItem.get('@odata.id', None)
            elif propDict[key]['realtype'] == 'complex':
                if jsonData.get(item,None) is not None:
                    if propDict[key].get('isCollection',None) is not None:
                        for listItem in jsonData[item]:
                            linkList.update( getAllLinks(listItem, propDict[key]['typeprops']))
                    else: 
                        linkList.update( getAllLinks(jsonData[item], propDict[key]['typeprops']))
        return linkList

        if '@odata.id' in jsonData and linkName is not None:
            if debug:                
                print("getLink:",jsonData['@odata.id'])
            linkList[linkName] = jsonData['@odata.id']
        for element in jsonData:
                value = jsonData[element]
                if type(value) is dict:
                    linkList.update( getAllLinks(value, linkName=element))
                if type(value) is list:
                    count = 0
                    for item in value:
                        if type(item) is dict:
                            linkList.update( getAllLinks(item, str(element) + "#" + str(count)))
        return linkList 

allLinks = set()
def validateURI (URI, uriName=''):
    # note: consider, write questions about these
    """
    <Annotation Term="OData.AutoExpand"/>
    <Annotation Term="OData.AutoExpandReferences"/>
    <NavigationProperty Name="Power" Type="Power.Power" ContainsTarget="true">
    <Annotation Term="Redfish.Required"/>
    <Annotation Term="Redfish.RequiredOnCreate"/>
    <Annotation Term="OData.AdditionalProperties"/>
    <Annotation Term="Measures.Unit" String="MiBy"/>

    • Modified schema may constrain a read/write property to be read only.
    • Modified schema may remove properties.
    • Modified schema may change any "Reference Uri" to point to Schema that adheres to the
    modification rules.
    • Other modifications to the Schema shall not be allowed.

    <edmx:Reference Uri="http://redfish.dmtf.org/schemas/v1/RedfishExtensions_v1.xml">
    <edmx:Include Namespace="RedfishExtensions.v1_0_0" Alias="Redfish"/>
    </edmx:Reference>
    """
    print("***", uriName, URI)
    counts = Counter()
    results = OrderedDict()

    success, jsonData = callResourceURI(URI)
    

    if not success:
        print("validateURI: Get URI failed.")
        counts['failGet'] += 1
        counts[URI] += 1
        results[uriName] = (URI, success, counts, None)
        return False, counts, results
    
    counts['passGet'] += 1
   
    # check for @odata mandatory stuff
    # check id if its the same as URI
    # check @odata.context instead of local 
    SchemaFullType = jsonData.get('@odata.type',None)
    if SchemaFullType is None:
        print("validateURI: Json does not contain type, is error?")
        counts['failJsonError'] += 1
        counts[URI] += 1
        return False, counts

    print(SchemaFullType)

    SchemaType = getType(SchemaFullType)
    SchemaNamespace = getNamespace(SchemaFullType)

    success, SchemaSoup = getSchemaDetails(SchemaNamespace)
   
    if not success:
        success, SchemaSoup = getSchemaDetails(SchemaType)
        if not success:
            success, SchemaSoup = getSchemaDetails(SchemaFullType)
        if not success: 
            print("validateURI: No schema for", SchemaFullType, SchemaType)
            counts['failSchema'] += 1
            results[uriName] = (URI, success, counts, None)
            return False, counts, results
    
    if debug:
        print(jsonData)
        print(SchemaSoup)
    
    try:
        propertyList = getTypeDetails(SchemaSoup,SchemaFullType,'entitytype')
    except Exception as ex:
        print(ex)
        counts['exceptionGetType'] += 1
        counts[URI] += 1
        results[uriName] = (URI, success, counts, None)
        return False, counts, results
    
    if debug:
        input(propertyList)

    try:
        propertyDict = getPropertyDetails(SchemaSoup, propertyList)
    except Exception as ex:
        print(ex)
        counts['exceptionGetDict'] += 1
        counts[URI] += 1
        results[uriName] = (URI, success, counts, None)
        return False, counts, results
    
    if debug:
        print(propertyDict)
   
    try:
        messages, checkCounts = checkPropertyCompliance(propertyDict, jsonData)
    except Exception as ex:
        print(ex)
        counts['exceptionPropCompliance'] += 1
        counts[URI] += 1
        results[uriName] = (URI, success, counts, None)
        return False, counts, results
   
    fmt = '%-20s%20s'
    print(uriName, SchemaType)

    for key in jsonData:
        print(fmt % (key, key in messages))
    for key in messages:
        if key not in jsonData :
            print( "missing:", key, messages[key][5] )

    counts.update(checkCounts)

    print(SchemaFullType, counts, len(propertyList))
    
    results[uriName] = (URI, success, counts, messages)
    
    links = getAllLinks(jsonData, propertyDict)
    
    if debug:
        print(links)

    for linkName in links:
        if links[linkName] in allLinks:
            counts['repeat'] += 1
            continue
        
        allLinks.add(links[linkName])
        
        success, linkCounts, linkResults = validateURI(links[linkName], uriName + '->' + linkName)
        if not success:
            counts['unvalidated'] += 1
        print(linkName, linkCounts)
        counts.update(linkCounts)
        results.update(linkResults)

    return True, counts, results

##########################################################################
######################          Script starts here              ######################
##########################################################################

if __name__ == '__main__':
    # Rewrite here
    startTick = datetime.now()
    status_code = 1
    success, finalCounts, results = validateURI ('/redfish/v1','ServiceRoot')
   
    
    nowTick = datetime.now()

    if not success:
        print("Validation has failed.")
        sys.exit(1)    
    htmlStr = '<html><head><title>Compliance Test Summary</title>\
            <style>\
            body {background-color:lightgrey}\
            th {text-align:center; background-color:beige}\
            td {text-align:left; background-color:white}\
            </style>\
            </head><body>'
    htmlStr += '<table>\
                <tr><th>##### Redfish Compliance Test Report #####</th></tr>\
                <tr><th>System: ' + ConfigURI + '</th></tr>\
                <tr><th>User: '+ User +'</th></tr>\
                <tr><th>Start time: ' + str(startTick) + '</th></tr>\
                <tr><th>Run time: ' + str(nowTick - startTick) +'</th></tr>\
                <tr><th></th></tr>'
    cnt = 1
    for item in results:
        print (cnt)
        cnt += 1
        htmlStr += '<tr><td><table><tr>'
        htmlStr += '<td>' + item + '</td>'
        htmlStr += '<td>' + str(results[item][0]) + '</td>'
        htmlStr += '<td>' + str(results[item][1]) + '</td>'
        innerCounts = results[item][2]
        for countType in ['pass','fail','skip']:
            innerCounts[countType] += 0 
            htmlStr += '<td>{p}</td>'.format(p=innerCounts.get(countType,0))
        htmlStr += '</tr>'
        if results[item][3] is not None:
            for i in results[item][3]:
                htmlStr += '<tr>'
                htmlStr += '<td>' + str(i) + '</td>'
                for j in results[item][3][i]:
                    htmlStr += '<td>' + str(j) + '</td>'
                htmlStr += '</tr>'
        htmlStr += '</table></td></tr>'
    htmlStr += '</body></html>'
    with open('log.html','w') as f:
        f.write(htmlStr)
    
    print(finalCounts)
    sys.exit(0)

