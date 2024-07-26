
from collections import Counter, OrderedDict
from redfish_service_validator.catalog import REDFISH_ABSENT, MissingSchemaError, ExcerptTypes, get_fuzzy_property, RedfishObject, RedfishType

from redfish_service_validator.helper import getNamespace, getNamespaceUnversioned, getType, checkPayloadConformance, stripCollection

import logging

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)


def validateExcerpt(prop, val):
    # check Navprop if it's NEUTRAL or CONTAINS
    base = prop.Type.getBaseType()

    if base == 'entity':
        my_excerpt_type, my_excerpt_tags = prop.Type.excerptType, prop.Type.excerptTags

        my_new_type = stripCollection(prop.Type.fulltype)

        new_type_obj = prop.Type.catalog.getSchemaDocByClass(getNamespace(my_new_type)).getTypeInSchemaDoc(my_new_type)

        my_props = new_type_obj.createObject(prop.Name).populate(val).properties

        for name, innerprop in my_props.items():
            if not innerprop.HasSchema:
                continue
            valid_tagging = any([x in my_excerpt_tags for x in innerprop.Type.excerptTags]) or innerprop.Type.excerptTags == []
            if my_excerpt_type == ExcerptTypes.NEUTRAL:
                if innerprop.Type.excerptType == [ExcerptTypes.EXCLUSIVE] and innerprop.Exists:
                    my_logger.error('{}: Exclusive Excerpt {} should not exist in this Resource/ComplexType'.format(prop.Name, innerprop.Name))
                    return False
            if my_excerpt_type == ExcerptTypes.CONTAINS:
                if innerprop.Type.excerptType in [ExcerptTypes.ALLOWED, ExcerptTypes.EXCLUSIVE, ExcerptTypes.CONTAINS]:
                    if innerprop.Exists and not valid_tagging:
                        my_logger.error('{}: Excerpt tags of owner {} do not match property {} {}'.format(innerprop.Name, prop.Name, my_excerpt_tags, innerprop.Type.excerptTags))
                        return False
                elif innerprop.Exists:
                    my_logger.error('{}: Property is not a valid Excerpt'.format(innerprop.Name))
                    return False

    # check our prop if it's EXCLUSIVE
    if prop.Type.excerptType == ExcerptTypes.EXCLUSIVE and prop.Exists:
        my_logger.error('{}: Exclusive Excerpt should not exist in a Resource/Complex'.format(prop.Name))
        return False

    return True


def validateAction(act_fulltype, actionDecoded, all_actions):
    actionMessages, actionCounts = OrderedDict(), Counter()
    act_namespace, act_type = getNamespace(act_fulltype.strip('#')), getType(act_fulltype)
    actPass = True
    if act_type not in all_actions:
        my_logger.error('Action {} does not exist in Namespace {}'.format(act_type, act_namespace))
        actionCounts['errorActionBadName'] += 1
        actionMessages[act_fulltype] = (
                'Action', '-',
                'Yes' if actionDecoded != REDFISH_ABSENT else 'No',
                'FAIL')
    else:
        my_act = all_actions[act_type]
        actOptional = my_act.find('annotation', {'term': 'Redfish.Required'}) is not None
        if actionDecoded == REDFISH_ABSENT:
            if not actOptional:
                actPass = False
                my_logger.error('{}: Mandatory action missing'.format(act_fulltype))
                actionCounts['failMandatoryAction'] += 1
        if actionDecoded != REDFISH_ABSENT:
            # validate target
            target = actionDecoded.get('target')
            if target is None:
                actPass = False
                my_logger.error('{}: target for action is missing'.format(act_fulltype))
            elif not isinstance(target, str):
                actPass = False
                my_logger.error('{}: target for action is malformed'.format(act_fulltype))
            # check for unexpected properties
            for ap_name in actionDecoded:
                expected = ['target', 'title', '@Redfish.ActionInfo', '@Redfish.OperationApplyTimeSupport']
                expected_patterns = ['@Redfish.AllowableValues', '@Redfish.AllowableNumbers', '@Redfish.AllowablePattern']
                if ap_name not in expected and not any(pattern in ap_name for pattern in expected_patterns):
                    actPass = False
                    my_logger.error('{}: Property "{}" is not allowed in actions property. ' \
                        'Allowed properties are {}, {}'.format(act_fulltype, ap_name, ', '.join(expected), ', '.join(expected_patterns)))
        if actOptional and actPass:
            actionCounts['optionalAction'] += 1
        elif actPass:
            actionCounts['passAction'] += 1
        else:
            actionCounts['failAction'] += 1
            
        actionMessages[act_fulltype] = (
                'Action', '-',
                'Yes' if actionDecoded != REDFISH_ABSENT else 'No',
                'Optional' if actOptional else 'PASS' if actPass else 'FAIL')
    return actionMessages, actionCounts


def validateEntity(service, prop, val, parentURI=""):
    """
    Validates an entity based on its uri given
    """
    name, val, autoExpand = prop.Name, val, prop.IsAutoExpanded
    excerptType = prop.Type.excerptType if prop.Type.Excerpt else ExcerptTypes.NEUTRAL
    my_logger.debug('validateEntity: name = {}'.format(name))

    # check for required @odata.id
    if not isinstance(val, dict):
        my_logger.info("{}: EntityType val is null/absent, not testing...".format(name))
        return False
    uri = val.get('@odata.id')
    if '@odata.id' not in val:
        if autoExpand:
            uri = parentURI + '#/{}'.format(name.replace('[', '/').strip(']'))
        else:
            uri = parentURI + '/{}'.format(name)

        if excerptType == ExcerptTypes.NEUTRAL:
            my_logger.error("{}: EntityType resource does not contain required @odata.id property, attempting default {}".format(name, uri))
            if parentURI == "":
                return False
        else:
            # Don't need to verify an excerpt's entity this way
            return True

    # check if the entity is truly what it's supposed to be
    # if not autoexpand, we must grab the resource
    if not autoExpand:
        success, data, response, delay = service.callResourceURI(uri)
        if success and response is not None:
            status = response.status
        else:
            status = -1
    else:
        success, data, response, delay = True, val, None, 0
        status = 200

    generics = ['Resource.ItemOrCollection', 'Resource.ResourceCollection', 'Resource.Item', 'Resource.Resource']
    my_type = prop.Type.fulltype
    if success and my_type in generics:
        return True
    elif success:
        my_target_type = data.get('@odata.type', 'Resource.Item').strip('#')
        # Attempt to grab an appropriate type to test against and its schema
        # Default lineup: payload type, collection type, property type
        my_type_chain = [str(x) for x in prop.Type.getTypeTree()]

        try:
            my_target_schema = prop.Type.catalog.getSchemaDocByClass(getNamespaceUnversioned(my_target_type))
        except MissingSchemaError:
            my_logger.error("{}: Could not get schema file for Entity check".format(name))
            return False

        if getNamespace(my_target_type) not in my_target_schema.classes:
            my_logger.error('{}: Linked resource reports version {} not in Schema'.format(name.split(':')[-1], my_target_type))
        else:
            my_target_type = my_target_schema.getTypeInSchemaDoc(my_target_type)
            all_target_types = [str(x) for x in my_target_type.getTypeTree()]
            expect_type = stripCollection(prop.Type.fulltype)
            if expect_type not in all_target_types and my_target_type != 'Resource.Item':
                my_logger.error('{}: Linked resource is not the correct type; found {}, expected {}' .format(name.split(':')[-1], my_target_type, expect_type))
                return False
            elif any(x in my_type_chain for x in all_target_types):
                return True
            else:
                my_logger.error('{}: Linked resource reports version {} not in Typechain' .format(name.split(':')[-1], my_target_type))
                return False
    else:
        if excerptType == ExcerptTypes.NEUTRAL:
            if "OriginOfCondition" in name:
                my_logger.verbose1("{}: GET of resource at URI {} returned HTTP {}, but was a temporary resource."
                                .format(name, uri, status if isinstance(status, int) and status >= 200 else "error"))
                return True

            else:
                my_logger.error("{}: GET of resource at URI {} returned HTTP {}. Check URI."
                                .format(name, uri, status if isinstance(status, int) and status >= 200 else "error"))
                return False
        else:
            return True
    return False


def validateComplex(service, sub_obj, prop_name, oem_check=True):
    subMsgs, subCounts = OrderedDict(), Counter()

    # Based on the object's properties, see if we need to insert a pattern to verify the contents
    # At this time, only the Identifier object has this type of check to ensure the DurableName matches the long description
    if "DurableName" in sub_obj.properties and "DurableNameFormat" in sub_obj.properties:
        if sub_obj.properties["DurableNameFormat"].Value == "NAA":
            sub_obj.properties["DurableName"].added_pattern = '^(([0-9A-Fa-f]{2}){8}){1,2}$'
        elif sub_obj.properties["DurableNameFormat"].Value == "FC_WWN":
            sub_obj.properties["DurableName"].added_pattern = '^([0-9A-Fa-f]{2}[:-]){7}([0-9A-Fa-f]{2})$'
        elif sub_obj.properties["DurableNameFormat"].Value == "UUID":
            sub_obj.properties["DurableName"].added_pattern = '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
        elif sub_obj.properties["DurableNameFormat"].Value == "EUI":
            sub_obj.properties["DurableName"].added_pattern = '^([0-9A-Fa-f]{2}[:-]){7}([0-9A-Fa-f]{2})$'
        elif sub_obj.properties["DurableNameFormat"].Value == "NGUID":
            sub_obj.properties["DurableName"].added_pattern = '^([0-9A-Fa-f]{2}){16}$'
        elif sub_obj.properties["DurableNameFormat"].Value == "MACAddress":
            sub_obj.properties["DurableName"].added_pattern = '^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'

    for sub_name, sub_prop in sub_obj.properties.items():
        if not sub_prop.HasSchema and not sub_prop.Exists:
            subCounts['skipNoSchema'] += 1
            continue
        elif not sub_prop.HasSchema:
            my_logger.error('No Schema for sub_property {}'.format(sub_prop.Name))
            subCounts['errorNoSchema'] += 1
            continue
        new_msgs, new_counts = checkPropertyConformance(service, sub_name, sub_prop)
        subMsgs.update(new_msgs)
        subCounts.update(new_counts)

    jsonData = sub_obj.Value
    allowAdditional = sub_obj.Type.HasAdditional
    if prop_name != 'Actions':
        for key in [k for k in jsonData if k not in subMsgs and k not in sub_obj.properties and '@' not in k]:
            # note: extra subMsgs for "unchecked" properties
            item = jsonData.get(key)
            if not allowAdditional:
                my_logger.error('{} not defined in Complex {} {} (check version, spelling and casing)'
                                .format(key, prop_name, sub_obj.Type))
                subCounts['failAdditional.complex'] += 1
                subMsgs[key] = (displayValue(item), '-', '-', 'FAIL')
            else:
                my_logger.warning('{} not defined in schema Complex {} {} (check version, spelling and casing)'
                                .format(key, prop_name, sub_obj.Type))
                subCounts['unverifiedAdditional.complex'] += 1
                subMsgs[key] = (displayValue(item), '-', '-', 'Additional')
            
            fuzz = get_fuzzy_property(key, sub_obj.properties)
            if fuzz != key and fuzz in sub_obj.properties:
                subMsgs[fuzz] = ('-', '-', '-', 'INVALID')
                my_logger.error('Attempting {} (from {})?'.format(fuzz, key))
                my_new_obj = sub_obj.properties[fuzz].populate(item)
                new_msgs, new_counts = checkPropertyConformance(service, key, my_new_obj)
                subMsgs.update(new_msgs)
                subCounts.update(new_counts)
                subCounts['invalidNamedProperty.complex'] += 1

    successPayload, odataMessages = checkPayloadConformance(sub_obj.Value, '')

    if not successPayload:
        odataMessages['failPayloadError.complex'] += 1
        my_logger.error('{}: complex payload error, @odata property non-conformant'.format(str(sub_obj.Name)))

    if prop_name == 'Actions':
        actionMessages, actionCounts = OrderedDict(), Counter()

        # Get our actions from the object itself to test
        # Action Namespace.Type, Action Object
        my_actions = [(x.strip('#'), y) for x, y in sub_obj.Value.items() if x != 'Oem']
        if 'Oem' in sub_obj.Value:
            if oem_check:
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
            if '@' in act_name:
                continue
            try:
                act_schema = sub_obj.Type.catalog.getSchemaDocByClass(getNamespace(act_name))
                act_class = act_schema.classes.get(getNamespace(act_name))
            except:
                my_logger.warning('Schema not found for action {}'.format(act_name))
                continue

            a, c = validateAction(act_name, actionDecoded, act_class.actions)

            actionMessages.update(a)
            actionCounts.update(c)
        subMsgs.update(actionMessages)
        subCounts.update(actionCounts)
    return subMsgs, subCounts


def displayType(propTypeObject, is_collection=False):
    """
    Convert inputs propType and propRealType to a simple, human readable type
    :param propType: the 'Type' attribute from the PropItem.propDict
    :param propRealType: the 'realtype' entry from the PropItem.propDict
    :param is_collection: For collections: True if these types are for the collection; False if for a member
    :return: the simplified type to display
    """
    propRealType, propCollection = propTypeObject.getBaseType(), propTypeObject.IsCollection()
    propType = propTypeObject.fulltype
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
        member_type = getType(propType.replace('Collection(', '').replace(')', ''))
        if propCollection:
            if is_collection:
                disp_type = 'links: {}'.format(member_type)
            else:
                disp_type = 'link: {}'.format(member_type)
        else:
            disp_type = 'link to: {}'.format(member_type)
        if propTypeObject.AutoExpand:
            disp_type.replace('link', 'Expanded link')
    # Complex types
    elif propRealType == 'complex':
        if propCollection:
            member_type = getType(propType.replace('Collection(', '').replace(')', ''))
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


def checkPropertyConformance(service, prop_name, prop, parent_name=None, parent_URI=""):
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

    my_logger.verbose1(prop_name)
    my_logger.verbose1("\tvalue: {} {}".format(prop.Value, type(prop.Value)))

    # Basic Validation of all properties
    prop_name = '.'.join([x for x in (parent_name, prop_name) if x])

    propNullable = prop.Type.IsNullable

    if not prop.SchemaExists:
        if not prop.Exists:
            my_logger.verbose1('{}: Item is skipped, no schema'.format(prop_name))
            counts['skipNoSchema'] += 1
            return {prop_name: ('-', '-', 'Yes' if prop.Exists else 'No', 'NoSchema')}, counts
        else:
            my_logger.error('{}: Item is present, but no schema found'.format(prop_name))
            counts['failNoSchema'] += 1
            return {prop_name: ('-', '-', 'Yes' if prop.Exists else 'No', 'FAIL')}, counts

    # check oem
    # rs-assertion: 7.4.7.2
    oem_check = service.config.get('oemcheck', True)

    if not oem_check:
        if 'Oem' in prop_name or 'Resource.OemObject' in prop.Type.getTypeTree():
            my_logger.verbose1('\tOem is skipped')
            counts['skipOem'] += 1
            return {prop_name: ('-', '-', 'Yes' if prop.Exists else 'No', 'OEM')}, counts

    # Parameter Passes
    paramPass = propMandatoryPass = propNullablePass = deprecatedPassOrSinceVersion = nullValid = permissionValid = True

    if prop.Type.IsMandatory:
        propMandatoryPass = True if prop.Exists else False
        my_logger.verbose1("\tMandatory Test: {}".format('OK' if propMandatoryPass else 'FAIL'))
    else:
        my_logger.verbose1("\tis Optional")
        if not prop.Exists:
            my_logger.verbose1("\tprop Does not exist, skip...")
            counts['skipOptional'] += 1
            return {prop_name: ( '-', displayType(prop.Type), 'Yes' if prop.Exists else 'No', 'Optional')}, counts

    # <Annotation Term="Redfish.Deprecated" String="This property has been Deprecated in favor of Thermal.v1_1_0.Thermal.Fan.Name"/>
    if prop.Type.Deprecated is not None and not prop.Type.IsMandatory:
        deprecatedPassOrSinceVersion = False
        counts['warnDeprecated'] += 1
        my_logger.warning('{}: The given property is deprecated: {}'.format(prop_name, prop.Type.Deprecated.get('String', '')))

    if prop.Type.Revisions is not None:
        for tag_item in prop.Type.Revisions:
            revision_tag = tag_item.find('PropertyValue', attrs={ 'EnumMember': 'Redfish.RevisionKind/Deprecated', 'Property': 'Kind'})
            if revision_tag and not prop.Type.IsMandatory:
                desc_tag = tag_item.find('PropertyValue', attrs={'Property': 'Description'})
                version_tag = tag_item.find('PropertyValue', attrs={'Property': 'Version'})
                deprecatedPassOrSinceVersion = version_tag.attrs.get('String', False) if version_tag else False
                counts['warnDeprecated'] += 1
                if desc_tag:
                    my_logger.warning('{}: The given property is deprecated: {}'.format(prop_name, desc_tag.attrs.get('String', '')))
                else:
                    my_logger.warning('{}: The given property is deprecated'.format(prop_name))

    # Note: consider http://docs.oasis-open.org/odata/odata-csdl-xml/v4.01/csprd01/odata-csdl-xml-v4.01-csprd01.html#_Toc472333112
    # Note: make sure it checks each one
    # propCollectionType = PropertyDict.get('isCollection')
    propRealType, isCollection = prop.Type.getBaseType(), prop.Type.IsCollection()

    excerptPass = True
    if not isCollection and isinstance(prop.Value, list): 
        my_logger.error('{}: Value of property is an array but is not a Collection'.format(prop_name))
        counts['failInvalidArray'] += 1
        return {prop_name: ( '-', displayType(prop.Type, is_collection=True), 'Yes' if prop.Exists else 'No', 'FAIL')}, counts

    if isCollection and prop.Value is None:
        # illegal for a collection to be null
        if 'EventDestination.v1_0_0.HttpHeaderProperty' == str(prop.Type.fulltype):
            # HttpHeaders in EventDestination has non-conformant details in the long description we need to allow to not break existing implementations
            my_logger.info('Value HttpHeaders can be Null')
            propNullable = True
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
        my_logger.verbose1("\tis Collection")
        if prop.Value == REDFISH_ABSENT:
            resultList[prop_name] = ('Array (absent) {}'.format(len(prop.Value)),
                                displayType(prop.Type, is_collection=True),
                                'Yes' if prop.Exists else 'No', 'PASS' if propMandatoryPass else 'FAIL')
        elif not isinstance(prop.Value, list):
            my_logger.error('{}: property is expected to contain an array'.format(prop_name))
            counts['failInvalidArray'] += 1
            resultList[prop_name] = ('-', displayType(prop.Type, is_collection=True), 'Yes' if prop.Exists else 'No', 'FAIL')
            return resultList, counts
        else:
            resultList[prop_name] = ('Array (size: {})'.format(len(prop.Value)), displayType(prop.Type, is_collection=True), 'Yes' if prop.Exists else 'No', '...')

    # If we're validating a complex object
    if propRealType == 'complex':
        result_str = 'complex'
        if prop.Type.IsMandatory and not prop.Exists:
            my_logger.error("{}: Mandatory prop does not exist".format(prop_name))
            counts['failMandatoryExist'] += 1
            result_str = 'FAIL'

        if not prop.Exists:
            return resultList, counts

        if prop.IsCollection:
            resultList[prop_name] = ('Array (size: {})'.format(len(prop.Value)), displayType(prop.Type, is_collection=True), 'Yes' if prop.Exists else 'No', result_str)
            object_list = prop.Value
        else:
            resultList[prop_name] = ('[JSON Object]', displayType(prop.Type), 'Yes' if prop.Exists else 'No', result_str)
            object_list = [prop]
    
        for n, sub_obj in enumerate(object_list):
            try:
                if sub_obj.Value is None:
                    if prop.Type.IsNullable or 'EventDestination.v1_0_0.HttpHeaderProperty' == str(prop.Type.fulltype):
                        # HttpHeaders in EventDestination has non-conformant details in the long description we need to allow to not break existing implementations
                        counts['pass'] += 1
                        result_str = 'PASS'
                    else:
                        my_logger.error('{}: Property is null but is not Nullable'.format(prop_name))
                        counts['failNullable'] += 1
                        result_str = 'FAIL'
                    if isinstance(prop, RedfishObject):
                        resultList['{}.[Value]'.format(prop_name)] = ('[null]', displayType(prop.Type),
                                                                        'Yes' if prop.Exists else 'No', result_str)
                    else:
                        resultList['{}.[Value]#{}'.format(prop_name, n)] = ('[null]', displayType(prop.Type), 'Yes' if prop.Exists else 'No', result_str)
                else:
                    subMsgs, subCounts = validateComplex(service, sub_obj, prop_name, oem_check)
                    if isCollection:
                        subMsgs = {'{}[{}].{}'.format(prop_name, n, x): y for x, y in subMsgs.items()}
                    elif isinstance(prop, RedfishObject):
                        subMsgs = {'{}.{}'.format(prop_name, x): y for x, y in subMsgs.items()}
                    else:
                        subMsgs = {'{}.{}#{}'.format(prop_name, x, n): y for x, y in subMsgs.items()}
                    resultList.update(subMsgs)
                    counts.update(subCounts)
            except Exception as ex:
                my_logger.verbose1('Exception caught while validating Complex', exc_info=1)
                my_logger.error('{}: Could not finish check on this property ({})'.format(prop_name, str(ex)))
                counts['exceptionPropCheck'] += 1
        return resultList, counts

    # Everything else...
    else:
        propValueList = prop.Value if prop.IsCollection else [prop.Value]
        for cnt, val in enumerate(propValueList):
            appendStr = (('[' + str(cnt) + ']') if prop.IsCollection else '')
            sub_item = prop_name + appendStr

            if propRealType == 'entity' and isinstance(prop.Type, RedfishType):
                if prop.Type.TypeName in service.config['collectionlimit']:
                    link_limit = service.config['collectionlimit'][prop.Type.TypeName]
                    if cnt >= link_limit:
                        my_logger.verbose1('Removing link check via limit: {} {}'.format(prop.Type.TypeName, val))
                        resultList[sub_item] = (
                                displayValue(val, sub_item if prop.IsAutoExpanded else None), displayType(prop.Type),
                                'Yes' if prop.Exists else 'No', 'NOT TESTED')
                        continue

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

                #   <Annotation Term="OData.Permissions" EnumMember="OData.Permission/ReadWrite"/>
                if prop.Type.Permissions == "OData.Permission/Write" or prop.Type.Permissions == "OData.Permission/None":
                    if val is not None:
                        my_logger.error('{}: Permissions for this property are Write only, reading this property should be null!!!'.format(sub_item))
                        permissionValid = False
                        counts['failWriteOnly'] += 1

                if val is None:
                    if propNullable:
                        my_logger.debug('Property {} is nullable and is null, so Nullable checking passes'.format(sub_item))
                    else:
                        propNullablePass = False
                
                if isinstance(prop.Type, str) and 'Edm.' in prop.Type:
                    try:
                        paramPass = prop.Exists and prop.validate_basic(val, prop.Type)
                    except ValueError as e:
                        my_logger.error('{}: {}'.format(prop.Name, e))  # log this
                        paramPass = False
                elif isinstance(prop.Type, RedfishType):
                    try:
                        paramPass = prop.Type.validate(val, prop.added_pattern)
                    except ValueError as e:
                        my_logger.error('{}: {}'.format(prop.Name, e))  # log this
                        paramPass = False

                if propRealType == 'entity':
                    paramPass = validateEntity(service, prop, val)

            # Render our result
            my_type = prop.Type.fulltype

            if all([paramPass, propMandatoryPass, propNullablePass, excerptPass, permissionValid]):
                my_logger.verbose1("\tSuccess")
                counts['pass'] += 1
                result_str = 'PASS'
                if deprecatedPassOrSinceVersion is False:
                    result_str = 'Deprecated'
                if isinstance(deprecatedPassOrSinceVersion, str):
                    result_str = 'Deprecated/{}'.format(deprecatedPassOrSinceVersion)
                if not nullValid:
                    counts['invalidPropertyValue'] += 1
                    result_str = 'WARN'
            else:
                my_logger.verbose1("\tFAIL")
                counts['err.' + str(my_type)] += 1
                result_str = 'FAIL'
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
                elif not excerptPass:
                    counts['errorExcerpt'] += 1
                    result_str = 'errorExcerpt'

            resultList[sub_item] = (
                    displayValue(val, sub_item if prop.IsAutoExpanded else None), displayType(prop.Type),
                    'Yes' if prop.Exists else 'No', result_str)

        return resultList, counts