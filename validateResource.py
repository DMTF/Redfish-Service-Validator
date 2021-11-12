# Copyright Notice:
# Copyright 2016-2021 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import logging
from collections import Counter, OrderedDict

import common.traverse as traverse
import common.catalog as catalog
from validateRedfish import checkPropertyConformance, displayValue
from common.helper import getNamespace, getType, createContext, checkPayloadConformance, navigateJsonFragment, create_entry, create_logging_capture, get_my_capture

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)

def validateSingleURI(service, URI, uriName='', expectedType=None, expectedJson=None, parent=None):
    # rs-assertion: 9.4.1
    # Initial startup here
    my_logger.log(logging.INFO-1,"\n*** %s, %s", uriName, URI)
    my_logger.info("\n*** %s", URI)
    my_logger.log(logging.INFO-1,"\n*** {}, {}".format(expectedType, expectedJson is not None))

    counts, results, messages = Counter(), OrderedDict(), OrderedDict()

    ehandler, whandler = create_logging_capture(my_logger)

    me = {'uri': URI, 'success': False, 'counts': counts, 'messages': messages,
            'errors': '', 'warns': '', 'rtime': '', 'rcode': 0,
            'fulltype': '', 'context': '...', 'payload': {}}
    results[uriName] = me

    # check for @odata mandatory stuff
    # check for version numbering problems # check id if its the same as URI

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
            me['rcode'] = response.status
        else:
            success, me['payload'], me['rcode'], me['rtime'] = True, expectedJson, -1, 0
            response = None
        
        if not success:
            my_logger.error('URI did not return resource {}'.format(URI))
            counts['failGet'] += 1
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
        my_logger.log(logging.INFO-1, 'Exception caught while creating ResourceObj', exc_info=1)
        my_logger.error('Unable to gather property info for URI {}: {}'.format(URI, repr(e)))
        counts['exceptionResource'] += 1
        me['warns'], me['errors'] = get_my_capture(my_logger, whandler), get_my_capture(my_logger, ehandler)
        return False, counts, results, None, None

    # Completed grabbing and setting up our Resource
    counts['passGet'] += 1

    # verify odata_id properly resolves to its parent if holding fragment
    odata_id = me['payload'].get('@odata.id')
    if odata_id is not None and '#' in odata_id:
        if parent is not None:
            payload_resolve = navigateJsonFragment(parent.payload, URI)
            if parent.payload.get('@odata.id') not in URI:
                my_logger.info('@odata.id of ReferenceableMember was referenced elsewhere...'.format(odata_id))
            elif payload_resolve is None:
                my_logger.error('@odata.id of ReferenceableMember does not contain a valid JSON pointer for this payload: {}'.format(odata_id))
                counts['badOdataIdResolution'] += 1
            elif payload_resolve != me['payload']:
                my_logger.error('@odata.id of ReferenceableMember does not point to the correct object: {}'.format(odata_id))
                counts['badOdataIdResolution'] += 1
        else:
            my_logger.warn('No parent found with which to test @odata.id of ReferenceableMember')
    
    if service.config['uricheck']:
        my_uris = redfish_obj.Type.getUris()
        if odata_id is not None and redfish_obj.Populated and len(my_uris) > 0:
            if redfish_obj.HasValidUri:
                counts['passRedfishUri'] += 1
            else:
                if '/Oem/' in odata_id:
                    counts['warnRedfishUri'] += 1
                    modified_entry = messages['@odata.id']
                    modified_entry.result = 'WARN'
                    my_logger.warning('URI {} does not match the following required URIs in Schema of {}'.format(odata_id, redfish_obj.Type))
                else:
                    counts['failRedfishUri'] += 1
                    modified_entry = messages['@odata.id']
                    modified_entry.result = 'FAIL'
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

    if not successPayload:
        counts['failPayloadError'] += 1
        my_logger.error(str(URI) + ': payload error, @odata property non-conformant',)

    # if URI was sampled, get the notation text from traverseService.uri_sample_map
    results[uriName]['uri'] = (str(URI))
    results[uriName]['context'] = createContext(me['fulltype'])
    results[uriName]['origin'] = redfish_obj.Type.owner.parent_doc.name
    results[uriName]['success'] = True

    my_logger.info("\t Type (%s), GET SUCCESS (time: %s)", me['fulltype'], me['rtime'])
    
    # Iterate through all properties and validate them
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

            # TODO: Cleanup message inconsistencies for html
            propMessages = {x:create_entry(x, *y) if isinstance(y, tuple) else y for x,y in propMessages.items()}

            if not 'MessageRegistry.MessageRegistry' in redfish_obj.Type.getTypeTree():
                if '@Redfish.Copyright' in propMessages:
                    modified_entry = propMessages['@Redfish.Copyright']
                    modified_entry.result = 'FAIL'
                    my_logger.error('@Redfish.Copyright is only allowed for mockups, and should not be allowed in official implementations')

            messages.update(propMessages)
            counts.update(propCounts)
        except traverse.AuthenticationError as e:
            raise  # re-raise exception
        except Exception as ex:
            my_logger.log(logging.INFO-1, 'Exception caught while validating single URI', exc_info=1)
            my_logger.error('{}: Could not finish check on this property ({})'.format(prop_name, str(ex)))
            propMessages[prop_name] = create_entry(prop_name, '', '', prop.Exists, 'exception')
            counts['exceptionPropCheck'] += 1

    SchemaFullType, jsonData = me['fulltype'], me['payload']
    SchemaNamespace, SchemaType = getNamespace(SchemaFullType), getType(SchemaFullType)

    # List all items checked and unchecked
    # current logic does not check inside complex types
    fmt = '%-30s%30s'
    my_logger.log(logging.INFO-1,'%s, %s, %s', uriName, SchemaNamespace, SchemaType)

    for key in jsonData:
        my_logger.log(logging.INFO-1,fmt % (key, messages[key].result if key in messages else 'Exists, no schema check'))

    allowAdditional = redfish_obj.Type.HasAdditional
    for key in [k for k in jsonData if k not in messages and k not in redfish_obj.properties and '@' not in k]:
        # note: extra messages for "unchecked" properties
        item = jsonData.get(key)
        if not allowAdditional:
            my_logger.error('{} not defined in schema {} (check version, spelling and casing)'.format(key, SchemaNamespace))
            counts['failAdditional'] += 1
            messages[key] = create_entry(key, displayValue(item), '-', '-', 'FAIL')
        else:
            my_logger.warn('{} not defined in schema {} (check version, spelling and casing)'.format(key, SchemaNamespace))
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
            my_logger.log(logging.INFO-1,fmt % (key, messages[key].result))

    # Collect our errors and warns, report our pass_val
    results[uriName]['warns'], results[uriName]['errors'] = get_my_capture(my_logger, whandler), get_my_capture(my_logger, ehandler)

    pass_val = len(results[uriName]['errors']) == 0
    for key in counts:
        if any(x in key for x in ['problem', 'fail', 'bad', 'exception']):
            pass_val = False
            break
    my_logger.info("\t {}".format('PASS' if pass_val else' FAIL...'))

    my_logger.log(logging.INFO-1,'%s, %s', SchemaFullType, counts)

    return True, counts, results, redfish_obj.getLinks(), redfish_obj


def validateURITree(service, URI, uriName, expectedType=None, expectedJson=None, parent=None, allLinks=None):
    # from given URI, validate it, then follow its links like nodes
    #   Other than expecting a valid URI, on success (real URI) expects valid links
    #   valid links come from getAllLinks, includes info such as expected values, etc
    #   as long as it is able to pass that info, should not crash
    # If this is our first called URI
    top = allLinks is None
    if top: allLinks = set()
    allLinks.add(URI)

    def executeLink(link, parent=None, my_payload=None):
        success, linkResults, extra_refs = True, {}, []
        if 'Uri' in link.Value:
            link_destination = link.Value.get('Uri')
        else:
            link_destination = link.Value.get('@odata.id')
        if link.Type.Excerpt:
            return success, linkResults, extra_refs
        if link_destination is None:
            errmsg = 'URI for NavigationProperty is missing {}'.format(uriName)
            my_logger.error(errmsg)
            results[uriName]['errors'] += '\n' + errmsg
            counts['errorMissingOdata'] += 1
            return success, linkResults, extra_refs
        if link_destination.split('#')[0].endswith('/'):
            # (elegantly) add warn message to resource html
            warnmsg = 'URI acquired ends in slash: {}'.format(link_destination)
            my_logger.warning(warnmsg)
            results[uriName]['warns'] += '\n' + warnmsg
            counts['warnTrailingSlashLink'] += 1
        if link_destination in allLinks or link_destination.rstrip('/') in allLinks:
            counts['repeat'] += 1
            return success, linkResults, extra_refs

        if link.Type is not None and link.Type.AutoExpand:
            success, linkCounts, linkResults, extra_refs, new_obj = validateURITree(service, link_destination, uriName + ' -> ' + link.Name, link.Type, link.Value, parent, allLinks)
        elif my_payload: # Ref objects...
            my_link_type = link.Type.parent_type[0] if link.Type.IsPropertyType else link.Type.fulltype
            success, linkCounts, linkResults, extra_refs, new_obj = validateURITree(service, link_destination, uriName + ' -> ' + link.Name, my_link_type, my_data, parent, allLinks)
        else:
            success, linkCounts, linkResults, extra_refs, new_obj = validateURITree(service, link_destination, uriName + ' -> ' + link.Name, parent=parent, allLinks=allLinks)
        my_logger.log(logging.INFO-1,'%s, %s', link.Name, linkCounts)
        return success, linkResults, extra_refs

    # refLinks are passed to the very top of the verification chain
    refLinks = []

    # validate this single URI
    validateSuccess, counts, results, links, thisobj = validateSingleURI(service, URI, uriName, expectedType, expectedJson, parent)

    # If successful and a MessageRegistryFile...
    if validateSuccess and 'MessageRegistryFile.MessageRegistryFile' in thisobj.Type.getTypeTree():
        # thisobj['Location'].Collection[0]['Uri'].Exists
        if 'Location' in thisobj:
            for sub_obj in thisobj['Location'].Collection:
                if 'Uri' in sub_obj:
                    registry_uri = sub_obj['Uri'].Value
                    success, my_data, _, rtime = service.callResourceURI(registry_uri)
                    if not success:
                        counts['missingMessageRegistry'] += 1
                        warnmsg = 'MessageRegistry did not return as present on Service...'
                        my_logger.warning(warnmsg)
                        results[uriName]['warns'] += '\n' + warnmsg
                    else:
                        success, linkResults, extra_refs = executeLink(sub_obj, None, my_data)
                        if not success:
                            counts['unvalidated'] += 1
                        refLinks.extend(extra_refs)
                        results.update(linkResults)

    # If successful...
    if validateSuccess:
        # Bring Registries to Front if possible
        pare_down_types = ['LogEntry', 'JsonSchemaFile']
        pare_down = [x for x in links if any([my_type in x.Type.fulltype for my_type in pare_down_types])]
        links = [x for x in links if not any([my_type in x.Type.fulltype for my_type in pare_down_types])] + pare_down[:15] # Pare down logentries

        for link in sorted(links, key=lambda x: (x.Type.fulltype != 'Registries.Registries')):
            if link.Value is None:
                my_logger.warning('Link of name link.Name returning a None, does it exist?')
                continue
            link_destination = link.Value.get('@odata.id')
            if any(x in str(link.parent.Type) or x in link.Name for x in ['RelatedItem', 'Redundancy', 'Links', 'OriginOfCondition']):
                refLinks.append(link)
                continue

            success, linkResults, extra_refs = executeLink(link, thisobj)

            if not success:
                counts['unvalidated'] += 1
            refLinks.extend(extra_refs)
            results.update(linkResults)

    # At the end of our complete validation, check our purely referenced, but not directly linked resources
    if top:
        for link in refLinks:
            link_destination = link.Value.get('@odata.id')

            if link_destination not in allLinks:
                my_logger.log(logging.INFO-1,'{}, {}'.format(link.Name, link))
                counts['reflink'] += 1
            else:
                continue

            success, my_data, _, __ = service.callResourceURI(link_destination)
            success, linkResults, extra_refs = executeLink(link, None, my_data)

            if not success:
                counts['unvalidatedRef'] += 1
                if 'OriginOfCondition' in link.Name or 'OriginOfCondition' in link.parent.Name:
                    my_logger.info('Link was unsuccessful, but non mandatory')
                else:
                    results.update(linkResults)
            else:
                results.update(linkResults)

    return validateSuccess, counts, results, refLinks, thisobj