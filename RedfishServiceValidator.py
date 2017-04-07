# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from traceback import format_exc
from bs4 import BeautifulSoup
from time import strftime, strptime
from datetime import datetime as DT
import configparser, glob, requests
import random, string, re
import time
import os
import sys
from collections import Counter
import re

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

ComplexTypeLinksDictionary = {'SubLinks':[]}
ComplexLinksIndex = 0
GlobalCount = 1
AllLinks = []
global SerialNumber
SerialNumber = 1
# Initiate counters for Pass/Fail report at Schema level and overall compliance level
countTotProp = countPassProp = countFailProp = countSkipProp = countWarnProp = 0
countTotSchemaProp = countPassSchemaProp = countFailSchemaProp = countSkipSchemaProp = countWarnSchemaProp = 0
countTotMandatoryProp = countPassMandatoryProp = countFailMandatoryProp = countWarnMandatoryProp = 0

# Function to GET ServiceRoot response from test system
# This call should not require authentication
def getRootURI():
    """
    Get JSON response from the Root URI of a configured server, ignoring chkCert

    :return: success, JSON dictionary, if failed then returns False, None 
    """
    oldVal, chkCert = chkCert, False
    retjson = callResourceURI("ServiceRoot", '/redfish/v1')
    chkCert = oldVal
    return retjson

# Function to GET/PATCH/POST resource URI
# Certificate check is conditional based on input from config ini file
# 
def callResourceURI(SchemaName, URILink, Method = 'GET', payload = None, mute = False):
        """
        Makes a call to a given URI
        
        param URILink: path to URI "/example/1"
        param Method: http message type, default 'GET'
        param payload: data for PATCH
        """
        URILink = URILink.replace("#", "%23")
        statusCode = ""
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
                    print(Method, statusCode, expCode)
                if statusCode in expCode:
                   decoded = response.json()
                   return True, decoded
        except Exception as ex:
                print("Something went wrong: ", ex)
                return False, None
        return False, None

# Function to parse individual Schema xml file and search for the Alias string
# Returns the content of the xml file on successfully matching the Alias
def getSchemaDetails(SchemaAlias):
        """
        Find Schema file for given Alias.
        
        param arg1: Schema Alias, such as ServiceRoot
        return: a Soup object
        """
        # Note: Add in calls to $metadata, references and URIs, instead of just locally
        if '.' in SchemaAlias:
                Alias = SchemaAlias[:SchemaAlias.find('.')]
        else:
                Alias = SchemaAlias
        for filename in glob.glob(SchemaLocation):
                if Alias not in filename:
                    continue
                try:
                        filehandle = open(filename, "r")
                        filedata = filehandle.read()
                        filehandle.close()
                        soup = BeautifulSoup(filedata, "html.parser")
                        parentTag = soup.find_all('edmx:dataservices', limit=1)
                        for eachTag in parentTag:
                                for child in eachTag.find_all('schema', limit=1):
                                        SchemaNamespace = child['namespace']
                                        FoundAlias = SchemaNamespace.split(".")[0]
                                        if FoundAlias == Alias:
                                                return True, soup
                except Exception as ex:
                        print("Something went wrong: ", ex)
                        return False, None 
        return False, None 

# note: Use some sort of re expression to parse SchemaAlias
def getNamespace(string):
    return string.split('.')[0].replace('#','')
def getNamespaceVersion(string):
    spl = string.replace('#','').split('.')[:2]
    return spl[0] + "." + spl[1]
def getType(string):
    return string.split('.')[-1].replace('#','')

# Function to search for all Property attributes in any target schema
# Schema XML may be the initial file for local properties or referenced schema for foreign properties
def getTypeDetails(soup, SchemaAlias, tagType):
        PropertyList = list()
        PropLink = ""
        SchemaType = getType(SchemaAlias)
        SchemaNamespace = getNamespace(SchemaAlias)
            
        sns = getNamespaceVersion(SchemaAlias)
        if '_' not in getNamespaceVersion(SchemaAlias):
            sns = SchemaNamespace
        if debug:
            print("Schema is", SchemaAlias, SchemaType, sns)
        innersoup = soup.find('schema',attrs={'namespace':sns})
          
        if innersoup is None:
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
                    PropertyList.extend( getTypeDetails(InnerSchemaSoup, baseType, tagType ) )
                    if not success:
                        print('problem')
                        break
                else: 
                    PropertyList.extend( getTypeDetails(soup, baseType, tagType) )

            for innerelement in usableProperties:
                if debug:
                    print(innerelement['name'])
                    print(innerelement['type'])
                    print(innerelement.attrs)
                newProp = innerelement['name']
                if SchemaAlias:
                    newProp = SchemaAlias + '.' + newProp
                if debug:
                    print("ADDING ::::", newProp) 
                if newProp not in PropertyList: 
                    PropertyList.append( newProp )

        return PropertyList

# Function to retrieve the detailed Property attributes and store in a dictionary format
# The attributes for each property are referenced through various other methods for compliance check
def getPropertyDetails(soup, PropertyList, SchemaAlias = None, tagType = 'entitytype'):
        # note: add docs
        PropertyDictionary = dict() 
         
        for prop in PropertyList:
            PropertyDictionary[prop] = dict()
            SchemaNamespace = getNamespaceVersion(prop)
            propSpec = prop.split('.')[2:]
            if '_' not in SchemaNamespace:
                SchemaNamespace = getNamespace(prop)
                propSpec = prop.split('.')[1:]
            print('___')
            print(SchemaNamespace, prop, propSpec)
            success, moreSoup = getSchemaDetails(SchemaNamespace)
            if not success:
                print("problem")
                continue
            propSchema = moreSoup.find('schema',attrs={'namespace':SchemaNamespace})
            propEntity = propSchema.find(tagType,attrs={'name':propSpec[0]})
            propTag = propEntity.find('property',attrs={'name':propSpec[1]})
            if propTag is None:
                propTag = propEntity.find('navigationproperty',attrs={'name':propSpec[1]})
            propAll = propTag.find_all()

            PropertyDictionary[prop]['attrs'] = propTag.attrs
            
            for tag in propAll:
                PropertyDictionary[prop][tag['term']] = tag.attrs
            print(PropertyDictionary[prop])
            
            propType = propTag.get('type',None)
            isCollection = False

            while propType is not None:
                print("HASTYPE")
                TypeNamespace = getNamespaceVersion(propType)
                typeSpec = propType.split('.')[2:]
                if '_' not in TypeNamespace:
                    TypeNamespace = getNamespace(propType)
                    typeSpec = propType.split('.')[1:]
                print(TypeNamespace, propType, typeSpec)
                if 'Collection(' in propType:
                    propType = propType.replace('Collection(', "")
                    propType = propType.replace(')', "")
                    PropertyDictionary[prop]['isCollection'] = True
                    # Note : this needs work
                    continue
                if 'Edm' in propType:
                    PropertyDictionary[prop]['realtype'] = propType
                    break
                if not success:
                    print("problem")
                    continue
                
                success, typeSoup = getSchemaDetails(TypeNamespace)

                typeSchema = typeSoup.find('schema',attrs={'namespace':TypeNamespace})
                typeSimpleTag = typeSchema.find('typedefinition',attrs={'name':typeSpec[0]})
                typeComplexTag = typeSchema.find('complextype',attrs={'name':typeSpec[0]}) 
                typeEnumTag = typeSchema.find('enumtype',attrs={'name':typeSpec[0]}) 
                typeEntityTag = typeSchema.find('entitytype',attrs={'name':typeSpec[0]})
                
                
                if typeSimpleTag is not None:
                    propType = typeSimpleTag.get('underlyingtype',None)
                    continue
                elif typeComplexTag is not None:
                    print("go DEEP")
                    propList = getTypeDetails(typeSoup, propType, tagType='complextype' ) 
                    print(propList)
                    propDict = getPropertyDetails(typeSoup, propList, tagType='complextype' ) 
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
                    print ("typeEntityTag found",propTag['name'])
                    break
                else:
                    print("!!problem!!")
                    break 
                
        return PropertyDictionary

# Function to check compliance of individual Properties based on the attributes retrieved from the schema xml
def checkPropertyCompliance(PropertyDictionary, decoded):
                resultList = dict()
                counts = Counter()
                for key in PropertyDictionary:
                    print(key)
                    item = getType(key)
                    if 'Oem' in key:
                        print('Oem is skipped')
                        counts['skip'] += 1
                        continue
                    propValue = decoded.get(item, None)
                    print(propValue)
                    propExists = propValue is not None
                    propNotNull = propExists and propValue is not ''
                    propMandatory = False
                    if 'Redfish.Required' in PropertyDictionary[key]:
                        propMandatory = True
                        print("\tis Mandatory?", propMandatory, propExists, propNotNull)
                    else:
                        print("\tis Optional")
                    propAttr = PropertyDictionary[key]['attrs']
                    propType = propAttr.get('type',None)
                    propRealType = PropertyDictionary[key].get('realtype',None)
                    print("\thas Type:", propType, propRealType)

                    propNullable = propAttr.get('nullable',None)
                    print("\tis Nullable:", propNullable)
                    if propNullable is not None:
                        print("\tbreaks nullability?", propNullable, propNotNull)
                    propPermissions = propAttr.get('Odata.Permissions',None)
                    if propPermissions is not None:
                        propPermissionsValue = propPermissions['enummember']
                        print("\tpermission", propPermissionsValue)
                    paramPass = True
                    # Note: consider http://docs.oasis-open.org/odata/odata-csdl-xml/v4.01/csprd01/odata-csdl-xml-v4.01-csprd01.html#_Toc472333112
                    if PropertyDictionary[key].get('isCollection',None) and propValue is not None:
                        propValue = propValue[0]
                    if propRealType is not None and propValue is not None:
                        paramPass = False
                        if propRealType == 'Edm.Boolean':
                            if str(propValue).lower() == "true" or str(propValue).lower() == "false":
                                 paramPass = True       
                        elif propRealType == 'Edm.DateTimeOffset':
                            # Note: check if this works with all variations
                            match = re.match('.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])',str(propValue))
                            if match:
                                paramPass = True
                        elif propRealType == 'Edm.Decimal':
                            # Note: check Ranges
                            paramPass = str(propValue).isnumeric()     
                        elif propType == 'Edm.Double':
                            # Note: check Ranges
                            paramPass = str(propValue).isnumeric()     
                        elif propRealType == 'Edm.Guid':
                            match = re.match("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",str(propValue))
                            if match:
                                paramPass = True
                        elif propRealType == 'Edm.Int16' or propType == 'Edm.Int32' or propType == 'Edm.Int64':
                            # Note: check Ranges
                            paramPass = str(propValue).isnumeric() and '.' not in str(propValue)
                        elif propRealType == 'Edm.String':
                            # Note: get Validation Pattern
                            paramPass = True 
                            pass
                        else:
                            if propRealType == 'complex':                           
                                complexResultList, complexCounts = checkPropertyCompliance( PropertyDictionary[key]['typeprops'], propValue)
                                counts.update(complexCounts)
                                counts['complex'] += 1
                                break
                            elif propRealType == 'enum':
                                if propValue in PropertyDictionary[key]['typeprops']:
                                    paramPass = True        
                            elif propRealType == 'entity':
                                success, data = callResourceURI('',propValue['@odata.id'])
                                print (success, propType, data)
                                if success:
                                    paramPass = getType(data.get('@odata.type',None)) in propType
                                # Note: Actually check if this is correct
                                pass
                    if paramPass:
                        counts['pass'] += 1
                        print ("Success")
                    else:
                        counts[propType] += 1
                        counts['fail'] += 1
                        print ("Fail")
                    
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

#Check all the GET property comparison with Schema files                
def checkPropertyType(PropertyName, PropertyDictionary, propValue, propType, optionalFlag, propMandatory, soup, SchemaName):

        if propType == 'Edm.String':
                if SchemaName + "-" + PropertyName+'.Validation.Pattern' in PropertyDictionary:
                        propValuePattern = PropertyDictionary[SchemaName + "-" + PropertyName+'.Validation.Pattern']['string']
                        if "\\" in propValuePattern:
                                propValuePattern = propValuePattern.replace("\\\\", "\\")
                        if (re.match(propValuePattern, propValue) == None):
                                generateLog(PropertyName, "String Value (Pattern: "+propValuePattern+")", propValue, propMandatory, logPass = False)
                        else:
                                generateLog(PropertyName, "String Value (Pattern: "+propValuePattern+")", propValue, propMandatory)
                elif (len(propValue) >= 1 or (optionalFlag and len(propValue) == 0)):
                        generateLog(PropertyName, "String Value", propValue, propMandatory)
                else:
                        generateLog(PropertyName, "String Value", propValue, propMandatory, logPass = False)
        elif propType == 'Edm.DateTimeOffset':
                temp = False
                try: 
                        propValueCheck = propValue[:19]
                        d1 = strptime(propValueCheck, "%Y-%m-%dT%H:%M:%S" )
                        temp = True
                except Exception as e:
                     if debug > 1: print("Exception has occurred: ", e)  
                try: 
                        propValueCheck = propValue.split("T")[0]
                        d1 = strptime(propValueCheck, "%Y-%m-%d" )
                        temp = True
                except Exception as e:
                     if debug > 1: print("Exception has occurred: ", e)  
                try:
                        propValueCheck = propValue.split(" ")[0]
                        d1 = strptime(propValueCheck, "%Y-%m-%d" )
                        temp = True
                except Exception as e:
                     if debug > 1: print("Exception has occurred: ", e)  
                if (temp):
                        generateLog(PropertyName, "DateTime Value", propValue, propMandatory)
                else:
                        generateLog(PropertyName, "DateTime Value", propValue, propMandatory, logPass = False)
        elif propType == 'Edm.Int16' or propType == 'Edm.Int32' or propType == 'Edm.Int64':
                if isinstance(propValue, int):
                        logText = "Integer Value"
                        if SchemaName + "-" + PropertyName+'.Validation.Minimum' in PropertyDictionary:
                                propMinValue = int(PropertyDictionary[SchemaName + "-" + PropertyName+'.Validation.Minimum']['int'])
                                if propValue >= propMinValue:
                                        logText += " Range: "+str(propMinValue)
                                else:
                                        generateLog("Check failed for property " + PropertyName, "Minimum Boundary = " + str(propMinValue), str(propValue), propMandatory, logPass = False)
                                        return
                        if SchemaName + "-"  +PropertyName+'.Validation.Maximum' in PropertyDictionary:
                                propMaxValue = int(PropertyDictionary[SchemaName + "-" + PropertyName+'.Validation.Maximum']['int'])
                                if propValue <= propMaxValue:
                                        logText += " - "+str(propMaxValue)
                                else:
                                        generateLog("Check failed for property " + PropertyName, "Maximum Boundary = " + str(propMaxValue), str(propValue), propMandatory, logPass = False)
                                        return
                        generateLog(PropertyName, logText, str(propValue), propMandatory)
                else:
                        generateLog(PropertyName, logText, str(propValue), propMandatory, logPass = False)
                        
        elif propType == 'Edm.Guid':
                propValuePattern = ""
                if (re.match(propValuePattern, propValue) == None):
                        generateLog(PropertyName, "String Value (Pattern: "+propValuePattern+")", propValue, propMandatory, logPass = False)
                else:
                        generateLog(PropertyName, "String Value (Pattern: "+propValuePattern+")", propValue, propMandatory)
        else:
                validList = temp = ""
                templist = []
                if debug:
                    print("Inside Complex Data Type")
                if propType.__contains__("Resource"):
                        status, soup = getSchemaDetails("Resource")
                        SchemaAlias = soup.find('schema')['namespace'].split(".")[0]
                else:
                        SchemaAlias = soup.find('schema')['namespace'].split(".")[0]
                        
                if SchemaAlias in propType:
                        if 'Collection(' in propType:
                                propType = propType.replace('Collection(', "")
                                propType = propType.replace(')', "")
                        
                        validList = getEnumTypeDetails(soup, propType.split(".")[-1])   

                        if not validList:
                                print('Special verification for Complex Data Types defined in schema', SchemaAlias+':', propType)
                                generateLog(PropertyName, "Complex Data Type", propType, propMandatory)                         
                        else:
                                flag =True
                                if type(propValue) is list:
                                        temp = str(propValue)
                                        temp = temp.replace("[","")
                                        temp = temp.replace("]","")
                                        temp = temp.replace("u'","")
                                        temp = temp.replace("'","")
                                        temp = temp.replace(", ",",")
                                        temp = temp.replace("\"","")
                                        templist = temp.split(",")
                                        templist = list(templist)
                                        for eachValue in templist:
                                                if eachValue.lower() in [element.lower() for element in validList]:
                                                        print("Covered")
                                                else:
                                                        flag = False
                                        if flag:
                                                print('Property present in List', SchemaAlias+':', propValue)
                                                generateLog(PropertyName, "Value Matched", str(propValue), propMandatory)
                                        else:
                                                generateLog(PropertyName, "Value Not Matched", str(propValue), propMandatory, logPass = False)
                                                        
                                elif propValue.lower() in [element.lower() for element in validList]:
                                        print('Property present in List', SchemaAlias+':', propValue)
                                        generateLog(PropertyName, "Value Matched", propValue, propMandatory)    
                                else:
                                        generateLog(PropertyName, "Value Not Matched", propValue, propMandatory, logPass = False)

gencount = Counter()
# Common function to handle rerport generation in HTML/XML format
def generateLog(logText, expValue, actValue, propMandatory = False, logPass = True, incrementCounter = True, header = False, spacer = False, summaryLog = False):
        global gencount
        if logPass:
                if (actValue == None or actValue == ""):
                        gencount['skip'] += 1
                        incrementCounter = False
                if incrementCounter:
                        gencount['pass'] += 1
                        countPassProp+=1
                        if propMandatory:
                                countPassMandatoryProp+=1
        else:
            if incrementCounter:
                    gencount['fail'] += 1
                    if propMandatory:
                            countFailMandatoryProp+=1
        print(gencount)
        return
        global countTotSchemaProp, countPassSchemaProp, countFailSchemaProp, countSkipSchemaProp, countWarnSchemaProp
        global countTotMandatoryProp, countPassMandatoryProp, countFailMandatoryProp, countWarnMandatoryProp
        global countTotProp, countPassProp, countFailProp, countSkipProp, countWarnProp
        global propTable

        if summaryLog:
                logTable = htmlSumTable
        else:
                logTable = htmlTable

        if spacer:
                logTable.tr.td(style = "height: 30")
                return

        if (expValue == None and actValue == None): # Add Information steps to log
                print(80*'*')
                print(logText)
                if header:
                        rowData = logTable.tr(align = "center", style = "font-size: 21px; background-color: #E6E6F0")
                else:
                        rowData = logTable.tr(align = "center", style = "font-size: 18px; background-color: #FFE0E0")

                if logText.__contains__("Compliance Check"):
                        clickLink = rowData.td.a(id = logText, href= SummaryLogFile)
                        clickLink(logText)                      
                else:
                        rowData.td(logText)
                
                return

        if propMandatory:
                logManOpt = 'Mandatory'
        else:
                logManOpt = 'Optional'
        if logPass:
                print('PASS:', 'Compliance successful for', logText, '|| Value matches compliance:', actValue)
                propRow = propTable.tr(style="color: #006B24")
                propRow.td(logText)
                propRow.td(logManOpt)
                if expValue == None:
                        propRow.td("No Value")
                else:
                        propRow.td(expValue)
                if (actValue == None or actValue == ""):
                        propRow.td("No Value Returned")
                        propRow.td("SKIP", align = "center")
                        counters['skip'] += 1
                        counters['total'] -= 1 
                        incrementCounter = False
                else:
                        propRow.td(actValue)
                        propRow.td("PASS", align = "center")
                if incrementCounter:
                        countPassProp+=1
                        if propMandatory:
                                countPassMandatoryProp+=1
        else:
                print('FAIL:', 'Compliance unsuccessful for', logText, '|| Expected:', expValue, '|| Actual:', actValue)
                propRow = propTable.tr(style="color: #ff0000")
                propRow.td(logText)
                propRow.td(logManOpt)
                if expValue == None:
                        propRow.td("No Value")
                else:
                        propRow.td(expValue)
                if (actValue == None or actValue == ""):
                        propRow.td("No Value Returned")
                else:
                        propRow.td(actValue)
                propRow.td("FAIL", align = "center")

# Common module to handle tabular reporting in HTML
def insertResultTable():
        global propTable
        propTable = htmlTable.tr.td.table(border='1', style="font-family: calibri; width: 100%")
        header = propTable.tr(style="background-color: #FFFFA3")
        header.th("Property Name", style="width: 40%")
        header.th("Type", style="width: 9%")
        header.th("Expected Value", style="width: 17%")
        header.th("Actual Value", style="width: 17%")
        header.th("Result", style="width: 17%")
        return propTable

# Function to traverse thorough all the pages of service
def corelogic(ResourceName, SchemaURI):

          
        counters = Counter()
        status, SchemaAlias = getMappedSchema(ResourceName, rootSoup)
        ComplexLinksFlag = False
        linkvar = ""
        ResourceURIlink2 = "ServiceRoot -> " + ResourceName
        if status:
                print(SchemaAlias)

                status, schemaSoup = getSchemaDetails(SchemaAlias)              
                if not(status):
                        return None     # Continue check of next schema         
                EntityName, PropertyList = getTypeDetails(schemaSoup, SchemaAlias)
                SerialNumber = SerialNumber + 1
                linkvar = "Compliance Check for Schema: "+EntityName + "-" + str(SerialNumber)
                generateLog(linkvar, None, None)
                
                propTable = insertResultTable()
                statusCode, status, jsonSchema, headers = callResourceURI(ResourceName, SchemaURI, 'GET')               
                if status:
                                
                        PropertyDictionary = {}
                        getPropertyDetails(schemaSoup, PropertyList, SchemaAlias)
                        propTable = insertResultTable()
                        SchemaName = SchemaAlias.split(".")[-1]
                        compliance, counts = checkPropertyCompliance(PropertyList, jsonSchema, schemaSoup, SchemaName)
                        patchComplaince, patchCounts = checkPropertyPatchCompliance(PropertyList, SchemaURI, jsonSchema, schemaSoup, headers, SchemaName)
                        ComplexLinksFlag = getChildLinks(PropertyList, jsonSchema, schemaSoup)
                else:
                        print(80*'*')
                        if debug:
                            print(schemaSoup)
                        print(80*'*')
                        
                generateLog("Properties checked for Schema %s: %s || Pass: %s || Fail: %s || Warning: %s " %(SchemaAlias, countTotProp-countTotSchemaProp, countPassProp-countPassSchemaProp, countFailProp-countFailSchemaProp, countWarnProp-countWarnSchemaProp), None, None)
                propRow = summaryLogTable.tr(align = "center")
                propRow.td(str(SerialNumber))           
                propRow.td(ResourceURIlink2, align = "left")
                propRow.td(SchemaURI, align = "left")
                propRow.td(str(countPassProp-countPassSchemaProp))
                propRow.td(str(countFailProp-countFailSchemaProp))
                propRow.td(str(countSkipProp-countSkipSchemaProp))
                propRow.td(str(countWarnProp-countWarnSchemaProp))
                clickLink = propRow.td.a(href= HTMLLogFile + "#" + linkvar)
                clickLink("Click")
                
                oldSchemaAlias = ""
                ResourceURIlink3 = ""
                while ComplexLinksFlag: # Go into loop only if SubLinks have been found
                        ResourceURIlink2 = ResourceURIlink2
                        SubLinks = ComplexTypeLinksDictionary['SubLinks'][ComplexLinksIndex:]
                        ComplexLinksFlag = False        # Reset the Flag to stop looping
                        for elem in SubLinks:
                                ComplexLinksIndex+=1    # Track the Index counter
                                #if elem in ComplexTypeLinksDictionary['SubLinks'][:ComplexLinksIndex-1]:
                                #       continue
                                countTotSchemaProp = countTotProp
                                countPassSchemaProp = countPassProp
                                countFailSchemaProp = countFailProp
                                countSkipSchemaProp = countSkipProp
                                countWarnSchemaProp = countWarnProp
                                SchemaAlias = ComplexTypeLinksDictionary[elem+'.Schema']
                                subLinkURI = ComplexTypeLinksDictionary[elem+'.Link']

                                if subLinkURI.strip().lower() in AllLinks:
                                        continue
                                else:
                                        AllLinks.append(subLinkURI.strip().lower())
                                
                                generateLog(None, None, None, spacer = True)
                                generateLog(None, None, None, spacer = True)

                                status, schemaSoup = getSchemaDetails(SchemaAlias)
                                if not(status):
                                        continue        # Continue check of next schema 
                        
                                EntityName, PropertyList = getTypeDetails(schemaSoup, SchemaAlias)
                                
                                        
                                SerialNumber = SerialNumber + 1
                                linkvar = "Compliance Check for Sub-Link Schema: "+EntityName + "-" + str(SerialNumber)
                                generateLog(linkvar, None, None)
                                
                                propTable = insertResultTable()                         
                                statusCode, status, jsonSchema, headers = callResourceURI(SchemaAlias, subLinkURI, 'GET')
                                
                                if status:
                                        PropertyDictionary = {}
                                        getPropertyDetails(schemaSoup, PropertyList, SchemaAlias)
                                        propTable = insertResultTable()
                                        SchemaName = SchemaAlias.split(".")[-1]
                                        compliance, counts = checkPropertyCompliance(PropertyList, jsonSchema, schemaSoup, SchemaName)
                                        patchComplaince, patchCounts = checkPropertyPatchCompliance(PropertyList, subLinkURI, jsonSchema, schemaSoup, headers, SchemaName)
                                        #checkPropertyPostCompliance(PropertyList, subLinkURI, jsonSchema, schemaSoup)
                                        ComplexLinksFlag = getChildLinks(PropertyList, jsonSchema, schemaSoup)

                                else:
                                        print(80*'*')
                                        if debug:
                                            print(schemaSoup)
                                        print(80*'*')
                                
                                ResourceURIlink3 = ResourceURIlink2 + " -> " + SchemaAlias.split(".")[0]
                                        
                                generateLog("Properties checked for Sub-Link Schema %s: %s || Pass: %s || Fail: %s || Warning: %s " %(SchemaAlias, countTotProp-countTotSchemaProp, countPassProp-countPassSchemaProp, countFailProp-countFailSchemaProp, countWarnProp-countWarnSchemaProp), None, None)
                                propRow = summaryLogTable.tr(align = "center")

                                propRow.td(str(SerialNumber))
                                propRow.td(ResourceURIlink3, align = "left")
                                propRow.td(subLinkURI, align = "left")
                                propRow.td(str(countPassProp-countPassSchemaProp))
                                propRow.td(str(countFailProp-countFailSchemaProp))
                                propRow.td(str(countSkipProp-countSkipSchemaProp))
                                propRow.td(str(countWarnProp-countWarnSchemaProp))
                                clickLink = propRow.td.a(href= HTMLLogFile + "#" + linkvar)
                                clickLink("Click")
                        oldSchemaAlias = SchemaAlias.split(".")[0]      
        else:
                print(80*'*')
                print(SchemaAlias)
                print(80*'*')

allLinks = set()
def validateURI (URI, uriName=''):
    print("***", uriName, URI)
    counts = Counter()
    print(uriName, URI)
    
    success, jsonData = callResourceURI(uriName, URI)
    
    if not success:
        print("Get URI failed.")
        counts['fail'] += 1
        return False, counts
    
    counts['pass'] += 1

    SchemaFullType = jsonData['@odata.type']
    SchemaType = getType(SchemaFullType)
    SchemaNamespace = getNamespace(SchemaFullType)

    success, SchemaSoup = getSchemaDetails(SchemaType)
   
    print(SchemaFullType)

    if not success:
        success, SchemaSoup = getSchemaDetails(SchemaNamespace)
        if not success:
            success, SchemaSoup = getSchemaDetails(uriName)
        if not success: 
            print("No schema for", SchemaFullType, uriName)
            counts['fail'] += 1
            return False, counts
    
    propertyList = getTypeDetails(SchemaSoup,SchemaFullType,'entitytype')
    
    print(propertyList)

    links = getAllLinks(jsonData)
    
    print(links)

    propertyDict = getPropertyDetails(SchemaSoup, propertyList, SchemaFullType)
   
    messages, checkCounts = checkPropertyCompliance(propertyDict, jsonData)
    
    counts.update(checkCounts)

    
    for linkName in links:
        print(uriName, '->', linkName)
        if links[linkName] in allLinks:
            counts['repeat'] += 1
            continue
        
        allLinks.add(links[linkName])
        
        success, linkCounts = validateURI(links[linkName],linkName)
        
        counts.update(linkCounts)
        if not success:
            counts['unvalidated'] += 1

    return True, counts

##########################################################################
######################          Script starts here              ######################
##########################################################################

if __name__ == '__main__':
    # Rewrite here
    status_code = 1
    success, counts = validateURI ('/redfish/v1','ServiceRoot')
    
    if not success:
        print("Validation has failed.")
        sys.exit(1)    
   
    print(counts)
    sys.exit(0)

    # Initialize Log files for HTML report
    HTMLLogFile = strftime("ComplianceTestDetailedResult_%m_%d_%Y_%H%M%S.html")
    SummaryLogFile = strftime("ComplianceTestSummary_%m_%d_%Y_%H%M%S.html")
    logHTML = HTML('html')
    logSummary = HTML('html')
    loghead = logHTML.head
    logbody = logHTML.body
    loghead.title('Compliance Log')
    logSumhead = logSummary.head
    logSumbody = logSummary.body
    logSumhead.title('Compliance Test Summary')
    startTime = DT.now()

    htmlTable = logbody.table(border='1', style="font-family: calibri; width: 100%; font-size: 14px")
    generateLog("#####         Starting Redfish Compliance Test || System: %s as User: %s     #####" %(ConfigURI, User), None, None, header = True)
    htmlSumTable = logSumbody.table(border='1', style="font-family: calibri; width: 80%; font-size: 14px", align = "center")
    generateLog("#####         Redfish Compliance Test Report         #####", None, None, header = True, summaryLog = True)
    generateLog("System: %s" %ConfigURI[ConfigURI.find("//")+2:], None, None, summaryLog = True)
    generateLog("User: %s" %(User), None, None, summaryLog = True)
    generateLog("Execution Date: %s" %strftime("%m/%d/%Y %H:%M:%S"), None, None, summaryLog = True)
    generateLog(None, None, None, spacer = True, summaryLog = True)

    summaryLogTable = htmlSumTable.tr.td.table(border='1', style="width: 100%")
    header = summaryLogTable.tr(style="background-color: #FFFFA3")
    header.th("Serial No", style="width: 5%")
    header.th("Resource Name", style="width: 30%")
    header.th("Resource URI", style="width: 40%")
    header.th("Passed", style="width: 5%")
    header.th("Failed", style="width: 5%")
    header.th("Skipped", style="width: 5%")
    header.th("Warning", style="width: 5%")
    header.th("Details", style="width: 5%")
    linkvar = "Compliance Check for Root Schema" + "-" + str(SerialNumber)
    print(80*'*')
    generateLog(None, None, None, spacer = True)
    propTable = insertResultTable()
    generateLog(linkvar, None, None)

    # Retrieve output of ServiceRoot URI
    status, jsonData = getRootURI()                                                        

    ResourceURIlink1 = "ServiceRoot"
    if status:
            # Check compliance for ServiceRoot
            status, schemaSoup = getSchemaDetails('ServiceRoot')

            Name, PropertyList = getTypeDetails(schemaSoup, 'ServiceRoot')
            
            PropertyDictionary = {}
            ComplexLinksFlag = False

            getPropertyDetails(schemaSoup, PropertyList, 'ServiceRoot')
            
            propTable = insertResultTable()
            checkPropertyCompliance(PropertyList, jsonData, schemaSoup, 'ServiceRoot')
            # Report log statistics for ServiceRoot schema
            generateLog("Properties checked: %s || Pass: %s || Fail: %s || Warning: %s " %(countTotProp, countPassProp, countFailProp, countWarnProp), None, None)
            propRow = summaryLogTable.tr(align = "center")
            propRow.td(str(SerialNumber))
            propRow.td(ResourceURIlink1, align = "left")
            propRow.td("/redfish/v1", align = "left")
            propRow.td(str(countPassProp-countPassSchemaProp))
            propRow.td(str(countFailProp-countFailSchemaProp))
            propRow.td(str(countSkipProp-countSkipSchemaProp))
            propRow.td(str(countWarnProp-countWarnSchemaProp))
            clickLink = propRow.td.a(href= HTMLLogFile + "#" + linkvar)
            clickLink("Click")

            rootSoup = schemaSoup
            generateLog(None, None, None, spacer = True)
            propTable = htmlTable.tr.td.table(border='1', style="width: 100%")
            header = propTable.tr(style="background-color: #FFFFA3")
            header.th("Resource Name", style="width: 30%")
            header.th("URI", style="width: 70%")
            
            ### Executing all the links on root URI         
            for elem, value in jsonData.items():
                            if type(value) is dict:
                                    for eachkey, eachvalue in value.items():
                                                    if eachkey == '@odata.id':
                                                            ResourceName = elem
                                                            SchemaURI = jsonData[ResourceName][eachkey]
                                                            corelogic(ResourceName, SchemaURI)
                                                            propRow = propTable.tr()
                                                            propRow.td(ResourceName)
                                                            propRow.td(SchemaURI)
                                                            
                                                    elif '@odata.id' in jsonData[elem][eachkey]:
                                                            ResourceName = eachkey
                                                            SchemaURI = jsonData[elem][ResourceName]['@odata.id']
                                                            corelogic(ResourceName, SchemaURI)
                                                            propRow = propTable.tr()
                                                            propRow.td(ResourceName)
                                                            propRow.td(SchemaURI)
                                                    else:
                                                            pass
                            else:
                                    pass
                            
            
            generateLog(None, None, None, spacer = True, summaryLog = True)
            summaryLogTable = htmlSumTable.tr.td.table(border='1', style="width: 100%")
            header = summaryLogTable.tr(style="background-color: #FFFFA3")
            header.th("Compliance Test Summary", style="width: 40%")
            header.th("Passed", style="width: 15%")
            header.th("Failed", style="width: 15%")
            header.th("Skipped", style="width: 15%")
            header.th("Warning", style="width: 15%")

            summaryRow = summaryLogTable.tr(align = "center")
            summaryRow.td("Mandatory Properties", align = "left")
            summaryRow.td(str(countPassMandatoryProp))
            summaryRow.td(str(countFailMandatoryProp))
            summaryRow.td('0')
            summaryRow.td(str(countWarnMandatoryProp))
            
            summaryRow = summaryLogTable.tr(align = "center")
            summaryRow.td("Optional Properties", align = "left")
            summaryRow.td(str(countPassProp - countPassMandatoryProp))
            summaryRow.td(str(countFailProp - countFailMandatoryProp))
            summaryRow.td(str(countSkipProp))
            summaryRow.td(str(countWarnProp - countWarnMandatoryProp))
            summaryRow = summaryLogTable.tr(align = "center", style = "background-color: #E6E6F0")
            summaryRow.td("Total Properties", align = "left")
            summaryRow.td(str(countPassProp))
            summaryRow.td(str(countFailProp))
            summaryRow.td(str(countSkipProp))
            summaryRow.td(str(countWarnProp))

            generateLog(None, None, None, spacer = True, summaryLog = True)
            if (countFailProp > 0 or countFailMandatoryProp > 0):
                    logComment = "Compliance Test Result: FAIL"
                    summaryRow = htmlSumTable.tr(align = "center", style = "font-size: 18px; background-color: #E6E6F0; color: #ff0000")
            elif (countPassProp > 0):
                    logComment = "Compliance Test Result: PASS"
                    summaryRow = htmlSumTable.tr(align = "center", style = "font-size: 18px; background-color: #E6E6F0; color: #006B24")
                    status_code = 0
            else:
                    logComment = "Compliance Test Result: INCOMPLETE"
            summaryRow.td(logComment)
    else:
            print("Compliance FAIL for ServiceRoot. Error:", jsonData)

    endTime = DT.now()
    execTime = endTime - startTime
    timeLog = htmlSumTable.tr(align = "left", style="font-size: 11px")
    timeLog.td("Execution Time: " + str(execTime))

    timeLog = htmlSumTable.tr(align = "left", style="font-size: 11px")
    timeLog.td("* Warning: " + str("Value which we are trying to configure is not getting set using compliance tool are may be due to external dependency."))

    # Save HTML Log Files
    filehandle = open(os.path.join('.', 'logs', HTMLLogFile), "w")
    filehandle.write(str(logHTML))
    filehandle.close()
    filehandle = open(os.path.join('.', 'logs', SummaryLogFile), "w")
    filehandle.write(str(logSummary))
    filehandle.close()

    generateLog("#####        End of Compliance Check. Please refer logs.    #####", None, None)
    print(80*'*')

