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
import traverseService as rst

rsvLogger = rst.getLogger()


def validateActions(name, val, propTypeObj, payloadType):
    """
    Validates an action dict (val)
    """
    actionMessages, actionCounts = OrderedDict(), Counter()
    # traverse through all parent types to discover Action tags
    success, baseSoup, baseRefs, baseType = True, propTypeObj.soup, propTypeObj.refs, payloadType
    actionsDict = dict()
    while success:
        SchemaNamespace = rst.getNamespace(baseType)
        innerschema = baseSoup.find('schema', attrs={'namespace': SchemaNamespace})
        actions = innerschema.find_all('action')
        for act in actions:
            keyname = '#%s.%s' % (SchemaNamespace, act['name'])
            actionsDict[keyname] = act
        success, baseSoup, baseRefs, baseType = rst.getParentType(baseSoup, baseRefs, baseType, 'entitytype')

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
                rsvLogger.warn(k + ': target for action is missing')
                actPass = True
            else:
                rsvLogger.error(k + ': target for action is malformed')
        else:
            # <Annotation Term="Redfish.Required"/>
            if actionsDict[k].find('annotation', {'term': 'Redfish.Required'}):
                rsvLogger.error(k + ': action not Found, is mandatory')
            else:
                actPass = True
                rsvLogger.warn(k + ': action not Found, is not mandatory')
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
    rsvLogger.debug('%s, %s, %s', success, (propType, propCollectionType), data)
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
        if soup.find('schema', attrs={'namespace': rst.getNamespace(currentType)}) is not None:
            success, baseSoup = True, soup
        elif baseLink is not None:
            success, baseSoup, uri = rst.getSchemaDetails(*baseLink)
        else:
            success = False
        rsvLogger.debug('success: %s %s %s', success, currentType, baseLink)

        # Recurse through parent types, gather type hierarchy to check against
        if currentType is not None and success:
            currentType = currentType.replace('#', '')
            baseRefs = rst.getReferenceDetails(baseSoup, refs)
            allTypes = []
            while currentType not in allTypes and success:
                allTypes.append(currentType)
                success, baseSoup, baseRefs, currentType = rst.getParentType(baseSoup, baseRefs, currentType, 'entitytype')
                rsvLogger.debug('success: %s %s', success, currentType)

            rsvLogger.debug('%s, %s, %s', propType, propCollectionType, allTypes)
            paramPass = propType in allTypes or propCollectionType in allTypes
            if not paramPass:
                rsvLogger.error("%s: Expected Entity type %s, but not found in type inheritance %s" % (name, (propType, propCollectionType), allTypes))
        else:
            rsvLogger.error("%s: Could not get schema file for Entity check" % name)
    else:
        rsvLogger.error("%s: Could not get resource for Entity check" % name)
    return paramPass


def validateComplex(name, val, propTypeObj, payloadType):
    """
    Validate a complex property
    """
    rsvLogger.info('\t***going into Complex')
    if not isinstance(val, dict):
        rsvLogger.error(name + ' : Complex item not a dictionary')
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
            propMessages, propCounts = checkPropertyCompliance(propSoup, prop.name, prop.propDict, val, propRefs)
            complexMessages.update(propMessages)
            complexCounts.update(propCounts)

    node = propTypeObj
    while node is not None:
        propList, propSoup, propRefs = node.propList, node.soup, node.refs
        for prop in propList:
            propMessages, propCounts = checkPropertyCompliance(propSoup, prop.name, prop.propDict, val, propRefs)
            complexMessages.update(propMessages)
            complexCounts.update(propCounts)
        node = node.parent
    successPayload, odataMessages = checkPayloadCompliance('', val)
    complexMessages.update(odataMessages)
    if not successPayload:
        complexCounts['failPayloadError'] += 1
        rsvLogger.error(str("In complex") + ':  payload error, @odata property noncompliant',)
    rsvLogger.info('\t***out of Complex')
    rsvLogger.info('complex %s', complexCounts)
    if ":Actions" in name:
        aMsgs, aCounts = validateActions(name, val, propTypeObj, payloadType)
        complexMessages.update(aMsgs)
        complexCounts.update(aCounts)
    return True, complexCounts, complexMessages


def validateDeprecatedEnum(name, val, listEnum):
    paramPass = True
    if isinstance(val, list):
        for enumItem in val:
            for k, v in enumItem.items():
                rsvLogger.debug('%s, %s' % (k, v))
                paramPass = paramPass and str(v) in listEnum
        if not paramPass:
            rsvLogger.error("%s: Invalid DeprecatedEnum found (check casing?)" % name)
    elif isinstance(val, str):
        rsvLogger.debug('%s' % val)
        paramPass = str(val) in listEnum
        if not paramPass:
            rsvLogger.error("%s: Invalid DeprecatedEnum found (check casing?)" % name)
    else:
        rsvLogger.error("%s: Expected list/str value for DeprecatedEnum? " % name)
    return paramPass


def validateEnum(name, val, listEnum):
    paramPass = isinstance(val, str)
    if paramPass:
        paramPass = val in listEnum
        if not paramPass:
            rsvLogger.error("%s: Invalid enum found (check casing?)" % name)
    else:
        rsvLogger.error("%s: Expected string value for Enum" % name)
    return paramPass


def validateString(name, val, pattern=None):
    paramPass = isinstance(val, str)
    if paramPass:
        if pattern is not None:
            match = re.fullmatch(pattern, val)
            paramPass = match is not None
            if not paramPass:
                rsvLogger.error("%s: Malformed String" % name)
        else:
            paramPass = True
    else:
        rsvLogger.error("%s: Expected string value" % name)
    return paramPass


def validateDatetime(name, val):
    paramPass = validateString(name, val, '.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])')
    if not paramPass:
        rsvLogger.error("\t%s: Malformed DateTimeOffset" % name)
    return paramPass


def validateGuid(name, val):
    paramPass = validateString(name, val, "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    if not paramPass:
        rsvLogger.error("\t%s: Malformed Guid" % name)
    return paramPass


def validateInt(name, val, minVal=None, maxVal=None):
    if not isinstance(val, int):
        rsvLogger.error("%s: Expected int" % name)
        return False
    else:
        return validateNumber(name, val, minVal, maxVal)


def validateNumber(name, val, minVal=None, maxVal=None):
    paramPass = isinstance(val, (int, float))
    if paramPass:
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
            return {item: (
                '-', (propType, propRealType),
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

    autoExpand = PropertyItem.get('OData.AutoExpand', None) is not None or\
        PropertyItem.get('OData.AutoExpand'.lower(), None) is not None

    validPatternAttr = PropertyItem.get(
        'Validation.Pattern')
    validMinAttr = PropertyItem.get('Validation.Minimum')
    validMaxAttr = PropertyItem.get('Validation.Maximum')

    validMin, validMax = int(validMinAttr['int']) if validMinAttr is not None else None, \
        int(validMaxAttr['int']) if validMaxAttr is not None else None
    validPattern = validPatternAttr.get('string', '') if validPatternAttr is not None else None
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
                    rsvLogger.error("%s: Not a boolean" % PropertyName)

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

                    for key in val:
                        if key not in complexMessages and not innerPropType.additional:
                            rsvLogger.error('%s: Appears to be an extra property (check inheritance or casing?)', item + '.' + key + appendStr)
                            counts['failAdditional'] += 1
                            resultList[item + '.' + key + appendStr] = (
                                    val[key], '-',
                                    'Exists',
                                    '-')
                    continue

                elif propRealType == 'enum':
                    paramPass = validateEnum(PropertyName, val, PropertyItem['typeprops'])

                elif propRealType == 'deprecatedEnum':
                    paramPass = validateDeprecatedEnum(PropertyName, val, PropertyItem['typeprops'])

                elif propRealType == 'entity':
                    paramPass = validateEntity(PropertyName, val, propType, propCollectionType, soup, refs, autoExpand)
                else:
                    rsvLogger.error("%s: This type is invalid %s" % (PropertyName, propRealType))
                    paramPass = False

        resultList[item + appendStr] = (
                val, (propType, propRealType),
                'Exists' if propExists else 'DNE',
                'PASS' if paramPass and propMandatoryPass and propNullablePass else 'FAIL')
        if paramPass and propNullablePass and propMandatoryPass:
            counts['pass'] += 1
            rsvLogger.info("\tSuccess")
        else:
            counts['err.' + str(propType)] += 1
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


def checkPayloadCompliance(uri, decoded):
    messages = dict()
    success = True
    for key in [k for k in decoded if '@odata' in k]:
        # itemType = key.split('.',1)[-1]
        # itemTarget = key.split('.',1)[0]
        paramPass = False
        if key == '@odata.id':
            paramPass = isinstance(decoded[key], str)
            paramPass = re.match('(\/.*)+(#([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*)?', decoded[key]) is not None
            pass
        elif key == '@odata.count':
            paramPass = isinstance(decoded[key], int)
            pass
        elif key == '@odata.context':
            paramPass = isinstance(decoded[key], str)
            paramPass = re.match('(\/.*)+#([a-zA-Z0-9_.-]*\.)[a-zA-Z0-9_.-]*', decoded[key]) is not None
            pass
        elif key == '@odata.type':
            paramPass = isinstance(decoded[key], str)
            paramPass = re.match('#([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*', decoded[key]) is not None
            pass
        else:
            paramPass = True
        if not paramPass:
            rsvLogger.error(key + "@odata item not compliant: " + decoded[key])
            success = False
        messages[key] = (
                decoded[key], 'odata',
                'Exists',
                'PASS' if paramPass else 'FAIL')
    return success, messages


def validateSingleURI(URI, uriName='', expectedType=None, expectedSchema=None, expectedJson=None, parent=None):
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
    results = OrderedDict()
    messages = OrderedDict()
    success = True

    # check for @odata mandatory stuff
    # check for version numbering problems
    # check id if its the same as URI
    # check @odata.context instead of local.  Realize that @odata is NOT a "property"

    # Attempt to get a list of properties
    successGet, jsondata, status, rtime = rst.callResourceURI(URI)
    successPayload, odataMessages = checkPayloadCompliance(URI, jsondata if successGet else {})
    messages.update(odataMessages)

    if not successPayload:
        counts['failPayloadError'] += 1
        rsvLogger.error(str(URI) + ':  payload error, @odata property noncompliant',)
        # rsvLogger.removeHandler(errh)
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
            return False, counts, results, None, None
    except Exception as e:
        counts['exceptionResource'] += 1
        success = False
        results[uriName] = (URI, success, counts, messages,
                            errorMessages, None, None)
        return False, counts, results, None, None
    counts['passGet'] += 1
    results[uriName] = (str(URI) + ' ({}s)'.format(propResourceObj.rtime), success, counts, messages, errorMessages, propResourceObj.context, propResourceObj.typeobj.fulltype)

    node = propResourceObj.typeobj
    while node is not None:
        for prop in node.propList:
            try:
                propMessages, propCounts = checkPropertyCompliance(node.soup, prop.name, prop.propDict, propResourceObj.jsondata, node.refs)
                messages.update(propMessages)
                counts.update(propCounts)
            except Exception as ex:
                rsvLogger.exception("Something went wrong")
                rsvLogger.error('%s:  Could not finish compliance check on this property' % (prop.name))
                counts['exceptionPropCompliance'] += 1
        node = node.parent

    successService, serviceSchemaSoup, SchemaServiceURI = rst.getSchemaDetails(
        '$metadata', '/redfish/v1/$metadata')
    if successService:
        serviceRefs = rst.getReferenceDetails(serviceSchemaSoup)
        for prop in propResourceObj.additionalList:
            propMessages, propCounts = checkPropertyCompliance(serviceSchemaSoup, prop.name, prop.propDict, propResourceObj.jsondata, serviceRefs)
            messages.update(propMessages)
            counts.update(propCounts)

    uriName, SchemaFullType, jsonData = propResourceObj.name, propResourceObj.typeobj.fulltype, propResourceObj.jsondata
    SchemaNamespace, SchemaType = rst.getNamespace(SchemaFullType), rst.getType(SchemaFullType)

    # List all items checked and unchecked
    # current logic does not check inside complex types
    fmt = '%-30s%30s'
    rsvLogger.info('%s, %s, %s', uriName, SchemaNamespace, SchemaType)

    for key in jsonData:
        item = jsonData[key]
        rsvLogger.info(fmt % (
            key, messages[key][3] if key in messages else 'Exists, no schema check'))
        if key not in messages and not propResourceObj.typeobj.additional:
            # note: extra messages for "unchecked" properties
            rsvLogger.error('%s: Appears to be an extra property (check inheritance or casing?)', key)
            counts['failAdditional'] += 1
            messages[key] = (item, '-',
                             'Exists',
                             '-')
    for key in messages:
        if key not in jsonData:
            rsvLogger.info(fmt % (key, messages[key][3]))

    rsvLogger.info('%s, %s', SchemaFullType, counts)

    # Get all links available

    rsvLogger.debug(propResourceObj.links)
    rsvLogger.removeHandler(errh)
    return True, counts, results, propResourceObj.links, propResourceObj


def validateURITree(URI, uriName, expectedType=None, expectedSchema=None, expectedJson=None, parent=None, allLinks=None):
    traverseLogger = rst.getLogger()

    def executeLink(linkItem, parent=None):
        linkURI, autoExpand, linkType, linkSchema, innerJson = linkItem

        if linkType is not None and autoExpand:
            returnVal = validateURITree(
                    linkURI, uriName + ' -> ' + linkName, linkType, linkSchema, innerJson, parent, allLinks)
        else:
            returnVal = validateURITree(
                    linkURI, uriName + ' -> ' + linkName, parent=parent, allLinks=allLinks)
        traverseLogger.info('%s, %s', linkName, returnVal[1])
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
                traverseLogger.info('%s, %s', linkName, refLinks[linkName])
                counts['reflink'] += 1
            else:
                continue

            success, linkCounts, linkResults, xlinks, xobj = executeLink(refLinks[linkName], thisobj)
            if not success:
                counts['unvalidatedRef'] += 1
            results.update(linkResults)

    return validateSuccess, counts, results, refLinks, thisobj


def main(argv):
    argget = argparse.ArgumentParser(description='Usecase tool to check compliance to POST Boot action')
    argget.add_argument('--ip', type=str, help='ip to test on [host:port]')
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

    args = argget.parse_args()

    try:
        if args.config is not None:
            rst.setConfig(args.config)
            rst.isConfigSet()
        elif args.ip is not None:
            rst.setConfigNamespace(args)
            rst.isConfigSet()
        else:
            rsvLogger.info('No ip or config specified.')
            argget.print_help()
            return 1
    except Exception as ex:
        rsvLogger.exception("Something went wrong")
        return 1

    sysDescription, ConfigURI, chkCert, localOnly = (rst.SysDescription, rst.ConfigURI, rst.ChkCert, rst.LocalOnly)
    User, SchemaLocation = rst.User, rst.SchemaLocation
    logpath = rst.LogPath

    # Logging config
    startTick = datetime.now()
    if not os.path.isdir(logpath):
        os.makedirs(logpath)
    fmt = logging.Formatter('%(levelname)s - %(message)s')
    fh = logging.FileHandler(datetime.strftime(startTick, os.path.join(logpath, "ComplianceLog_%m_%d_%Y_%H%M%S.txt")))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    rsvLogger.addHandler(fh)
    rsvLogger.info('System Info: ' + sysDescription)
    rsvLogger.info("RedfishServiceValidator Config details: %s",
        (ConfigURI, 'user:' + str(User), SchemaLocation, 'CheckCert' if chkCert else 'no CheckCert', 'localOnly or service' if localOnly or rst.ServiceOnly else 'Attempt for Online Schema'))

    rsvLogger.info('Start time: ' + startTick.strftime('%x - %X'))

    # Start main
    status_code = 1
    success, counts, results, xlinks, topobj = validateURITree('/redfish/v1', 'ServiceRoot')
    finalCounts = Counter()
    nowTick = datetime.now()
    rsvLogger.info('Elapsed time: ' + str(nowTick-startTick).rsplit('.', 1)[0])
    rst.currentSession.killSession()

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
                <tr><th>User: ' + str(User) + ' ###  \
                SSL Cert Check: ' + str(chkCert) + ' ###  \n\
                Local Only Schema:' + str(localOnly) + ' ###  Local Schema Location :' + SchemaLocation + '</th></tr>\
                <tr><th>Start time: ' + (startTick).strftime('%x - %X') + '</th></tr>\
                <tr><th>Run time: ' + str(nowTick-startTick).rsplit('.', 1)[0] + '</th></tr>\
                <tr><th></th></tr>'

    htmlStr = ''

    rsvLogger.info(len(results))
    for cnt, item in enumerate(results):
        htmlStr += '<tr><td class="titlerow"><table class="titletable"><tr>'
        htmlStr += '<td class="title" style="width:40%"><div>{}</div>\
                <div class="button warn" onClick="document.getElementById(\'resNum{}\').classList.toggle(\'resultsShow\');">Show results</div>\
                </td>'.format(item, cnt, cnt)
        htmlStr += '<td class="titlesub log" style="width:30%"><div><b>URI:</b> {}</div><div><b>XML:</b> {}</div><div><b>type:</b> {}</div></td>'.format(results[item][0], results[item][5], results[item][6])
        htmlStr += '<td style="width:10%"' + \
            ('class="pass"> GET Success' if results[item]
             [1] else 'class="fail"> GET Failure') + '</td>'
        htmlStr += '<td style="width:10%">'

        innerCounts = results[item][2]
        finalCounts.update(innerCounts)
        for countType in sorted(innerCounts.keys()):
            if 'problem' in countType or 'fail' in countType or 'exception' in countType:
                rsvLogger.error('{} {} errors in {}'.format(innerCounts[countType], countType, results[item][0].split(' ')[0]))
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
                    if 'PASS' in str(j):
                        htmlStr += '<td class="pass center">' + str(j) + '</td>'
                    elif 'FAIL' in str(j):
                        htmlStr += '<td class="fail center">' + str(j) + '</td>'
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

    with open(datetime.strftime(startTick, os.path.join(logpath, "ComplianceHtmlLog_%m_%d_%Y_%H%M%S.html")), 'w') as f:
        f.write(htmlPage)

    fails = 0
    for key in finalCounts:
        if 'problem' in key or 'fail' in key or 'exception' in key:
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
