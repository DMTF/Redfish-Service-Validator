
from collections import Counter, OrderedDict

import re
import traverseService
import common.simpletypes as simpletypes

rsvLogger = traverseService.getLogger()

import logging

def validateActions(name: str, val: dict, propTypeObj: traverseService.schema.PropType, payloadType: str):
    """validateActions

    Validates actions dict

    :param name:  Identity of the property
    :type name: str
    :param val:  Dictionary of the Actions
    :type val: dict
    :param propTypeObj:  TypeObject of the Actions
    :type propTypeObj: traverseService.PropType
    :param payloadType:  Payload type of the owner of Actions
    :type payloadType: str
    """
    actionMessages, actionCounts = {}, Counter()

    parentTypeObj = traverseService.schema.PropType(payloadType, propTypeObj.schemaObj)
    actionsDict = {act.name: (val.get(act.name, 'n/a'), act.actTag) for act in parentTypeObj.getActions()}

    if 'Oem' in val:
        if traverseService.currentService.config.get('oemcheck'):
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
                if prop not in ['target', 'title', '@Redfish.ActionInfo',
                                '@Redfish.OperationApplyTimeSupport'] and '@Redfish.AllowableValues' not in prop:
                    actPass = False
                    rsvLogger.error('{}: Property "{}" is not allowed in actions property. Allowed properties are "{}", "{}", "{}", "{}" and "{}"'
                            .format(name + '.' + k, prop, 'target', 'title', '@Redfish.ActionInfo', '@Redfish.OperationApplyTimeSupport', '*@Redfish.AllowableValues'))
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
            default = parentURI + '#/{}'.format(name.replace('[', '/').strip(']'))
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
        success, data, status, delay = traverseService.callResourceURI(uri)
    else:
        success, data, status, delay = True, val, 200, 0
    rsvLogger.debug('(success, uri, status, delay) = {}, (propType, propCollectionType) = {}, data = {}'
                    .format((success, uri, status, delay), (propType, propCollectionType), data))
    # if the reference is a Resource, save us some trouble as most/all basetypes are Resource
    generics = ['Resource.ItemOrCollection', 'Resource.ResourceCollection', 'Resource.Item', 'Resource.Resource']
    if (propCollectionType in generics or propType in generics) and success:
        return True
    elif success:
        # Attempt to grab an appropriate type to test against and its schema
        # Default lineup: payload type, collection type, property type
        currentType = data.get('@odata.type', propCollectionType)
        if currentType is None:
            currentType = propType
        soup, refs = schemaObj.soup, schemaObj.refs
        baseLink = refs.get(traverseService.getNamespace(propCollectionType if propCollectionType is not None else propType))
        # if schema in current schema, then use it
        #   elif namespace in References, use that
        #   else we have no lead
        if soup.find('Schema', attrs={'Namespace': traverseService.getNamespace(currentType)}) is not None:
            success, baseObj = True, schemaObj
        elif baseLink is not None:
            baseObj = schemaObj.getSchemaFromReference(traverseService.getNamespaceUnversioned(currentType))
            success = baseObj is not None
        else:
            success = False

        if not success:
            rsvLogger.error("Schema of target {} not referenced in current resource, concluding type {} is not of expected type {}".format(uri, currentType, propType))
        rsvLogger.debug('success = {}, currentType = {}, baseLink = {}'.format(success, currentType, baseLink))

        # Recurse through parent types, gather type hierarchy to check against
        if success and currentType is not None and baseObj.getTypeTagInSchema(currentType) is None and success:
            rsvLogger.error(
                '{}: Linked resource reports version {} not in Schema {}'
                .format(name.split(':')[-1], currentType, baseObj.origin))

        elif success and currentType is not None :
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
        if "OriginOfCondition" in name:
            rsvLogger.log(logging.INFO-1, "{}: GET of resource at URI {} returned HTTP {}, but was a temporary resource."
                            .format(name, uri, status if isinstance(status, int) and status >= 200 else "error"))
            return True

        else:
            rsvLogger.error("{}: GET of resource at URI {} returned HTTP {}. Check URI."
                            .format(name, uri, status if isinstance(status, int) and status >= 200 else "error"))
    return paramPass


def validateComplex(name, val, propComplexObj, payloadType, attrRegistryId):
    """
    Validate a complex property
    """
    rsvLogger.log(logging.INFO-1,'\t***going into Complex')
    if not isinstance(val, dict):
        rsvLogger.error(name + ': Complex item not a dictionary')
        return False, None, None

    # Check inside of complexType, treat it like an Entity
    complexMessages = {}
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

    successPayload, odataMessages = traverseService.ResourceObj.checkPayloadConformance(propComplexObj.jsondata, propComplexObj.uri)
    complexMessages.update(odataMessages)

    if not successPayload:
        complexCounts['failComplexPayloadError'] += 1
        rsvLogger.error('{}: complex payload error, @odata property non-conformant'.format(str(name)))
    rsvLogger.log(logging.INFO-1,'\t***out of Complex')
    rsvLogger.log(logging.INFO-1,'complex {}'.format(str(complexCounts)))

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
    messages = {}
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
    elif propRealType == 'Edm.Duration':
        disp_type = 'duration'
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

    resultList = {}
    counts = Counter()

    rsvLogger.log(logging.INFO-1, PropertyName)
    item = prop.payloadName

    propValue = prop.val
    rsvLogger.log(logging.INFO-1,"\tvalue: {} {}".format(propValue, type(propValue)))

    propExists = not (propValue == 'n/a')

    if ParentItem is not None:
        item = ParentItem + '.' + item

    PropertyDict = prop.propDict

    if PropertyDict is None:
        if not propExists:
            rsvLogger.log(logging.INFO-1,'{}: Item is skipped, no schema'.format(item))
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
    rsvLogger.log(logging.INFO-1,"\thas Type: {} {}".format(propType, propRealType))

    # why not actually check oem
    # rs-assertion: 7.4.7.2
    if 'Oem' in PropertyName and not traverseService.config.get('oemcheck', False):
        rsvLogger.log(logging.INFO-1,'\tOem is skipped')
        counts['skipOem'] += 1
        return {item: ('-', '-', 'Yes' if propExists else 'No', 'OEM')}, counts

    propMandatory = False
    propMandatoryPass = True

    if 'Redfish.Required' in PropertyDict:
        propMandatory = True
        propMandatoryPass = True if propExists else False
        rsvLogger.log(logging.INFO-1,"\tMandatory Test: {}".format(
                       'OK' if propMandatoryPass else 'FAIL'))
    else:
        rsvLogger.log(logging.INFO-1,"\tis Optional")
        if not propExists:
            rsvLogger.log(logging.INFO-1,"\tprop Does not exist, skip...")
            counts['skipOptional'] += 1
            return {item: (
                '-', displayType(propType, propRealType),
                'Yes' if propExists else 'No',
                'Optional')}, counts

    nullable_attr = propAttr.get('Nullable')
    propNullable = False if nullable_attr == 'false' else True  # default is true

    # rs-assertion: Check for permission change
    propPermissions = PropertyDict.get('OData.Permissions')
    propPermissionsValue = None
    if propPermissions is not None:
        propPermissionsValue = propPermissions['EnumMember']
        rsvLogger.debug("\tpermission {}".format(propPermissionsValue))

    autoExpand = PropertyDict.get('OData.AutoExpand', None) is not None or\
        PropertyDict.get('OData.AutoExpand'.lower(), None) is not None

    validPatternAttr = PropertyDict.get(
        'Validation.Pattern')
    validMinAttr = PropertyDict.get('Validation.Minimum')
    validMaxAttr = PropertyDict.get('Validation.Maximum')

    paramPass = propNullablePass = deprecatedPass = nullValid = True

    # <Annotation Term="Redfish.Deprecated" String="This property has been Deprecated in favor of Thermal.v1_1_0.Thermal.Fan.Name"/>
    validDeprecated = PropertyDict.get('Redfish.Deprecated')
    if validDeprecated is not None:
        deprecatedPass = False
        counts['warnDeprecated'] += 1
        rsvLogger.warning('{}: The given property is deprecated: {}'.format(item, validDeprecated.get('String', '')))

    validDeprecated = PropertyDict.get('Redfish.Revisions')
    if validDeprecated is not None:
        for tag_item in validDeprecated:
            revision_tag = tag_item.find('PropertyValue', attrs={
                'EnumMember': 'Redfish.RevisionKind/Deprecated',
                'Property': 'Kind'})
            if (revision_tag):
                desc_tag = tag_item.find('PropertyValue', attrs={'Property': 'Description'})
                deprecatedPass = False
                counts['warnDeprecated'] += 1
                if (desc_tag):
                    rsvLogger.warning('{}: The given property is deprecated by revision: {}'.format(item, desc_tag.attrs.get('String', '')))
                else:
                    rsvLogger.warning('{}: The given property is deprecated by revision'.format(item))

    validMin, validMax = int(validMinAttr['Int']) if validMinAttr is not None else None, \
        int(validMaxAttr['Int']) if validMaxAttr is not None else None
    validPattern = validPatternAttr.get('String', '') if validPatternAttr is not None else None

    # Note: consider http://docs.oasis-open.org/odata/odata-csdl-xml/v4.01/csprd01/odata-csdl-xml-v4.01-csprd01.html#_Toc472333112
    # Note: make sure it checks each one
    propCollectionType = PropertyDict.get('isCollection')
    isCollection = propCollectionType is not None
    if isCollection and propValue is None:
        # illegal for a collection to be null
        if prop.propChild == 'HttpHeaders' and traverseService.getType(prop.propOwner) == 'EventDestination':
            rsvLogger.info('Value HttpHeaders can be Null')
            propNullable = True
            propValueList = []
            resultList[item] = ('Array (size: null)',
                                displayType(propType, propRealType, is_collection=True),
                                'Yes' if propExists else 'No', '...')
        else:
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
        rsvLogger.log(logging.INFO-1,"\tis Collection")
        if propValue == 'n/a':
            propValueList = []
            resultList[item] = ('Array (absent)'.format(len(propValue)),
                                displayType(propType, propRealType, is_collection=True),
                                'Yes' if propExists else 'No', 'PASS' if propMandatoryPass else 'FAIL')
            rsvLogger.error("{}: Mandatory prop does not exist".format(item))
            counts['failMandatoryExist'] += 1
        else:
            propValueList = propValue
            resultList[item] = ('Array (size: {})'.format(len(propValue)),
                                displayType(propType, propRealType, is_collection=True),
                                'Yes' if propExists else 'No', '...')
    else:
        # not a collection
        propValueList = [propValue]
    # note: make sure we don't enter this on null values, some of which are
    # OK!
    for cnt, val in enumerate(propValueList):
        appendStr = (('[' + str(cnt) + ']') if isCollection else '')
        sub_item = item + appendStr
        if isinstance(val, str):
            if val == '' and propPermissionsValue == 'OData.Permission/Read':
                rsvLogger.warning('{}: Empty string found - Services should omit properties if not supported'.format(sub_item))
                nullValid = False
            if val.lower() == 'null':
                rsvLogger.warning('{}: "null" string found - Did you mean to use an actual null value?'.format(sub_item))
                nullValid = False
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
                paramPass = simpletypes.validateDatetime(sub_item, val)

            elif propRealType == 'Edm.Duration':
                paramPass = simpletypes.validateDayTimeDuration(sub_item, val)

            elif propRealType == 'Edm.Int16' or propRealType == 'Edm.Int32' or\
                    propRealType == 'Edm.Int64' or propRealType == 'Edm.Int':
                paramPass = simpletypes.validateInt(sub_item, val, validMin, validMax)

            elif propRealType == 'Edm.Decimal' or propRealType == 'Edm.Double':
                paramPass = simpletypes.validateNumber(sub_item, val, validMin, validMax)

            elif propRealType == 'Edm.Guid':
                paramPass = simpletypes.validateGuid(sub_item, val)

            elif propRealType == 'Edm.String':
                paramPass = simpletypes.validateString(sub_item, val, validPattern)

            elif propRealType == 'Edm.Primitive' or propRealType == 'Edm.PrimitiveType':
                paramPass = simpletypes.validatePrimitive(sub_item, val)

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
                    paramPass = simpletypes.validateEnum(sub_item, val, PropertyDict['typeprops'])

                elif propRealType == 'deprecatedEnum':
                    paramPass = simpletypes.validateDeprecatedEnum(sub_item, val, PropertyDict['typeprops'])

                elif propRealType == 'entity':
                    paramPass = validateEntity(sub_item, val, propType, propCollectionType, schemaObj, autoExpand, parentURI)
                else:
                    rsvLogger.error("%s: This type is invalid %s" % (sub_item, propRealType))
                    paramPass = False

        if not paramPass or not propMandatoryPass or not propNullablePass:
            result_str = 'FAIL'
        elif not deprecatedPass:
            result_str = 'Deprecated'
        elif not nullValid:
            counts['invalidPropertyValue'] += 1
            result_str = 'WARN'
        else:
            result_str = 'PASS'
        resultList[sub_item] = (
                displayValue(val, sub_item if autoExpand else None), displayType(propType, propRealType),
                'Yes' if propExists else 'No', result_str)
        if paramPass and propNullablePass and propMandatoryPass:
            counts['pass'] += 1
            rsvLogger.log(logging.INFO-1,"\tSuccess")
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
            rsvLogger.log(logging.INFO-1,"\tFAIL")

    return resultList, counts
