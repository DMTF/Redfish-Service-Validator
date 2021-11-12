
from collections import Counter, OrderedDict
from common.catalog import REDFISH_ABSENT, MissingSchemaError, ExcerptTypes, get_fuzzy_property

from common.helper import getNamespace, getNamespaceUnversioned, getType, checkPayloadConformance

import logging

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)

def validateExcerpt(prop, val):
    # check Navprop if it's NEUTRAL or CONTAINS
    base, _ = prop.Type.getBaseType()

    if base == 'entity':
        my_excerpt_type, my_excerpt_tags = prop.Type.excerptType, prop.Type.excerptTags
        my_props = prop.Type.createObject().populate(val).properties

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


def validateEntity(service, prop, val, parentURI=""):
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
        success, data, _, delay = service.callResourceURI(uri)
        status = _.status
    else:
        success, data, _, delay = True, val, None, 0
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


def validateComplex(service, sub_obj, prop_name, oem_check=True):
    subMsgs, subCounts = OrderedDict(), Counter()

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
                my_logger.warn('{} not defined in schema Complex {} {} (check version, spelling and casing)'
                                .format(key, prop_name, sub_obj.Type))
                subCounts['unverifiedAdditional.complex'] += 1
                subMsgs[key] = (displayValue(item), '-', '-', 'FAIL')
            
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

        my_actions = [(x.strip('#'), y) for x, y in sub_obj.Value.items() if x != 'Oem']
        if 'Oem' in sub_obj.Value.items():
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
            act_schema = sub_obj.Type.catalog.getSchemaDocByClass(getNamespace(act_name))
            act_class = act_schema.classes.get(getNamespace(act_name))

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
    propRealType, propCollection = propTypeObject.getBaseType()
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
    oem_check = service.config.get('oemcheck', True)
    if 'Oem' in prop_name and not oem_check:
        my_logger.log(logging.INFO-1,'\tOem is skipped')
        counts['skipOem'] += 1
        return {prop_name: ('-', '-', 'Yes' if prop.Exists else 'No', 'OEM')}, counts

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
                if sub_obj.Value is None:
                    if prop.Type.IsNullable:
                        counts['pass'] += 1
                        result_str = 'PASS'
                    else:
                        my_logger.error('{}: Property is null but is not Nullable'.format(prop_name))
                        counts['failNullable'] += 1
                        result_str = 'FAIL'
                    if len(prop.Collection) == 1:
                        resultList['{}.[Value]'.format(prop_name)] = ('[null]', displayType(prop.Type),
                                                                      'Yes' if prop.Exists else 'No', result_str)
                    else:
                        resultList['{}.[Value]#{}'.format(prop_name,n)] = ('[null]', displayType(prop.Type),
                                                                           'Yes' if prop.Exists else 'No', result_str)
                else:
                    subMsgs, subCounts = validateComplex(service, sub_obj, prop_name, oem_check)
                    if len(prop.Collection) == 1:
                        subMsgs = {'{}.{}'.format(prop_name,x):y for x,y in subMsgs.items()}
                    else:
                        subMsgs = {'{}.{}#{}'.format(prop_name,x,n):y for x,y in subMsgs.items()}
                    resultList.update(subMsgs)
                    counts.update(subCounts)
            except Exception as ex:
                my_logger.log(logging.INFO-1, 'Exception caught while validating Complex', exc_info=1)
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
                paramPass = validateEntity(service, prop, val)


        # Render our result
        my_type = prop.Type.fulltype

        if all([paramPass, propMandatoryPass, propNullablePass, excerptPass]):
            my_logger.log(logging.INFO-1,"\tSuccess")
            counts['pass'] += 1
            result_str = 'PASS'
            if not deprecatedPass:
                result_str = 'Deprecated'
            if not nullValid:
                counts['invalidPropertyValue'] += 1
                result_str = 'WARN'
        else:
            my_logger.log(logging.INFO-1,"\tFAIL")
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
                displayValue(val, sub_item if prop.Type.AutoExpand else None), displayType(prop.Type),
                'Yes' if prop.Exists else 'No', result_str)

    return resultList, counts
