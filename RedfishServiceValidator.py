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
import traverseService as rst

def validateEntity(name, val, soup):
    # check if the entity is truly what it's supposed to be
    autoExpand = PropertyItem.get('OData.AutoExpand',None) is not None or\
    PropertyItem.get('OData.AutoExpand'.lower(),None) is not None
    uri = val['@odata.id']
    if not autoExpand:
        success, data, status = rst.callResourceURI(uri)
    else:
        success, data, status = True, val, 200
    rsvLogger.debug('%s, %s, %s', success, (propType, propCollectionType), data)
    if propCollectionType == 'Resource.Item' or propType == 'Resource.Item' and success: 
        paramPass = success 
    elif success:
        currentType = data.get('@odata.type', propCollectionType)
        if currentType is None:
            currentType = propType
        baseLink = refs.get(rst.getNamespace(propCollectionType if propCollectionType is not None else propType))
        baseLinkObj = refs.get(rst.getNamespace(currentType.split('.')[0]))
        if soup.find('schema',attrs={'namespace': rst.getNamespace(currentType)}) is not None:
            success, baseSoup = True, soup
        elif baseLink is not None:
            success, baseSoup, uri = rst.getSchemaDetails(*baseLink)
        else:
            success = False

        rsvLogger.debug('success: %s %s %s',success, currentType, baseLink)        
        if currentType is not None and success:
            currentType = currentType.replace('#','')
            baseRefs = rst.getReferenceDetails(baseSoup)
            allTypes = []
            while currentType not in allTypes and success: 
                allTypes.append(currentType)
                success, baseSoup, baseRefs, currentType = rst.getParentType(baseSoup, baseRefs, currentType, 'entitytype')
                rsvLogger.debug('success: %s %s',success, currentType)

            rsvLogger.debug('%s, %s, %s', propType, propCollectionType, allTypes)
            paramPass = propType in allTypes or propCollectionType in allTypes
            if not paramPass:
                rsvLogger.error("%s: Expected Entity type %s, but not found in type inheritance %s" % (PropertyName, (propType, propCollectionType), allTypes))
        else:
            rsvLogger.error("%s: Could not get schema file for Entity check" % PropertyName)
    else:
        rsvLogger.error("%s: Could not get resource for Entity check" % PropertyName)

def validateComplex(name, val, propDict, propSoup):
    rsvLogger.info('\t***going into Complex')
    if not isinstance( val, dict ):
        rsvLogger.error(item + ' : Complex item not a dictionary')
        return 
        
    # innerPropDict = PropertyItem['typeprops']
    # innerPropSoup = PropertyItem['soup']
    successService, serviceSchemaSoup, SchemaServiceURI = rst.getSchemaDetails('metadata','/redfish/v1/$metadata','.xml')
    if successService:
        serviceRefs = rst.getReferenceDetails(serviceSchemaSoup)
        successService, additionalProps = rst.getAnnotations(serviceSchemaSoup, serviceRefs, val)
        for prop in additionalProps:
            innerPropDict[prop[2]] = rst.getPropertyDetails(*prop)
    for prop in innerPropDict:
        propMessages, propCounts = checkPropertyCompliance(innerPropSoup, prop, innerPropDict[prop], val, refs)
        complexMessages.update(propMessages)
        complexCounts.update(propCounts)
    successPayload, odataMessages = rst.checkPayloadCompliance('',val)
    complexMessages.update(odataMessages)
    rsvLogger.info('\t***out of Complex')
    rsvLogger.info('complex %s', complexCounts)
    if item == "Actions":
        def validateActions(name, val, innerPropSoup, typeOf):
            success, baseSoup, baseRefs, baseType = True, innerPropSoup, rst.getReferenceDetails(innerPropSoup), decoded.get('@odata.type')
            actionsDict = dict()

            while success:
                SchemaNamespace, SchemaType = rst.getNamespace(baseType), rst.getType(baseType)
                innerschema = baseSoup.find('schema', attrs={'namespace': SchemaNamespace})
                actions = innerschema.find_all('action')
                for act in actions:
                    keyname = '#%s.%s' % (SchemaNamespace, act['name'])
                    actionsDict[keyname] = act
                success, baseSoup, baseRefs, baseType = rst.getParentType(baseSoup, baseRefs, baseType, 'entitytype')
            
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
        
def validateDeprecatedEnum(name, val, listEnum):
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

def validateEnum(name, val, listEnum):
    if isinstance(val, str):
        paramPass = val in listEnum
        if not paramPass:
            rsvLogger.error("%s: Invalid enum found (check casing?)" % PropertyName)
    else:
        rsvLogger.error("%s: Expected string value for Enum" % PropertyName)

def validateString(name, val, pattern):
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
    return paramPass

def validateNumber(name, val, numType, minVal=None, maxVal=None):
    rsvLogger = rst.getLogger()
    paramPass = isinstance( val, (int, float) ) 
    if paramPass:
        if 'Int' in numType:
            paramPass = isinstance( val, int )
            if not paramPass:
                rsvLogger.error("%s: Expected int" % name)
        if minVal is not None:
            paramPass = paramPass and minVal <= val
            if not paramPass:
                rsvLogger.error("%s: Value out of assigned min range" % name)
        if maxVal is not None:
            paramPass = paramPass and maxVal >= val
            if not paramPass:
                rsvLogger.error("%s: Value out of assigned max range" % name)
    else:
        rsvLogger.error("%s: Expected numeric type" % name)
    return paramPass

def checkPropertyCompliance(soup, PropertyName, PropertyItem, decoded, refs):
    """
    Given a dictionary of properties, check the validitiy of each item, and return a
    list of counted properties

    param arg1: property name
    param arg2: property item dictionary
    param arg3: json payload
    param arg4: refs
    """
    rsvLogger = rst.getLogger()

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

    validMin, validMax = validMinAttr['int'] if validMinAttr is not None else None, \
                            validMaxAttr['int'] if validMaxAttr is not None else None
    validPattern = validPatternAttr.get('string','') if validPatternAttr is not None else None
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
        printval = str(val)
        if propRealType is not None and propExists and propNotNull:
            paramPass = False
            if propRealType == 'Edm.Boolean':
                paramPass = isinstance( val, bool )
                if not paramPass:
                    rsvLogger.error("%s: Not a boolean" % PropertyName)

            elif propRealType == 'Edm.DateTimeOffset':
                paramPass = validateString(name, val, 
                        '.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])')
                if not paramPass:
                    rsvLogger.error("\t%s: Malformed DateTimeOffset" % PropertyName)

            elif propRealType == 'Edm.Int16' or propRealType == 'Edm.Int32' or\
                    propRealType == 'Edm.Int64' or propRealType == 'Edm.Int' or\
                    propRealType == 'Edm.Decimal' or propRealType == 'Edm.Double':
                paramPass = validateNumber(PropertyName, val, propRealType, validMin, validMax) 

            elif propRealType == 'Edm.Guid':
                paramPass = validateString(name, val, 
                        "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
                if not paramPass:
                    rsvLogger.error("\t%s: Malformed Guid" % PropertyName)
                    
            elif propRealType == 'Edm.String':
                paramPass = validateString(PropertyName, val, validPatternAttr.get('string',''))

            else:
                if propRealType == 'complex':
                    counts['complex'] += 1
                    counts['failComplex'] += 1
                    counts.update(complexCounts)
                    for complexKey in complexMessages:
                        resultList[item + '.' + complexKey + appendStr] = complexMessages[complexKey]

                    for key in val:
                        if key not in complexMessages:
                            rsvLogger.error('%s: Appears to be an extra property (check inheritance or casing?)', item + '.' + key + appendStr)
                            counts['failAdditional'] += 1
                            resultList[item + '.' + key + appendStr] = (val[key], '-',
                                                                 'Exists',
                                                                 '-')
                elif propRealType == 'enum':
                    paramPass = validateEnum(PropertyName, val, PropertyItem['typeprops'])
                    
                elif propRealType == 'deprecatedEnum':
                    paramPass = validateDeprecatedEnum(PropertyName, val, PropertyItem['typeprops'])

                elif propRealType == 'entity':
                    paramPass = validateEntity(PropertyName, val, soup)
            else:
                rsvLogger.error("%s: This type is invalid %s" % (PropertyName, propRealType))
                paramPass = False


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


def validateSingleURI(URI, uriName='', expectedType=None, expectedSchema=None, expectedJson=None):
    # rs-assertion: 9.4.1
    # Initial startup here
    errorMessages = io.StringIO()
    fmt = logging.Formatter('%(levelname)s - %(message)s')
    errh = logging.StreamHandler(errorMessages)
    errh.setLevel(logging.ERROR)
    errh.setFormatter(fmt)
    rsvLogger = rst.getLogger()
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
        success, jsonData, status = rst.callResourceURI(URI)
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
    successPayload, odataMessages = rst.checkPayloadCompliance(URI,jsonData)
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
    SchemaNamespace, SchemaType = rst.getNamespace(SchemaFullType), rst.getType(SchemaFullType)
    if expectedSchema is None:
        SchemaURI = jsonData.get('@odata.context',None)
    else:
        SchemaURI = expectedSchema
    rsvLogger.debug("%s %s", SchemaType, SchemaURI)
       
    success, SchemaSoup, SchemaURI = rst.getSchemaDetails( SchemaNamespace, SchemaURI=SchemaURI)

    if not success:
        rsvLogger.error("validateURI: No schema XML for %s %s",
                        SchemaFullType, SchemaType)
        counts['failSchema'] += 1
        rsvLogger.removeHandler(errh) 
        return False, counts, results, None

    refDict = rst.getReferenceDetails(SchemaSoup)

    rsvLogger.debug(jsonData)
    rsvLogger.debug(SchemaURI)
    
    successService, serviceSchemaSoup, SchemaServiceURI = rst.getSchemaDetails('metadata','/redfish/v1/$metadata','.xml')
    if successService:
        serviceRefs = rst.getReferenceDetails(serviceSchemaSoup)
        successService, additionalProps = rst.getAnnotations(serviceSchemaSoup, serviceRefs, jsonData)
    
    # Fallback typing for properties without types
    # Use string comprehension to get highest type
    if expectedType is SchemaFullType:
        for schema in SchemaSoup.find_all('schema'):
            newNamespace = schema.get('namespace')
            if schema.find('entitytype',attrs={'name': SchemaType}):
                SchemaNamespace = newNamespace
                SchemaFullType = newNamespace + '.' + SchemaType
        rsvLogger.warn('No @odata.type present, assuming highest type %s', SchemaFullType)
    
    results[uriName] = (URI, success, counts, messages, errorMessages, SchemaURI, ('assuming ' if expectedType is SchemaFullType else '') + str(SchemaFullType))

    # Attempt to get a list of properties
    propertyList = list()
    success, baseSoup, baseRefs, baseType = True, SchemaSoup, refDict, SchemaFullType
    while success:
        try:
            propertyList.extend(rst.getTypeDetails(
                baseSoup, baseRefs, baseType, 'entitytype'))
            success, baseSoup, baseRefs, baseType = rst.getParentType(baseSoup, baseRefs, baseType, 'entitytype')
        except Exception as ex:
            rsvLogger.exception("Something went wrong")
            rsvLogger.error(URI + ':  Getting type failed for ' + SchemaFullType + " " + baseType)
            counts['exceptionGetType'] += 1
            break
    for item in propertyList:
        rsvLogger.debug(item[2])
    
    if successService:
        propertyList.extend(additionalProps)

    # Generate dictionary of property info
    for prop in propertyList:
        try:
            propertyDict[prop[2]] = rst.getPropertyDetails(*prop)
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
            rsvLogger.error('%s:  Could not finish compliance check on this property' % (prop))
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
    links = rst.getAllLinks(jsonData, propertyDict, refDict, context=SchemaURI)

    rsvLogger.debug(links)
    rsvLogger.removeHandler(errh) 
    return True, counts, results, links

##########################################################################
######################          Script starts here              ##########
##########################################################################

def main(argv):
    # Set config
    if (len(argv) == 1):
        rst.setConfig('./config/config.ini')
    else:
        rst.setConfig(argv[1])
    rst.isConfigSet()
    rsvLogger = rst.getLogger()

    sysDescription, ConfigURI, chkCert, localOnly = (rst.sysDescription, rst.ConfigURI, rst.chkCert, rst.localOnly)
    User, SchemaLocation = rst.User, rst.SchemaLocation

    # Logging config
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
    success, counts, results, xlinks = rst.validateURITree('/redfish/v1', 'ServiceRoot', validateSingleURI)
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
            .log {text-align:left; white-space:pre-wrap; word-wrap:break-word; font-size:smaller}\
            .title {background-color:#DDDDDD; border: 1pt solid; font-height: 30px; padding: 8px}\
            .titlesub {padding: 8px}\
            .titlerow {border: 2pt solid}\
            .results {transition: visibility 0s, opacity 0.5s linear; display: none; opacity: 0}\
            .resultsShow {display: block; opacity: 1}\
            body {background-color:lightgrey; border: 1pt solid; text-align:center; margin-left:auto; margin-right:auto}\
            th {text-align:center; background-color:beige; border: 1pt solid}\
            td {text-align:left; background-color:white; border: 1pt solid; word-wrap:break-word;}\
            table {width:90%; margin: 0px auto; table-layout:fixed;}\
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
        htmlStr += '<tr><td class="results" id=\'resNum{}\'><table><tr><td><table><tr><th style="width:15%"> Name</th> <th> Value</th> <th>Type</th> <th style="width:10%">Exists?</th> <th style="width:10%">Success</th> <tr>'.format(cnt)
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

    return status_code

if __name__ == '__main__':
    sys.exit(main(sys.argv))
