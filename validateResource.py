# Copyright Notice:
# Copyright 2016-2021 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

from types import SimpleNamespace
from common.redfish import getNamespaceUnversioned, getType
import logging
from collections import Counter, OrderedDict
from io import StringIO

import traverseService
import common.catalog as catalog
from common.redfish import checkPayloadConformance
from validateSpecial import loadAttributeRegDict, checkPropertyConformance, displayValue

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)
class WarnFilter(logging.Filter):
       def filter(self, rec):
           return rec.levelno == logging.WARN

LOG_ENTRY = ('name', 'value', 'type', 'exists', 'result')

def create_entry(name, value, type, exists, result):
    return SimpleNamespace(**{
        "name": name,
        "value": value,
        "type": type,
        "exists": 'Exists' if True else 'DNE',
        "result": result
    })

fmt = logging.Formatter('%(levelname)s - %(message)s')

my_catalog = catalog.SchemaCatalog('./SchemaFiles/metadata/')

def create_logging_capture(this_logger):
    errorMessages = StringIO()
    warnMessages = StringIO()

    errh = logging.StreamHandler(errorMessages)
    errh.setLevel(logging.ERROR)
    errh.setFormatter(fmt)

    warnh = logging.StreamHandler(warnMessages)
    warnh.setLevel(logging.WARN)
    warnh.addFilter(WarnFilter())
    warnh.setFormatter(fmt)

    this_logger.addHandler(errh)
    this_logger.addHandler(warnh)

    return errh, warnh


def get_my_capture(this_logger, handler):
    this_logger.removeHandler(handler)
    strings = handler.stream.getvalue()
    handler.stream.close()
    return strings


def validateSingleURI(URI, uriName='', expectedType=None, expectedJson=None, parent=None):
    # rs-assertion: 9.4.1
    # Initial startup here
    my_logger.log(logging.INFO-1,"\n*** %s, %s", uriName, URI)
    my_logger.info("\n*** %s", URI)
    my_logger.log(logging.INFO-1,"\n*** {}, {}".format(expectedType, expectedJson is not None))
    counts = Counter()
    results, messages = OrderedDict(), OrderedDict()

    ehandler, whandler = create_logging_capture(my_logger)

    me = {'uri': URI, 'success': False, 'counts': counts, 'messages': messages,
            'errors': '', 'warns': '', 'rtime': '', 'rcode': 0,
            'fulltype': '', 'context': '', 'payload': {}}
    results[uriName] = me

    # check for @odata mandatory stuff
    # check for version numbering problems # check id if its the same as URI
    # check @odata.context instead of local.  Realize that @odata is NOT a "property"

    # Attempt to get a list of properties
    if URI is None:
        if parent is not None:
            parentURI = parent.uri
        else:
            parentURI = 'MissingParent'
        URI = parentURI + '/Missing URI Link'
        my_logger.warning('Tool appears to be missing vital URI information, replacing URI w/: {}'.format(URI))
    # Generate dictionary of property info
    try:
        if expectedJson is None:
            success, jsondata, status, rtime = traverseService.callResourceURI(URI)
            me['payload'] = jsondata
            me['rtime'] = rtime
            me['rcode'] = status
        else:
            me['payload'] = expectedJson
            me['rtime'] = 0
            me['rcode'] = -1

        # verify basic odata strings
        if results[uriName]['payload'] is not None:
            successPayload, odataMessages = checkPayloadConformance(me['payload'], URI)
            for m in odataMessages:
                msg = create_entry(*m)
                messages[msg.name] = msg

        type_string = str(expectedType) if expectedType else me['payload'].get('@odata.type')
        me['fulltype'] = type_string
        redfish_schema = my_catalog.getSchemaDocByClass(type_string)
        redfish_type = redfish_schema.getTypeInSchema(type_string)
        redfish_obj = redfish_type.createObject().populate(me['payload'], parent)

        if not redfish_obj:
            counts['problemResource'] += 1
            me['warns'], me['errors'] = get_my_capture(my_logger, whandler), get_my_capture(my_logger, ehandler)
            return False, counts, results, None, None
    except traverseService.AuthenticationError as e:
        raise  # re-raise exception
    except Exception as e:
        my_logger.error('Exception caught while creating ResourceObj', exc_info=1)
        my_logger.error('Unable to gather property info for URI {}: {}'.format(URI, repr(e)))
        counts['exceptionResource'] += 1
        me['warns'], me['errors'] = get_my_capture(my_logger, whandler), get_my_capture(my_logger, ehandler)
        return False, counts, results, None, None

    counts['passGet'] += 1

    # verify odata_id properly resolves to its parent if holding fragment
    odata_id = me['payload'].get('@odata.id', '')
    if '#' in odata_id:
        if parent is not None:
            payload_resolve = traverseService.navigateJsonFragment(parent.jsondata, URI)
            if payload_resolve is None:
                my_logger.error('@odata.id of ReferenceableMember does not contain a valid JSON pointer for this payload: {}'.format(odata_id))
                counts['badOdataIdResolution'] += 1
            elif payload_resolve != me['payload']:
                my_logger.error('@odata.id of ReferenceableMember does not point to the correct object: {}'.format(odata_id))
                counts['badOdataIdResolution'] += 1
        else:
            my_logger.warn('No parent found with which to test @odata.id of ReferenceableMember')

    if not successPayload:
        counts['failPayloadError'] += 1
        my_logger.error(str(URI) + ': payload error, @odata property non-conformant',)

    # if URI was sampled, get the notation text from traverseService.uri_sample_map
    sample_string = traverseService.uri_sample_map.get(URI)
    sample_string = sample_string + ', ' if sample_string is not None else ''

    results[uriName]['uri'] = (str(URI))
    results[uriName]['samplemapped'] = (str(sample_string))
    # results[uriName]['rtime'] = propResourceObj.rtime
    # results[uriName]['rcode'] = propResourceObj.status
    # results[uriName]['payload'] = propResourceObj.jsondata
    # results[uriName]['context'] = propResourceObj.context
    # results[uriName]['origin'] = propResourceObj.schemaObj.origin
    # results[uriName]['fulltype'] = propResourceObj.typename
    results[uriName]['success'] = True

    my_logger.info("\t Type (%s), GET SUCCESS (time: %s)", me['fulltype'], me['rtime'])

    # If this is an AttributeRegistry, load it for later use
    if isinstance(me['payload'], dict):
        odata_type = me['payload'].get('@odata.type')
        if odata_type is not None:
            namespace = getNamespaceUnversioned(odata_type)
            type_name = getType(odata_type)
            if namespace == 'AttributeRegistry' and type_name == 'AttributeRegistry':
                loadAttributeRegDict(odata_type, me['payload'])
    
    for prop_name, prop in redfish_obj.properties.items():
        assert isinstance(prop, catalog.RedfishProperty)
        try:
            if not prop.IsValid and not prop.Exists:
                continue
            propMessages, propCounts = checkPropertyConformance(redfish_obj, prop_name, prop)

            propMessages = {x:create_entry(x, *y) for x,y in propMessages.items()}

            if '@Redfish.Copyright' in propMessages and 'MessageRegistry' not in redfish_obj.type.fulltype:
                modified_entry = list(propMessages['@Redfish.Copyright'])
                modified_entry[-1] = 'FAIL'
                propMessages['@Redfish.Copyright'] = create_entry(*modified_entry)
                my_logger.error('@Redfish.Copyright is only allowed for mockups, and should not be allowed in official implementations')
            # if prop.payloadName != prop.propChild:
            #     propCounts['invalidName'] += 1
            #     for propMsg in propMessages:
            #         modified_entry = list(propMessages[propMsg])
            #         modified_entry[-1] = 'Invalid'
            #         propMessages[propMsg] = tuple(modified_entry)
            # if not prop.valid:
            #     my_logger.error('Verifying property that does not belong to this version: {}'.format(prop.name))
            #     for propMsg in propMessages:
            #         propCounts['invalidEntry'] += 1
            #         modified_entry = list(propMessages[propMsg])
            #         modified_entry[-1] = 'Invalid'
            #         propMessages[propMsg] = tuple(modified_entry)

            messages.update(propMessages)
            counts.update(propCounts)
        except traverseService.AuthenticationError as e:
            raise  # re-raise exception
        except Exception as ex:
            my_logger.error('Exception caught while validating single URI', exc_info=1)
            my_logger.error('{}: Could not finish check on this property ({})'.format(prop_name, str(ex)))
            counts['exceptionPropCheck'] += 1


    SchemaFullType, jsonData = me['fulltype'], me['payload']
    SchemaNamespace, SchemaType = traverseService.getNamespace(SchemaFullType), traverseService.getType(SchemaFullType)

    # List all items checked and unchecked
    # current logic does not check inside complex types
    fmt = '%-30s%30s'
    my_logger.log(logging.INFO-1,'%s, %s, %s', uriName, SchemaNamespace, SchemaType)

    for key in jsonData:
        item = jsonData[key]
        my_logger.log(logging.INFO-1,fmt % (key, messages[key].result if key in messages else 'Exists, no schema check'))

    # allowAdditional = redfish_obj.type.additional
    # for key in [k for k in jsonData if k not in messages and k not in propResourceObj.unknownProperties] + propResourceObj.unknownProperties:
    #     # note: extra messages for "unchecked" properties
    #     if not allowAdditional:
    #         my_logger.error('{} not defined in schema {} (check version, spelling and casing)'
    #                         .format(key, SchemaNamespace))
    #         counts['failAdditional'] += 1
    #         messages[key] = (displayValue(item), '-',
    #                          '-',
    #                          'FAIL')
    #     else:
    #         my_logger.warn('{} not defined in schema {} (check version, spelling and casing)'
    #                         .format(key, SchemaNamespace))
    #         counts['unverifiedAdditional'] += 1
    #         messages[key] = (displayValue(item), '-',
    #                          '-',
    #                          'Additional')

    for key in messages:
        if key not in jsonData:
            my_logger.log(logging.INFO-1,fmt % (key, messages[key].result))

    results[uriName]['warns'], results[uriName]['errors'] = get_my_capture(my_logger, whandler), get_my_capture(my_logger, ehandler)

    pass_val = len(results[uriName]['errors']) == 0
    for key in counts:
        if any(x in key for x in ['problem', 'fail', 'bad', 'exception']):
            pass_val = False
            break
    my_logger.info("\t {}".format('PASS' if pass_val else' FAIL...'))

    my_logger.log(logging.INFO-1,'%s, %s', SchemaFullType, counts)

    # Get all links available

    my_logger.debug(redfish_obj.getLinks())

    return True, counts, results, redfish_obj.getLinks(), redfish_obj


def validateURITree(URI, uriName, expectedType=None, expectedJson=None, parent=None, allLinks=None):
    # from given URI, validate it, then follow its links like nodes
    #   Other than expecting a valid URI, on success (real URI) expects valid links
    #   valid links come from getAllLinks, includes info such as expected values, etc
    #   as long as it is able to pass that info, should not crash
    # info: destinations, individual expectations of each?
    # error: on fail
    # warn: reference only?
    # debug:
    traverseLogger = traverseService.getLogger()

    # If this is our first called URI
    top = allLinks is None
    if top: allLinks = set()
    allLinks.add(URI)

    refLinks = OrderedDict()

    validateSuccess, counts, results, links, thisobj = validateSingleURI(URI, uriName, expectedType, expectedJson, parent)
    if validateSuccess:
        # Bring Registries to Front if possible
        if 'Registries.Registries' in [x.Type.fulltype for x in links]:
            logging.info('Move Registries to front for validation')
        for link in sorted(links, key=lambda x: x.Type.fulltype != 'Registries.Registries'):
            link_destination = link.Value.get('@odata.id')
            if link.Type.Excerpt:
                continue
            if any(x in link.Name for x in ['RelatedItem', 'Redundancy', 'Links', 'OriginOfCondition']):
                refLinks[link.Name] = (link, thisobj)
                continue
            if link_destination in allLinks:
                counts['repeat'] += 1
                continue
            elif link_destination is None:
                errmsg = 'URI for NavigationProperty is missing {}'.format(uriName)
                traverseLogger.error(errmsg)
                results[uriName]['errors'] += '\n' + errmsg
                counts['errorMissingOdata'] += 1
                continue
            elif link_destination.split('#')[0].endswith('/'):
                # (elegantly) add warn message to resource html
                warnmsg = 'URI acquired ends in slash: {}'.format(link_destination)
                traverseLogger.warning(warnmsg)
                results[uriName]['warns'] += '\n' + warnmsg
                counts['warnTrailingSlashLink'] += 1
                newLink = ''.join(link_destination.split('/')[:-1])
                if newLink in allLinks:
                    counts['repeat'] += 1
                    continue

            linkURI = link.Value.get('@odata.id') if link.Value else ''
            linkName = link.Name

            if link.Type is not None and link.Type.AutoExpand:
                returnVal = validateURITree(linkURI, uriName + ' -> ' + linkName, link.Type, link.Value, thisobj, allLinks)
            else:
                returnVal = validateURITree(linkURI, uriName + ' -> ' + linkName, parent=thisobj, allLinks=allLinks)
            traverseLogger.log(logging.INFO-1,'%s, %s', linkName, returnVal[1])

            success, _, linkResults, new_refs, _ = returnVal

            refLinks.update(new_refs)
            results.update(linkResults)
            if not success: counts['unvalidated'] += 1

    if top:
        for linkName in refLinks:
            link, refparent = refLinks[linkName]
            link_destination = link.Value.get('@odata.id')
            if link.Type.Excerpt:
                continue
            elif link_destination is None:
                errmsg = 'Referenced URI for NavigationProperty is missing {}'.format(uriName)
                traverseLogger.error(errmsg)
                results[uriName]['errors'] += '\n' + errmsg
                counts['errorMissingRefOdata'] += 1
                continue
            elif link_destination.split('#')[0].endswith('/'):
                # (elegantly) add warn message to resource html
                warnmsg = 'Referenced URI acquired ends in slash: {}'.format(link_destination)
                traverseLogger.warning(warnmsg)
                results[uriName]['warns'] += '\n' + warnmsg
                counts['warnTrailingSlashRefLink'] += 1
                newLink = ''.join(link_destination.split('/')[:-1])
                if newLink in allLinks:
                    counts['repeat'] += 1
                    continue

            if link_destination not in allLinks:
                traverseLogger.log(logging.INFO-1,'{}, {}'.format(linkName, link))
                counts['reflink'] += 1
            else:
                continue

            linkURI = link.Value.get('@odata.id') if link.Value else ''
            linkName = link.Name

            if link.Type is not None and link.Type.AutoExpand:
                returnVal = validateURITree(linkURI, uriName + ' -> ' + linkName, link.Type, link.Value, thisobj, allLinks)
            else:
                returnVal = validateURITree(linkURI, uriName + ' -> ' + linkName, parent=thisobj, allLinks=allLinks)
            traverseLogger.log(logging.INFO-1,'%s, %s', linkName, returnVal[1])

            success, _, linkResults, new_refs, _ = returnVal

            results.update(linkResults)
            if not success:
                counts['unvalidatedRef'] += 1
                if 'OriginOfCondition' in link.Name:
                    traverseLogger.info('Link was unsuccessful, but non mandatory')
                    pass
                else:
                    results.update(linkResults)
            else:
                results.update(linkResults)

    return validateSuccess, counts, results, refLinks, thisobj
