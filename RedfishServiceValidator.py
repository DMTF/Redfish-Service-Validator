# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

from traceback import format_exc
from bs4 import BeautifulSoup
from time import strftime, strptime
from datetime import datetime as DT
import ConfigParser, glob, requests
import random, string, re
from html import HTML
import time
import os

# Read config info from ini file placed in config folder of tool
config = ConfigParser.ConfigParser()
config.read(os.path.join('.', 'config', 'config.ini'))
ConfigURI = 'https://'+config.get('SystemInformation', 'TargetIP')
User = config.get('SystemInformation', 'UserName')
Passwd = config.get('SystemInformation', 'Password')
SchemaLocation = config.get('Options', 'MetadataFilePath')
chkCert = config.get('Options', 'CertificateCheck')

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
        global countTotProp
        countTotProp+=1
        try:
                if chkCert == 'On':
                        geturl = requests.get(ConfigURI+'/redfish/v1')
                else:
                        geturl = requests.get(ConfigURI+'/redfish/v1', verify=False)
                statusCode = geturl.status_code
                decoded = geturl.json()
                if statusCode == 200:
                        generateLog("Retrieving Resource ServiceRoot ("+ConfigURI+"/redfish/v1)", '200', str(statusCode))
                        return True, decoded
                else:
                        generateLog("Retrieving Resource ServiceRoot ("+ConfigURI+"/redfish/v1)", '200', str(statusCode), logPass = False)
                        return False, statusCode
        except Exception:
                return False, "ERROR: %s" % str(format_exc())

# Function to GET/PATCH/POST resource URI
# Certificate check is conditional based on input from config ini file
def callResourceURI(SchemaName, URILink, Method = 'GET', payload = None):
        URILink = URILink.replace("#", "%23")
        statusCode = ""
        global countTotProp
        if Method == 'GET':
                countTotProp+=1
        try:
                if chkCert == 'On':
                        if Method == 'GET' or Method == 'ReGET':
                                response = requests.get(ConfigURI+URILink, auth = (User, Passwd))
                        elif Method == 'PATCH':
                                response = requests.patch(ConfigURI+URILink, data = payload, auth = (User, Passwd))
                else:
                        if Method == 'GET' or Method == 'ReGET':
                                response = requests.get(ConfigURI+URILink, verify=False, auth = (User, Passwd))
                        elif Method == 'PATCH':
                                response = requests.patch(ConfigURI+URILink, data = payload, verify=False, auth = (User, Passwd))
                statusCode = response.status_code
                if Method == 'GET' or Method == 'ReGET':
                        expCode = [200, 204]
                elif Method == 'PATCH':
                        expCode = [200, 204, 400, 405]
                print Method, statusCode, expCode
                if ((Method == 'GET' or Method == 'ReGET') and statusCode in expCode):
                        if Method == 'GET':
                                generateLog("Retrieving Resource "+SchemaName+" ("+ConfigURI+URILink+")", str(expCode), str(statusCode))
                        decoded = response.json()
                        return statusCode, True, decoded, response.headers
                elif (Method == 'PATCH' and statusCode in expCode):
                        return statusCode, True, '', response.headers
                else:
                        if Method == 'GET':
                                generateLog(SchemaName+" Resource ("+ConfigURI+URILink+")", str(expCode), str(statusCode), logPass = False)
                        return statusCode, False, statusCode, ''
        except Exception:
                return statusCode, False, "ERROR: %s" % str(format_exc()), ''

# Function to GET/PATCH/POST resource URI
# Certificate check is conditional based on input from config ini file
def ResetPatchedAttribute(SchemaName, URILink, Method = 'GET', payload = None):
        URILink = URILink.replace("#", "%23")
        global countTotProp
        if Method == 'GET':
                countTotProp+=1
        try:
                if chkCert == 'On':
                        if Method == 'GET' or Method == 'ReGET':
                                response = requests.get(ConfigURI+URILink, auth = (User, Passwd))
                        elif Method == 'PATCH':
                                response = requests.patch(ConfigURI+URILink, data = payload, auth = (User, Passwd))
                else:
                        if Method == 'GET' or Method == 'ReGET':
                                response = requests.get(ConfigURI+URILink, verify=False, auth = (User, Passwd))
                        elif Method == 'PATCH':
                                response = requests.patch(ConfigURI+URILink, data = payload, verify=False, auth = (User, Passwd))
                statusCode = response.status_code
                decoded = response.json()
                return statusCode, True, decoded, response.headers
        except Exception:
                return statusCode, False, "ERROR: %s" % str(format_exc()), ''
                        
# Function to parse individual Schema xml file and search for the Alias string
# Returns the content of the xml file on successfully matching the Alias
def getSchemaDetails(SchemaAlias):
        if '.' in SchemaAlias:
                Alias = SchemaAlias[:SchemaAlias.find('.')]
        else:
                Alias = SchemaAlias
        for filename in glob.glob(SchemaLocation):
                try:
                        filehandle = open(filename, "r")
                        filedata = filehandle.read()
                        filehandle.close()
                        soup = BeautifulSoup(filedata)
                        parentTag = soup.find_all('edmx:dataservices', limit=1)
                        for eachTag in parentTag:
                                for child in eachTag.find_all('schema', limit=1):
                                        
                                        SchemaNamespace = child['namespace']
                                        SchemaAlias = SchemaNamespace.split(".")[0]
                                        if SchemaAlias == Alias:
                                                return True, soup
                except:
                        return False, "ERROR: %s" % str(format_exc())
        return False, "Schema File not found for " + Alias


# Function to search for all Property attributes in any target schema
# Schema XML may be the initial file for local properties or referenced schema for foreign properties
def getEntityTypeDetails(soup, SchemaAlias):

        PropertyList = []
        PropLink = ""
        def getResourceProperties(myAlias, soup, subProperty):
                AllforeignEntityName = soup.find_all('entitytype', attrs={'name':subProperty})
                for foreignEntityName in AllforeignEntityName:                  
                        EntityBaseType = ""
                        try:
                                EntityBaseType = foreignEntityName['basetype']                          
                        except:
                                EntityBaseType = ''

                        if '.' in EntityBaseType:
                                Alias = EntityBaseType.split('.')[0]
                                subProperty1 = EntityBaseType.split('.')[-1]
                                if Alias == myAlias and Alias == subProperty1:
                                        pass
                                elif (Alias == myAlias) and (Alias != subProperty1):
                                        if (subProperty1 == subProperty):
                                                pass
                                        else:
                                                getResourceProperties(Alias, soup, subProperty1)
                                else:   
                                        status, moreSoup = getSchemaDetails(Alias)
                                        getResourceProperties(Alias, moreSoup, subProperty1)
                        try:
                                for PropertyName in foreignEntityName.find_all('property'):
                                        PropLink = myAlias+':'+PropertyName['name']
                                        if PropLink in PropertyList:
                                                continue
                                        else:
                                                PropertyList.append(PropLink)
                        except:
                                print 'No properties defined for ', foreignEntityName

        searchEntity = SchemaAlias.split('.')[-1]
        aliasCheck = SchemaAlias.split('.')[0]
        
        for child in soup.find_all('entitytype'):
                EntityName = child['name']

                if EntityName == searchEntity:
                        try:
                                EntityBaseType = child['basetype']
                        except:
                                EntityBaseType = ''
                        if '.' in EntityBaseType:

                                Alias = EntityBaseType.split('.')[0]
                                subProperty = EntityBaseType.split('.')[-1]
                                if Alias == aliasCheck:
                                        print "Already covered Schema 1"
                                else:
                                        status, moreSoup = getSchemaDetails(Alias)
                                        getResourceProperties(Alias, moreSoup, subProperty)
                        for PropertyTag in child.find_all('property'):
                        
                                propName = PropertyTag['name']
                                propType = PropertyTag['type']
                                if '.' in propType:
                                        complexTypeSchema = propType.split('.')[0]
                                        if complexTypeSchema == aliasCheck:
                                                complexTypeSchemaPropName = ""
                                                complexTypeSchemaPropName = propType.split('.')[-1]
                                                FindComplexType = None
                                                #if complexTypeSchemaPropName == propName:
                                                try:
                                                        FindComplexType = soup.find('complextype', attrs={'name':complexTypeSchemaPropName})
                                                except:
                                                        FindComplexType = None

                                                try:
                                                        ComplexBaseType = FindComplexType['basetype']
                                                except:
                                                        ComplexBaseType = None

                                                if ComplexBaseType:
                                                        if '.' in ComplexBaseType:
                                                                ComplexAlias = ComplexBaseType.split('.')[0]
                                                                subComplexProperty = ComplexBaseType.split('.')[-1]
                                                                if ComplexAlias == aliasCheck:
                                                                        print "Already covered Schema 2"
                                                                        FindComplexInnerType = soup.find('complextype', attrs={'name':subComplexProperty})                                                      
                                                                        if FindComplexInnerType:
                                                                                for EachProperty in FindComplexInnerType.find_all('property'):
                                                                                        eachChildAttribute = EachProperty['name']
                                                                                        ComplexChildPropName = propName + "." + eachChildAttribute
                                                                                        if ComplexChildPropName in PropertyList:
                                                                                                continue
                                                                                        else:
                                                                                                PropertyList.append(ComplexChildPropName)
                                                                                                
                                                                elif ComplexAlias == "Resource":
                                                                        status, moreSoup = getSchemaDetails(ComplexAlias)
                                                                        try:
                                                                                FindComplexTypeChild2 = moreSoup.find('complextype', attrs={'name':subComplexProperty})
                                                                        except:
                                                                                FindComplexTypeChild2 = None
                                                                        
                                                                        if FindComplexTypeChild2:
                                                                                for eachChildProperty1 in FindComplexTypeChild2.find_all('property'):
                                                                                        eachChildAttribute1 = eachChildProperty1['name']
                                                                                        ComplexChildPropName1 =  'Resource:'+propName + "." + eachChildAttribute1
                                                                                        if ComplexChildPropName1 in PropertyList:
                                                                                                continue
                                                                                        else:
                                                                                                PropertyList.append(ComplexChildPropName1)
                                                                        else:
                                                                                PropLink = 'Resource:'+subComplexProperty
                                                                                if PropLink in PropertyList:
                                                                                        continue
                                                                                else:
                                                                                        PropertyList.append(PropLink)
                                                                                        continue
                                                
                                                if FindComplexType:
                                                        for EachProperty in FindComplexType.find_all('property'):
                                                                eachAttribute = EachProperty['name']
                                                                eachAttributeType = EachProperty['type']
                                                                if '.' in eachAttributeType:
                                                                        complexTypeSchemaChild = eachAttributeType.split('.')[0]
                                                                        if complexTypeSchemaChild == 'Resource':
                                                                                status, moreSoup = getSchemaDetails(complexTypeSchemaChild)
                                                                                try:
                                                                                        FindComplexTypeChild = moreSoup.find('complextype', attrs={'name':eachAttribute})
                                                                                except:
                                                                                        FindComplexTypeChild = None
                                                                                
                                                                                if FindComplexTypeChild:
                                                                                        for eachChildProperty in FindComplexTypeChild.find_all('property'):
                                                                                                eachChildAttribute = eachChildProperty['name']
                                                                                                ComplexChildPropName = 'Resource:'+propName + "." + eachAttribute + "." + eachChildAttribute
                                                                                                if ComplexChildPropName in PropertyList:
                                                                                                        continue
                                                                                                else:
                                                                                                        PropertyList.append(ComplexChildPropName)
                                                                                                        
                                                                ComplexPropName = propName + "." + eachAttribute
                                                                if ComplexPropName in PropertyList:
                                                                        continue
                                                                else:
                                                                        PropertyList.append(ComplexPropName)
                                                                        
                                        if complexTypeSchema == 'Resource':
                                                status, moreSoup = getSchemaDetails(complexTypeSchema)
                                                try:
                                                        FindComplexTypeChild1 = moreSoup.find('complextype', attrs={'name':propName})
                                                except:
                                                        FindComplexTypeChild1 = None
                                                
                                                if FindComplexTypeChild1:
                                                        for eachChildProperty1 in FindComplexTypeChild1.find_all('property'):
                                                                eachChildAttribute1 = eachChildProperty1['name']
                                                                ComplexChildPropName1 =  'Resource:'+propName + "." + eachChildAttribute1
                                                                if ComplexChildPropName1 in PropertyList:
                                                                        continue
                                                                else:
                                                                        PropertyList.append(ComplexChildPropName1)
                                                else:
                                                        PropLink = 'Resource:'+propName
                                                        if PropLink in PropertyList:
                                                                continue
                                                        else:
                                                                PropertyList.append(PropLink)
                                                                continue
                                        
                                if propName in PropertyList:
                                        continue
                                else:
                                        PropertyList.append(propName)
        
        print "PropertyList:::::::::::::::::::::::::::::::::::::::::::::::::::::::", PropertyList
        return EntityName, PropertyList

#Get the Mapped schema details for navigating to the resource schema    
def getMappedSchema(ResourceName, soup):
        try:
                containerlist = soup.find_all('complextype')
                for containerlist1 in containerlist:
                        for child in containerlist1.find_all('navigationproperty'):
                                listName = child['name']
                                listType = child['type']
                                if listName == ResourceName:
                                        return True, listType
        except:
                pass
                
        try:
                containerlist = soup.find_all('entitytype')
                for containerlist2 in containerlist:
                        for child in containerlist2.find_all('navigationproperty'):
                                listName = child['name']
                                listType = child['type']
                                if listName == ResourceName:
                                        return True, listType
        except:
                pass
        return False, "Schema Alias not found for " + ResourceName

# Function to retrieve the detailed Property attributes and store in a dictionary format
# The attributes for each property are referenced through various other methods for compliance check
def getPropertyDetails(soup, PropertyList, SchemaAlias = None):
        def getResourcePropertyDetails(soup, PropertyName, SchemaName):
                try:
                        try:

                                if PropertyName.count(".") == 2:
                                        PropertyDetails = soup.find('property', attrs={'name':PropertyName.split(".")[-1]})
                                elif PropertyName.count(".") == 1:
                                        try:
                                                complexDetails = ""
                                                complexDetails = soup.find('complextype', attrs={'name':PropertyName.split(".")[0]})
                                                if not (complexDetails == None):
                                                        PropertyDetails = complexDetails.find('property', attrs={'name':PropertyName.split(".")[-1]})
                                                        if (PropertyDetails == None):
                                                                PropertyDetails = soup.find('property', attrs={'name':PropertyName.split(".")[-1]})
                                                else:
                                                        PropertyDetails = soup.find('property', attrs={'name':PropertyName.split(".")[-1]})
                                                        
                                                if PropertyDetails == None or PropertyDetails == "":
                                                        status, moreSoup = getSchemaDetails("Resource")
                                                        PropertyDetails = moreSoup.find('property', attrs={'name':PropertyName.split(".")[-1]})
                                        except:
                                                pass
                                else:
                                        PropertyDetails = soup.find('property', attrs={'name':PropertyName})
                        except:
                                pass
                        try:
                                status, moreSoup = getSchemaDetails("Resource")
                                key = "Resource." + PropertyName

                                if not (PropertyDetails == None):
                                        
                                        if PropertyDetails.attrs['type'] == (key):
                                                try:
        
                                                        FindAll = moreSoup.find('typedefinition', attrs={'name':PropertyDetails.attrs['type'].split(".")[-1]})
                                                        try:
                                                                FindAll.attrs['type'] = FindAll.attrs['underlyingtype']
                                                        except:
                                                                pass
                                                        PropertyDictionary [SchemaName + "-" + PropertyName+'.Attributes'] = FindAll.attrs
                                                        for propertyTerm in FindAll.find_all('annotation'):
                                                                PropertyDictionary [SchemaName + "-" + PropertyName+'.'+propertyTerm['term']] = propertyTerm.attrs
                                        
                                                except:
                                                        PropertyDictionary [SchemaName + "-" + PropertyName+'.Attributes'] = PropertyDetails.attrs
                                                        for propertyTerm in PropertyDetails.find_all('annotation'):
                                                                PropertyDictionary [SchemaName + "-" + PropertyName+'.'+propertyTerm['term']] = propertyTerm.attrs              
                                        else:
                                                
                                                try:
                                                        
                                                        FindAll = soup.find('typedefinition', attrs={'name':PropertyDetails.attrs['type'].split(".")[-1]})
                                                        try:
                                                                FindAll.attrs['type'] = FindAll.attrs['underlyingtype']
                                                        except:
                                                                pass
                                                        PropertyDictionary [SchemaName + "-" + PropertyName+'.Attributes'] = FindAll.attrs
                                                        for propertyTerm in FindAll.find_all('annotation'):
                                                                PropertyDictionary [SchemaName + "-" + PropertyName+'.'+propertyTerm['term']] = propertyTerm.attrs
                                        
                                                except:
                                                        PropertyDictionary [SchemaName + "-" + PropertyName+'.Attributes'] = PropertyDetails.attrs
                                                        for propertyTerm in PropertyDetails.find_all('annotation'):
                                                                PropertyDictionary [SchemaName + "-" + PropertyName+'.'+propertyTerm['term']] = propertyTerm.attrs
                                
                                else:
                                        print "No details present"
                                        try:
                                                
                                                FindAll = soup.find('typedefinition', attrs={'name':PropertyName.split(".")[-1]})
                                                try:
                                                        FindAll.attrs['type'] = FindAll.attrs['underlyingtype']
                                                except:
                                                        pass
                                                PropertyDictionary [SchemaName + "-" + PropertyName+'.Attributes'] = FindAll.attrs
                                                for propertyTerm in FindAll.find_all('annotation'):
                                                        PropertyDictionary [SchemaName + "-" + PropertyName+'.'+propertyTerm['term']] = propertyTerm.attrs
                                
                                        except:
                                                PropertyDictionary [SchemaName + "-" + PropertyName+'.Attributes'] = PropertyDetails.attrs
                                                for propertyTerm in PropertyDetails.find_all('annotation'):
                                                        PropertyDictionary [SchemaName + "-" + PropertyName+'.'+propertyTerm['term']] = propertyTerm.attrs
                                
                        except:
                                pass
                except:
                        pass

        SchemaList = []
        for PropertyName in PropertyList:

                if ':' in PropertyName:
                        Alias = PropertyName[:PropertyName.find(':')]
#                       if not(Alias in SchemaList):
#                               SchemaList.append(Alias)
                        status, moreSoup = getSchemaDetails(Alias)
                        SchemaName = SchemaAlias.split(".")[-1]
                        getResourcePropertyDetails(moreSoup, PropertyName[PropertyName.find(':')+1:], SchemaName)
                elif SchemaAlias != None:
                        SchemaName = SchemaAlias.split(".")[-1]
                        getResourcePropertyDetails(soup, PropertyName, SchemaName)
                else:
                        getResourcePropertyDetails(soup, PropertyName)


# Function to retrieve all possible values for any particular Property
# if Schema puts a restriction on the values that the property should have
def getEnumTypeDetails(soup, enumName):

        for child in soup.find_all('enumtype'):
                if child['name'] == enumName:
                        PropertyList1 = []
                        for MemberName in child.find_all('member'):
                                if MemberName['name'] in PropertyList1:
                                        continue
                                PropertyList1.append(MemberName['name'])
                        return PropertyList1

# Function to check compliance of individual Properties based on the attributes retrieved from the schema xml
def checkPropertyCompliance(PropertyList, decoded, soup, SchemaName):

        global countTotSchemaProp, countPassSchemaProp, countFailSchemaProp, countSkipSchemaProp, countWarnSchemaProp
        global countTotMandatoryProp, countPassMandatoryProp, countFailMandatoryProp, countWarnMandatoryProp
        global countTotProp, countPassProp, countFailProp, countSkipProp, countWarnProp
        global propTable
        try:
                for PropertyName in PropertyList:

                        try:            
                                if ':' in PropertyName:
                                        PropertyName = PropertyName[PropertyName.find(':')+1:]

                                if 'Oem' in PropertyName:
                                        propRow = propTable.tr
                                        print 'OEM Properties outside of Compliance Tool scope. Skipping check for the property.'
                                        print 80*'*'
                                        propRow.td(PropertyName)
                                        propRow.td("Skip")
                                        propRow.td("No Value")
                                        propRow.td("No Value")
                                        propRow.td("Skip check for OEM", align = "center")
                                        countSkipProp+=1
                                        continue
                                countTotProp+=1
                                propMandatory = False
                                try:
                                        if PropertyName.count(".") == 2:
                                                MainAttribute = midAttribute = SubAttribute = propValue = ""

                                                MainAttribute = PropertyName.split(".")[0]
                                                midAttribute = PropertyName.split(".")[1]
                                                SubAttribute = PropertyName.split(".")[-1]
                                                propValue = decoded[MainAttribute][midAttribute][SubAttribute]
                                                
                                        elif PropertyName.count(".") == 1:
                                                MainAttribute = PropertyName.split(".")[0]
                                                SubAttribute = PropertyName.split(".")[1]
                                                propValue = decoded[MainAttribute][SubAttribute]
                                        else:
                                                propValue = decoded[PropertyName]
                                except:
                                        print 'Value not found for property', PropertyName
                                        propValue = None

                                if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.Redfish.Required') or PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.DMTF.Required'):
                                        propMandatory = True
                                        countTotMandatoryProp+=1
                                propAttr = PropertyDictionary[SchemaName + "-" + PropertyName+'.Attributes']
                                print "propAttr:::::::::::::::::::::::::::", propAttr
                                
                                optionalFlag = True
                                if (propAttr.has_key('type')):
                                        propType = propAttr['type']
                                if propAttr.has_key('nullable'):
                                        optionalFlag = False
                                        propNullable = propAttr['nullable']
                                        if (propNullable == 'false' and propValue == ''):
                                                if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.Redfish.RequiredOnCreate'):
                                                        generateLog(PropertyName, propType + ' (Not Nullable)', propValue, propMandatory, logPass = True)
                                                else:
                                                        generateLog(PropertyName, propType + ' (Not Nullable)', propValue, propMandatory, logPass = False)
                                                continue
                                if (propMandatory == True and (propValue == None or propValue == '')):
                                        generateLog(PropertyName, propType + ' (Not Nullable)', propValue, propMandatory, logPass = False)
                                        continue
                                if propAttr.has_key(PropertyName+'.OData.Permissions'):
                                        propPermissions = propAttr[PropertyName+'.OData.Permissions']['enummember']
                                        if propPermissions == 'OData.Permissions/ReadWrite':
                                                print 'Check Update Functionality for', PropertyName
                                if propValue != None:
                                        checkPropertyType(PropertyName, propValue, propType, optionalFlag, propMandatory, soup, SchemaName)
                                elif propValue == None:
                                        generateLog(PropertyName, propType, propValue, propMandatory)
                                else:
                                        generateLog(PropertyName, "No Value Specified", propValue, propMandatory)
                        except:
                                print "Inside inner exception"
        except:
                print "Inside exception"
        

# Function to collect all links in current resource schema
def     getAllLinks(jsonData):
        linkList = {}
        for elem, value in jsonData.iteritems():
                try:
                        if type(value) is dict:
                                for eachkey, eachvalue in value.iteritems():
                                        try:
                                                if eachkey == '@odata.id':
                                                        ResourceName = elem
                                                        SchemaURI = jsonData[ResourceName][eachkey]
                                                        linkList[ResourceName] = SchemaURI
                                        except:
                                                pass
                                        try:    
                                                if jsonData[elem][eachkey].has_key('@odata.id'):
                                                        ResourceName = eachkey
                                                        SchemaURI = jsonData[elem][ResourceName]['@odata.id']
                                                        linkList[ResourceName] = SchemaURI
                                        except:
                                                pass                                    
                                        try:
                                                if type(eachvalue) is list:             
                                                        temp = {}
                                                        i = 0
                                                        for eachattr in eachvalue:
                                                                try:
                                                                        if type(eachattr) is dict:                                                                              
                                                                                if eachattr.has_key('@odata.id'):
                                                                                        SchemaURI = eachattr['@odata.id']
                                                                                        temp[i] = SchemaURI
                                                                                        i+=1
                                                                except:
                                                                        pass
                                                        ResourceName = eachkey          
                                                        linkList[ResourceName] = temp           
                                        except:
                                                pass
                        elif type(value) is list:       
                                try:
                                        temp = {}
                                        i = 0                                   
                                        for eachattr in value:
                                                try:
                                                        if type(eachattr) is dict:                                                                              
                                                                if eachattr.has_key('@odata.id'):
                                                                        temp[i] = eachattr['@odata.id']
                                                                        i+=1                                                                    
                                                except:
                                                        pass
                                        ResourceName = elem             
                                        linkList[ResourceName] = temp
                                except:
                                        pass
                        elif jsonData[elem].has_key('@odata.id'):
                                ResourceName = elem
                                SchemaURI = jsonData[ResourceName]['@odata.id']
                                linkList[ResourceName] = SchemaURI
                        else:
                                pass
                except:
                        pass
        
        print "linkList::::::::::::::::::::::::::::::::::::::::::::::", linkList
        return linkList

# Function to handle sub-Links retrieved from parent URI's which are not directly accessible from ServiceRoot
def getChildLinks(PropertyList, decoded, soup):
        global ComplexTypeLinksDictionary
        global ComplexLinksFlag
        global GlobalCount
        linkList = getAllLinks(jsonData= decoded)

        for PropertyName, value in linkList.iteritems():
                
                print "PropertyName::::::::::::::::::::::::::::::::::::::::::::::", PropertyName
                print "value:::::::::::::::::::::::::::::::::::::::::::::::::::::", value
                        
                SchemaAlias = soup.find('schema')['namespace'].split(".")[0]
                try:
                        AllComplexTypeDetails = soup.find_all('entitytype')
                except:
                        pass
                        #ComplexTypeDetails = soup.find_all('entitytype')[0]
                i = 0
                for ComplexTypeDetails in AllComplexTypeDetails: 
                        for child in ComplexTypeDetails.find_all('navigationproperty'):
                                if PropertyName == child['name']:
                                        NavigationPropertyName = child['name']
                                        NavigationPropertyType = child['type']
                                        PropIndex = NavigationPropertyName+":"+NavigationPropertyType
                                        
                                        
                                        if 'Collection(' in NavigationPropertyType:
                                                for elem, data in value.iteritems():
                                                        LinkIndex = PropIndex+"_"+str(elem) + "_" + str(GlobalCount)
                                                        try:
                                                                NavigationPropertyLink = value[elem]
                                                        except:
                                                                NavigationPropertyLink = value['@odata.id']

                                                        tempFlag = False
                                                        temp = ""
                                                        for eachCount in range(0, GlobalCount):
                                                                
                                                                temp = PropIndex + "_" +str(elem) + "_" + str(eachCount)
                                                                if (temp in ComplexTypeLinksDictionary['SubLinks']) and (NavigationPropertyLink in ComplexTypeLinksDictionary[temp+'.Link']):
                                                                        tempFlag = True # Skip duplicate sublink addition
                                                                        break
                                                        if tempFlag:
                                                                continue
                                                        else:
                                                                GlobalCount = GlobalCount + 1
                                                                
                                                        
                                                        ComplexTypeLinksDictionary['SubLinks'].append(LinkIndex)
                                                        SchemaAlias = NavigationPropertyType[NavigationPropertyType.find('(')+1:NavigationPropertyType.find(')')]
                                                        ComplexTypeLinksDictionary[LinkIndex+'.Schema'] = SchemaAlias
                                                        ComplexTypeLinksDictionary[LinkIndex+'.Link'] = NavigationPropertyLink
                                                        i+=1
                                        else:
                                                PropIndexAppend = PropIndex + "_" + str(GlobalCount)
                                                NavigationPropertyLink = value
                                                try:
                                                        tempFlag = False
                                                        temp = ""
                                                        for eachCount in range(0, GlobalCount):
                                                                temp = PropIndex + "_" + str(eachCount)
                                                                
                                                                if (temp in ComplexTypeLinksDictionary['SubLinks']) and (NavigationPropertyLink in ComplexTypeLinksDictionary[temp+'.Link']):
                                                                        tempFlag = True # Skip duplicate sublink addition
                                                                        break
                                                        if tempFlag:
                                                                continue
                                                        else:
                                                                GlobalCount = GlobalCount + 1
                                                except:
                                                        pass
                                                        
                                                ComplexTypeLinksDictionary['SubLinks'].append(PropIndexAppend)                                  
                                                ComplexTypeLinksDictionary[PropIndexAppend+'.Schema'] = NavigationPropertyType
                                                ComplexTypeLinksDictionary[PropIndexAppend+'.Link'] = NavigationPropertyLink
                                                print "ComplexTypeLinksDictionary[PropIndex+'.Schema']:::::::::::::::::::::::", ComplexTypeLinksDictionary[PropIndexAppend+'.Schema']
                                                print "ComplexTypeLinksDictionary[PropIndex+'.Link']:::::::::::::::::::::::::", ComplexTypeLinksDictionary[PropIndexAppend+'.Link']
                                                
                                ComplexLinksFlag = True                         
                i = 0
                ComplexTypeDetails = soup.find('complextype', attrs={'name':"Links"})
                try:                    
                        for child in ComplexTypeDetails.find_all('navigationproperty'):
                                if PropertyName == child['name']:
                                        NavigationPropertyName = child['name']
                                        NavigationPropertyType = child['type']
                                        PropIndex = NavigationPropertyName+":"+NavigationPropertyType
                                        
                                        if 'Collection(' in NavigationPropertyType:
                                                for elem, data in value.iteritems():
                                                        LinkIndex = PropIndex+"_"+str(elem) + "_" + str(GlobalCount)
                                                        try:
                                                                NavigationPropertyLink = value[elem]
                                                        except:
                                                                NavigationPropertyLink = value['@odata.id']                                                     
                                                        
                                                        tempFlag = False
                                                        temp = ""
                                                        for eachCount in range(0, GlobalCount):
                                                                
                                                                temp = PropIndex + "_" +str(elem) + "_" + str(eachCount)
                                                                if (temp in ComplexTypeLinksDictionary['SubLinks']) and (NavigationPropertyLink in ComplexTypeLinksDictionary[temp+'.Link']):
                                                                        tempFlag = True # Skip duplicate sublink addition
                                                                        break
                                                        if tempFlag:
                                                                continue
                                                        else:
                                                                GlobalCount = GlobalCount + 1
                                                                
                                                        ComplexTypeLinksDictionary['SubLinks'].append(LinkIndex)
                                                        SchemaAlias = NavigationPropertyType[NavigationPropertyType.find('(')+1:NavigationPropertyType.find(')')]
                                                        ComplexTypeLinksDictionary[LinkIndex+'.Schema'] = SchemaAlias

                                                        ComplexTypeLinksDictionary[LinkIndex+'.Link'] = NavigationPropertyLink
                                                        i+=1
                                        else:
                                                PropIndexAppend = PropIndex + "_" + str(GlobalCount)
                                                NavigationPropertyLink = value
                                                try:
                                                        tempFlag = False
                                                        temp = ""
                                                        for eachCount in range(0, GlobalCount):
                                                                print "GlobalCount::::::::::::::::::::::::::::::::::::::::::::", GlobalCount
                                                                temp = PropIndex + "_" + str(eachCount)
                                                                if (temp in ComplexTypeLinksDictionary['SubLinks']) and (NavigationPropertyLink in ComplexTypeLinksDictionary[temp+'.Link']):
                                                                        tempFlag = True # Skip duplicate sublink addition
                                                                        break
                                                        if tempFlag:
                                                                continue
                                                        else:
                                                                GlobalCount = GlobalCount + 1
                                                except:
                                                        pass    
                                                
                                                ComplexTypeLinksDictionary['SubLinks'].append(PropIndex)
                                                
                                                ComplexTypeLinksDictionary[PropIndex+'.Schema'] = NavigationPropertyType
                                                ComplexTypeLinksDictionary[PropIndex+'.Link'] = NavigationPropertyLink          
                                ComplexLinksFlag = True         

                except:
                        pass
        return ComplexLinksFlag
        
        
# Function to generate Random Value for PATCH requests
def getRandomValue(PropertyName, SchemaAlias, soup, propOrigValue, SchemaName):
        propUpdateValue = propMinValue = propMaxValue = propValuePattern = None
        try:
                propAttr = PropertyDictionary[SchemaName + "-" + PropertyName+'.Attributes']
                if propAttr.has_key('type'):
                        propType = propAttr['type']

                        if propType == 'Edm.Int16' or propType == 'Edm.Int32' or propType == 'Edm.Int64':
                                valueType = 'Int'
                                if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.Validation.Minimum'):
                                        propMinValue = int(PropertyDictionary[SchemaName + "-" + PropertyName+'.Validation.Minimum']['int'])
                                if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.Validation.Maximum'):
                                        propMaxValue = int(PropertyDictionary[SchemaName + "-" + PropertyName+'.Validation.Maximum']['int'])
                                if propMinValue == None and propMaxValue == None:
                                        propUpdateValue = random.randint(30,200)
                                elif propMinValue == None:
                                        propUpdateValue = random.randint(1, propMaxValue)
                                else:
                                        propMinValue = 30
                                        propMaxValue = 200
                                        propUpdateValue = random.randint(propMinValue, propMaxValue)
                
                        elif propType == 'Edm.String':
                                if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.Validation.Pattern'):
                                        propValuePattern = PropertyDictionary[SchemaName + "-" + PropertyName+'.Validation.Pattern']['string']
                                        propUpdateValue = str(propOrigValue)
                                else:
                                        propUpdateValue = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(7))
                                valueType = 'Str'
                        elif propType == 'Edm.DateTimeOffset':
                                propUpdateValue = strftime("%Y-%m-%d")+"T00:00:00+0000"
                                valueType = 'Date'
                        elif SchemaAlias in propType:
                                enumName = propType.split(".")[-1]
                                validList = getEnumTypeDetails(soup, enumName)
                                if validList:
                                        propUpdateValue = str(random.choice(validList))
                                        try:
                                                propUpdateValue = int(propUpdateValue)
                                                valueType = 'Int'
                                        except:
                                                valueType = 'Str'                                       
                                else:
                                        propUpdateValue = "None"                                
                        elif PropertyName.count(".") == 2:
                                        status, moreSoup = getSchemaDetails("Resource")
                                        validList = getEnumTypeDetails(moreSoup, enumName)
                                        if validList:
                                                propUpdateValue = str(random.choice(validList))
                                                try:
                                                        propUpdateValue = int(propUpdateValue)
                                                        valueType = 'Int'
                                                except:
                                                        valueType = 'Str'                                       
                                        else:
                                                propUpdateValue = "None"
                        elif propType == "Edm.Boolean":
                                if str(propOrigValue).lower() == "true":
                                        propUpdateValue = False
                                else:
                                        propUpdateValue = True
                                valueType = 'Bool'
                else:
                        propUpdateValue = "None"
                        valueType = 'Str'
        except:
                pass
        return propUpdateValue, valueType

# Function to handle Patch functionality checks for ReadWrite attributes
def checkPropertyPatchCompliance(PropertyList, PatchURI, decoded, soup, headers, SchemaName):
        global countTotProp, countPassProp, countFailProp, countSkipProp
        try:    
                def propertyUpdate(PropertyName, PatchURI, payload):
                        statusCode, status, jsonSchema, headers = callResourceURI('', PatchURI, 'PATCH', payload)
                        if not(status):
                                failMessage = "Update Failed - " + str(statusCode)
                                return statusCode, status, failMessage
                        time.sleep(5)
                        statusCode, status, jsonSchema, headers = callResourceURI('', PatchURI, 'ReGET')
                        if not(status):
                                failMessage = "GET after Update Failed - " + str(statusCode)
                                return statusCode, status, failMessage
                
                        try:
                                if PropertyName.count(".") == 2:
                                        MainAttribute = midAttribute = SubAttribute = propNewValue = ""
                                        try:
                                                MainAttribute = PropertyName.split(".")[0]
                                                midAttribute = PropertyName.split(".")[1]
                                                SubAttribute = PropertyName.split(".")[-1]
                                                propNewValue = jsonSchema[MainAttribute][midAttribute][SubAttribute]
                                        except:
                                                propNewValue = "Value Not Available"
                                                return statusCode, False, propNewValue
                                                
                                elif PropertyName.count(".") == 1:
                                        try:
                                                MainAttribute = PropertyName.split(".")[0]
                                                SubAttribute = PropertyName.split(".")[1]
                                                propNewValue = jsonSchema[MainAttribute][SubAttribute]                                                  
                                        except:
                                                propNewValue = "Value Not Available"
                                                return statusCode, False, propNewValue
                                else:
                                        propNewValue = jsonSchema[PropertyName] 
                                return statusCode, True, propNewValue
                        except Exception:
                                propNewValue = "Value Not Available"                    
                                return statusCode, False, propNewValue
                        
                def logPatchResult(status, patchTable, logText, expValue, actValue, WarnCheck = None):
                        global countTotProp, countPassProp, countFailProp, countWarnProp
                        countTotProp+=1
                        if isinstance(expValue, int):
                                expValue = str(expValue)
                        if isinstance(actValue, int):
                                actValue = str(actValue)
                        if status:
                                propRow = patchTable.tr(style="color: #006B24")
                                propRow.td(logText)
                                propRow.td(expValue)
                                propRow.td(actValue)
                                propRow.td("PASS", align = "center")
                                countPassProp+=1
                        else:
                                if WarnCheck:
                                        propRow = patchTable.tr(style="color: #0000ff")
                                        propRow.td(logText)
                                        propRow.td(expValue)
                                        propRow.td(actValue)
                                        propRow.td("Warning", align = "center")
                                        countWarnProp+=1                                
                                else:
                                        propRow = patchTable.tr(style="color: #ff0000")
                                        propRow.td(logText)
                                        propRow.td(expValue)
                                        propRow.td(actValue)
                                        propRow.td("FAIL", align = "center")
                                        countFailProp+=1        
                                        
                for PropertyName in PropertyList:
                        try:
                                if ':' in PropertyName:
                                        PropertyName = PropertyName[PropertyName.find(':')+1:]
                                if 'Oem' in PropertyName:
                                        continue
                                countTotProp+=1
                                propMandatory = False

                                if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.OData.Permissions'):
                                        propPermissions = PropertyDictionary[SchemaName + "-" + PropertyName+'.OData.Permissions']['enummember']
                                else:
                                        propPermissions = ""
                                print "Property Name:", PropertyName, "Permission:", propPermissions
                                
                                if propPermissions == 'OData.Permissions/ReadWrite' or propPermissions == "":
                                        propAttr = PropertyDictionary[SchemaName + "-" + PropertyName+'.Attributes']
                                        if (propAttr.has_key('type')):
                                                propType = propAttr['type']                             
                                        if PropertyName.__contains__("UserName") or PropertyName.__contains__("Password") or PropertyName == "Links" or PropertyName.__contains__("HTTP") or PropertyName == "Enabled"  or PropertyName == "Locked":
                                                continue

                                        SchemaAlias = soup.find('schema')['namespace'].split(".")[0]
                                        propUpdateValue = ""
                                        try:
                                                if PropertyName.count(".") == 2:
                                                        MainAttribute = midAttribute = SubAttribute = propOrigValue = ""
                                                        try:
                                                                MainAttribute = PropertyName.split(".")[0]
                                                                midAttribute = PropertyName.split(".")[1]
                                                                SubAttribute = PropertyName.split(".")[-1]
                                                                propOrigValue = decoded[MainAttribute][midAttribute][SubAttribute]
                                                        except:
                                                                propOrigValue = None
                                                elif PropertyName.count(".") == 1:
                                                        try:
                                                                MainAttribute = PropertyName.split(".")[0]
                                                                SubAttribute = PropertyName.split(".")[1]
                                                                propOrigValue = decoded[MainAttribute][SubAttribute]                                                    
                                                        except:
                                                                propOrigValue = None
                                                else:
                                                        try:
                                                                propOrigValue = decoded[PropertyName]                                           
                                                        except:
                                                                propOrigValue = None
                                                                
                                        except Exception:
                                                propOrigValue = "Value Not Available"
                                        
                                        if propOrigValue == None:
                                                print "No Property available for patch: " % PropertyName
                                                continue
                                                
                                        breakloop = 1   
                                        while True:
                                                breakloop = breakloop + 1
                                                propUpdateValue, valueType = getRandomValue(PropertyName, SchemaAlias, soup, propOrigValue, SchemaName)
                                                if not(str(propUpdateValue).lower() == str(propOrigValue).lower()):
                                                        break
                                                if propUpdateValue == "None" or propUpdateValue == "" or propUpdateValue == True or propUpdateValue == False or propUpdateValue == "Disabled" or propUpdateValue == "Enabled":
                                                        break
                                                if breakloop >= 5:
                                                        break
                                                        
                                        if propUpdateValue == "None":
                                                print "No patch support on: " % PropertyName
                                                continue
                                                
                                        patchTable = htmlTable.tr.td.table(border='1', style="font-family: calibri; width: 100%")
                                        header = patchTable.tr(style="background-color: #FFFFA3")
                                        header.th("PATCH Compliance for Property: "+PropertyName, style="width: 40%")
                                        header.th("Expected Value", style="width: 20%")
                                        header.th("Actual Value", style="width: 20%")
                                        header.th("Result", style="width: 20%")         
                                        
                                        if valueType == 'Int':
                                                propMinValue = propMaxValue = None
                                                if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.Validation.Minimum'):
                                                        propMinValue = int(PropertyDictionary[SchemaName + "-" + PropertyName+'.Validation.Minimum']['int'])
                                                        if PropertyName.count(".") == 1:
                                                                MainAttribute = PropertyName.split(".")[0]
                                                                SubAttribute = PropertyName.split(".")[1]                                                       
                                                                payload = "{\""+ MainAttribute +"\":{\""+SubAttribute+"\":"+str(propMinValue)+"}}"
                                                                
                                                        else:
                                                                payload = "{\""+PropertyName+"\":"+str(propMinValue)+"}"
                                                                
                                                        statusCode, status, retValue = propertyUpdate(PropertyName, PatchURI, payload)
                                                        
                                                        if retValue == propMinValue:
                                                                logPatchResult(True, patchTable, "Valid Update Value", propMinValue, retValue)
                                                        elif str(statusCode) in ["200", "204", "400", "405"]:
                                                                logPatchResult(False, patchTable, "Valid Update Value", propMinValue, retValue, WarnCheck = True)
                                                        else:
                                                                logPatchResult(False, patchTable, "Valid Update Value", propMinValue, retValue)                                                                 

                                                if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.Validation.Maximum'):
                                                        propMaxValue = int(PropertyDictionary[SchemaName + "-" + PropertyName+'.Validation.Maximum']['int'])
                                                        if PropertyName.count(".") == 1:
                                                                MainAttribute = PropertyName.split(".")[0]
                                                                SubAttribute = PropertyName.split(".")[1]                                                       
                                                                payload = "{\""+ MainAttribute +"\":{\""+SubAttribute+"\":"+str(propMaxValue)+"}}"
                                                        else:
                                                                payload = "{\""+PropertyName+"\":"+str(propMaxValue)+"}"
                                                                
                                                        statusCode, status, retValue = propertyUpdate(PropertyName, PatchURI, payload)

                                                        if retValue == propMaxValue:
                                                                logPatchResult(True, patchTable, "Valid Update Value", propMaxValue, retValue)
                                                        elif str(statusCode) in ["200", "204", "400", "405"]:
                                                                logPatchResult(False, patchTable, "Valid Update Value", propMaxValue, retValue, WarnCheck = True)
                                                        else:
                                                                logPatchResult(False, patchTable, "Valid Update Value", propMaxValue, retValue)
                                                                
                                                if PropertyName.count(".") == 1:
                                                        MainAttribute = PropertyName.split(".")[0]
                                                        SubAttribute = PropertyName.split(".")[1]                                                       
                                                        payload = "{\""+ MainAttribute +"\":{\""+SubAttribute+"\":"+str(propUpdateValue)+"}}"
                                                        payloadOriginalValue = "{\""+ MainAttribute +"\":{\""+SubAttribute+"\":"+str(propOrigValue)+"}}"
                                                else:                                                   
                                                        payload = "{\""+PropertyName+"\":"+str(propUpdateValue)+"}"
                                                        payloadOriginalValue = "{\""+PropertyName+"\":"+str(propOrigValue)+"}"
                                                        
                                                statusCode, status, retValue = propertyUpdate(PropertyName, PatchURI, payload)
                                                if retValue == propUpdateValue:
                                                        logPatchResult(True, patchTable, "Valid Update Value", propUpdateValue, retValue)
                                                elif str(statusCode) in ["200", "204", "400", "405"]:
                                                        logPatchResult(False, patchTable, "Valid Update Value", propUpdateValue, retValue, WarnCheck = True)
                                                else:
                                                        logPatchResult(False, patchTable, "Valid Update Value", propUpdateValue, retValue)
                                                
                                                statusCode, status, jsonSchema, headers = ResetPatchedAttribute('', PatchURI, 'PATCH', payload=payloadOriginalValue)

                                        elif valueType == 'Bool':
                                                if PropertyName.count(".") == 1:
                                                        MainAttribute = PropertyName.split(".")[0]
                                                        SubAttribute = PropertyName.split(".")[1]                                                       
                                                        payload = "{\""+ MainAttribute +"\":{\""+SubAttribute+"\":"+str(propUpdateValue).lower() +"}}"
                                                        payloadOriginalValue = "{\""+ MainAttribute +"\":{\""+SubAttribute+"\":"+str(propOrigValue).lower() +"}}"
                                                else:
                                                        payload = "{\""+PropertyName+"\":"+str(propUpdateValue).lower()+"}"
                                                        payloadOriginalValue = "{\""+PropertyName+"\":"+str(propOrigValue).lower()+"}"
                                                        
                                                statusCode, status, retValue = propertyUpdate(PropertyName, PatchURI, payload)

                                                if str(retValue).lower() == str(propUpdateValue).lower():
                                                        logPatchResult(True, patchTable, "Valid Update Value", propUpdateValue, retValue)
                                                elif str(statusCode) in ["200", "204", "400", "405"]:
                                                        logPatchResult(False, patchTable, "Valid Update Value", propUpdateValue, retValue, WarnCheck = True)
                                                else:
                                                        logPatchResult(False, patchTable, "Valid Update Value", propUpdateValue, retValue)
                                        
                                                statusCode, status, jsonSchema, headers = ResetPatchedAttribute('', PatchURI, 'PATCH', payload=payloadOriginalValue)
                                                
                                        else:
                                                if PropertyName.count(".") == 1:
                                                        MainAttribute = PropertyName.split(".")[0]
                                                        SubAttribute = PropertyName.split(".")[1]                                                       
                                                        payload = "{\""+ MainAttribute +"\":{\""+SubAttribute+"\":\""+str(propUpdateValue)+"\"}}"
                                                        payloadOriginalValue = "{\""+ MainAttribute +"\":{\""+SubAttribute+"\":\""+str(propOrigValue)+"\"}}"
                                                else:
                                                        payload = "{\""+PropertyName+"\":\""+propUpdateValue+"\"}"
                                                        payloadOriginalValue = "{\""+PropertyName+"\":\""+str(propOrigValue)+"\"}"
                                                        
                                                statusCode, status, retValue = propertyUpdate(PropertyName, PatchURI, payload)

                                                if str(retValue).lower() == str(propUpdateValue).lower():
                                                        logPatchResult(True, patchTable, "Valid Update Value", propUpdateValue, retValue)
                                                elif str(statusCode) in ["200", "204", "400", "405"]:
                                                        logPatchResult(False, patchTable, "Valid Update Value", propUpdateValue, retValue, WarnCheck = True)
                                                else:
                                                        logPatchResult(False, patchTable, "Valid Update Value", propUpdateValue, retValue)
                                        
                                                statusCode, status, jsonSchema, headers = ResetPatchedAttribute('', PatchURI, 'PATCH', payload=payloadOriginalValue)

                                else:
                                        continue
                        except:
                                pass
        except:
                pass

#Check all the GET property comparison with Schema files                
def checkPropertyType(PropertyName, propValue, propType, optionalFlag, propMandatory, soup, SchemaName):
        global countTotSchemaProp, countPassSchemaProp, countFailSchemaProp, countSkipSchemaProp, countWarnSchemaProp
        global countTotMandatoryProp, countPassMandatoryProp, countFailMandatoryProp, countWarnMandatoryProp
        global countTotProp, countPassProp, countFailProp, countSkipProp, countWarnProp

        if propType == 'Edm.Boolean':
                if str(propValue).lower() == "true" or str(propValue).lower() == "false":
                        generateLog(PropertyName, "Boolean Value", str(propValue), propMandatory)
                else:
                        generateLog(PropertyName, "Boolean Value", str(propValue), propMandatory, logPass = False)
        elif propType == 'Edm.String':
                if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.Validation.Pattern'):
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
                except:
                        pass
                try: 
                        propValueCheck = propValue.split("T")[0]
                        d1 = strptime(propValueCheck, "%Y-%m-%d" )
                        temp = True
                except:
                        pass
                try:
                        propValueCheck = propValue.split(" ")[0]
                        d1 = strptime(propValueCheck, "%Y-%m-%d" )
                        temp = True
                except:
                        pass                    
                if (temp):
                        generateLog(PropertyName, "DateTime Value", propValue, propMandatory)
                else:
                        generateLog(PropertyName, "DateTime Value", propValue, propMandatory, logPass = False)
        elif propType == 'Edm.Int16' or propType == 'Edm.Int32' or propType == 'Edm.Int64':
                if isinstance(propValue, int):
                        logText = "Integer Value"
                        if PropertyDictionary.has_key(SchemaName + "-" + PropertyName+'.Validation.Minimum'):
                                propMinValue = int(PropertyDictionary[SchemaName + "-" + PropertyName+'.Validation.Minimum']['int'])
                                if propValue >= propMinValue:
                                        logText += " Range: "+str(propMinValue)
                                else:
                                        generateLog("Check failed for property " + PropertyName, "Minimum Boundary = " + str(propMinValue), str(propValue), propMandatory, logPass = False)
                                        return
                        if PropertyDictionary.has_key(SchemaName + "-"  +PropertyName+'.Validation.Maximum'):
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
                propValuePattern = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                if (re.match(propValuePattern, propValue) == None):
                        generateLog(PropertyName, "String Value (Pattern: "+propValuePattern+")", propValue, propMandatory, logPass = False)
                else:
                        generateLog(PropertyName, "String Value (Pattern: "+propValuePattern+")", propValue, propMandatory)
        else:
                validList = temp = ""
                templist = []
                print "Inside Complex Data Type"
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
                                print 'Special verification for Complex Data Types defined in schema', SchemaAlias+':', propType
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
                                                        print "Covered"
                                                else:
                                                        flag = False
                                        if flag:
                                                print 'Property present in List', SchemaAlias+':', propValue
                                                generateLog(PropertyName, "Value Matched", str(propValue), propMandatory)
                                        else:
                                                generateLog(PropertyName, "Value Not Matched", str(propValue), propMandatory, logPass = False)
                                                        
                                elif propValue.lower() in [element.lower() for element in validList]:
                                        print 'Property present in List', SchemaAlias+':', propValue
                                        generateLog(PropertyName, "Value Matched", propValue, propMandatory)    
                                else:
                                        generateLog(PropertyName, "Value Not Matched", propValue, propMandatory, logPass = False)

# Common function to handle rerport generation in HTML/XML format
def generateLog(logText, expValue, actValue, propMandatory = False, logPass = True, incrementCounter = True, header = False, spacer = False, summaryLog = False):
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
                print 80*'*'
                print logText
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
                print 'PASS:', 'Compliance successful for', logText, '|| Value matches compliance:', actValue
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
                        countSkipProp+=1
                        countTotProp-=1
                        incrementCounter = False
                else:
                        propRow.td(actValue)
                        propRow.td("PASS", align = "center")
                if incrementCounter:
                        countPassProp+=1
                        if propMandatory:
                                countPassMandatoryProp+=1
        else:
                print 'FAIL:', 'Compliance unsuccessful for', logText, '|| Expected:', expValue, '|| Actual:', actValue
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
                if incrementCounter:
                        countFailProp+=1
                        if propMandatory:
                                countFailMandatoryProp+=1

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
        global AllLinks
        global SerialNumber
        global countTotSchemaProp, countPassSchemaProp, countFailSchemaProp, countSkipSchemaProp, countWarnSchemaProp
        global countTotMandatoryProp, countPassMandatoryProp, countFailMandatoryProp, countWarnMandatoryProp
        global countTotProp, countPassProp, countFailProp, countSkipProp, countWarnProp
        
        global ComplexTypeLinksDictionary
        global ComplexLinksIndex

#       if not (ResourceName == 'Manager'):
#               return 0
        status, SchemaAlias = getMappedSchema(ResourceName, rootSoup)
        countTotSchemaProp = countTotProp
        countPassSchemaProp = countPassProp
        countFailSchemaProp = countFailProp
        countSkipSchemaProp = countSkipProp
        countWarnSchemaProp = countWarnProp
        ComplexLinksFlag = False
        linkvar = ""
        ResourceURIlink2 = "ServiceRoot -> " + ResourceName
        if status:
                print SchemaAlias
                generateLog(None, None, None, spacer = True)
                generateLog(None, None, None, spacer = True)

                status, schemaSoup = getSchemaDetails(SchemaAlias)              
                if not(status):
                        return None     # Continue check of next schema         
                EntityName, PropertyList = getEntityTypeDetails(schemaSoup, SchemaAlias)
                SerialNumber = SerialNumber + 1
                linkvar = "Compliance Check for Schema: "+EntityName + "-" + str(SerialNumber)
                generateLog(linkvar, None, None)
                
                propTable = insertResultTable()
                statusCode, status, jsonSchema, headers = callResourceURI(ResourceName, SchemaURI, 'GET')               
                if status:
                        
                        PropertyDictionary = {}
                        getPropertyDetails(schemaSoup, PropertyList, SchemaAlias)
                        propTable = insertResultTable()
                        try:
                                SchemaName = SchemaAlias.split(".")[-1]
                                checkPropertyCompliance(PropertyList, jsonSchema, schemaSoup, SchemaName)
                                checkPropertyPatchCompliance(PropertyList, SchemaURI, jsonSchema, schemaSoup, headers, SchemaName)
                        except:
                                pass
                        try:
                                ComplexLinksFlag = getChildLinks(PropertyList, jsonSchema, schemaSoup)
                        except:
                                pass
                else:
                        print 80*'*'
                        print schemaSoup
                        print 80*'*'
                        
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
                        
                                EntityName, PropertyList = getEntityTypeDetails(schemaSoup, SchemaAlias)
                                
                                        
                                SerialNumber = SerialNumber + 1
                                linkvar = "Compliance Check for Sub-Link Schema: "+EntityName + "-" + str(SerialNumber)
                                generateLog(linkvar, None, None)
                                
                                propTable = insertResultTable()                         
                                statusCode, status, jsonSchema, headers = callResourceURI(SchemaAlias, subLinkURI, 'GET')
                                
                                if status:
                                        PropertyDictionary = {}
                                        getPropertyDetails(schemaSoup, PropertyList, SchemaAlias)
                                        propTable = insertResultTable()
                                        try:
                                                SchemaName = SchemaAlias.split(".")[-1]
                                                checkPropertyCompliance(PropertyList, jsonSchema, schemaSoup, SchemaName)
                                                checkPropertyPatchCompliance(PropertyList, subLinkURI, jsonSchema, schemaSoup, headers, SchemaName)
                                                #checkPropertyPostCompliance(PropertyList, subLinkURI, jsonSchema, schemaSoup)
                                        except:
                                                pass
                                        try:
                                                ComplexLinksFlag = getChildLinks(PropertyList, jsonSchema, schemaSoup)

                                        except:
                                                pass
                                else:
                                        print 80*'*'
                                        print schemaSoup
                                        print 80*'*'
                                
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
                print 80*'*'
                print SchemaAlias
                print 80*'*'


##########################################################################
######################          Script starts here              ######################
##########################################################################

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
print 80*'*'
generateLog(None, None, None, spacer = True)
propTable = insertResultTable()
generateLog(linkvar, None, None)

# Retrieve output of ServiceRoot URI
status, jsonData = getRootURI()
                                                        
ResourceURIlink1 = "ServiceRoot"
if status:
        # Check compliance for ServiceRoot
        status, schemaSoup = getSchemaDetails('ServiceRoot')

        Name, PropertyList = getEntityTypeDetails(schemaSoup, 'ServiceRoot')
        
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

        
### Only for output
        
        for elem, value in jsonData.iteritems():
                try:
                        if type(value) is dict:
                                for eachkey, eachvalue in value.iteritems():
                                        try:
                                                if eachkey == '@odata.id':
                                                        ResourceName = elem
                                                        SchemaURI = jsonData[ResourceName][eachkey]
                                                        propRow = propTable.tr()
                                                        propRow.td(ResourceName)
                                                        propRow.td(SchemaURI)
                                                        
                                                elif jsonData[elem][eachkey].has_key('@odata.id'):
                                                        ResourceName = eachkey
                                                        SchemaURI = jsonData[elem][ResourceName]['@odata.id']
                                                        propRow = propTable.tr()
                                                        propRow.td(ResourceName)
                                                        propRow.td(SchemaURI)                                           
                                                else:
                                                        pass
                                        except:
                                                pass
                                        
                        elif jsonData[elem].has_key('@odata.id'):
                                ResourceName = elem
                                SchemaURI = jsonData[ResourceName]['@odata.id']
                                propRow = propTable.tr()
                                propRow.td(ResourceName)
                                propRow.td(SchemaURI)
                        else:
                                pass
                except:
                        pass    
        
### Executing all the links on root URI         
        for elem, value in jsonData.iteritems():
                try:
                        if type(value) is dict:
                                for eachkey, eachvalue in value.iteritems():
                                        try:
                                                if eachkey == '@odata.id':
                                                        ResourceName = elem
                                                        SchemaURI = jsonData[ResourceName][eachkey]
                                                        corelogic(ResourceName, SchemaURI)
                                                        
                                                elif jsonData[elem][eachkey].has_key('@odata.id'):
                                                        ResourceName = eachkey
                                                        SchemaURI = jsonData[elem][ResourceName]['@odata.id']
                                                        corelogic(ResourceName, SchemaURI)
                                                else:
                                                        pass
                                        except:
                                                pass
                                        
                        elif jsonData[elem].has_key('@odata.id'):
                                ResourceName = elem
                                SchemaURI = jsonData[ResourceName]['@odata.id']
                                corelogic(ResourceName, SchemaURI)
                        else:
                                pass
                except:
                        pass
                        
#        generateLog("Total Properties checked: %s || Pass: %s || Fail: %s" %(countTotProp, countPassProp, countFailProp), None, None)
#        generateLog("Total Mandatory Properties checked: %s || Pass: %s || Fail: %s" %(countTotMandatoryProp, countPassMandatoryProp, countFailMandatoryProp), None, None)
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
        else:
                logComment = "Compliance Test Result: INCOMPLETE"
        summaryRow.td(logComment)
else:
        print "Compliance FAIL for ServiceRoot. Error:", jsonData

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
print 80*'*'
