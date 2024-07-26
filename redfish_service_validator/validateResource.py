# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import logging
from collections import Counter, OrderedDict
from io import StringIO

import redfish_service_validator.traverse as traverse
import redfish_service_validator.catalog as catalog
from redfish_service_validator.validateRedfish import checkPropertyConformance, displayValue
from redfish_service_validator.helper import getNamespace, getType, createContext, checkPayloadConformance, navigateJsonFragment, create_entry

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)
class WarnFilter(logging.Filter):
       def filter(self, rec):
           return rec.levelno == logging.WARN

fmt = logging.Formatter('%(levelname)s - %(message)s')

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


def validateSingleURI(service, URI, uriName='', expectedType=None, expectedJson=None, parent=None):
    # rs-assertion: 9.4.1
    # Initial startup here
    my_logger.verbose1("\n*** %s, %s", uriName, URI)
    my_logger.info("\n*** %s", URI)
    my_logger.verbose1("\n*** {}, {}".format(expectedType, expectedJson is not None))
    counts = Counter()
    results, messages = OrderedDict(), OrderedDict()

    ehandler, whandler = create_logging_capture(my_logger)

    me = {'uri': URI, 'success': False, 'counts': counts, 'messages': messages,
            'errors': '', 'warns': '', 'rtime': '', 'rcode': 0,
            'fulltype': '', 'context': '...', 'payload': {}}
    results[uriName] = me

    # check for @odata mandatory stuff
    # check for version numbering problems # check id if its the same as URI
    # check @odata.context instead of local.  Realize that @odata is NOT a "property"

    # Attempt to get a list of properties
    if URI is None:
        URI = '/Missing URI Link'
        if parent: URI = str(parent.payload.get('@odata.id')) + URI
        my_logger.warning('Tool appears to be missing vital URI information, replacing URI w/: {}'.format(URI))
    # Generate dictionary of property info
    try:
        if expectedJson is None:
            ret = service.callResourceURI(URI)
            success, me['payload'], response, me['rtime'] = ret
            me['rcode'] = response.status if response else -1
        else:
            success, me['payload'], me['rcode'], me['rtime'] = True, expectedJson, -1, 0
            response = None
        
        if not success:
            my_logger.error('URI did not return resource {}'.format(URI))
            counts['failGet'] += 1
            # Failure to connect to the scheme is an important error that must be included in FAILS
            counts['fails'] += 1
            me['warns'], me['errors'] = get_my_capture(my_logger, whandler), get_my_capture(my_logger, ehandler)
            return False, counts, results, None, None

        # verify basic odata strings
        if results[uriName]['payload'] is not None:
            successPayload, odataMessages = checkPayloadConformance(me['payload'], URI)
            for m in odataMessages:
                msg = create_entry(m, *odataMessages[m])
                messages[msg.name] = msg

        my_type = me['payload'].get('@odata.type', expectedType)
        me['fulltype'] = str(my_type)
        if my_type is None:
            redfish_obj = None
        else:
            # TODO: don't have the distinction between Property Type and a Normal Type
            if isinstance(my_type, catalog.RedfishType):
                my_type = my_type.fulltype
            redfish_schema = service.catalog.getSchemaDocByClass(my_type)
            redfish_type = redfish_schema.getTypeInSchemaDoc(my_type)

            redfish_obj = catalog.RedfishObject(redfish_type, 'Object', parent=parent).populate(me['payload']) if redfish_type else None

        if redfish_obj:
            me['fulltype'] = redfish_obj.Type.fulltype
        else:
            counts['problemResource'] += 1
            me['warns'], me['errors'] = get_my_capture(my_logger, whandler), get_my_capture(my_logger, ehandler)
            return False, counts, results, None, None
    except traverse.AuthenticationError as e:
        raise  # re-raise exception
    except Exception as e:
        my_logger.verbose1('Exception caught while creating ResourceObj', exc_info=1)
        my_logger.error('Unable to gather property info from schema for URI {}; check its schema definition for schema errors: {}'.format(URI, repr(e)))
        counts['exceptionResource'] += 1
        # ExceptionResource is an important error that must be included in FAILS
        counts['fails'] += 1
        me['warns'], me['errors'] = get_my_capture(my_logger, whandler), get_my_capture(my_logger, ehandler)
        return False, counts, results, None, None

    counts['passGet'] += 1

    # verify odata_id properly resolves to its parent if holding fragment
    odata_id = me['payload'].get('@odata.id')
    if odata_id is None:
        # Do not error for namespace.type MessageRegistry.MessageRegistry, etc 
        if any(['{}.{}'.format(x, x) in redfish_obj.Type.getTypeTree() for x in ['MessageRegistry', 'AttributeRegistry', 'PrivilegeRegistry']]):
            my_logger.debug('No @odata.id was found in this resource, but not needed')
        else:
            my_logger.error('No @odata.id was found in this resource')
            messages['@odata.id'] = create_entry('@odata.id', '-', '-', 'DNE', 'FAIL')
            counts['errorMissingOdataId'] += 1

    if odata_id is not None and '#' in odata_id:
        if parent is not None:
            payload_resolve = navigateJsonFragment(parent.payload, URI)
            if parent.payload.get('@odata.id') not in URI:
                my_logger.info('@odata.id of ReferenceableMember was referenced elsewhere...: {}'.format(odata_id))
            elif payload_resolve is None:
                my_logger.error('@odata.id of ReferenceableMember does not contain a valid JSON pointer for this payload: {}'.format(odata_id))
                counts['badOdataIdResolution'] += 1
            elif payload_resolve != me['payload']:
                my_logger.error('@odata.id of ReferenceableMember does not point to the correct object: {}'.format(odata_id))
                counts['badOdataIdResolution'] += 1
            _, end_fragment = tuple(odata_id.split('#', 1))
            my_member_id = me['payload'].get('MemberId')
            if not my_member_id:
                my_logger.error('ReferenceableMember MemberId does not exist...')
                counts['badMemberId'] += 1
            elif my_member_id not in end_fragment.split('/'):
                my_logger.error('ReferenceableMember MemberId does not match id: {} {}'.format(my_member_id, odata_id))
                counts['badMemberId'] += 1
        else:
            my_logger.warning('No parent found with which to test @odata.id of ReferenceableMember')
    
    if service.config['uricheck']:
        my_uris = redfish_obj.Type.getUris()
        if odata_id is not None and redfish_obj.Populated and len(my_uris) > 0:
            if redfish_obj.HasValidUri:
                counts['passRedfishUri'] += 1
                if not redfish_obj.HasValidUriStrict and redfish_obj.payload.get('Id') is not None:
                    counts['failRedfishUriStrict'] += 1
                    messages['@odata.id'].result = 'FAIL'
                    my_logger.error('The Id property does not match the last segment of the URI {}'.format(odata_id))
            else:
                if '/Oem/' in odata_id:
                    counts['warnRedfishUri'] += 1
                    messages['@odata.id'].result = 'WARN'
                    my_logger.warning('URI {} does not match the following required URIs in Schema of {}'.format(odata_id, redfish_obj.Type))
                else:
                    counts['failRedfishUri'] += 1
                    messages['@odata.id'].result = 'FAIL'
                    my_logger.error('URI {} does not match the following required URIs in Schema of {}'.format(odata_id, redfish_obj.Type))

    if response and response.getheader('Allow'):
        allowed_responses = [x.strip().upper() for x in response.getheader('Allow').split(',')]
        if not redfish_obj.Type.CanInsert and 'POST' in allowed_responses:
            my_logger.error('Allow header should NOT contain POST for {}'.format(redfish_obj.Type))
            counts['failAllowHeader'] += 1
        if not redfish_obj.Type.CanDelete and 'DELETE' in allowed_responses:
            my_logger.error('Allow header should NOT contain DELETE for {}'.format(redfish_obj.Type))
            counts['failAllowHeader'] += 1
        if not redfish_obj.Type.CanUpdate and any([x in allowed_responses for x in ['PATCH', 'PUT']]):
            my_logger.warning('Allow header should NOT contain PATCH or PUT for {}'.format(redfish_obj.Type))
            counts['warnAllowHeader'] += 1

    if response and response.getheader('x-Redfish-Mockup'):
        my_logger.warning('Response payload loaded from mockup, not the service under test')
        counts['warnMockupUsed'] += 1

    if not successPayload:
        counts['failPayloadError'] += 1
        my_logger.error(str(URI) + ': payload error, @odata property non-conformant',)

    # if URI was sampled, get the notation text from traverseService.uri_sample_map
    results[uriName]['uri'] = (str(URI))
    results[uriName]['context'] = createContext(me['fulltype'])
    results[uriName]['origin'] = redfish_obj.Type.owner.parent_doc.name
    results[uriName]['success'] = True

    my_logger.info("\t Type (%s), GET SUCCESS (time: %s)", me['fulltype'], me['rtime'])
    
    for prop_name, prop in redfish_obj.properties.items():
        try:
            if not prop.HasSchema and not prop.Exists:
                counts['skipNoSchema'] += 1
                continue
            elif not prop.HasSchema:
                my_logger.error('No Schema for property {}'.format(prop.Name))
                counts['errorNoSchema'] += 1
                continue
            propMessages, propCounts = checkPropertyConformance(service, prop_name, prop)

            propMessages = {x:create_entry(x, *y) if isinstance(y, tuple) else y for x,y in propMessages.items()}

            if 'MessageRegistry.MessageRegistry' not in redfish_obj.Type.getTypeTree():
                if '@Redfish.Copyright' in propMessages:
                    modified_entry = propMessages['@Redfish.Copyright']
                    modified_entry.result = 'FAIL'
                    my_logger.error('@Redfish.Copyright is only allowed for mockups, and should not be allowed in official implementations')

            messages.update(propMessages)
            counts.update(propCounts)
        except traverse.AuthenticationError as e:
            raise  # re-raise exception
        except Exception as ex:
            my_logger.verbose1('Exception caught while validating single URI', exc_info=1)
            my_logger.error('{}: Could not finish check on this property ({})'.format(prop_name, str(ex)))
            messages[prop_name] = create_entry(prop_name, '', '', '...', 'exception')
            counts['exceptionPropCheck'] += 1

    SchemaFullType, jsonData = me['fulltype'], me['payload']
    SchemaNamespace, SchemaType = getNamespace(SchemaFullType), getType(SchemaFullType)

    # List all items checked and unchecked
    # current logic does not check inside complex types
    fmt = '%-30s%30s'
    my_logger.verbose1('%s, %s, %s', uriName, SchemaNamespace, SchemaType)

    for key in jsonData:
        my_logger.verbose1(fmt % (key, messages[key].result if key in messages else 'Exists, no schema check'))

    allowAdditional = redfish_obj.Type.HasAdditional
    for key in [k for k in jsonData if k not in messages and k not in redfish_obj.properties and '@' not in k]:
        # note: extra messages for "unchecked" properties
        item = jsonData.get(key)
        if not allowAdditional:
            my_logger.error('{} not defined in schema {} (check version, spelling and casing)'.format(key, SchemaNamespace))
            counts['failAdditional'] += 1
            messages[key] = create_entry(key, displayValue(item), '-', '-', 'FAIL')
        else:
            my_logger.warning('{} not defined in schema {} (check version, spelling and casing)'.format(key, SchemaNamespace))
            counts['unverifiedAdditional'] += 1
            messages[key] = create_entry(key, displayValue(item), '-', '-', 'Additional')

        fuzz = catalog.get_fuzzy_property(key, redfish_obj.properties)
        if fuzz != key and fuzz in redfish_obj.properties:
            messages[fuzz] = create_entry(fuzz, '-', '-', '-', 'INVALID')
            my_logger.error('Attempting {} (from {})?'.format(fuzz, key))
            my_new_obj = redfish_obj.properties[fuzz].populate(item)
            new_msgs, new_counts = checkPropertyConformance(service, key, my_new_obj)
            new_msgs = {x:create_entry(x, *y) for x,y in new_msgs.items()}
            messages.update(new_msgs)
            counts.update(new_counts)
            counts['invalidNamedProperty'] += 1

    for key in messages:
        if key not in jsonData:
            my_logger.verbose1(fmt % (key, messages[key].result))

    results[uriName]['warns'], results[uriName]['errors'] = get_my_capture(my_logger, whandler), get_my_capture(my_logger, ehandler)

    pass_val = len(results[uriName]['errors']) == 0
    for key in counts:
        if any(x in key for x in ['problem', 'fail', 'bad', 'exception']):
            pass_val = False
            break
    my_logger.info("\t {}".format('PASS' if pass_val else ' FAIL...'))

    my_logger.verbose1('%s, %s', SchemaFullType, counts)

    # Get all links available

    collection_limit = service.config['collectionlimit']

    # Count of occurrences of fail, warn, invalid and deprecated in result of tests to FAILS / WARNINGS
    for value in messages.values():
        if "FAIL" in value.result:
            counts['fails'] += 1
        if "WARN" in value.result or "INVALID" in value.result or "Deprecated" in value.result:
            counts['warnings'] += 1
    
    # Additional analysis of whether failMandatoryExist occurred in the scheme and adding the number of failMandatoryExist to FAILS
    if 'failMandatoryExist' in counts.keys():
        counts['fails'] += counts['failMandatoryExist']

    return True, counts, results, redfish_obj.getLinks(collection_limit), redfish_obj


def validateURITree(service, URI, uriName, expectedType=None, expectedJson=None, parent=None, all_links_traversed=None, inAnnotation=False):
    # from given URI, validate it, then follow its links like nodes
    #   Other than expecting a valid URI, on success (real URI) expects valid links
    #   valid links come from getAllLinks, includes info such as expected values, etc
    #   as long as it is able to pass that info, should not crash
    # If this is our first called URI
    top_of_tree = all_links_traversed is None
    if top_of_tree:
        all_links_traversed = set()
    all_links_traversed.add(URI)

    # Links that are not direct, usually "Redundancy"
    referenced_links = []

    if inAnnotation and service.config['uricheck']:
        service.catalog.flags['ignore_uri_checks'] = True
    validateSuccess, counts, results, gathered_links, thisobj = validateSingleURI(service, URI, uriName, expectedType, expectedJson, parent)
    if inAnnotation and service.config['uricheck']:
        service.catalog.flags['ignore_uri_checks'] = False

    # If successful and a MessageRegistryFile...
    if validateSuccess and 'MessageRegistryFile.MessageRegistryFile' in thisobj.Type.getTypeTree():
        # thisobj['Location'].Collection[0]['Uri'].Exists
        if 'Location' in thisobj:
            if thisobj['Location'].IsCollection:
                val_list = thisobj['Location'].Value
            else:
                val_list = [thisobj['Location'].Value]
            for sub_obj in val_list:
                if 'Uri' in sub_obj:
                    gathered_links.append(sub_obj)

    # If successful...
    if validateSuccess:
        # Bring Registries to Front if possible

        for link in sorted(gathered_links, key=lambda link: (link.Type.fulltype != 'Registries.Registries')):
            if link is None or link.Value is None:
                my_logger.warning('Link is None, does it exist?')
                continue

            # get Uri or @odata.id
            if not isinstance(link.Value, dict):
                errmsg = '{} is expected to be an object containing @odata.id'.format(link.Name)
                my_logger.error(errmsg)
                results[uriName]['errors'] += '\n' + errmsg
                counts['errorInvalidReferenceObject'] += 1
                continue
            link_destination = link.Value.get('@odata.id', link.Value.get('Uri'))

            if link.IsExcerpt or link.Type.Excerpt:
                continue
            if not service.config['oemcheck']:
                if link_destination and '/Oem/' in link_destination or link and 'Resource.OemObject' in link.Type.getTypeTree():
                    my_logger.info('Oem link skipped: {}'.format(link_destination))
                    counts['skipOemLink'] += 1
                    continue
            if any(x in str(link.parent.Type) or x in link.Name for x in ['RelatedItem', 'Redundancy', 'Links', 'OriginOfCondition']) and not link.IsAutoExpanded:
                referenced_links.append((link, thisobj))
                continue
            if link_destination in all_links_traversed:
                counts['repeat'] += 1
                continue
            elif link_destination is None:
                errmsg = 'URI for NavigationProperty is missing {}'.format(uriName)
                my_logger.error(errmsg)
                results[uriName]['errors'] += '\n' + errmsg
                counts['errorMissingOdata'] += 1
                continue
            elif link_destination.split('#')[0].endswith('/'):
                # (elegantly) add warn message to resource html
                warnmsg = 'URI acquired ends in slash: {}'.format(link_destination)
                my_logger.warning(warnmsg)
                results[uriName]['warns'] += '\n' + warnmsg
                counts['warnTrailingSlashLink'] += 1
                newLink = ''.join(link_destination.split('/')[:-1])
                if newLink in all_links_traversed:
                    counts['repeat'] += 1
                    continue

            if link.Type is not None and link.IsAutoExpanded:
                returnVal = validateURITree(service, link_destination, uriName + ' -> ' + link.Name, link.Type, link.Value, thisobj, all_links_traversed, link.InAnnotation)
            else:
                returnVal = validateURITree(service, link_destination, uriName + ' -> ' + link.Name, parent=parent, all_links_traversed=all_links_traversed, inAnnotation=link.InAnnotation)
            success, linkCounts, linkResults, xlinks, xobj = returnVal

            my_logger.verbose1('%s, %s', link.Name, linkCounts)

            referenced_links.extend(xlinks)
            if not success:
                counts['unvalidated'] += 1
            results.update(linkResults)

    if top_of_tree:
        # TODO: consolidate above code block with this
        for link in referenced_links:
            link, refparent = link
            # get Uri or @odata.id
            if link is None or link.Value is None:
                my_logger.warning('Link is None, does it exist?')
                continue
            link_destination = link.Value.get('@odata.id', link.Value.get('Uri'))
            if link.IsExcerpt or link.Type.Excerpt:
                continue
            elif link_destination is None:
                errmsg = 'Referenced URI for NavigationProperty is missing {} {} {}'.format(link_destination, link.Name, link.parent)
                my_logger.error(errmsg)
                results[uriName]['errors'] += '\n' + errmsg
                counts['errorMissingRefOdata'] += 1
                continue
            elif not isinstance(link_destination, str):
                errmsg = 'URI for NavigationProperty is not a string {} {} {}'.format(link_destination, link.Name, link.parent)
                my_logger.error(errmsg)
                results[uriName]['errors'] += '\n' + errmsg
                counts['errorInvalidReferenceObject'] += 1
                continue
            elif link_destination.split('#')[0].endswith('/'):
                # (elegantly) add warn message to resource html
                warnmsg = 'Referenced URI acquired ends in slash: {}'.format(link_destination)
                my_logger.warning(warnmsg)
                results[uriName]['warns'] += '\n' + warnmsg
                counts['warnTrailingSlashRefLink'] += 1
                newLink = ''.join(link_destination.split('/')[:-1])
                if newLink in all_links_traversed:
                    counts['repeat'] += 1
                    continue

            if link_destination not in all_links_traversed:
                my_logger.verbose1('{}, {}'.format(link.Name, link))
                counts['reflink'] += 1
            else:
                continue

            my_link_type = link.Type.fulltype
            success, my_data, _, _ = service.callResourceURI(link_destination)
            # Using None instead of refparent simply because the parent is not where the link comes from
            returnVal = validateURITree(service, link_destination, uriName + ' -> ' + link.Name, my_link_type, my_data, None, all_links_traversed)
            success, linkCounts, linkResults, xlinks, xobj = returnVal
            # refLinks.update(xlinks)

            if not success:
                counts['unvalidatedRef'] += 1
                if 'OriginOfCondition' in link.Name or 'OriginOfCondition' in link.parent.Name:
                    my_logger.info('Link was unsuccessful, but non mandatory')
                else:
                    results.update(linkResults)
            else:
                results.update(linkResults)

    return validateSuccess, counts, results, referenced_links, thisobj
