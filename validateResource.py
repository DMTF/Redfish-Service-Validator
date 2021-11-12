# Copyright Notice:
# Copyright 2016-2021 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import logging
from collections import Counter, OrderedDict
from io import StringIO

import common.traverse as traverse
import common.catalog as catalog
from validateRedfish import checkPropertyConformance, displayValue
from common.helper import getNamespace, getType, createContext, checkPayloadConformance, navigateJsonFragment, create_entry

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
    my_logger.log(logging.INFO-1,"\n*** %s, %s", uriName, URI)
    my_logger.info("\n*** %s", URI)
    my_logger.log(logging.INFO-1,"\n*** {}, {}".format(expectedType, expectedJson is not None))
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
            success, me['payload'], me['rcode'], me['rtime'] = ret
        else:
            success, me['payload'], me['rcode'], me['rtime'] = True, expectedJson, -1, 0
        
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
                my_type = my_type.parent_type[0] if my_type.IsPropertyType else my_type.fulltype
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
                counts['failRedfishUri'] += 1
                my_logger.error('URI {} does not match the following required URIs in Schema of {}'.format(odata_id, redfish_obj.Type))

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

            if '@Redfish.Copyright' in propMessages:
                modified_entry = propMessages['@Redfish.Copyright']
                modified_entry.success = 'FAIL'
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


def validateURITree(service, URI, uriName, expectedType=None, expectedJson=None, parent=None, allLinks=None):
    # from given URI, validate it, then follow its links like nodes
    #   Other than expecting a valid URI, on success (real URI) expects valid links
    #   valid links come from getAllLinks, includes info such as expected values, etc
    #   as long as it is able to pass that info, should not crash
    # If this is our first called URI
    top = allLinks is None
    if top: allLinks = set()
    allLinks.add(URI)

    def executeLink(link, parent=None):
        linkURI = link.Value.get('@odata.id') if link.Value else ''
        linkName = link.Name

        if link.Type is not None and link.Type.AutoExpand:
            returnVal = validateURITree(service, linkURI, uriName + ' -> ' + linkName, link.Type, link.Value, parent, allLinks)
        else:
            returnVal = validateURITree(service, linkURI, uriName + ' -> ' + linkName, parent=parent, allLinks=allLinks)
        my_logger.log(logging.INFO-1,'%s, %s', linkName, returnVal[1])
        return returnVal

    refLinks = []

    validateSuccess, counts, results, links, thisobj = validateSingleURI(service, URI, uriName, expectedType, expectedJson, parent)

    if validateSuccess:
        # Bring Registries to Front if possible
        if 'Registries.Registries' in [x.Type.fulltype for x in links]:
            logging.info('Move Registries to front for validation')
        log_entries = [x for x in links if 'LogEntry' in x.Type.fulltype]
        links = [x for x in links if 'LogEntry' not in x.Type.fulltype] + log_entries[:15] # Pare down logentries
        for link in sorted(links, key=lambda x: (x.Type.fulltype != 'Registries.Registries')):
            link_destination = link.Value.get('@odata.id')
            if link.Type.Excerpt:
                continue
            if any(x in str(link.parent.Type) or x in link.Name for x in ['RelatedItem', 'Redundancy', 'Links', 'OriginOfCondition']):
                refLinks.append((link, thisobj))
                continue
            if link_destination in allLinks:
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
                if newLink in allLinks:
                    counts['repeat'] += 1
                    continue

            success, linkCounts, linkResults, xlinks, xobj = executeLink(link, thisobj)
            refLinks.extend(xlinks)
            if not success:
                counts['unvalidated'] += 1
            results.update(linkResults)

    if top:
        for link in refLinks:
            link, refparent = link
            link_destination = link.Value.get('@odata.id')
            if link.Type.Excerpt:
                continue
            elif link_destination is None:
                errmsg = 'Referenced URI for NavigationProperty is missing {} {}'.format(link_destination, uriName)
                my_logger.error(errmsg)
                results[uriName]['errors'] += '\n' + errmsg
                counts['errorMissingRefOdata'] += 1
                continue
            elif link_destination.split('#')[0].endswith('/'):
                # (elegantly) add warn message to resource html
                warnmsg = 'Referenced URI acquired ends in slash: {}'.format(link_destination)
                my_logger.warning(warnmsg)
                results[uriName]['warns'] += '\n' + warnmsg
                counts['warnTrailingSlashRefLink'] += 1
                newLink = ''.join(link_destination.split('/')[:-1])
                if newLink in allLinks:
                    counts['repeat'] += 1
                    continue

            if link_destination not in allLinks:
                my_logger.log(logging.INFO-1,'{}, {}'.format(link.Name, link))
                counts['reflink'] += 1
            else:
                continue


            my_link_type = link.Type.parent_type[0] if link.Type.IsPropertyType else link.Type.fulltype
            success, my_data, _, __ = service.callResourceURI(link_destination)
            # Using None instead of refparent simply because the parent is not where the link comes from
            returnVal = validateURITree(service, link_destination, uriName + ' -> ' + link.Name,
                    my_link_type, my_data, None, allLinks)
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

    return validateSuccess, counts, results, refLinks, thisobj
