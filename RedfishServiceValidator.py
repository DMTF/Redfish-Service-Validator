
# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link:
# https://github.com/DMTF/Redfish-Service-Validator/LICENSE.md

import argparse
import io
import os
import sys
import re
from datetime import datetime
from collections import Counter, OrderedDict
import logging
import json
import traverseService as rst

rsvLogger = rst.getLogger()

def validateActions(name, val, propTypeObj, payloadType):
    # checks for all Schema parents and gets their Action tags, does validation
    # info: what tags are we getting, treat them as if they were properties in a complex
    # error: broken/missing action, largely the only problem that's validateable
    # warn: action is missing something, but is fine or not mandatory
    """
    Validates an action dict (val)
    """
    actionMessages, actionCounts = OrderedDict(), Counter()
    # traverse through all parent types to discover Action tags
    success, baseSoup, baseRefs, baseType = True, propTypeObj.soup, propTypeObj.refs, payloadType
    actionsDict = dict()
    while success:
        SchemaNamespace = rst.getNamespace(baseType)
        innerschema = baseSoup.find('Schema', attrs={'Namespace': SchemaNamespace})
        actions = innerschema.find_all('Action')
        for act in actions:
            keyname = '#{}.{}'.format(SchemaNamespace, act['Name'])
            actionsDict[keyname] = act
        success, baseSoup, baseRefs, baseType = rst.getParentType(baseSoup, baseRefs, baseType, 'EntityType')

    # For each action found, check action dictionary for existence and compliance
    # No action is required unless specified, target is not required unless specified
    # (should check for viable parameters)
    for k in actionsDict:
        actionDecoded = val.get(k, 'n/a')
        actPass = False
        if actionDecoded != 'n/a':
            target = actionDecoded.get('target')
            if target is not None and isinstance(target, str):
                actPass = True
            elif target is None:
                rsvLogger.warn('{}: target for action is missing'.format(k))
                actPass = True
            else:
                rsvLogger.error('{} : target for action is malformed, expected string got'.format(k, str(type(target))))
        else:
            # <Annotation Term="Redfish.Required"/>
            if actionsDict[k].find('annotation', {'term': 'Redfish.Required'}):

                rsvLogger.error('{}: action not Found, is mandatory'.format(k))
            else:
                actPass = True
                rsvLogger.warn('{}: action not Found, is not mandatory'.format(k))
        actionMessages[k] = (
                    'Action', '-',
                    'Exists' if actionDecoded != 'n/a' else 'DNE',
                    'PASS' if actPass else 'FAIL')
        if actPass:
            actionCounts['pass'] += 1
        else:
            actionCounts['failAction'] += 1
    return actionMessages, actionCounts


def validateEntity(name, val, propType, propCollectionType, soup, refs, autoExpand):
    # info: what are we looking for (the type), what are we getting (the uri), does the uri make sense based on type (does not do this yet)
    # error: this type is bad, could not get resource, could not find the type, no reference, cannot construct type (doesn't do this yet)
    # debug: what types do we have, what reference did we get back
    """
    Validates an entity based on its uri given
    """
    # check if the entity is truly what it's supposed to be
    uri = val['@odata.id']
    paramPass = False
    # if not autoexpand, we must grab the resource
    if not autoExpand:
        success, data, status, delay = rst.callResourceURI(uri)
    else:
        success, data, status, delay = True, val, 200, 0
    rsvLogger.debug('{}, {}, {}'.format(success, (propType, propCollectionType), data))
    # if the reference is a Resource, save us some trouble as most/all basetypes are Resource
    if propCollectionType == 'Resource.Item' or propType in ['Resource.ResourceCollection', 'Resource.Item'] and success:
        paramPass = success
    elif success:
        # Attempt to grab an appropriate type to test against and its schema
        # Default lineup: payload type, collection type, property type
        currentType = data.get('@odata.type', propCollectionType)
        if currentType is None:
            currentType = propType
        baseLink = refs.get(rst.getNamespace(propCollectionType if propCollectionType is not None else propType))
        if soup.find('Schema', attrs={'Namespace': rst.getNamespace(currentType)}) is not None:

            success, baseSoup = True, soup
        elif baseLink is not None:
            success, baseSoup, uri = rst.getSchemaDetails(*baseLink)
        else:
            success = False
        rsvLogger.debug('success: {} {} {}'.format(success, currentType, baseLink))

        # Recurse through parent types, gather type hierarchy to check against
        if currentType is not None and success:
            
            currentType = currentType.replace('#', '')
            baseRefs = rst.getReferenceDetails(baseSoup, refs, uri)
            allTypes = []
            while currentType not in allTypes and success:
                allTypes.append(currentType)
                success, baseSoup, baseRefs, currentType = rst.getParentType(baseSoup, baseRefs, currentType, 'EntityType')
                rsvLogger.debug('success: {} {}'.format(success, currentType))

            rsvLogger.debug('{}, {}, {}'.format(propType, propCollectionType, allTypes))
            paramPass = propType in allTypes or propCollectionType in allTypes
            if not paramPass:
                rsvLogger.error("{}: Expected Entity type {}, but not found in type inheritance {}".format(name, (propType, propCollectionType), allTypes))
        else:
            rsvLogger.error("{}: Could not get schema file for Entity check".format(name))
    else:
        rsvLogger.error("{}: Could not get resource for Entity check".format(name))
    return paramPass


def validateComplex(name, val, propTypeObj, payloadType):
    # one of the more complex validation methods, but is similar to validateSingleURI
    # info: treat this like an individual payload, where is it, what is going on, perhaps reuse same code by moving it to helper
    # warn: lacks an odata type, defaulted to highest type (this would happen during type gen)
    # error: this isn't a dict, these properties aren't good/missing/etc, just like a payload
    # debug: what are the properties we are looking for, what vals, etc (this is genned during checkPropertyConformance)

    """
    Validate a complex property
    """
    rsvLogger.info('\t***going into Complex')
    if not isinstance(val, dict):
        rsvLogger.error(name + ' : Complex item not a dictionary')  # Printout FORMAT
        return False, None, None

    # Check inside of complexType, treat it like an Entity
    complexMessages = OrderedDict()
    complexCounts = Counter()
    propList = list()

    successService, serviceSchemaSoup, SchemaServiceURI = rst.getSchemaDetails('$metadata', '/redfish/v1/$metadata')
    if successService:
        serviceRefs = rst.getReferenceDetails(serviceSchemaSoup)
        successService, additionalProps = rst.getAnnotations(serviceSchemaSoup, serviceRefs, val)
        propSoup, propRefs = serviceSchemaSoup, serviceRefs
        for prop in additionalProps:
            propMessages, propCounts = checkPropertyConformance(propSoup, prop.name, prop.propDict, val, propRefs)
            complexMessages.update(propMessages)
            complexCounts.update(propCounts)
    


    node = propTypeObj
    while node is not None:
        propList, propSoup, propRefs = node.propList, node.soup, node.refs
        for prop in propList:
            propMessages, propCounts = checkPropertyConformance(propSoup, prop.name, prop.propDict, val, propRefs)
            complexMessages.update(propMessages)
            complexCounts.update(propCounts)
        node = node.parent
    successPayload, odataMessages = checkPayloadConformance('', val)
    complexMessages.update(odataMessages)
    if not successPayload:
        complexCounts['failComplexPayloadError'] += 1
        rsvLogger.error('In complex {}:  payload error, @odata property noncompliant'.format(str(name)))
    rsvLogger.info('\t***out of Complex')
    rsvLogger.info('complex {}'.format(str(complexCounts)))
    if ":Actions" in name:
        aMsgs, aCounts = validateActions(name, val, propTypeObj, payloadType)
        complexMessages.update(aMsgs)
        complexCounts.update(aCounts)
    return True, complexCounts, complexMessages


def validateDeprecatedEnum(name, val, listEnum):
    """
    Validates a DeprecatedEnum
    """
    paramPass = True
    if isinstance(val, list):
        for enumItem in val:
            for k, v in enumItem.items():
                paramPass = paramPass and str(v) in listEnum
        if not paramPass:
            rsvLogger.error("{}: Invalid DeprecatedEnum, expected {}".format(str(name), str(listEnum)))
    elif isinstance(val, str):
        paramPass = str(val) in listEnum
        if not paramPass:
            rsvLogger.error("{}: Invalid DeprecatedEnum, expected {}".format(str(name), str(listEnum)))
    else:
        rsvLogger.error("{}: Expected list/str value for DeprecatedEnum, got {}".format(str(name), str(type(val))))
    return paramPass


def validateEnum(name, val, listEnum):
    paramPass = isinstance(val, str)
    if paramPass:
        paramPass = val in listEnum
        if not paramPass:
            rsvLogger.error("{}: Invalid Enum value '{}' found, expected {}".format(str(name), val, str(listEnum)))
    else:
        rsvLogger.error("{}: Expected str value for Enum, got {}".format(str(name), str(type(val))))
    return paramPass


def validateString(name, val, pattern=None):
    """
    Validates a string, given a value and a pattern
    """
    paramPass = isinstance(val, str)
    if paramPass:
        if pattern is not None:
            match = re.fullmatch(pattern, val)
            paramPass = match is not None
            if not paramPass:
                rsvLogger.error("{}: String '{}' does not match pattern '{}'".format(name, str(val), str(pattern)))
        else:
            paramPass = True
    else:
        rsvLogger.error("{}: Expected string value, got type {}".format(name, str(type(val))))
    return paramPass


def validateDatetime(name, val):
    """
    Validates a Datetime, given a value (pattern predetermined)
    """
    paramPass = validateString(name, val, '.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])')
    if not paramPass:
        rsvLogger.error("\t...: Malformed DateTimeOffset")
    return paramPass


def validateGuid(name, val):
    """
    Validates a Guid, given a value (pattern predetermined)
    """
    paramPass = validateString(name, val, "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    if not paramPass:
        rsvLogger.error("\t...: Malformed Guid")
    return paramPass


def validateInt(name, val, minVal=None, maxVal=None):
    """
    Validates a Int, then passes info to validateNumber
    """
    if not isinstance(val, int):
        rsvLogger.error("{}: Expected integer, got type {}".format(name, str(type(val))))
        return False
    else:
        return validateNumber(name, val, minVal, maxVal)


def validateNumber(name, val, minVal=None, maxVal=None):
    """
    Validates a Number and its min/max values
    """
    paramPass = isinstance(val, (int, float))
    if paramPass:
        if minVal is not None:
            paramPass = paramPass and minVal <= val
            if not paramPass:
                rsvLogger.error("{}: Value out of assigned min range, {} < {}".format(name, str(val), str(minVal)))
        if maxVal is not None:
            paramPass = paramPass and maxVal >= val
            if not paramPass:
                rsvLogger.error("{}: Value out of assigned max range, {} > {}".format(name, str(val), str(maxVal)))
    else:
        rsvLogger.error("{}: Expected integer or float, got type {}".format(name, str(type(val))))
    return paramPass


def checkPropertyConformance(soup, PropertyName, PropertyItem, decoded, refs):
    # The biggest piece of code, but also mostly collabs info for other functions
    #   this part of the program should maybe do ALL setup for functions above, do not let them do requests?
    # info: what about this property is important (read/write, name, val, nullability, mandatory), 
    # warn: No compiled info but that's ok, it's not implemented
    # error: no pass, mandatory/null fail, no compiled info but is present/mandatory
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
    rsvLogger.info("\tvalue: {} {}".format(propValue, type(propValue)))

    propExists = not (propValue == 'n/a')
    propNotNull = propExists and propValue is not None and propValue is not 'None'

    if PropertyItem is None:
        if not propExists:
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

    propType = propAttr.get('Type')
    propRealType = PropertyItem.get('realtype')
    rsvLogger.info("\thas Type: {} {}".format(propType, propRealType))

    # why not actually check oem
    # rs-assertion: 7.4.7.2
    if 'Oem' in PropertyName:
        rsvLogger.info('\tOem is skipped')
        counts['skipOem'] += 1
        return {item: ('-', '-',
                            'Exists' if propExists else 'DNE', 'skipOEM')}, counts

    propMandatory = False
    propMandatoryPass = True

    if 'Redfish.Required' in PropertyItem:
        propMandatory = True
        propMandatoryPass = True if propExists else False
        rsvLogger.info("\tMandatory Test: {}".format(
                       'OK' if propMandatoryPass else 'FAIL'))
    else:
        rsvLogger.info("\tis Optional")
        if not propExists:
            rsvLogger.info("\tprop Does not exist, skip...")
            counts['skipOptional'] += 1
            return {item: (
                '-', (propType, propRealType),
                'Exists' if propExists else 'DNE',
                'skipOptional')}, counts

    propNullable = propAttr.get('nullable')
    propNullablePass = True
    if propNullable is not None:
        propNullablePass = (
            propNullable == 'true') or not propExists or propNotNull
        rsvLogger.info("\tis Nullable: {} {}".format(propNullable, propNotNull))
        rsvLogger.info("\tNullability test: {}".format(
                       'OK' if propNullablePass else 'FAIL'))

    # rs-assertion: Check for permission change
    propPermissions = propAttr.get('Odata.Permissions')
    if propPermissions is not None:
        propPermissionsValue = propPermissions['EnumMember']
        rsvLogger.info("\tpermission {}".format(propPermissionsValue))

    autoExpand = PropertyItem.get('OData.AutoExpand', None) is not None or\
        PropertyItem.get('OData.AutoExpand'.lower(), None) is not None

    validPatternAttr = PropertyItem.get(
        'Validation.Pattern')
    validMinAttr = PropertyItem.get('Validation.Minimum')
    validMaxAttr = PropertyItem.get('Validation.Maximum')

    validMin, validMax = int(validMinAttr['Int']) if validMinAttr is not None else None, \
        int(validMaxAttr['Int']) if validMaxAttr is not None else None
    validPattern = validPatternAttr.get('String', '') if validPatternAttr is not None else None
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
                paramPass = isinstance(val, bool)
                if not paramPass:
                    rsvLogger.error("{}: Not a boolean".format(PropertyName))

            elif propRealType == 'Edm.DateTimeOffset':
                paramPass = validateDatetime(PropertyName, val)

            elif propRealType == 'Edm.Int16' or propRealType == 'Edm.Int32' or\
                    propRealType == 'Edm.Int64' or propRealType == 'Edm.Int':
                paramPass = validateInt(PropertyName, val, validMin, validMax)

            elif propRealType == 'Edm.Decimal' or propRealType == 'Edm.Double':
                paramPass = validateNumber(PropertyName, val, validMin, validMax)

            elif propRealType == 'Edm.Guid':
                paramPass = validateGuid(PropertyName, val)

            elif propRealType == 'Edm.String':
                paramPass = validateString(PropertyName, val, validPattern)

            else:
                if propRealType == 'complex':
                    innerPropType = PropertyItem['typeprops']
                    success, complexCounts, complexMessages = validateComplex(PropertyName, val, innerPropType, decoded.get('@odata.type'))
                    if not success:
                        counts['failComplex'] += 1
                        resultList[item + appendStr] = (
                                    'ComplexDictionary' + appendStr, (propType, propRealType),
                                    'Exists' if propExists else 'DNE',
                                    'failComplex')
                        continue
                    resultList[item + appendStr] = (
                                    'ComplexDictionary' + appendStr, (propType, propRealType),
                                    'Exists' if propExists else 'DNE',
                                    'complex')

                    counts.update(complexCounts)
                    for complexKey in complexMessages:
                        resultList[item + '.' + complexKey + appendStr] = complexMessages[complexKey]
                    additionalComplex = innerPropType.additional 
                    for key in val:
                        if key not in complexMessages and not additionalComplex:
                            rsvLogger.error('%s: Appears to be an extra property (check inheritance or casing?)', item + '.' + key + appendStr)  # Printout FORMAT
                            counts['failComplexAdditional'] += 1
                            resultList[item + '.' + key + appendStr] = (
                                    val[key], '-',
                                    'Exists (additional)',
                                    'failAdditional')
                        elif key not in complexMessages:
                            counts['unverifiedComplexAdditional'] += 1
                            resultList[item + '.' + key + appendStr] = (val[key], '-',
                                             'Exists (additional.ok)',
                                             'skipAdditional')
                    continue

                elif propRealType == 'enum':
                    paramPass = validateEnum(PropertyName, val, PropertyItem['typeprops'])

                elif propRealType == 'deprecatedEnum':
                    paramPass = validateDeprecatedEnum(PropertyName, val, PropertyItem['typeprops'])

                elif propRealType == 'entity':
                    paramPass = validateEntity(PropertyName, val, propType, propCollectionType, soup, refs, autoExpand)
                else:
                    rsvLogger.error("%s: This type is invalid %s" % (PropertyName, propRealType))  # Printout FORMAT
                    paramPass = False

        resultList[item + appendStr] = (
                val, (propType, propRealType),
                'Exists' if propExists else 'DNE',
                'PASS' if paramPass and propMandatoryPass and propNullablePass else 'FAIL')
        if paramPass and propNullablePass and propMandatoryPass:
            counts['pass'] += 1
            rsvLogger.info("\tSuccess")  # Printout FORMAT
        else:
            counts['err.' + str(propType)] += 1
            if not paramPass:
                if propMandatory:
                    rsvLogger.error("%s: Mandatory prop has failed to check" % PropertyName)  # Printout FORMAT
                    counts['failMandatoryProp'] += 1
                else:
                    counts['failProp'] += 1
            elif not propMandatoryPass:
                rsvLogger.error("%s: Mandatory prop does not exist" % PropertyName)  # Printout FORMAT
                counts['failMandatoryExist'] += 1
            elif not propNullablePass:
                rsvLogger.error("%s: This property is not nullable" % PropertyName)  # Printout FORMAT
                counts['failNull'] += 1
            rsvLogger.info("\tFAIL")  # Printout FORMAT

    return resultList, counts


def checkPayloadConformance(uri, decoded):
    # Checks for @odata, generates "messages"
    #   largely not a lot of error potential
    # info: what did we get?  did it pass?
    # error: what went wrong?  do this per key
    messages = dict()
    success = True
    for key in [k for k in decoded if '@odata' in k]:
        paramPass = False
        if key == '@odata.id':
            paramPass = isinstance(decoded[key], str)
            if paramPass:
                paramPass = re.match('(\/.*)+(#([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*)?', decoded[key]) is not None
        elif key == '@odata.count':
            paramPass = isinstance(decoded[key], int)
        elif key == '@odata.context':
            paramPass = isinstance(decoded[key], str)
            if paramPass:
                paramPass = re.match('(\/.*)+#([a-zA-Z0-9_.-]*\.)[a-zA-Z0-9_.-]*', decoded[key]) is not None or\
                    re.match('(\/.*)+#(\/.*)+[/]$entity', decoded[key]) is not None
        elif key == '@odata.type':
            paramPass = isinstance(decoded[key], str)
            if paramPass:
                paramPass = re.match('#([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*', decoded[key]) is not None
            pass
        else:
            paramPass = True
        if not paramPass:
            rsvLogger.error(key + "@odata item not compliant: " + decoded[key])  # Printout FORMAT
            success = False
        messages[key] = (
                decoded[key], 'odata',
                'Exists',
                'PASS' if paramPass else 'FAIL')
    return success, messages


def validateSingleURI(URI, uriName='', expectedType=None, expectedSchema=None, expectedJson=None, parent=None):
    # Single payload validation, gets the data, connstructs, validates all properties found...
    #   A lot can go wrong, but not a lot of program happens here, it is in other functions
    #   returns a load of work, that is collabed in validateTree... 
    #   change: why should we get the payload in traverseService, maybe don't do that if we can afford not to
    #           get the payload and pass it in personally... no validation takes place in traverse, but what about
    #           checking if a payload is not broken?  true csdl xml and true json...
    #   relies on lack of nones, only errors should occur inside of other functions... should NOT be drawing errors outside
    #   hereon out, after type construction, all validation functions will expect real/nonbroken values... how can they be broken?
    #   type construction should not be broken, property construction should be entirely valid, nothing missing if it can't be missing
    # info: where are we going, what is our payload 
    # error: broken odata, broken uri, broken properties... good for informing user, wrap exceptions to keep program trucking
    # warn: 
    # debug: 
    # rs-assertion: 9.4.1
    # Initial startup here
    errorMessages = io.StringIO()
    fmt = logging.Formatter('%(levelname)s - %(message)s')
    errh = logging.StreamHandler(errorMessages)
    errh.setLevel(logging.ERROR)
    errh.setFormatter(fmt)
    rsvLogger = rst.getLogger()
    rsvLogger.addHandler(errh)  # Printout FORMAT

    # Start
    rsvLogger.info("\n*** %s, %s", uriName, URI)  # Printout FORMAT
    rsvLogger.debug("\n*** %s, %s, %s", expectedType, expectedSchema is not None, expectedJson is not None)  # Printout FORMAT
    counts = Counter()
    results = OrderedDict()
    messages = OrderedDict()
    success = True

    # check for @odata mandatory stuff
    # check for version numbering problems
    # check id if its the same as URI
    # check @odata.context instead of local.  Realize that @odata is NOT a "property"

    # Attempt to get a list of properties
    if expectedJson is None:
        successGet, jsondata, status, rtime = rst.callResourceURI(URI)
    else:
        successGet, jsondata = True, expectedJson
    successPayload, odataMessages = checkPayloadConformance(URI, jsondata if successGet else {})
    messages.update(odataMessages)

    if not successPayload:
        counts['failPayloadError'] += 1
        rsvLogger.error(str(URI) + ':  payload error, @odata property noncompliant',)  # Printout FORMAT
        # rsvLogger.removeHandler(errh)  # Printout FORMAT
        # return False, counts, results, None, propResourceObj
    # Generate dictionary of property info

    try:
        propResourceObj = rst.ResourceObj(
            uriName, URI, expectedType, expectedSchema, expectedJson, parent)
        if not propResourceObj.initiated:
            counts['problemResource'] += 1
            success = False
            results[uriName] = (URI, success, counts, messages,
                                errorMessages, None, None)
            rsvLogger.removeHandler(errh)  # Printout FORMAT
            return False, counts, results, None, None
    except Exception as e:
        rsvLogger.exception("")  # Printout FORMAT
        counts['exceptionResource'] += 1
        success = False
        results[uriName] = (URI, success, counts, messages,
                            errorMessages, None, None)
        rsvLogger.removeHandler(errh)  # Printout FORMAT
        return False, counts, results, None, None
    counts['passGet'] += 1
    results[uriName] = (str(URI) + ' (response time: {}s)'.format(propResourceObj.rtime), success, counts, messages, errorMessages, propResourceObj.context, propResourceObj.typeobj.fulltype)

    node = propResourceObj.typeobj
    while node is not None:
        for prop in node.propList:
            try:
                propMessages, propCounts = checkPropertyConformance(node.soup, prop.name, prop.propDict, propResourceObj.jsondata, node.refs)
                messages.update(propMessages)
                counts.update(propCounts)
            except Exception as ex:
                rsvLogger.exception("Something went wrong")  # Printout FORMAT
                rsvLogger.error('%s:  Could not finish check on this property' % (prop.name))  # Printout FORMAT
                counts['exceptionPropCheck'] += 1
        node = node.parent

    successService, serviceSchemaSoup, SchemaServiceURI = rst.getSchemaDetails(
        '$metadata', '/redfish/v1/$metadata')
    if successService:
        serviceRefs = rst.getReferenceDetails(serviceSchemaSoup, name="$metadata")
        for prop in propResourceObj.additionalList:
            propMessages, propCounts = checkPropertyConformance(serviceSchemaSoup, prop.name, prop.propDict, propResourceObj.jsondata, serviceRefs)
            messages.update(propMessages)
            counts.update(propCounts)

    uriName, SchemaFullType, jsonData = propResourceObj.name, propResourceObj.typeobj.fulltype, propResourceObj.jsondata
    SchemaNamespace, SchemaType = rst.getNamespace(SchemaFullType), rst.getType(SchemaFullType)

    # List all items checked and unchecked
    # current logic does not check inside complex types
    fmt = '%-30s%30s'
    rsvLogger.info('%s, %s, %s', uriName, SchemaNamespace, SchemaType)  # Printout FORMAT

    for key in jsonData:
        item = jsonData[key]
        rsvLogger.info(fmt % (  # Printout FORMAT
            key, messages[key][3] if key in messages else 'Exists, no schema check'))
        if key not in messages: 
            # note: extra messages for "unchecked" properties
            if not propResourceObj.typeobj.additional:
                rsvLogger.error('%s: Appears to be an extra property (check inheritance or casing?)', key)  # Printout FORMAT
                counts['failAdditional'] += 1
                messages[key] = (item, '-',
                                 'Exists (add.)',
                                 'failAdditional')
            else:
                counts['unverifiedAdditional'] += 1
                messages[key] = (item, '-',
                                 'Exists (add.ok)',
                                 'skipAdditional')

    for key in messages:
        if key not in jsonData:
            rsvLogger.info(fmt % (key, messages[key][3]))  # Printout FORMAT

    rsvLogger.info('%s, %s', SchemaFullType, counts)  # Printout FORMAT

    # Get all links available

    rsvLogger.debug(propResourceObj.links)  # Printout FORMAT
    rsvLogger.removeHandler(errh)  # Printout FORMAT
    return True, counts, results, propResourceObj.links, propResourceObj


def validateURITree(URI, uriName, expectedType=None, expectedSchema=None, expectedJson=None, parent=None, allLinks=None):
    # from given URI, validate it, then follow its links like nodes
    #   Other than expecting a valid URI, on success (real URI) expects valid links
    #   valid links come from getAllLinks, includes info such as expected values, etc
    #   as long as it is able to pass that info, should not crash
    # info: destinations, individual expectations of each?
    # error: on fail
    # warn: reference only?
    # debug:
    traverseLogger = rst.getLogger()

    def executeLink(linkItem, parent=None):
        linkURI, autoExpand, linkType, linkSchema, innerJson = linkItem

        if linkType is not None and autoExpand:
            returnVal = validateURITree(
                    linkURI, uriName + ' -> ' + linkName, linkType, linkSchema, innerJson, parent, allLinks)
        else:
            returnVal = validateURITree(
                    linkURI, uriName + ' -> ' + linkName, parent=parent, allLinks=allLinks)
        traverseLogger.info('%s, %s', linkName, returnVal[1])  # Printout FORMAT
        return returnVal

    top = allLinks is None
    if top:
        allLinks = set()
    allLinks.add(URI)
    refLinks = OrderedDict()

    validateSuccess, counts, results, links, thisobj = validateSingleURI(
                URI, uriName, expectedType, expectedSchema, expectedJson, parent)
    if validateSuccess:
        for linkName in links:
            if 'Links' in linkName.split('.', 1)[0] or 'RelatedItem' in linkName.split('.', 1)[0] or 'Redundancy' in linkName.split('.',1)[0]:
                refLinks[linkName] = links[linkName]
                continue
            if links[linkName][0] in allLinks:
                counts['repeat'] += 1
                continue

            success, linkCounts, linkResults, xlinks, xobj = executeLink(links[linkName], thisobj)
            refLinks.update(xlinks)
            if not success:
                counts['unvalidated'] += 1
            results.update(linkResults)

    if top:
        for linkName in refLinks:
            if refLinks[linkName][0] not in allLinks:
                traverseLogger.info('%s, %s', linkName, refLinks[linkName])  # Printout FORMAT
                counts['reflink'] += 1
            else:
                continue

            success, linkCounts, linkResults, xlinks, xobj = executeLink(refLinks[linkName], thisobj)
            if not success:
                counts['unvalidatedRef'] += 1
            results.update(linkResults)

    return validateSuccess, counts, results, refLinks, thisobj


def main(argv):
    # this should be surface level, does no execution (should maybe move html rendering to its own function
    # Only worry about configuring, executing and exiting circumstances, printout setup
    # info: config information (without password), time started/finished, individual problems, pass/fail
    # error: config is not good (catch, success), traverse is not good (should never happen)
    # warn: what's missing that we can work around (local files?)
    # debug:    
    argget = argparse.ArgumentParser(description='tool to test a service against a collection of Schema')
    argget.add_argument('--ip', type=str, help='ip to test on [host:port]')
    argget.add_argument('--payload', type=str, help='mode to validate payloads [Tree, Single, SingleFile, TreeFile] followed by resource/filepath', nargs=2)
    argget.add_argument('--cache', type=str, help='cache mode [Off, Fallback, Prefer] followed by directory', nargs=2)
    argget.add_argument('-c', '--config', type=str, help='config file (overrides other params)')
    argget.add_argument('-u', '--user', default=None, type=str, help='user for basic auth')
    argget.add_argument('-p', '--passwd', default=None, type=str, help='pass for basic auth')
    argget.add_argument('--desc', type=str, default='No desc', help='sysdescription for identifying logs')
    argget.add_argument('--dir', type=str, default='./SchemaFiles/metadata', help='directory for local schema files')
    argget.add_argument('--logdir', type=str, default='./logs', help='directory for log files')
    argget.add_argument('--timeout', type=int, default=30, help='requests timeout in seconds')
    argget.add_argument('--nochkcert', action='store_true', help='ignore check for certificate')
    argget.add_argument('--nossl', action='store_true', help='use http instead of https')
    argget.add_argument('--authtype', type=str, default='Basic', help='authorization type (None|Basic|Session)')
    argget.add_argument('--localonly', action='store_true', help='only use locally stored schema on your harddrive')
    argget.add_argument('--service', action='store_true', help='only use uris within the service')
    argget.add_argument('--suffix', type=str, default='_v1.xml', help='suffix of local schema files (for version differences)')
    argget.add_argument('--ca_bundle', default="", type=str, help='path to Certificate Authority bundle file or directory')
    argget.add_argument('--http_proxy', type=str, default=None, help='URL for the HTTP proxy')
    argget.add_argument('--https_proxy', type=str, default=None, help='URL for the HTTPS proxy')
    argget.add_argument('-v', action='store_true', help='verbose log output to stdout')

    args = argget.parse_args()

    if args.v:
        rst.ch.setLevel(logging.DEBUG)

    try:
        if args.config is not None:
            rst.setConfig(args.config)
            rst.isConfigSet()
        elif args.ip is not None:
            rst.setConfigNamespace(args)
            rst.isConfigSet()
        else:
            rsvLogger.info('No ip or config specified.')  # Printout FORMAT
            argget.print_help()
            return 1
    except Exception as ex:
        rsvLogger.exception("Something went wrong")  # Printout FORMAT
        return 1

    config_str = ""
    for cnt, item in enumerate(sorted(list(rst.config.keys() - set(['systeminfo', 'configuri', 'targetip', 'configset', 'password']))), 1):
        config_str += "{}: {},  ".format(str(item), str(rst.config[item] if rst.config[item] != '' else 'None'))
        if cnt % 6 == 0:
            config_str += '\n'

    sysDescription, ConfigURI = (rst.config['systeminfo'], rst.config['configuri'])
    logpath = rst.config['logpath']

    # Logging config
    startTick = datetime.now()
    if not os.path.isdir(logpath):
        os.makedirs(logpath)
    fmt = logging.Formatter('%(levelname)s - %(message)s')
    fh = logging.FileHandler(datetime.strftime(startTick, os.path.join(logpath, "ConformanceLog_%m_%d_%Y_%H%M%S.txt")))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    rsvLogger.addHandler(fh)  # Printout FORMAT
    rsvLogger.info('ConfigURI: ' + ConfigURI)
    rsvLogger.info('System Info: ' + sysDescription)  # Printout FORMAT
    rsvLogger.info(config_str)
    rsvLogger.info('Start time: ' + startTick.strftime('%x - %X'))  # Printout FORMAT

    # Start main
    status_code = 1
    jsonData = None
    if rst.config.get('payloadmode') not in ['Tree', 'Single', 'SingleFile', 'TreeFile', 'Default']:
        rst.config['payloadmode'] = 'Default'
        rsvLogger.error('PayloadMode or path invalid, using Default behavior')
    if 'File' in rst.config.get('payloadmode'):
        if rst.config.get('payloadfilepath') is not None and os.path.isfile(rst.config.get('payloadfilepath')):
            with open(rst.config.get('payloadfilepath')) as f:
                jsonData = json.load(f)
                f.close()
        else:
            rsvLogger.error('File not found {}'.format(rst.config.get('payloadfilepath')))
            return 1
    if 'Single' in rst.config.get('payloadmode'):
        success, counts, results, xlinks, topobj = validateSingleURI(rst.config.get('payloadfilepath'), 'Target', expectedJson=jsonData)
    elif 'Tree' in rst.config.get('payloadmode'):
        success, counts, results, xlinks, topobj = validateURITree(rst.config.get('payloadfilepath'), 'Target', expectedJson=jsonData)
    else:
        success, counts, results, xlinks, topobj = validateURITree('/redfish/v1', 'ServiceRoot', expectedJson=jsonData)
    finalCounts = Counter()
    nowTick = datetime.now()
    rsvLogger.info('Elapsed time: {}'.format(str(nowTick-startTick).rsplit('.', 1)[0]))  # Printout FORMAT
    if rst.currentSession.started:
        rst.currentSession.killSession()

    # Render html
    htmlStrTop = '<html><head><title>Conformance Test Summary</title>\
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
                <tr><th>##### Redfish Conformance Test Report #####</th></tr>\
                <tr><th>System: ' + ConfigURI + '</th></tr>\
                <tr><th>Description: ' + sysDescription + '</th></tr>\
                <tr><th>' + str(config_str.replace('\n', '</br>')) + '</th></tr>\
                <tr><th>Start time: ' + (startTick).strftime('%x - %X') + '</th></tr>\
                <tr><th>Run time: ' + str(nowTick-startTick).rsplit('.', 1)[0] + '</th></tr>\
                <tr><th></th></tr>'

    htmlStr = ''

    rsvLogger.info(len(results))
    for cnt, item in enumerate(results):
        htmlStr += '<tr><td class="titlerow"><table class="titletable"><tr>'
        htmlStr += '<td class="title" style="width:40%"><div>{}</div>\
                <div class="button warn" onClick="document.getElementById(\'resNum{}\').classList.toggle(\'resultsShow\');">Show results</div>\
                </td>'.format(results[item][0], cnt, cnt)
        htmlStr += '<td class="titlesub log" style="width:30%"><div><b>ResourcePath:</b> {}</div><div><b>XML:</b> {}</div><div><b>type:</b> {}</div></td>'.format(item, results[item][5], results[item][6])
        htmlStr += '<td style="width:10%"' + \
            ('class="pass"> GET Success' if results[item]
             [1] else 'class="fail"> GET Failure') + '</td>'
        htmlStr += '<td style="width:10%">'

        innerCounts = results[item][2]
        finalCounts.update(innerCounts)
        for countType in sorted(innerCounts.keys()):
            if 'problem' in countType or 'fail' in countType or 'exception' in countType:
                rsvLogger.error('{} {} errors in {}'.format(innerCounts[countType], countType, str(results[item][0]).split(' ')[0]))  # Printout FORMAT
            innerCounts[countType] += 0
            htmlStr += '<div {style}>{p}: {q}</div>'.format(
                    p=countType,
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
                    if 'PASS' in str(j).upper():
                        htmlStr += '<td class="pass center">' + str(j) + '</td>'
                    elif 'FAIL' in str(j).upper():
                        htmlStr += '<td class="fail center">' + str(j) + '</td>'
                    elif 'SKIP' in str(j).upper():
                        htmlStr += '<td class="warn center">' + str(j) + '</td>'
                    else:
                        htmlStr += '<td >' + str(j) + '</td>'
                htmlStr += '</tr>'
        htmlStr += '</table></td></tr>'
        if results[item][4] is not None:
            htmlStr += '<tr><td class="fail log">' + str(results[item][4].getvalue()).replace('\n', '<br />') + '</td></tr>'
            results[item][4].close()
        htmlStr += '<tr><td>---</td></tr></table></td></tr>'

    htmlStr += '</table></body></html>'

    htmlStrTotal = '<tr><td><div>Final counts: '
    for countType in sorted(finalCounts.keys()):
        htmlStrTotal += '{p}: {q},   '.format(p=countType, q=finalCounts.get(countType, 0))
    htmlStrTotal += '</div><div class="button warn" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results resultsShow\'};">Expand All</div>'
    htmlStrTotal += '</div><div class="button fail" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results\'};">Collapse All</div>'

    htmlPage = htmlStrTop + htmlStrBodyHeader + htmlStrTotal + htmlStr

    with open(datetime.strftime(startTick, os.path.join(logpath, "ConformanceHtmlLog_%m_%d_%Y_%H%M%S.html")), 'w') as f:
        f.write(htmlPage)

    fails = 0
    for key in finalCounts:
        if 'problem' in key or 'fail' in key or 'exception' in key:
            fails += finalCounts[key]

    success = success and not (fails > 0)
    rsvLogger.info(finalCounts)

    if not success:
        rsvLogger.info("Validation has failed: {} problems found".format(fails))
    else:
        rsvLogger.info("Validation has succeeded.")
        status_code = 0

    return status_code


if __name__ == '__main__':
    sys.exit(main(sys.argv))
