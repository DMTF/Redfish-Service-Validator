# Copyright Notice:
# Copyright 2016-2018 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import argparse
import os
import sys
import re
import logging
import json

from io import StringIO
from datetime import datetime
from collections import Counter, OrderedDict

import traverseService as rst

from simpletypes import *
from traverseService import AuthenticationError
from tohtml import renderHtml, writeHtml

from metadata import setup_schema_pack

tool_version = '1.2.0'

rsvLogger = rst.getLogger()

VERBO_NUM = 15
logging.addLevelName(VERBO_NUM, "VERBO")
def verboseout(self, message, *args, **kws):
    if self.isEnabledFor(VERBO_NUM):
        self._log(VERBO_NUM, message, args, **kws)
logging.Logger.verboseout = verboseout


def validateActions(name: str, val: dict, propTypeObj: rst.rfSchema.PropType, payloadType: str):
    """validateActions

    Validates actions dict

    :param name:  Identity of the property
    :type name: str
    :param val:  Dictionary of the Actions
    :type val: dict
    :param propTypeObj:  TypeObject of the Actions
    :type propTypeObj: rst.PropType
    :param payloadType:  Payload type of the owner of Actions
    :type payloadType: str
    """
    actionMessages, actionCounts = OrderedDict(), Counter()

    parentTypeObj = rst.rfSchema.PropType(payloadType, propTypeObj.schemaObj)
    actionsDict = {act.name: (val.get(act.name, 'n/a'), act.actTag) for act in parentTypeObj.getActions()}

    if 'Oem' in val:
        if rst.currentService.config.get('oemcheck'):
            for newAct in val['Oem']:
                actionsDict['Oem.' + newAct] = (val['Oem'][newAct], None)
        else:
            actionCounts['oemActionSkip'] += 1


    # For each action found, check action dictionary for existence and conformance
    # No action is required unless specified, target is not required unless specified
    # (should check for viable parameters)
    for k in actionsDict:
        actionDecoded, actDict = actionsDict[k]
        actPass = True
        actOptional = False
        if actionDecoded != 'n/a':
            # validate target
            target = actionDecoded.get('target')
            if target is None:
                actPass = False
                rsvLogger.error('{}: target for action is missing'.format(name + '.' + k))
            elif not isinstance(target, str):
                actPass = False
                rsvLogger.error('{}: target for action is malformed; expected string, got {}'
                        .format(name + '.' + k, str(type(target)).strip('<>')))
                # check for unexpected properties
            for prop in actionDecoded:
                if prop not in ['target', 'title', '@Redfish.ActionInfo'] and '@Redfish.AllowableValues' not in prop:
                    actPass = False
                    rsvLogger.error('{}: Property "{}" is not allowed in actions property. Allowed properties are "{}", "{}", "{}" and "{}"'
                            .format(name + '.' + k, prop, 'target', 'title', '@Redfish.ActionInfo', '*@Redfish.AllowableValues'))
        else:
            # <Annotation Term="Redfish.Required"/>
            if actDict is not None and actDict.find('annotation', {'term': 'Redfish.Required'}):
                actPass = False
                rsvLogger.error('{}: action not found, is mandatory'.format(name + '.' + k))
            else:
                actOptional = True
                rsvLogger.debug('{}: action not found, is not mandatory'.format(name + '.' + k))
        actionMessages[name + '.' + k] = (
                'Action', '-',
                'Yes' if actionDecoded != 'n/a' else 'No',
                'Optional' if actOptional else 'PASS' if actPass else 'FAIL')
        if actOptional:
            actionCounts['optionalAction'] += 1
        elif actPass:
            actionCounts['passAction'] += 1
        else:
            actionCounts['failAction'] += 1
    return actionMessages, actionCounts


def validateEntity(name: str, val: dict, propType: str, propCollectionType: str, schemaObj, autoExpand, parentURI=""):
    """
    Validates an entity based on its uri given
    """
    rsvLogger.debug('validateEntity: name = {}'.format(name))

    # check for required @odata.id
    if '@odata.id' not in val:
        if autoExpand:
            default = parentURI + '#/{}'.format(name.replace('[','/').strip(']'))
        else:
            default = parentURI + '/{}'.format(name)
        rsvLogger.error("{}: EntityType resource does not contain required @odata.id property, attempting default {}".format(name, default))
        if parentURI == "":
            return False
        uri = default
    else:
        uri = val['@odata.id']
    # check if the entity is truly what it's supposed to be
    paramPass = False
    # if not autoexpand, we must grab the resource
    if not autoExpand:
        success, data, status, delay = rst.callResourceURI(uri)
    else:
        success, data, status, delay = True, val, 200, 0
    rsvLogger.debug('(success, uri, status, delay) = {}, (propType, propCollectionType) = {}, data = {}'
                    .format((success, uri, status, delay), (propType, propCollectionType), data))
    # if the reference is a Resource, save us some trouble as most/all basetypes are Resource
    generics = ['Resource.ItemOrCollection', 'Resource.ResourceCollection', 'Resource.Item']
    if (propCollectionType in generics or propType in generics) and success:
        return True
    elif success:
        # Attempt to grab an appropriate type to test against and its schema
        # Default lineup: payload type, collection type, property type
        currentType = data.get('@odata.type', propCollectionType)
        if currentType is None:
            currentType = propType
        soup, refs = schemaObj.soup, schemaObj.refs
        baseLink = refs.get(rst.getNamespace(propCollectionType if propCollectionType is not None else propType))
        if soup.find('Schema', attrs={'Namespace': rst.getNamespace(currentType)}) is not None:
            success, baseObj = True, schemaObj
        elif baseLink is not None:
            baseObj = schemaObj.getSchemaFromReference(rst.getNamespaceUnversioned(currentType))
            success = baseObj is not None
        else:
            success = False
        rsvLogger.debug('success = {}, currentType = {}, baseLink = {}'.format(success, currentType, baseLink))

        # Recurse through parent types, gather type hierarchy to check against
        if currentType is not None and baseObj.getTypeTagInSchema(currentType) is None:
            rsvLogger.error(
                '{}: Linked resource reports version {} not in Schema {}'
                .format(name.split(':')[-1], currentType, baseObj.origin))

        elif currentType is not None and success:
            currentType = currentType.replace('#', '')
            allTypes = []
            while currentType not in allTypes and success:
                allTypes.append(currentType)
                success, baseObj, currentType = baseObj.getParentType(currentType, 'EntityType')
                rsvLogger.debug('success = {}, currentType = {}'.format(success, currentType))

            rsvLogger.debug('propType = {}, propCollectionType = {}, allTypes = {}'
                            .format(propType, propCollectionType, allTypes))
            paramPass = propType in allTypes or propCollectionType in allTypes
            if not paramPass:
                full_namespace = propCollectionType if propCollectionType is not None else propType
                rsvLogger.error(
                    '{}: Linked resource reports schema version (or namespace): {} not found in typechain'
                    .format(name.split(':')[-1], full_namespace))
        else:
            rsvLogger.error("{}: Could not get schema file for Entity check".format(name))
    else:
        rsvLogger.error("{}: Could not get resource for Entity check".format(name))
    return paramPass


def validateComplex(name, val, propComplexObj, payloadType, attrRegistryId):
    """
    Validate a complex property
    """
    rsvLogger.verboseout('\t***going into Complex')
    if not isinstance(val, dict):
        rsvLogger.error(name + ': Complex item not a dictionary')
        return False, None, None

    # Check inside of complexType, treat it like an Entity
    complexMessages = OrderedDict()
    complexCounts = Counter()

    if 'OemObject' in propComplexObj.typeobj.fulltype:
        rsvLogger.error('{}: OemObjects are required to be typecast with @odata.type'.format(str(name)))
        return False, complexCounts, complexMessages

    for prop in propComplexObj.getResourceProperties():
        if not prop.valid and not prop.exists:
            continue
        if prop.propChild == 'Oem' and name == 'Actions':
            continue
        propMessages, propCounts = checkPropertyConformance(propComplexObj.schemaObj, prop.name, prop, val, ParentItem=name)
        if prop.payloadName != prop.propChild:
            propCounts['invalidComplexName'] += 1
            for propMsg in propMessages:
                modified_entry = list(propMessages[propMsg])
                modified_entry[-1] = 'Invalid'
                propMessages[propMsg] = tuple(modified_entry)
        if not prop.valid:
            rsvLogger.error('Verifying complex property that does not belong to this version: {}'.format(prop.name))
            for propMsg in propMessages:
                propCounts['invalidComplexEntry'] += 1
                modified_entry = list(propMessages[propMsg])
                modified_entry[-1] = 'Invalid'
                propMessages[propMsg] = tuple(modified_entry)

        complexMessages.update(propMessages)
        complexCounts.update(propCounts)

    successPayload, odataMessages = checkPayloadConformance('', val, ParentItem=name)
    complexMessages.update(odataMessages)
    if not successPayload:
        complexCounts['failComplexPayloadError'] += 1
        rsvLogger.error('{}: complex payload error, @odata property non-conformant'.format(str(name)))
    rsvLogger.verboseout('\t***out of Complex')
    rsvLogger.verboseout('complex {}'.format(str(complexCounts)))

    propTypeObj = propComplexObj.typeobj

    if name == 'Actions':
        aMsgs, aCounts = validateActions(name, val, propTypeObj, payloadType)
        complexMessages.update(aMsgs)
        complexCounts.update(aCounts)

    # validate the Redfish.DynamicPropertyPatterns if present
    # current issue, missing refs where they are appropriate, may cause issues
    if propTypeObj.propPattern:
        patternMessages, patternCounts = validateDynamicPropertyPatterns(name, val, propTypeObj,
                                                                         payloadType, attrRegistryId, ParentItem=name)
        complexMessages.update(patternMessages)
        complexCounts.update(patternCounts)

    return True, complexCounts, complexMessages


attributeRegistries = dict()


def validateAttributeRegistry(name, key, value, attr_reg):
    """
    Checks the given value against the type specified in the associated attribute registry
    :param name: the name of the dictionary of properties being validated
    :param key: the key of the individual property being validated
    :param value: the value of the individual property being validated
    :param attr_reg: the attribute registry entry for this property
    :return: a tuple containing (1) True if the type check passes, False otherwise and (2) value of 'Type' property
    """
    fn = 'validateAttributeRegistry'
    if key in attr_reg:
        rsvLogger.debug('{}: {}: found attribute registry entry for key {}'.format(fn, name, key))
        attr = attr_reg.get(key)
    else:
        rsvLogger.debug('{}: {}: did not find attribute registry entry for key {}'.format(fn, name, key))
        return True, None
    type_prop = attr.get('Type')
    if type_prop is None:
        rsvLogger.debug('{}: {}: no Type property found for key {}'.format(fn, name, key))
        return True, None
    reg_pass = True
    if value is None:
        # null value is OK
        reg_pass = True
    elif type_prop == 'Enumeration':
        # validate enumeration
        value_prop = attr.get('Value')
        if value_prop is not None and isinstance(value_prop, list):
            val_list = [a.get("ValueName") for a in value_prop]
            reg_pass = value in val_list
            if not reg_pass:
                rsvLogger.error(
                    '{} has a value of {}. This is not an expected value from the Enumeration: {}'
                    .format(name + '.' + key, value, val_list))
        else:
            rsvLogger.debug('{}: Expected Value property key {} to be a list, found type {}'
                            .format(fn, name + '.' + key, str(type(value)).strip('<>')))
    elif type_prop == 'String':
        # validate type is string
        reg_pass = isinstance(value, str)
        if not reg_pass:
            rsvLogger.error(
                '{} has a value of {}. The expected type is String but the type found is {}'
                .format(name + '.' + key, value, str(type(value)).strip('<>')))
        else:
            # validate MaxLength
            max_len = attr.get('MaxLength')
            if max_len is not None:
                if isinstance(max_len, int):
                    if len(value) > max_len:
                        reg_pass = False
                        rsvLogger.error(
                            '{} has a length of {}, which is greater than its MaxLength of {}'
                            .format(name + '.' + key, len(value), max_len))
                else:
                    reg_pass = False
                    rsvLogger.error('{} should have a MaxLength property that is an integer, but the type found is {}'
                                    .format(name + '.' + key, str(type(max_len)).strip('<>')))
            # validate MinLength
            min_len = attr.get('MinLength')
            if min_len is not None:
                if isinstance(min_len, int):
                    if len(value) < min_len:
                        reg_pass = False
                        rsvLogger.error('{} has a length of {}, which is less than its MinLength of {}'
                                        .format(name + '.' + key, len(value), min_len))
                else:
                    reg_pass = False
                    rsvLogger.error('{} should have a MinLength property that is an integer, but the type found is {}'
                                    .format(name + '.' + key, str(type(min_len)).strip('<>')))
            # validate ValueExpression
            val_expr = attr.get('ValueExpression')
            if val_expr is not None:
                if isinstance(val_expr, str):
                    regex = re.compile(val_expr)
                    if regex.match(value) is None:
                        reg_pass = False
                        rsvLogger.error(
                            '{} has a value of {} which does not match the ValueExpression regex "{}"'
                            .format(name + '.' + key, value, val_expr))
                else:
                    reg_pass = False
                    rsvLogger.error(
                        '{} should have a ValueExpression property that is a string, but the type found is {}'
                        .format(name + '.' + key, str(type(val_expr)).strip('<>')))
    elif type_prop == 'Integer':
        # validate type is int
        reg_pass = isinstance(value, int)
        if not reg_pass:
            rsvLogger.error(
                '{} has a value of {}. The expected type is Integer but the type found is {}'
                .format(name + '.' + key, value, str(type(value)).strip('<>')))
        else:
            # validate LowerBound
            lower_bound = attr.get('LowerBound')
            if isinstance(lower_bound, int):
                if value < lower_bound:
                    reg_pass = False
                    rsvLogger.error('{} has a value of {}, which is less than its LowerBound of {}'
                                    .format(name + '.' + key, value, lower_bound))
            else:
                reg_pass = False
                rsvLogger.error('{} should have a LowerBound property that is an integer, but the type found is {}'
                                .format(name + '.' + key, str(type(lower_bound)).strip('<>')))
            # validate UpperBound
            upper_bound = attr.get('UpperBound')
            if isinstance(upper_bound, int):
                if value > upper_bound:
                    reg_pass = False
                    rsvLogger.error('{} has a value of {}, which is greater than its UpperBound of {}'
                                    .format(name + '.' + key, value, upper_bound))
            else:
                reg_pass = False
                rsvLogger.error('{} should have an UpperBound property that is an integer, but the type found is {}'
                                .format(name + '.' + key, str(type(upper_bound)).strip('<>')))
    elif type_prop == 'Boolean':
        reg_pass = isinstance(value, bool)
        if not reg_pass:
            rsvLogger.error(
                '{} has a value of {}. The expected type is Boolean but the type found is {}'
                .format(name + '.' + key, value, str(type(value)).strip('<>')))
    elif type_prop == 'Password':
        reg_pass = value is None
        if not reg_pass:
            rsvLogger.error(
                '{} is a Password. The value returned from GET must be null, but was of type {}'
                .format(name + '.' + key, str(type(value)).strip('<>')))
    else:
        rsvLogger.warning('{} has an unexpected Type property of {}'
                          .format(name + '.' + key, type_prop))
    return reg_pass, type_prop


def validateDynamicPropertyPatterns(name, val, propTypeObj, payloadType, attrRegistryId, ParentItem=None):
    """
    Checks the value type and key pattern of the properties specified via Redfish.DynamicPropertyPatterns annotation
    :param name: the name of the dictionary of properties being validated
    :param val: the dictionary of properties being validated
    :param propTypeObj: the PropType instance
    :param payloadType: the type of the payload being validated
    :param attrRegistryId: teh AttributeRegistry ID (if applicable) for this dictionary of properties
    :return: the messages and counts of the validation results
    """
    fn = 'validateDynamicPropertyPatterns'
    messages = OrderedDict()
    counts = Counter()
    rsvLogger.debug('{}: name = {}, type(val) = {}, pattern = {}, payloadType = {}'
                    .format(fn, name, type(val), propTypeObj.propPattern, payloadType))
    prop_pattern = prop_type = None
    if propTypeObj.propPattern is not None and len(propTypeObj.propPattern) > 0:
        prop_pattern = propTypeObj.propPattern.get('Pattern')
        prop_type = propTypeObj.propPattern.get('Type')
    if prop_pattern is None or prop_type is None:
        rsvLogger.error('{} has Redfish.DynamicPropertyPatterns annotation, but Pattern or Type properties missing'
                        .format(name))
        return messages, counts
    if not isinstance(prop_pattern, str):
        rsvLogger.error('{} has Redfish.DynamicPropertyPatterns annotation, but Pattern property not a string'
                        .format(name))
        return messages, counts
    if not isinstance(prop_type, str):
        rsvLogger.error('{} has Redfish.DynamicPropertyPatterns annotation, but Type property not a string'
                        .format(name))
        return messages, counts
    if not isinstance(val, dict):
        rsvLogger.error('{} has Redfish.DynamicPropertyPatterns annotation, but payload value not a dictionary'
                        .format(name))
        return messages, counts
    # get the attribute registry dictionary if applicable
    attr_reg = None
    if attrRegistryId is not None:
        if attrRegistryId in attributeRegistries:
            rsvLogger.debug('{}: {}: Using attribute registry for {}'.format(fn, name, attrRegistryId))
            attr_reg = attributeRegistries.get(attrRegistryId)
        elif 'default' in attributeRegistries:
            rsvLogger.debug('{}: {}: Using default attribute registry for {}'.format(fn, name, attrRegistryId))
            attr_reg = attributeRegistries.get('default')
        else:
            rsvLogger.warning('{}: Attribute Registry with ID {} not found'.format(name, attrRegistryId))
    else:
        rsvLogger.debug('{}: {}: No Attribute Registry ID found'.format(fn, name, attrRegistryId))
    # validate each property
    regex = re.compile(prop_pattern)
    for key, value in val.items():
        # validate the value key against the Pattern
        pattern_pass = True
        if isinstance(key, str):
            if regex.match(key) is None:
                if '@odata.' in key or '@Redfish.' in key or '@Message.' in key:
                    # @odata, @Redfish and @Message properties are acceptable as well
                    pattern_pass = True
                else:
                    pattern_pass = False
                    rsvLogger.error('{} does not match pattern "{}"'.format(name + '.' + key, prop_pattern))
        else:
            pattern_pass = False
            rsvLogger.error('{} is not a string, so cannot be validated against pattern "{}"'
                            .format(name + '.' + key, prop_pattern))
        if pattern_pass:
            counts['pass'] += 1
        else:
            counts['failDynamicPropertyPatterns'] += 1
        # validate the value type against the Type
        reg_pass = True
        attr_reg_type = None
        if attr_reg is not None:
            reg_pass, attr_reg_type = validateAttributeRegistry(name, key, value, attr_reg)
            if reg_pass:
                counts['pass'] += 1
            else:
                counts['failAttributeRegistry'] += 1

    return messages, counts


def displayType(propType, propRealType, is_collection=False):
    """
    Convert inputs propType and propRealType to a simple, human readable type
    :param propType: the 'Type' attribute from the PropItem.propDict
    :param propRealType: the 'realtype' entry from the PropItem.propDict
    :param is_collection: For collections: True if these types are for the collection; False if for a member
    :return: the simplified type to display
    """
    if propType is None:
        propType = ''
    if propRealType is None:
        propRealType = ''

    # Edm.* and other explicit types
    if propRealType == 'Edm.Boolean' or propRealType == 'Boolean':
        disp_type = 'boolean'
    elif propRealType == 'Edm.String' or propRealType == 'String':
        disp_type = 'string'
    elif (propRealType.startswith('Edm.Int') or propRealType == 'Edm.Decimal' or
        propRealType == 'Edm.Double' or propRealType == 'Integer'):
        disp_type = 'number'
    elif propRealType == 'Edm.Guid':
        disp_type = 'GUID'
    elif propRealType == 'Edm.Primitive' or propRealType == 'Edm.PrimitiveType':
        disp_type = 'primitive'
    elif propRealType == 'Edm.DateTimeOffset':
        disp_type = 'date'
    elif propRealType == 'Password':
        disp_type = 'password'
    elif propRealType == 'enum' or propRealType == 'deprecatedEnum' or propRealType == 'Enumeration':
        disp_type = 'string (enum)'
    elif propRealType.startswith('Edm.'):
        disp_type = propRealType.split('.', 1)[1]
    # Entity types
    elif propRealType == 'entity':
        if propType.startswith('Collection('):
            member_type = propType.replace('Collection(', '').replace(')', '')
            if is_collection:
                disp_type = 'array of: {}'.format(member_type.rsplit('.', 1)[-1])
            else:
                disp_type = member_type.rsplit('.', 1)[-1]
        else:
            disp_type = 'link to: {}'.format(propType.rsplit('.', 1)[-1])
    # Complex types
    elif propRealType == 'complex':
        if propType.startswith('Collection('):
            member_type = propType.replace('Collection(', '').replace(')', '')
            if is_collection:
                disp_type = 'array of: {}'.format(member_type.rsplit('.', 1)[-1])
            else:
                disp_type = member_type.rsplit('.', 1)[-1]
        else:
            disp_type = propType
    # Fallback cases
    elif len(propRealType) > 0:
        disp_type = propRealType
    elif len(propType) > 0:
        disp_type = propType
    else:
        disp_type = 'n/a'

    rsvLogger.debug('displayType: ({}, {}) -> {}'.format(propType, propRealType, disp_type))
    return disp_type


def displayValue(val, autoExpandName=None):
    """
    Convert input val to a simple, human readable value
    :param val: the value to be displayed
    :param autoExpand: optional, name of JSON Object if it is a referenceable member
    :return: the simplified value to display
    """
    if val is None:
        disp_val = '[null]'
    elif isinstance(val, dict) and len(val) == 1 and '@odata.id' in val:
        disp_val = 'Link: {}'.format(val.get('@odata.id'))
    elif isinstance(val, (int, float, str, bool)):
        disp_val = val
    elif autoExpandName is not None:
        disp_val = 'Referenceable object - see report {} listed below'.format(autoExpandName)
    else:
        disp_val = '[JSON Object]'

    rsvLogger.debug('displayValue: {} -> {}'.format(val, disp_val))
    return disp_val


def loadAttributeRegDict(odata_type, json_data):
    """
    Load the attribute registry from the json payload into a dictionary and store it in global attributeRegistries dict
    :param odata_type: the @odata.type for this json payload
    :param json_data: the json payload from which to extract the attribute registry
    :return:
    """
    fn = 'loadAttributeRegDict'
    if not isinstance(json_data, dict):
        rsvLogger.debug('{}: Expected json_data param to be a dict, found {}'.format(fn, type(json_data)))
        return

    # get Id property if present; if missing use a key of 'default' to store the dictionary
    reg_id = json_data.get('Id')
    if reg_id is None:
        reg_id = 'default'

    rsvLogger.debug('{}: @odata.type = {}, Id = {}'.format(fn, odata_type, reg_id))

    # do some validations on the format of the attribute registry
    if reg_id in attributeRegistries:
        rsvLogger.error('{}: An AttributeRegistry with Id "{}" has already been loaded'.format(fn, reg_id))
        return
    reg_entries = json_data.get('RegistryEntries')
    if not isinstance(reg_entries, dict):
        rsvLogger.warning('{}: Expected RegistryEntries property to be a dict, found {}'.format(fn, type(reg_entries)))
        return
    attributes = reg_entries.get('Attributes')
    if not isinstance(attributes, list):
        rsvLogger.warning('{}: Expected Attributes property to be an array, found {}'.format(fn, type(attributes)))
        return
    if len(attributes) > 0:
        if not isinstance(attributes[0], dict):
            rsvLogger.warning('{}: Expected elements of Attributes array to be of type dict, found {}'
                              .format(fn, type(attributes[0])))
            return
    else:
        rsvLogger.debug('{}: Attributes element was zero length'.format(fn))
        return

    # load the attribute registry into a dictionary
    attr_dict = dict()
    for attr in attributes:
        attr_name = attr.get('AttributeName')
        if attr_name is None:
            rsvLogger.debug('{}: Expected AttributeName property was not found in array element'.format(fn))
            continue
        if attr.get(attr_name) is not None:
            rsvLogger.warning('{}: AttributeName {} was already seen; previous version will be overwritten'
                            .format(fn, attr_name))
        attr_dict[attr_name] = attr

    # store the attribute registry in global dict `attributeRegistries`
    if len(attr_dict) > 0:
        rsvLogger.debug('{}: Adding "{}" AttributeRegistry dict with {} entries'.format(fn, reg_id, len(attr_dict)))
        attributeRegistries[reg_id] = attr_dict
    else:
        rsvLogger.debug('{}: "{}" AttributeRegistry dict has zero entries; not adding'.format(fn, reg_id))


def checkPropertyConformance(schemaObj, PropertyName, prop, decoded, ParentItem=None, parentURI=""):
    """checkPropertyConformance

    Given a dictionary of properties, check the validitiy of each item, and return a
    list of counted properties

    :param schemaObj:
    :param PropertyName:
    :param PropertyItem:
    :param decoded:
    :param ParentItem:
    :param parentURI:
    """

    resultList = OrderedDict()
    counts = Counter()
    soup, refs = schemaObj.soup, schemaObj.refs

    rsvLogger.verboseout(PropertyName)
    item = prop.payloadName

    propValue = prop.val
    rsvLogger.verboseout("\tvalue: {} {}".format(propValue, type(propValue)))

    propExists = not (propValue == 'n/a')

    if ParentItem is not None:
        item = ParentItem + '.' + item

    PropertyDict = prop.propDict

    if PropertyDict is None:
        if not propExists:
            rsvLogger.verboseout('{}: Item is skipped, no schema'.format(item))
            counts['skipNoSchema'] += 1
            return {item: ('-', '-',
                                'Yes' if propExists else 'No', 'NoSchema')}, counts
        else:
            rsvLogger.error('{}: Item is present, but no schema found'.format(item))
            counts['failNoSchema'] += 1
            return {item: ('-', '-',
                                'Yes' if propExists else 'No', 'FAIL')}, counts

    propAttr = PropertyDict['attrs']

    propType = propAttr.get('Type')
    propRealType = PropertyDict.get('realtype')
    rsvLogger.verboseout("\thas Type: {} {}".format(propType, propRealType))

    # why not actually check oem
    # rs-assertion: 7.4.7.2
    if 'Oem' in PropertyName and not rst.config.get('oemcheck', False):
        rsvLogger.verboseout('\tOem is skipped')
        counts['skipOem'] += 1
        return {item: ('-', '-', 'Yes' if propExists else 'No', 'OEM')}, counts

    propMandatory = False
    propMandatoryPass = True

    if 'Redfish.Required' in PropertyDict:
        propMandatory = True
        propMandatoryPass = True if propExists else False
        rsvLogger.verboseout("\tMandatory Test: {}".format(
                       'OK' if propMandatoryPass else 'FAIL'))
    else:
        rsvLogger.verboseout("\tis Optional")
        if not propExists:
            rsvLogger.verboseout("\tprop Does not exist, skip...")
            counts['skipOptional'] += 1
            return {item: (
                '-', displayType(propType, propRealType),
                'Yes' if propExists else 'No',
                'Optional')}, counts

    nullable_attr = propAttr.get('Nullable')
    propNullable = False if nullable_attr == 'false' else True  # default is true

    # rs-assertion: Check for permission change
    propPermissions = propAttr.get('Odata.Permissions')
    if propPermissions is not None:
        propPermissionsValue = propPermissions['EnumMember']
        rsvLogger.verboseout("\tpermission {}".format(propPermissionsValue))

    autoExpand = PropertyDict.get('OData.AutoExpand', None) is not None or\
        PropertyDict.get('OData.AutoExpand'.lower(), None) is not None

    validPatternAttr = PropertyDict.get(
        'Validation.Pattern')
    validMinAttr = PropertyDict.get('Validation.Minimum')
    validMaxAttr = PropertyDict.get('Validation.Maximum')

    paramPass = propNullablePass = deprecatedPass = True

    # <Annotation Term="Redfish.Deprecated" String="This property has been Deprecated in favor of Thermal.v1_1_0.Thermal.Fan.Name"/>
    validDeprecated = PropertyDict.get('Redfish.Deprecated')
    if validDeprecated is not None:
        deprecatedPass = False
        counts['warnDeprecated'] += 1
        rsvLogger.warning('{}: The given property is deprecated: {}'.format(item, validDeprecated.get('String', '')))

    validMin, validMax = int(validMinAttr['Int']) if validMinAttr is not None else None, \
        int(validMaxAttr['Int']) if validMaxAttr is not None else None
    validPattern = validPatternAttr.get('String', '') if validPatternAttr is not None else None

    # Note: consider http://docs.oasis-open.org/odata/odata-csdl-xml/v4.01/csprd01/odata-csdl-xml-v4.01-csprd01.html#_Toc472333112
    # Note: make sure it checks each one
    propCollectionType = PropertyDict.get('isCollection')
    isCollection = propCollectionType is not None
    if isCollection and propValue is None:
        # illegal for a collection to be null
        rsvLogger.error('{}: Value of Collection property is null but Collections cannot be null, only their entries'
                        .format(item))
        counts['failNullCollection'] += 1
        return {item: (
            '-', displayType(propType, propRealType, is_collection=True),
            'Yes' if propExists else 'No',
            'FAIL')}, counts
    elif isCollection and propValue is not None:
        # note: handle collections correctly, this needs a nicer printout
        # rs-assumption: do not assume URIs for collections
        # rs-assumption: check @odata.count property
        # rs-assumption: check @odata.link property
        rsvLogger.verboseout("\tis Collection")
        resultList[item] = ('Array (size: {})'.format(len(propValue)),
                            displayType(propType, propRealType, is_collection=True),
                            'Yes' if propExists else 'No', '...')
        propValueList = propValue
    else:
        # not a collection
        propValueList = [propValue]
    # note: make sure we don't enter this on null values, some of which are
    # OK!
    for cnt, val in enumerate(propValueList):
        appendStr = (('[' + str(cnt) + ']') if isCollection else '')
        sub_item = item + appendStr
        if isinstance(val, str):
            if val == '':
                rsvLogger.warning('{}: Empty string found - Services should omit properties if not supported'.format(sub_item))
            if val.lower() == 'null':
                rsvLogger.warning('{}: "null" string found - Did you mean to use an actual null value?'.format(sub_item))
        if propRealType is not None and propExists:
            paramPass = propNullablePass = True
            if val is None:
                if propNullable:
                    rsvLogger.debug('Property {} is nullable and is null, so Nullable checking passes'
                                    .format(sub_item))
                else:
                    propNullablePass = False

            elif propRealType == 'Edm.Boolean':
                paramPass = isinstance(val, bool)
                if not paramPass:
                    rsvLogger.error("{}: Not a boolean".format(sub_item))

            elif propRealType == 'Edm.DateTimeOffset':
                paramPass = validateDatetime(sub_item, val)

            elif propRealType == 'Edm.Int16' or propRealType == 'Edm.Int32' or\
                    propRealType == 'Edm.Int64' or propRealType == 'Edm.Int':
                paramPass = validateInt(sub_item, val, validMin, validMax)

            elif propRealType == 'Edm.Decimal' or propRealType == 'Edm.Double':
                paramPass = validateNumber(sub_item, val, validMin, validMax)

            elif propRealType == 'Edm.Guid':
                paramPass = validateGuid(sub_item, val)

            elif propRealType == 'Edm.String':
                paramPass = validateString(sub_item, val, validPattern)

            elif propRealType == 'Edm.Primitive' or propRealType == 'Edm.PrimitiveType':
                paramPass = validatePrimitive(sub_item, val)

            else:
                if propRealType == 'complex':
                    if PropertyDict['typeprops'] is not None:
                        if isCollection:
                            innerComplex = PropertyDict['typeprops'][cnt]
                            innerPropType = PropertyDict['typeprops'][cnt].typeobj
                        else:
                            innerComplex = PropertyDict['typeprops']
                            innerPropType = PropertyDict['typeprops'].typeobj

                        success, complexCounts, complexMessages = validateComplex(sub_item, val, innerComplex,
                                                                                  decoded.get('@odata.type'),
                                                                                  decoded.get('AttributeRegistry'))
                    else:
                        success = False

                    if not success:
                        counts['failComplex'] += 1
                        resultList[sub_item] = (
                                    '[JSON Object]', displayType(propType, propRealType),
                                    'Yes' if propExists else 'No',
                                    'FAIL')
                        continue
                    resultList[sub_item] = (
                                    '[JSON Object]', displayType(propType, propRealType),
                                    'Yes' if propExists else 'No',
                                    'complex')

                    counts.update(complexCounts)
                    resultList.update(complexMessages)
                    allowAdditional = innerPropType.additional
                    for key in innerComplex.unknownProperties:
                        if sub_item + '.' + key not in complexMessages and not allowAdditional:
                            rsvLogger.error('{} not defined in schema {} (check version, spelling and casing)'
                                            .format(sub_item + '.' + key, innerPropType.snamespace))
                            counts['failComplexAdditional'] += 1
                            resultList[sub_item + '.' + key] = (displayValue(val[key]), '-', '-', 'FAIL')
                        elif sub_item + '.' + key not in complexMessages:
                            rsvLogger.warn('{} not defined in schema {} (check version, spelling and casing)'
                                            .format(sub_item + '.' + key, innerPropType.snamespace))
                            counts['unverifiedComplexAdditional'] += 1
                            resultList[sub_item + '.' + key] = (displayValue(val[key]), '-', '-', 'Additional')
                    continue

                elif propRealType == 'enum':
                    paramPass = validateEnum(sub_item, val, PropertyDict['typeprops'])

                elif propRealType == 'deprecatedEnum':
                    paramPass = validateDeprecatedEnum(sub_item, val, PropertyDict['typeprops'])

                elif propRealType == 'entity':
                    paramPass = validateEntity(sub_item, val, propType, propCollectionType, schemaObj, autoExpand, parentURI)
                else:
                    rsvLogger.error("%s: This type is invalid %s" % (sub_item, propRealType))
                    paramPass = False

        if not paramPass or not propMandatoryPass or not propNullablePass:
            result_str = 'FAIL'
        elif not deprecatedPass:
            result_str = 'Deprecated'
        else:
            result_str = 'PASS'
        resultList[sub_item] = (
                displayValue(val, sub_item if autoExpand else None), displayType(propType, propRealType),
                'Yes' if propExists else 'No', result_str)
        if paramPass and propNullablePass and propMandatoryPass:
            counts['pass'] += 1
            rsvLogger.verboseout("\tSuccess")
        else:
            counts['err.' + str(propType)] += 1
            if not paramPass:
                if propMandatory:
                    counts['failMandatoryProp'] += 1
                else:
                    counts['failProp'] += 1
            elif not propMandatoryPass:
                rsvLogger.error("{}: Mandatory prop does not exist".format(sub_item))
                counts['failMandatoryExist'] += 1
            elif not propNullablePass:
                rsvLogger.error('{}: Property is null but is not Nullable'.format(sub_item))
                counts['failNullable'] += 1
            rsvLogger.verboseout("\tFAIL")

    return resultList, counts


def checkPayloadConformance(uri, decoded, ParentItem=None):
    # Checks for @odata, generates "messages"
    #   largely not a lot of error potential
    # info: what did we get?  did it pass?
    # error: what went wrong?  do this per key
    prefix = ParentItem + '.' if ParentItem is not None else ''
    messages = dict()
    success = True
    for key in [k for k in decoded if '@odata' in k]:
        paramPass = False
        annotation = '@' + key.split('@')[-1]
        display_type = 'string'
        if annotation == '@odata.id' or annotation == '@odata.nextLink':
            paramPass = isinstance(decoded[key], str)
            if paramPass:
                paramPass = re.match('(\/.*)+(#([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*)?', decoded[key]) is not None
        elif annotation == '@odata.count':
            display_type = 'number'
            paramPass = isinstance(decoded[key], int)
        elif annotation == '@odata.context':
            paramPass = isinstance(decoded[key], str)
            if paramPass:
                paramPass = re.match('(\/.*)+#([a-zA-Z0-9_.-]*\.)[a-zA-Z0-9_.-]*', decoded[key]) is not None or\
                    re.match('(\/.*)+#(\/.*)+[/]$entity', decoded[key]) is not None
        elif annotation == '@odata.type':
            paramPass = isinstance(decoded[key], str)
            if paramPass:
                paramPass = re.match('#([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*', decoded[key]) is not None
        else:
            rsvLogger.warn(prefix + key + " @odata item not checked: " + str(decoded[key]))
            paramPass = True
        if not paramPass:
            rsvLogger.error(prefix + key + " @odata item not conformant: " + str(decoded[key]))
            success = False
        messages[prefix + key] = (
                decoded[key], display_type,
                'Yes',
                'PASS' if paramPass else 'FAIL')
    return success, messages


def setupLoggingCaptures():
    class WarnFilter(logging.Filter):
        def filter(self, rec):
            return rec.levelno == logging.WARN

    errorMessages = StringIO()
    warnMessages = StringIO()
    fmt = logging.Formatter('%(levelname)s - %(message)s')
    errh = logging.StreamHandler(errorMessages)
    errh.setLevel(logging.ERROR)
    errh.setFormatter(fmt)

    warnh = logging.StreamHandler(warnMessages)
    warnh.setLevel(logging.WARN)
    warnh.addFilter(WarnFilter())
    warnh.setFormatter(fmt)

    rsvLogger.addHandler(errh)
    rsvLogger.addHandler(warnh)

    yield

    rsvLogger.removeHandler(errh)
    rsvLogger.removeHandler(warnh)
    warnstrings = warnMessages.getvalue()
    warnMessages.close()
    errorstrings = errorMessages.getvalue()
    errorMessages.close()

    yield warnstrings, errorstrings


def validateSingleURI(URI, uriName='', expectedType=None, expectedSchema=None, expectedJson=None, parent=None):
    # rs-assertion: 9.4.1
    # Initial startup here
    lc = setupLoggingCaptures()
    next(lc)
    # Start
    rsvLogger.verboseout("\n*** %s, %s", uriName, URI)
    rsvLogger.info("\n*** %s", URI)
    rsvLogger.debug("\n*** %s, %s, %s", expectedType, expectedSchema is not None, expectedJson is not None)
    counts = Counter()
    results = OrderedDict()
    messages = OrderedDict()
    success = True

    results[uriName] = {'uri':URI, 'success':False, 'counts':counts,\
            'messages':messages, 'errors':'', 'warns': '',\
            'rtime':'', 'context':'', 'fulltype':''}

    # check for @odata mandatory stuff
    # check for version numbering problems
    # check id if its the same as URI
    # check @odata.context instead of local.  Realize that @odata is NOT a "property"

    # Attempt to get a list of properties
    if URI is None:
        if parent is not None:
            parentURI = parent.uri
        else:
            parentURI = '...'
        URI = parentURI + '/Missing URI Link'
    # Generate dictionary of property info
    try:
        propResourceObj = rst.createResourceObject(
            uriName, URI, expectedJson, expectedType, expectedSchema, parent)
        if not propResourceObj:
            counts['problemResource'] += 1
            results[uriName]['warns'], results[uriName]['errors'] = next(lc)
            return False, counts, results, None, None
    except AuthenticationError as e:
        raise  # re-raise exception
    except Exception as e:
        rsvLogger.debug('Exception caught while creating ResourceObj', exc_info=1)
        rsvLogger.error('Unable to gather property info for URI {}: {}'
                        .format(URI, repr(e)))
        counts['exceptionResource'] += 1
        results[uriName]['warns'], results[uriName]['errors'] = next(lc)
        return False, counts, results, None, None
    counts['passGet'] += 1

    successPayload, odataMessages = checkPayloadConformance(URI, propResourceObj.jsondata)
    messages.update(odataMessages)

    if not successPayload:
        counts['failPayloadError'] += 1
        rsvLogger.error(str(URI) + ': payload error, @odata property non-conformant',)


    # if URI was sampled, get the notation text from rst.uri_sample_map
    sample_string = rst.uri_sample_map.get(URI)
    sample_string = sample_string + ', ' if sample_string is not None else ''

    results[uriName]['uri'] = (str(URI))
    results[uriName]['samplemapped'] = (str(sample_string))
    results[uriName]['rtime'] = propResourceObj.rtime
    results[uriName]['context'] = propResourceObj.context
    results[uriName]['origin'] = propResourceObj.schemaObj.origin
    results[uriName]['fulltype'] = propResourceObj.typename
    results[uriName]['success'] = True

    rsvLogger.info("\t Type (%s), GET SUCCESS (time: %s)", propResourceObj.typename, propResourceObj.rtime)

    # If this is an AttributeRegistry, load it for later use
    if isinstance(propResourceObj.jsondata, dict):
        odata_type = propResourceObj.jsondata.get('@odata.type')
        if odata_type is not None:
            namespace = odata_type.split('.')[0]
            type_name = odata_type.split('.')[-1]
            if namespace == '#AttributeRegistry' and type_name == 'AttributeRegistry':
                loadAttributeRegDict(odata_type, propResourceObj.jsondata)

    for prop in propResourceObj.getResourceProperties():
        try:
            if not prop.valid and not prop.exists:
                continue
            propMessages, propCounts = checkPropertyConformance(propResourceObj.schemaObj, prop.name, prop, propResourceObj.jsondata, parentURI=URI)
            if '@Redfish.Copyright' in propMessages and 'MessageRegistry' not in propResourceObj.typeobj.fulltype:
                modified_entry = list(propMessages['@Redfish.Copyright'])
                modified_entry[-1] = 'FAIL'
                propMessages['@Redfish.Copyright'] = tuple(modified_entry)
                rsvLogger.error('@Redfish.Copyright is only allowed for mockups, and should not be allowed in official implementations')
            if prop.payloadName != prop.propChild:
                propCounts['invalidName'] += 1
                for propMsg in propMessages:
                    modified_entry = list(propMessages[propMsg])
                    modified_entry[-1] = 'Invalid'
                    propMessages[propMsg] = tuple(modified_entry)
            if not prop.valid:
                rsvLogger.error('Verifying property that does not belong to this version: {}'.format(prop.name))
                for propMsg in propMessages:
                    propCounts['invalidEntry'] += 1
                    modified_entry = list(propMessages[propMsg])
                    modified_entry[-1] = 'Invalid'
                    propMessages[propMsg] = tuple(modified_entry)

            messages.update(propMessages)
            counts.update(propCounts)
        except AuthenticationError as e:
            raise  # re-raise exception
        except Exception as ex:
            rsvLogger.debug('Exception caught while validating single URI', exc_info=1)
            rsvLogger.error('{}: Could not finish check on this property ({})'.format(prop.name, str(ex)))  # Printout FORMAT
            counts['exceptionPropCheck'] += 1


    uriName, SchemaFullType, jsonData = propResourceObj.name, propResourceObj.typeobj.fulltype, propResourceObj.jsondata
    SchemaNamespace, SchemaType = rst.getNamespace(SchemaFullType), rst.getType(SchemaFullType)

    # List all items checked and unchecked
    # current logic does not check inside complex types
    fmt = '%-30s%30s'
    rsvLogger.verboseout('%s, %s, %s', uriName, SchemaNamespace, SchemaType)

    for key in jsonData:
        item = jsonData[key]
        rsvLogger.verboseout(fmt % (
            key, messages[key][3] if key in messages else 'Exists, no schema check'))

    allowAdditional = propResourceObj.typeobj.additional
    for key in [k for k in jsonData if k not in messages and k not in propResourceObj.unknownProperties] + propResourceObj.unknownProperties:
        # note: extra messages for "unchecked" properties
        if not allowAdditional:
            rsvLogger.error('{} not defined in schema {} (check version, spelling and casing)'
                            .format(key, SchemaNamespace))
            counts['failAdditional'] += 1
            messages[key] = (displayValue(item), '-',
                             '-',
                             'FAIL')
        else:
            rsvLogger.warn('{} not defined in schema {} (check version, spelling and casing)'
                            .format(key, SchemaNamespace))
            counts['unverifiedAdditional'] += 1
            messages[key] = (displayValue(item), '-',
                             '-',
                             'Additional')

    for key in messages:
        if key not in jsonData:
            rsvLogger.verboseout(fmt % (key, messages[key][3]))

    results[uriName]['warns'], results[uriName]['errors'] = next(lc)

    pass_val = len(results[uriName]['errors']) == 0
    for key in counts:
        if any(x in key for x in ['problem', 'fail', 'bad', 'exception']):
            pass_val = False
            break
    rsvLogger.info("\t {}".format('PASS' if pass_val else' FAIL...'))

    rsvLogger.verboseout('%s, %s', SchemaFullType, counts)

    # Get all links available

    rsvLogger.debug(propResourceObj.links)

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

    top = allLinks is None
    if top:
        allLinks = set()
    allLinks.add(URI)

    def executeLink(linkItem, parent=None):
        linkURI, autoExpand, linkType, linkSchema, innerJson = linkItem

        if linkType is not None and autoExpand:
            returnVal = validateURITree(
                    linkURI, uriName + ' -> ' + linkName, linkType, linkSchema, innerJson, parent, allLinks)
        else:
            returnVal = validateURITree(
                    linkURI, uriName + ' -> ' + linkName, parent=parent, allLinks=allLinks)
        traverseLogger.verboseout('%s, %s', linkName, returnVal[1])
        return returnVal

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
                traverseLogger.verboseout('%s, %s', linkName, refLinks[linkName])
                counts['reflink'] += 1
            else:
                continue

            success, linkCounts, linkResults, xlinks, xobj = executeLink(refLinks[linkName], thisobj)
            if not success:
                counts['unvalidatedRef'] += 1
            results.update(linkResults)

    return validateSuccess, counts, results, refLinks, thisobj


validatorconfig = {'payloadmode': 'Default', 'payloadfilepath': None, 'logpath': './logs'}


def main(arglist=None, direct_parser=None):
    """
    Main program
    """
    argget = argparse.ArgumentParser(description='tool to test a service against a collection of Schema, version {}'.format(tool_version))

    # config
    argget.add_argument('-c', '--config', type=str, help='config file')

    # tool
    argget.add_argument('--desc', type=str, default='No desc', help='sysdescription for identifying logs')
    argget.add_argument('--payload', type=str, help='mode to validate payloads [Tree, Single, SingleFile, TreeFile] followed by resource/filepath', nargs=2)
    argget.add_argument('-v', action='store_const', const=True, default=None, help='verbose log output to stdout (parameter-only)')
    argget.add_argument('--logdir', type=str, default='./logs', help='directory for log files')
    argget.add_argument('--debug_logging', action="store_const", const=logging.DEBUG, default=logging.INFO,
            help='Output debug statements to text log, otherwise it only uses INFO (parameter-only)')
    argget.add_argument('--verbose_checks', action="store_const", const=VERBO_NUM, default=logging.INFO,
            help='Show all checks in logging (parameter-only)')
    argget.add_argument('--nooemcheck', action='store_const', const=True, default=None, help='Don\'t check OEM items')

    # service
    argget.add_argument('-i', '--ip', type=str, help='ip to test on [host:port]')
    argget.add_argument('-u', '--user', type=str, help='user for basic auth')
    argget.add_argument('-p', '--passwd', type=str, help='pass for basic auth')
    argget.add_argument('--linklimit', type=str, help='Limit the amount of links in collections, formatted TypeName:## TypeName:## ..., default LogEntry:20 ', nargs='*')
    argget.add_argument('--sample', type=int, help='sample this number of members from large collections for validation; default is to validate all members')
    argget.add_argument('--timeout', type=int, help='requests timeout in seconds')
    argget.add_argument('--nochkcert', action='store_const', const=True, default=None, help='ignore check for certificate')
    argget.add_argument('--nossl', action='store_const', const=True, default=None, help='use http instead of https')
    argget.add_argument('--forceauth', action='store_const', const=True, default=None, help='force authentication on unsecure connections')
    argget.add_argument('--authtype', type=str, help='authorization type (None|Basic|Session|Token)')
    argget.add_argument('--localonly', action='store_const', const=True, default=None, help='only use locally stored schema on your harddrive')
    argget.add_argument('--preferonline', action='store_const', const=True, default=None, help='use online schema')
    argget.add_argument('--service', action='store_const', const=True, default=None, help='only use uris within the service')
    argget.add_argument('--ca_bundle', type=str, help='path to Certificate Authority bundle file or directory')
    argget.add_argument('--token', type=str, help='bearer token for authtype Token')
    argget.add_argument('--http_proxy', type=str, help='URL for the HTTP proxy')
    argget.add_argument('--https_proxy', type=str, help='URL for the HTTPS proxy')
    argget.add_argument('--cache', type=str, help='cache mode [Off, Fallback, Prefer] followed by directory to fallback or override problem service JSON payloads', nargs=2)
    argget.add_argument('--uri_check', action='store_const', const=True, default=None, help='Check for URI if schema supports it')
    argget.add_argument('--version_check', type=str, help='Change default tool configuration based on the version provided (default use target version)')

    # metadata
    argget.add_argument('--schemadir', type=str, help='directory for local schema files')
    argget.add_argument('--schema_pack', type=str, help='Deploy DMTF schema from zip distribution, for use with --localonly (Specify url or type "latest", overwrites current schema)')
    argget.add_argument('--suffix', type=str, help='suffix of local schema files (for version differences)')

    args = argget.parse_args(arglist)

    # set up config
    rst.ch.setLevel(args.verbose_checks if not args.v else logging.DEBUG)
    if direct_parser is not None:
        try:
            cdict = rst.convertConfigParserToDict(direct_parser)
            config, default_list = rst.setConfig(cdict)
        except Exception as ex:
            rsvLogger.debug('Exception caught while parsing configuration', exc_info=1)
            rsvLogger.error('Unable to parse configuration: {}'.format(repr(ex)))
            return 1, None, 'Config Parser Exception'
    elif args.config is None and args.ip is None:
        rsvLogger.info('No ip or config specified.')
        argget.print_help()
        return 1, None, 'Config Incomplete'
    else:
        try:
            config, default_list = rst.setByArgparse(args)
        except Exception as ex:
            rsvLogger.debug('Exception caught while parsing configuration', exc_info=1)
            rsvLogger.error('Unable to parse configuration: {}'.format(repr(ex)))
            return 1, None, 'Config Exception'

    # Setup schema store
    if config['schema_pack'] is not None and config['schema_pack'] != '':
        httpprox = config['httpproxy']
        httpsprox = config['httpsproxy']
        proxies = {}
        proxies['http'] = httpprox if httpprox != "" else None
        proxies['https'] = httpsprox if httpsprox != "" else None
        setup_schema_pack(config['schema_pack'], config['metadatafilepath'], proxies, config['timeout'])

    # Logging config
    logpath = config['logpath']
    schemadir = config['metadatafilepath']
    startTick = datetime.now()
    if not os.path.isdir(logpath):
        os.makedirs(logpath)
    if not os.path.isdir(schemadir) and not config['preferonline']:
        rsvLogger.info('First run suggested to create and own local schema files, please download manually or use --schema_pack latest')
        rsvLogger.info('Alternatively, use the option --prefer_online to skip local schema file checks')
    fmt = logging.Formatter('%(levelname)s - %(message)s')
    fh = logging.FileHandler(datetime.strftime(startTick, os.path.join(logpath, "ConformanceLog_%m_%d_%Y_%H%M%S.txt")))
    fh.setLevel(min(args.debug_logging, args.verbose_checks))
    fh.setFormatter(fmt)
    rsvLogger.addHandler(fh)

    # Then start service
    rsvLogger.info("Redfish Service Validator, version {}".format(tool_version))
    try:
        currentService = rst.startService(config, default_list)
    except Exception as ex:
        rsvLogger.debug('Exception caught while creating Service', exc_info=1)
        rsvLogger.error("Service could not be started: {}".format(ex))
        return 1, None, 'Service Exception'

    metadata = currentService.metadata
    sysDescription, ConfigURI = (config['systeminfo'], config['targetip'])

    # start printing config details, remove redundant/private info from print
    rsvLogger.info('ConfigURI: ' + ConfigURI)
    rsvLogger.info('System Info: ' + sysDescription)
    rsvLogger.info('\n'.join(
        ['{}: {}'.format(x, config[x]) for x in sorted(list(config.keys() - set(['systeminfo', 'targetip', 'password', 'description']))) if config[x] not in ['', None]]))
    rsvLogger.info('Start time: ' + startTick.strftime('%x - %X'))

    # Start main
    status_code = 1
    jsonData = None

    # Determine runner
    pmode, ppath = config.get('payloadmode', 'Default'), config.get('payloadfilepath')
    if pmode not in ['Tree', 'Single', 'SingleFile', 'TreeFile', 'Default']:
        pmode = 'Default'
        rsvLogger.error('PayloadMode or path invalid, using Default behavior')
    if 'File' in pmode:
        if ppath is not None and os.path.isfile(ppath):
            with open(ppath) as f:
                jsonData = json.load(f)
                f.close()
        else:
            rsvLogger.error('File not found: {}'.format(ppath))
            return 1, None, 'File not found: {}'.format(ppath)

    try:
        if 'Single' in pmode:
            success, counts, results, xlinks, topobj = validateSingleURI(ppath, 'Target', expectedJson=jsonData)
        elif 'Tree' in pmode:
            success, counts, results, xlinks, topobj = validateURITree(ppath, 'Target', expectedJson=jsonData)
        else:
            success, counts, results, xlinks, topobj = validateURITree('/redfish/v1', 'ServiceRoot', expectedJson=jsonData)
    except AuthenticationError as e:
        # log authentication error and terminate program
        rsvLogger.error('{}'.format(e))
        return 1, None, 'Failed to authenticate with the service'

    currentService.close()

    rsvLogger.debug('Metadata: Namespaces referenced in service: {}'.format(metadata.get_service_namespaces()))
    rsvLogger.debug('Metadata: Namespaces missing from $metadata: {}'.format(metadata.get_missing_namespaces()))

    finalCounts = Counter()
    nowTick = datetime.now()
    rsvLogger.info('Elapsed time: {}'.format(str(nowTick-startTick).rsplit('.', 1)[0]))

    finalCounts.update(metadata.get_counter())
    for item in results:
        innerCounts = results[item]['counts']

        # detect if there are error messages for this resource, but no failure counts; if so, add one to the innerCounts
        counters_all_pass = True
        for countType in sorted(innerCounts.keys()):
            if innerCounts.get(countType) == 0:
                continue
            if any(x in countType for x in ['problem', 'fail', 'bad', 'exception']):
                counters_all_pass = False
            if 'fail' in countType or 'exception' in countType:
                rsvLogger.error('{} {} errors in {}'.format(innerCounts[countType], countType, results[item]['uri']))
            innerCounts[countType] += 0
        error_messages_present = False
        if results[item]['errors'] is not None and len(results[item]['errors']) > 0:
            error_messages_present = True
        if results[item]['warns'] is not None and len(results[item]['warns']) > 0:
            innerCounts['warningPresent'] = 1
        if counters_all_pass and error_messages_present:
            innerCounts['failErrorPresent'] = 1
            rsvLogger.error('Error message present in {}'.format(results[item]['uri']))

        finalCounts.update(results[item]['counts'])

    fails = 0
    for key in [key for key in finalCounts.keys()]:
        if finalCounts[key] == 0:
            del finalCounts[key]
            continue
        if any(x in key for x in ['problem', 'fail', 'bad', 'exception']):
            fails += finalCounts[key]

    html_str = renderHtml(results, finalCounts, tool_version, startTick, nowTick)

    lastResultsPage = datetime.strftime(startTick, os.path.join(logpath, "ConformanceHtmlLog_%m_%d_%Y_%H%M%S.html"))

    writeHtml(html_str, lastResultsPage)

    success = success and not (fails > 0)
    rsvLogger.info(finalCounts)

    # dump cache info to debug log
    rsvLogger.debug('getSchemaDetails() -> {}'.format(rst.rfSchema.getSchemaDetails.cache_info()))
    rsvLogger.debug('callResourceURI() -> {}'.format(currentService.callResourceURI.cache_info()))

    if not success:
        rsvLogger.error("Validation has failed: {} problems found".format(fails))
    else:
        rsvLogger.info("Validation has succeeded.")
        status_code = 0

    return status_code, lastResultsPage, 'Validation done'

if __name__ == '__main__':
    status_code, lastResultsPage, exit_string = main()
    sys.exit(status_code)
