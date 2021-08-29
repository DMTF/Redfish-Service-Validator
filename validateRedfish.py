
from collections import Counter, OrderedDict
from common.catalog import REDFISH_ABSENT, MissingSchemaError, RedfishType

import re
import traverseService
from common.redfish import getNamespace, getNamespaceUnversioned, getType, checkPayloadConformance
from common.catalog import ExcerptTypes
from tohtml import create_entry

my_logger = traverseService.getLogger()

import logging

def validateExcerpt(prop, val):
    # check Navprop if it's NEUTRAL or CONTAINS
    base, _ = prop.Type.getBaseType()

    if base == 'entity':
        my_excerpt_type, my_excerpt_tags = prop.Type.excerptType, prop.Type.excerptTags

        my_props = prop.Type.createObject().populate(val).properties

        for name, innerprop in my_props.items():
            valid_tagging = any([x in my_excerpt_tags for x in innerprop.Type.excerptTags]) or innerprop.Type.excerptTags == []
            if my_excerpt_type == ExcerptTypes.NEUTRAL:
                if innerprop.Type.excerptType == [ExcerptTypes.EXCLUSIVE] and innerprop.Exists:
                    my_logger.error('{}: Exclusive Excerpt {} should not exist in this Resource/ComplexType'.format(prop.name, innerprop.name))
                    return False
            if my_excerpt_type == ExcerptTypes.CONTAINS:
                if innerprop.Type.excerptType in [ExcerptTypes.ALLOWED, ExcerptTypes.EXCLUSIVE, ExcerptTypes.CONTAINS]:
                    if innerprop.Exists and not valid_tagging:
                        my_logger.error('{}: Excerpt tags of owner {} do not match property {} {}'.format(innerprop.name, prop.name, my_excerpt_tags, innerprop.Type.excerptTags))
                        return False
                elif innerprop.Exists:
                    my_logger.error('{}: Property is not a valid Excerpt'.format(innerprop.name))
                    return False

    # check our prop if it's EXCLUSIVE
    if prop.Type.excerptType == ExcerptTypes.EXCLUSIVE and prop.Exists:
        my_logger.error('{}: Exclusive Excerpt should not exist in a Resource/Complex'.format(prop.name))
        return False

    return True


def validateAction(act_name, actionDecoded, all_actions):
    actionMessages, actionCounts = OrderedDict(), Counter()
    act_name, act_type = getNamespace(act_name.strip('#')), getType(act_name)
    actPass = False
    if act_type not in all_actions:
        actionCounts['errorActionBadName'] += 1
    else:
        my_act = all_actions[act_type]
        actOptional = my_act.find('annotation', {'term': 'Redfish.Required'}) is not None
        if actionDecoded == REDFISH_ABSENT:
            if actOptional:
                actPass = True
            else:
                my_logger.error('{}: Mandatory action missing'.format(act_name))
                actionCounts['failMandatoryAction'] += 1
        if actionDecoded != REDFISH_ABSENT:
            # validate target
            target = actionDecoded.get('target')
            if target is None:
                my_logger.error('{}: target for action is missing'.format(act_name))
            elif not isinstance(target, str):
                my_logger.error('{}: target for action is malformed'.format(act_name))
                # check for unexpected properties
            for ap_name in actionDecoded:
                expected = ['target', 'title', '@Redfish.ActionInfo', '@Redfish.OperationApplyTimeSupport']
                if ap_name not in expected and '@Redfish.AllowableValues' not in ap_name:
                    my_logger.error('{}: Property "{}" is not allowed in actions property. \
                        Allowed properties are "{}", "{}", "{}", "{}" and "{}"'.format(act_name, ap_name, *expected, '*@Redfish.AllowableValues'))
            actPass = True
        if actOptional and actPass:
            actionCounts['optionalAction'] += 1
        elif actPass:
            actionCounts['passAction'] += 1
        else:
            actionCounts['failAction'] += 1
            
        actionMessages[act_name] = (
                'Action', '-',
                'Yes' if actionDecoded != 'n/a' else 'No',
                'Optional' if actOptional else 'PASS' if actPass else 'FAIL')
    return actionMessages, actionCounts


def validateEntity(prop, val, parentURI=""):
    """
    Validates an entity based on its uri given
    """
    name, val, autoExpand = prop.Name, val, prop.Type.AutoExpand
    excerptType = prop.Type.excerptType if prop.Type.Excerpt else ExcerptTypes.NEUTRAL
    my_logger.debug('validateEntity: name = {}'.format(name))

    # check for required @odata.id
    uri = val.get('@odata.id')
    if '@odata.id' not in val:
        if autoExpand: uri = parentURI + '#/{}'.format(name.replace('[', '/').strip(']'))
        else: uri = parentURI + '/{}'.format(name)
        if excerptType == ExcerptTypes.NEUTRAL:
            my_logger.error("{}: EntityType resource does not contain required @odata.id property, attempting default {}".format(name, uri))
            if parentURI == "":
                return False

    # check if the entity is truly what it's supposed to be
    # if not autoexpand, we must grab the resource
    if not autoExpand:
        success, data, status, delay = traverseService.callResourceURI(uri)
    else:
        success, data, status, delay = True, val, 200, 0

    my_target_type = data.get('@odata.type', 'Resource.Item').strip('#')
    
    # if the reference is a Resource, save us some trouble as most/all basetypes are Resource
    generics = ['Resource.ItemOrCollection', 'Resource.ResourceCollection', 'Resource.Item', 'Resource.Resource']
    my_type = prop.Type.parent_type[0] if prop.Type.IsPropertyType else prop.Type.fulltype
    if success and my_type in generics:
        return True
    elif success:
        # Attempt to grab an appropriate type to test against and its schema
        # Default lineup: payload type, collection type, property type
        my_type_chain = [str(x) for x in prop.Type.getTypeTree()]

        try:
            my_target_schema = prop.Type.catalog.getSchemaDocByClass(getNamespaceUnversioned(my_target_type))
        except MissingSchemaError:
            my_logger.error("{}: Could not get schema file for Entity check".format(name))

        if getNamespace(my_target_type) not in my_target_schema.classes:
            my_logger.error('{}: Linked resource reports version {} not in Schema'.format(name.split(':')[-1], my_target_type))
        else:
            my_target_type = my_target_schema.getTypeInSchemaDoc(my_target_type)
            all_target_types = [str(x) for x in my_target_type.getTypeTree()]
            if any(x in my_type_chain for x in all_target_types):
                return True
            else:
                my_logger.error('{}: Linked resource reports version {} not in Typechain' .format(name.split(':')[-1], my_target_type))
                return False
    else:
        if excerptType == ExcerptTypes.NEUTRAL:
            if "OriginOfCondition" in name:
                my_logger.log(logging.INFO-1, "{}: GET of resource at URI {} returned HTTP {}, but was a temporary resource."
                                .format(name, uri, status if isinstance(status, int) and status >= 200 else "error"))
                return True

            else:
                my_logger.error("{}: GET of resource at URI {} returned HTTP {}. Check URI."
                                .format(name, uri, status if isinstance(status, int) and status >= 200 else "error"))
                return False
        else:
            return True
    return False


def validateComplex(sub_obj, prop_name):
    subMsgs, subCounts = OrderedDict(), Counter()
    for sub_name, sub_prop in sub_obj.properties.items():
        new_msgs, new_counts = checkPropertyConformance(sub_obj, sub_name, sub_prop)
        subMsgs.update(new_msgs)
        subCounts.update(new_counts)

    jsonData = sub_obj.Value
    allowAdditional = sub_obj.Type.HasAdditional
    if prop_name != 'Actions':
        for key in [k for k in jsonData if k not in subMsgs and k not in sub_obj.properties and '@' not in k]:
            # note: extra subMsgs for "unchecked" properties
            item = jsonData.get(key)
            if not allowAdditional:
                my_logger.error('{} not defined in Complex {} (check version, spelling and casing)'
                                .format(key, prop_name))
                subCounts['failAdditional.complex'] += 1
                subMsgs[key] = (displayValue(item), '-', '-', 'FAIL')
            else:
                my_logger.warn('{} not defined in schema Complex {} (check version, spelling and casing)'
                                .format(key, prop_name))
                subCounts['unverifiedAdditional.complex'] += 1
                subMsgs[key] = (displayValue(item), '-', '-', 'Additional')

    successPayload, odataMessages = checkPayloadConformance(sub_obj.Value, '')
    if not successPayload:
        odataMessages['failPayloadError.complex'] += 1
        my_logger.error('{}: complex payload error, @odata property non-conformant'.format(str(sub_obj.Name)))
    subMsgs.update(odataMessages)

    if prop_name == 'Actions':
        actionMessages, actionCounts = OrderedDict(), Counter()

        my_actions = [(x.strip('#'), y) for x, y in sub_obj.Value.items() if x != 'Oem']
        if 'Oem' in sub_obj.Value.items():
            if traverseService.currentService.config.get('oemcheck'):
                my_actions.extend([(x, y) for x, y in sub_obj.Value['Oem'].items()])
            else:
                actionCounts['oemActionSkip'] += len(sub_obj.Value['Oem'])

        # get ALL actions (but we don't need to test for them...)
        # ...
        # for new_act in sub_class.actions:
        #     new_act_name = '#{}.{}'.format(base_type, new_act)
        #     if new_act_name not in my_actions:
        #         my_actions.append((new_act_name, REDFISH_ABSENT))
        for act_name, actionDecoded in my_actions:
            act_schema = sub_obj.Type.catalog.getSchemaDocByClass(getNamespace(act_name))
            act_class = act_schema.classes.get(getNamespace(act_name))

            a, c = validateAction(act_name, actionDecoded, act_class.actions)

            actionMessages.update(a)
            actionCounts.update(c)
        subMsgs.update(actionMessages)
        subCounts.update(actionCounts)
    return subMsgs, subCounts


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
        my_logger.debug('{}: {}: found attribute registry entry for key {}'.format(fn, name, key))
        attr = attr_reg.get(key)
    else:
        my_logger.debug('{}: {}: did not find attribute registry entry for key {}'.format(fn, name, key))
        return True, None
    type_prop = attr.get('Type')
    if type_prop is None:
        my_logger.debug('{}: {}: no Type property found for key {}'.format(fn, name, key))
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
                my_logger.error(
                    '{} has a value of {}. This is not an expected value from the Enumeration: {}'
                    .format(name + '.' + key, value, val_list))
        else:
            my_logger.debug('{}: Expected Value property key {} to be a list, found type {}'
                            .format(fn, name + '.' + key, str(type(value)).strip('<>')))
    elif type_prop == 'String':
        # validate type is string
        reg_pass = isinstance(value, str)
        if not reg_pass:
            my_logger.error(
                '{} has a value of {}. The expected type is String but the type found is {}'
                .format(name + '.' + key, value, str(type(value)).strip('<>')))
        else:
            # validate MaxLength
            max_len = attr.get('MaxLength')
            if max_len is not None:
                if isinstance(max_len, int):
                    if len(value) > max_len:
                        reg_pass = False
                        my_logger.error(
                            '{} has a length of {}, which is greater than its MaxLength of {}'
                            .format(name + '.' + key, len(value), max_len))
                else:
                    reg_pass = False
                    my_logger.error('{} should have a MaxLength property that is an integer, but the type found is {}'
                                    .format(name + '.' + key, str(type(max_len)).strip('<>')))
            # validate MinLength
            min_len = attr.get('MinLength')
            if min_len is not None:
                if isinstance(min_len, int):
                    if len(value) < min_len:
                        reg_pass = False
                        my_logger.error('{} has a length of {}, which is less than its MinLength of {}'
                                        .format(name + '.' + key, len(value), min_len))
                else:
                    reg_pass = False
                    my_logger.error('{} should have a MinLength property that is an integer, but the type found is {}'
                                    .format(name + '.' + key, str(type(min_len)).strip('<>')))
            # validate ValueExpression
            val_expr = attr.get('ValueExpression')
            if val_expr is not None:
                if isinstance(val_expr, str):
                    regex = re.compile(val_expr)
                    if regex.match(value) is None:
                        reg_pass = False
                        my_logger.error(
                            '{} has a value of {} which does not match the ValueExpression regex "{}"'
                            .format(name + '.' + key, value, val_expr))
                else:
                    reg_pass = False
                    my_logger.error(
                        '{} should have a ValueExpression property that is a string, but the type found is {}'
                        .format(name + '.' + key, str(type(val_expr)).strip('<>')))
    elif type_prop == 'Integer':
        # validate type is int
        reg_pass = isinstance(value, int)
        if not reg_pass:
            my_logger.error(
                '{} has a value of {}. The expected type is Integer but the type found is {}'
                .format(name + '.' + key, value, str(type(value)).strip('<>')))
        else:
            # validate LowerBound
            lower_bound = attr.get('LowerBound')
            if isinstance(lower_bound, int):
                if value < lower_bound:
                    reg_pass = False
                    my_logger.error('{} has a value of {}, which is less than its LowerBound of {}'
                                    .format(name + '.' + key, value, lower_bound))
            else:
                reg_pass = False
                my_logger.error('{} should have a LowerBound property that is an integer, but the type found is {}'
                                .format(name + '.' + key, str(type(lower_bound)).strip('<>')))
            # validate UpperBound
            upper_bound = attr.get('UpperBound')
            if isinstance(upper_bound, int):
                if value > upper_bound:
                    reg_pass = False
                    my_logger.error('{} has a value of {}, which is greater than its UpperBound of {}'
                                    .format(name + '.' + key, value, upper_bound))
            else:
                reg_pass = False
                my_logger.error('{} should have an UpperBound property that is an integer, but the type found is {}'
                                .format(name + '.' + key, str(type(upper_bound)).strip('<>')))
    elif type_prop == 'Boolean':
        reg_pass = isinstance(value, bool)
        if not reg_pass:
            my_logger.error(
                '{} has a value of {}. The expected type is Boolean but the type found is {}'
                .format(name + '.' + key, value, str(type(value)).strip('<>')))
    elif type_prop == 'Password':
        reg_pass = value is None
        if not reg_pass:
            my_logger.error(
                '{} is a Password. The value returned from GET must be null, but was of type {}'
                .format(name + '.' + key, str(type(value)).strip('<>')))
    else:
        my_logger.warning('{} has an unexpected Type property of {}'
                          .format(name + '.' + key, type_prop))
    return reg_pass, type_prop


# unusued
# validate the Redfish.DynamicPropertyPatterns if present
# current issue, missing refs where they are appropriate, may cause issues
# if sub_obj.Type.property_pattern:
#     patternMessages, patternCounts = validateDynamicPropertyPatterns(prop_name, val, propTypeObj, payloadType, attrRegistryId, ParentItem=name)
#     complexMessages.update(patternMessages)
#     complexCounts.update(patternCounts)

def validateDynamicPropertyPatterns(name, val, pattern_obj, attrRegistryId):
    """
    Checks the value type and key pattern of the properties specified via Redfish.DynamicPropertyPatterns annotation
    :param name: the name of the dictionary of properties being validated
    :param val: the dictionary of properties being validated
    :param propTypeObj: the PropType instance
    :param payloadType: the type of the payload being validated
    :param attrRegistryId: teh AttributeRegistry ID (if applicable) for this dictionary of properties
    :return: the subMsgs and counts of the validation results
    """
    fn = 'validateDynamicPropertyPatterns'
    subMsgs = OrderedDict()
    counts = Counter()
    prop_pattern = pattern_obj.get('Pattern')
    prop_type = pattern_obj.get('Type')
    if prop_pattern is None or prop_type is None:
        my_logger.error('{} has Redfish.DynamicPropertyPatterns annotation, but Pattern or Type properties missing'
                        .format(name))
        return subMsgs, counts
    if not isinstance(prop_pattern, str):
        my_logger.error('{} has Redfish.DynamicPropertyPatterns annotation, but Pattern property not a string'
                        .format(name))
        return subMsgs, counts
    if not isinstance(prop_type, str):
        my_logger.error('{} has Redfish.DynamicPropertyPatterns annotation, but Type property not a string'
                        .format(name))
        return subMsgs, counts
    if not isinstance(val, dict):
        my_logger.error('{} has Redfish.DynamicPropertyPatterns annotation, but payload value not a dictionary'
                        .format(name))
        return subMsgs, counts
    # get the attribute registry dictionary if applicable
    attr_reg = None
    if attrRegistryId is not None:
        if attrRegistryId in attributeRegistries:
            my_logger.debug('{}: {}: Using attribute registry for {}'.format(fn, name, attrRegistryId))
            attr_reg = attributeRegistries.get(attrRegistryId)
        elif 'default' in attributeRegistries:
            my_logger.debug('{}: {}: Using default attribute registry for {}'.format(fn, name, attrRegistryId))
            attr_reg = attributeRegistries.get('default')
        else:
            my_logger.warning('{}: Attribute Registry with ID {} not found'.format(name, attrRegistryId))
    else:
        my_logger.debug('{}: {}: No Attribute Registry ID found'.format(fn, name, attrRegistryId))
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
                    my_logger.error('{} does not match pattern "{}"'.format(name + '.' + key, prop_pattern))
        else:
            pattern_pass = False
            my_logger.error('{} is not a string, so cannot be validated against pattern "{}"'
                            .format(name + '.' + key, prop_pattern))
        if pattern_pass:
            counts['passPattern'] += 1
        else:
            counts['failDynamicPropertyPatterns'] += 1
        # validate the value type against the Type
        reg_pass = True
        attr_reg_type = None
        if attr_reg is not None:
            reg_pass, attr_reg_type = validateAttributeRegistry(name, key, value, attr_reg)
            if reg_pass:
                counts['passReg'] += 1
            else:
                counts['failAttributeRegistry'] += 1

    return subMsgs, counts


def displayType(propTypeObject, is_collection=False):
    """
    Convert inputs propType and propRealType to a simple, human readable type
    :param propType: the 'Type' attribute from the PropItem.propDict
    :param propRealType: the 'realtype' entry from the PropItem.propDict
    :param is_collection: For collections: True if these types are for the collection; False if for a member
    :return: the simplified type to display
    """
    propRealType, propCollection = propTypeObject.getBaseType()
    propType = propTypeObject.parent_type[0] if propTypeObject.IsPropertyType else propTypeObject.fulltype
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
        if propCollection:
            member_type = propType.replace('Collection(', '').replace(')', '')
            if is_collection:
                disp_type = 'array of: {}'.format(member_type)
            else:
                disp_type = member_type
        else:
            disp_type = 'link to: {}'.format(propTypeObject)
    # Complex types
    elif propRealType == 'complex':
        if propCollection:
            member_type = propType.replace('Collection(', '').replace(')', '')
            if is_collection:
                disp_type = 'array of: {}'.format(member_type)
            else:
                disp_type = member_type
        else:
            disp_type = propType
    # Fallback cases
    elif len(propRealType) > 0:
        disp_type = propRealType
    elif len(propType) > 0:
        disp_type = propType
    else:
        disp_type = 'n/a'

    my_logger.debug('displayType: ({}, {}) -> {}'.format(propType, propRealType, disp_type))
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

    my_logger.debug('displayValue: {} -> {}'.format(val, disp_val))
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
        my_logger.debug('{}: Expected json_data param to be a dict, found {}'.format(fn, type(json_data)))
        return

    # get Id property if present; if missing use a key of 'default' to store the dictionary
    reg_id = json_data.get('Id')
    if reg_id is None:
        reg_id = 'default'

    my_logger.debug('{}: @odata.type = {}, Id = {}'.format(fn, odata_type, reg_id))

    # do some validations on the format of the attribute registry
    if reg_id in attributeRegistries:
        my_logger.error('{}: An AttributeRegistry with Id "{}" has already been loaded'.format(fn, reg_id))
        return
    reg_entries = json_data.get('RegistryEntries')
    if not isinstance(reg_entries, dict):
        my_logger.warning('{}: Expected RegistryEntries property to be a dict, found {}'.format(fn, type(reg_entries)))
        return
    attributes = reg_entries.get('Attributes')
    if not isinstance(attributes, list):
        my_logger.warning('{}: Expected Attributes property to be an array, found {}'.format(fn, type(attributes)))
        return
    if len(attributes) > 0:
        if not isinstance(attributes[0], dict):
            my_logger.warning('{}: Expected elements of Attributes array to be of type dict, found {}'
                              .format(fn, type(attributes[0])))
            return
    else:
        my_logger.debug('{}: Attributes element was zero length'.format(fn))
        return

    # load the attribute registry into a dictionary
    attr_dict = dict()
    for attr in attributes:
        attr_name = attr.get('AttributeName')
        if attr_name is None:
            my_logger.debug('{}: Expected AttributeName property was not found in array element'.format(fn))
            continue
        if attr.get(attr_name) is not None:
            my_logger.warning('{}: AttributeName {} was already seen; previous version will be overwritten'
                            .format(fn, attr_name))
        attr_dict[attr_name] = attr

    # store the attribute registry in global dict `attributeRegistries`
    if len(attr_dict) > 0:
        my_logger.debug('{}: Adding "{}" AttributeRegistry dict with {} entries'.format(fn, reg_id, len(attr_dict)))
        attributeRegistries[reg_id] = attr_dict
    else:
        my_logger.debug('{}: "{}" AttributeRegistry dict has zero entries; not adding'.format(fn, reg_id))


def checkPropertyConformance(parent_obj, prop_name, prop, parent_name=None, parent_URI=""):
    """checkPropertyConformance

    Given a dictionary of properties, check the validitiy of each prop_name, and return a
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

    my_logger.log(logging.INFO-1, prop_name)
    my_logger.log(logging.INFO-1,"\tvalue: {} {}".format(prop.Value, type(prop.Value)))

    prop_name = '.'.join([x for x in (parent_name, prop_name) if x])

    propNullable = prop.Type.IsNullable

    if not prop.SchemaExists:
        if not prop.Exists:
            my_logger.log(logging.INFO-1,'{}: Item is skipped, no schema'.format(prop_name))
            counts['skipNoSchema'] += 1
            return {prop_name: ('-', '-', 'Yes' if prop.Exists else 'No', 'NoSchema')}, counts
        else:
            my_logger.error('{}: Item is present, but no schema found'.format(prop_name))
            counts['failNoSchema'] += 1
            return {prop_name: ('-', '-', 'Yes' if prop.Exists else 'No', 'FAIL')}, counts

    # check oem
    # rs-assertion: 7.4.7.2
    if 'Oem' in prop_name and not traverseService.config.get('oemcheck', True):
        my_logger.log(logging.INFO-1,'\tOem is skipped')
        counts['skipOem'] += 1
        return {prop_name: (prop_name, '-', '-', 'Yes' if prop.Exists else 'No', 'OEM')}, counts

    # Parameter Passes
    paramPass = propMandatoryPass = propNullablePass = deprecatedPass = nullValid = True

    if prop.Type.IsMandatory:
        propMandatoryPass = True if prop.Exists else False
        my_logger.log(logging.INFO-1,"\tMandatory Test: {}".format('OK' if propMandatoryPass else 'FAIL'))
    else:
        my_logger.log(logging.INFO-1,"\tis Optional")
        if not prop.Exists:
            my_logger.log(logging.INFO-1,"\tprop Does not exist, skip...")
            counts['skipOptional'] += 1
            return {prop_name: ( '-', displayType(prop.Type), 'Yes' if prop.Exists else 'No', 'Optional')}, counts

    # <Annotation Term="Redfish.Deprecated" String="This property has been Deprecated in favor of Thermal.v1_1_0.Thermal.Fan.Name"/>
    if prop.Type.Deprecated is not None:
        deprecatedPass = False
        counts['warnDeprecated'] += 1
        my_logger.warning('{}: The given property is deprecated: {}'.format(prop_name, prop.Type.Deprecated.get('String', '')))

    if prop.Type.Revisions is not None:
        for tag_item in prop.Type.Revisions:
            revision_tag = tag_item.find('PropertyValue', attrs={ 'EnumMember': 'Redfish.RevisionKind/Deprecated', 'Property': 'Kind'})
            if (revision_tag):
                desc_tag = tag_item.find('PropertyValue', attrs={'Property': 'Description'})
                deprecatedPass = False
                counts['warnDeprecated'] += 1
                if (desc_tag):
                    my_logger.warning('{}: The given property is deprecated by revision: {}'.format(prop_name, desc_tag.attrs.get('String', '')))
                else:
                    my_logger.warning('{}: The given property is deprecated by revision'.format(prop_name))

    # Note: consider http://docs.oasis-open.org/odata/odata-csdl-xml/v4.01/csprd01/odata-csdl-xml-v4.01-csprd01.html#_Toc472333112
    # Note: make sure it checks each one
    # propCollectionType = PropertyDict.get('isCollection')
    propRealType, isCollection = prop.Type.getBaseType()

    excerptPass = True
    if isCollection and prop.Value is None:
        # illegal for a collection to be null
        if 'HttpHeaders' in str(prop.Type.fulltype) and getType(str(prop.Type.fulltype)) == 'EventDestination':
            my_logger.info('Value HttpHeaders can be Null')
            propNullable = True
            propValueList = []
            resultList[prop_name] = ('Array (size: null)', displayType(prop.Type, is_collection=True), 'Yes' if prop.Exists else 'No', '...')
        else:
            my_logger.error('{}: Value of Collection property is null but Collections cannot be null, only their entries'.format(prop_name))
            counts['failNullCollection'] += 1
            return {prop_name: ( '-', displayType(prop.Type, is_collection=True), 'Yes' if prop.Exists else 'No', 'FAIL')}, counts
    elif isCollection and prop.Value is not None:
        # note: handle collections correctly, this needs a nicer printout
        # rs-assumption: do not assume URIs for collections
        # rs-assumption: check @odata.count property
        # rs-assumption: check @odata.link property
        my_logger.log(logging.INFO-1,"\tis Collection")
        if prop.Value == 'n/a':
            propValueList = []
            resultList[prop_name] = ('Array (absent)'.format(len(prop.Value)),
                                displayType(prop.Type, is_collection=True),
                                'Yes' if prop.Exists else 'No', 'PASS' if propMandatoryPass else 'FAIL')
            my_logger.error("{}: Mandatory prop does not exist".format(prop_name))
            counts['failMandatoryExist'] += 1
        else:
            propValueList = prop.Value
            resultList[prop_name] = ('Array (size: {})'.format(len(prop.Value)), 
                                displayType(prop.Type, is_collection=True),
                                'Yes' if prop.Exists else 'No', '...')
    else:
        # not a collection
        propValueList = [prop.Value]

    if propRealType == 'complex':
        resultList[prop_name] = (
                        '[JSON Object]', displayType(prop.Type),
                        'Yes' if prop.Exists else 'No',
                        'complex')
        for n, sub_obj in enumerate(prop.Collection):
            try:
                subMsgs, subCounts = validateComplex(sub_obj, prop_name)
                if len(prop.Collection) == 1:
                    subMsgs = {'{}.{}'.format(prop_name,x):y for x,y in subMsgs.items()}
                else:
                    subMsgs = {'{}.{}#{}'.format(prop_name,x,n):y for x,y in subMsgs.items()}
                resultList.update(subMsgs)
                counts.update(subCounts)
            except Exception as ex:
                my_logger.error('Exception caught while validating Complex', exc_info=1)
                my_logger.error('{}: Could not finish check on this property ({})'.format(prop_name, str(ex)))
                counts['exceptionPropCheck'] += 1
        return resultList, counts
    
    # all other types...
    for cnt, val in enumerate(propValueList):
        appendStr = (('[' + str(cnt) + ']') if isCollection else '')
        sub_item = prop_name + appendStr

        excerptPass = validateExcerpt(prop, val)

        if isinstance(val, str):
            if val == '' and prop.Type.Permissions == 'OData.Permission/Read':
                my_logger.warning('{}: Empty string found - Services should omit properties if not supported'.format(sub_item))
                nullValid = False
            if val.lower() == 'null':
                my_logger.warning('{}: "null" string found - Did you mean to use an actual null value?'.format(sub_item))
                nullValid = False

        if prop.Exists:
            paramPass = propNullablePass = True
            if val is None:
                if propNullable:
                    my_logger.debug('Property {} is nullable and is null, so Nullable checking passes'.format(sub_item))
                else:
                    propNullablePass = False
            
            paramPass = prop.IsValid
        
            paramPass = prop.populate(val, True)

            if propRealType == 'entity':
                paramPass = validateEntity(prop, val)


        my_type = prop.Type.parent_type[0] if prop.Type.IsPropertyType else prop.Type.fulltype

        if not paramPass or not propMandatoryPass or not propNullablePass:
            result_str = 'FAIL'
        elif not deprecatedPass:
            result_str = 'Deprecated'
        elif not nullValid:
            counts['invalidPropertyValue'] += 1
            result_str = 'WARN'
        else:
            result_str = 'PASS'
        if not excerptPass:
            counts['errorExcerpt'] += 1
            result_str = 'errorExcerpt'
        resultList[sub_item] = (
                displayValue(val, sub_item if prop.Type.AutoExpand else None), displayType(prop.Type),
                'Yes' if prop.Exists else 'No', result_str)
        if paramPass and propNullablePass and propMandatoryPass and excerptPass:
            counts['pass'] += 1
            my_logger.log(logging.INFO-1,"\tSuccess")
        else:
            counts['err.' + str(my_type)] += 1
            if not paramPass:
                if prop.Type.IsMandatory:
                    counts['failMandatoryProp'] += 1
                else:
                    counts['failProp'] += 1
            elif not propMandatoryPass:
                my_logger.error("{}: Mandatory prop does not exist".format(sub_item))
                counts['failMandatoryExist'] += 1
            elif not propNullablePass:
                my_logger.error('{}: Property is null but is not Nullable'.format(sub_item))
                counts['failNullable'] += 1
            my_logger.log(logging.INFO-1,"\tFAIL")

    return resultList, counts
