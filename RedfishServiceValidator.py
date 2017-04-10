# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from bs4 import BeautifulSoup
import configparser, glob, requests
import random, string, re
import time, os, sys
from collections import Counter
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
                        decoded = response.json()
                    else:
                        decoded = response.text
                    return True, decoded
        except Exception as ex:
                print("Something went wrong: ", ex)
        return False, None

# Function to parse individual Schema xml file and search for the Alias string
# Returns the content of the xml file on successfully matching the Alias
@lru_cache(maxsize=64)
def getSchemaDetails(SchemaAlias, SchemaURI=None):
        """
        Find Schema file for given Alias.
        
        param arg1: Schema Alias, such as ServiceRoot
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

# note: Use some sort of re expression to parse SchemaAlias
def getNamespace(string):
    ret = string.rsplit('.',1)[0].replace('#','')
    retTo = ret.split('.')
    if len(retTo) <= 3:
        return ret
    return retTo[0] + '.' + 'v' + retTo[1] + '_' + retTo[2] + '_' + retTo[3]
def getType(string):
    return string.rsplit('.',1)[-1].replace('#','')

# Function to search for all Property attributes in any target schema
# Schema XML may be the initial file for local properties or referenced schema for foreign properties
def getTypeDetails(SchemaAlias, tagType):
        """
        Gets list of surface level properties for a given SchemaAlias,
        including base type inheritance.
        
        param arg1: SchemaAlias string
        param arg2: tag of Type, which can be EntityType or ComplexType...
        return: list of properties as strings
        """
        PropertyList = list()

        SchemaType = getType(SchemaAlias)
        SchemaNamespace = getNamespace(SchemaAlias)

        if debug:
            print("Schema is", SchemaAlias, SchemaType, SchemaNamespace)

        success, soup = getSchemaDetails(SchemaNamespace)

        if not success:
            print("Problem getting Soup", SchemaAlias)
            raise Exception("getTypeDetails: no such soup for " + SchemaAlias)

        innersoup = soup.find('schema',attrs={'namespace':SchemaNamespace})
          
        if innersoup is None:
            print("innerSoup doesn't exist...?", SchemaNamespace)
            return PropertyList
        
        for element in innersoup.find_all(tagType,attrs={'name': SchemaType}):
            if debug:
                print("___")
                print(element['name'])
                print(element.attrs)
                print(element.get('basetype',None))
            # note: Factor in navigationproperties properly
            #       what about EntityContainers?
            usableProperties = element.find_all('property') + element.find_all('navigationproperty')
            baseType = element.get('basetype',None)
            
            if baseType is not None:
                if getNamespace(baseType) != SchemaNamespace:
                    success, InnerSchemaSoup = getSchemaDetails(baseType)
                    PropertyList.extend( getTypeDetails( baseType, tagType)  )
                    if not success:
                        raise Exception('problem')
                else: 
                    PropertyList.extend( getTypeDetails(baseType, tagType ) )

            for innerelement in usableProperties:
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
def getPropertyDetails(PropertyList, tagType = 'entitytype'):
        """
        Get dictionary of tag attributes for properties given, including basetypes.

        param arg1: list of properties as strings
        param tagtype: type of Tag, such as EntityType or ComplexType
        """
        PropertyDictionary = dict() 
         
        for prop in PropertyList:
            PropertyDictionary[prop] = dict()
            
            propOwner, propChild = prop.split(':')[0], prop.split(':')[-1]

            SchemaNamespace = getNamespace(propOwner)
            SchemaType = getType(propOwner)
             
            if debug:
                print('___')
                print(SchemaNamespace, prop)
            
            success, moreSoup = getSchemaDetails(SchemaNamespace)
            if not success:
                raise Exception("getPropertyDetails: no such soup for "+SchemaNamespace)
            
            propSchema = moreSoup.find('schema',attrs={'namespace':SchemaNamespace})
            propEntity = propSchema.find(tagType,attrs={'name':SchemaType})
            propTag = propEntity.find('property',attrs={'name':propChild})
            
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
            isCollection = False

            while propType is not None:
                if debug:
                    print("HASTYPE")
                TypeNamespace = getNamespace(propType)
                typeSpec = getType(propType)

                if debug:
                    print(TypeNamespace, propType)
                if 'Collection(' in propType:
                    propType = propType.replace('Collection(', "")
                    propType = propType.replace(')', "")
                    PropertyDictionary[prop]['isCollection'] = True
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
                    propList = getTypeDetails(propType, tagType='complextype') 
                    if debug:
                        print(propList)
                    propDict = getPropertyDetails(propList, tagType='complextype' ) 
                    if debug:
                        print(propDict)
                    PropertyDictionary[prop]['realtype'] = 'complex'
                    PropertyDictionary[prop]['typeprops'] = propDict
                    break
                elif typeEnumTag is not None:
                    PropertyDictionary[prop]['realtype'] = 'enum'
                    PropertyDictionary[prop]['typeprops'] = list() 
                    for MemberName in typeEnumTag.find_all('member'):
                        PropertyDictionary[prop]['typeprops'].append(MemberName['name'])
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
                resultList = dict()
                counts = Counter()

                for key in PropertyDictionary:

                    print(key)
                    if 'Oem' in key:
                        print('\tOem is skipped')
                        counts['skip'] += 1
                        continue
                    
                    item = key.split(':')[-1]

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
                        print("\tMandatory Test:", propMandatoryPass)
                    else:
                        if debug:
                            print("\tis Optional")

                    propNullable = propAttr.get('nullable',None)
                    propNullablePass = True
                    
                    if propNullable is not None:
                        propNullablePass = (propNullable == 'true') or not propExists or (propNotNull and propNullable == 'false')
                        print("\tis Nullable:", propNullable)
                        print("\tNullability test:", propNullablePass)

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
                    if PropertyDictionary[key].get('isCollection',None) and propValue is not None:
                        print("\tis Collection")
                        propValue = propValue[0]
                    
                    if propRealType is not None and propValue is not None:
                        paramPass = False

                        if propRealType == 'Edm.Boolean':
                            if str(propValue).lower() == "true" or str(propValue).lower() == "false":
                                 paramPass = True       

                        elif propRealType == 'Edm.DateTimeOffset':
                            match = re.match('.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])',str(propValue))
                            if match:
                                paramPass = True

                        elif propRealType == 'Edm.Int16' or propRealType == 'Edm.Int32' or\
                                propRealType == 'Edm.Int64' or propRealType == 'Edm.Int':
                            paramPass = str(propValue).isnumeric() and '.' not in str(propValue)
                            if validMinAttr is not None:
                                paramPass = paramPass and int(validMinAttr['int']) <= int(propValue)
                            if validMaxAttr is not None:
                                paramPass = paramPass and int(validMaxAttr['int']) >= int(propValue)

                        elif propRealType == 'Edm.Decimal':
                            paramPass = str(propValue).isnumeric()     
                            if validMinAttr is not None:
                                paramPass = paramPass and int(validMinAttr['int']) <= float(propValue)
                            if validMaxAttr is not None:
                                paramPass = paramPass and int(validMaxAttr['int']) >= float(propValue)

                        elif propRealType == 'Edm.Double':
                            paramPass = str(propValue).isnumeric()     
                            if validMinAttr is not None:
                                paramPass = paramPass and int(validMinAttr['int']) <= float(propValue)
                            if validMaxAttr is not None:
                                paramPass = paramPass and int(validMaxAttr['int']) >= float(propValue)

                        elif propRealType == 'Edm.Guid':
                            match = re.match("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",str(propValue))
                            if match:
                                paramPass = True

                        elif propRealType == 'Edm.String':
                            if validPatternAttr is not None:
                                pattern = validPatternAttr.get('string','')
                                match = re.fullmatch(pattern,propValue)
                                paramPass = match is not None
                            else:
                                paramPass = True 

                        else:
                            if propRealType == 'complex':                           
                                complexResultList, complexCounts = checkPropertyCompliance( PropertyDictionary[key]['typeprops'], propValue)
                                print('complex',complexCounts)
                                counts.update(complexCounts)
                                counts['complex'] += 1
                                continue

                            elif propRealType == 'enum':
                                if propValue in PropertyDictionary[key]['typeprops']:
                                    paramPass = True        

                            elif propRealType == 'entity':
                                success, data = callResourceURI(propValue['@odata.id'])
                                if debug:
                                    print (success, propType, data)
                                if success:
                                    paramPass = True
                                else:
                                    paramPass = '#' in propValue['@odata.id']
                                # Note: Actually check if this is correct

                    if paramPass and propNullablePass and propMandatoryPass:
                        counts['pass'] += 1
                        print ("\tSuccess")
                    else:
                        counts[propType] += 1
                        counts['fail'] += 1
                        print ("\tFAIL")
                
                return resultList, counts

# Function to collect all links in current resource schema
def     getAllLinks(jsonData, linkName=None):
        """
        Function that returns all links provided in a given JSON response.
        This result will include a link to itself.

        :param jsonData: json dict
        :return: list of links, including itself
        """
        linkList = dict()
        if '@odata.id' in jsonData and linkName is not None:
            if debug:                
                print("getLink:",jsonData['@odata.id'])
            linkList[linkName] = jsonData['@odata.id']
        for element in jsonData:
                value = jsonData[element]
                if type(value) is dict:
                    linkList.update( getAllLinks(value, element))
                if type(value) is list:
                    count = 0
                    for item in value:
                        if type(item) is dict:
                            linkList.update( getAllLinks(item, str(element) + "#" + str(count)))
        return linkList 

allLinks = set()
def validateURI (URI, uriName=''):
    print("***", uriName, URI)
    counts = Counter()
    
    success, jsonData = callResourceURI(URI)
    
    if not success:
        print("validateURI: Get URI failed.")
        counts['failGet'] += 1
        counts[URI] += 1
        return False, counts
    
    counts['pass'] += 1
    
    SchemaFullType = jsonData.get('@odata.type',None)
    if SchemaFullType is None:
        print("validateURI: Json does not contain type, is error?")
        counts['failJsonError'] += 1
        counts[URI] += 1
        return False, counts
    
    print(SchemaFullType)

    SchemaType = getType(SchemaFullType)
    SchemaNamespace = getNamespace(SchemaFullType)

    success, SchemaSoup = getSchemaDetails(SchemaType)
   

    if not success:
        success, SchemaSoup = getSchemaDetails(SchemaNamespace)
        if not success:
            success, SchemaSoup = getSchemaDetails(uriName)
        if not success: 
            print("validateURI: No schema for", SchemaFullType, SchemaType, uriName)
            counts['failSchema'] += 1
            return False, counts
    
    if debug:
        print(jsonData)
        print(SchemaSoup)
    
    links = getAllLinks(jsonData)
    
    if debug:
        print(links)

    try:
        propertyList = getTypeDetails(SchemaFullType,'entitytype')
    except Exception as ex:
        print(ex)
        counts['exceptionGetType'] += 1
        counts[URI] += 1
        return False, counts
    
    if debug:
        print(propertyList)

    try:
        propertyDict = getPropertyDetails(propertyList)
    except Exception as ex:
        print(ex)
        counts['exceptionGetDict'] += 1
        counts[URI] += 1
        return False, counts
    
    if debug:
        print(propertyDict)
   
    try:
        messages, checkCounts = checkPropertyCompliance(propertyDict, jsonData)
    except Exception as ex:
        print(ex)
        counts['exceptionPropCompliance'] += 1
        counts[URI] += 1
        return False, counts
   
    counts.update(checkCounts)

    print(SchemaFullType, counts, len(propertyList))

    for linkName in links:
        if links[linkName] in allLinks:
            counts['repeat'] += 1
            continue
        
        allLinks.add(links[linkName])
        
        success, linkCounts = validateURI(links[linkName],linkName)
        if not success:
            counts['unvalidated'] += 1
        print(linkName, linkCounts)
        counts.update(linkCounts)

    return True, counts

##########################################################################
######################          Script starts here              ######################
##########################################################################

if __name__ == '__main__':
    # Rewrite here
    status_code = 1
    success, finalCounts = validateURI ('/redfish/v1','ServiceRoot')
    
    if not success:
        print("Validation has failed.")
        sys.exit(1)    
   
    print(finalCounts)
    sys.exit(0)

