# Copyright Notice:
# Copyright 2016-2020 DMTF. All rights reserved.
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

from traverseService import AuthenticationError
from tohtml import renderHtml, writeHtml, count_errors

from metadata import setup_schema_pack

from commonValidator import *

tool_version = '1.3.7'

rsvLogger = rst.getLogger()

VERBO_NUM = 15
logging.addLevelName(VERBO_NUM, "VERBO")


def verboseout(self, message, *args, **kws):
    if self.isEnabledFor(VERBO_NUM):
        self._log(VERBO_NUM, message, args, **kws)


logging.Logger.verboseout = verboseout


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

    results[uriName] = {'uri': URI, 'success': False, 'counts': counts,
            'messages': messages, 'errors': '', 'warns': '', 'rtime': '',
            'context': '', 'fulltype': '', 'rcode': 0, 'payload': {}}

    # check for @odata mandatory stuff
    # check for version numbering problems
    # check id if its the same as URI
    # check @odata.context instead of local.  Realize that @odata is NOT a "property"

    # Attempt to get a list of properties
    if URI is None:
        if parent is not None:
            parentURI = parent.uri
        else:
            parentURI = 'MissingParent'
        URI = parentURI + '/Missing URI Link'
        rsvLogger.warning('Tool appears to be missing vital URI information, replacing URI w/: {}'.format(URI))
    # Generate dictionary of property info
    try:
        if expectedJson is None:
            success, jsondata, status, rtime = rst.callResourceURI(URI)
            results[uriName]['payload'] = jsondata
        else:
            results[uriName]['payload'] = expectedJson

        # verify basic odata strings
        if results[uriName]['payload'] is not None:
            successPayload, odataMessages = rst.ResourceObj.checkPayloadConformance(results[uriName]['payload'], URI)
            messages.update(odataMessages)

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

    # verify odata_id properly resolves to its parent if holding fragment
    odata_id = propResourceObj.jsondata.get('@odata.id', 'void')
    if '#' in odata_id:
        if parent is not None:
            payload_resolve = rst.navigateJsonFragment(parent.jsondata, URI)
            if payload_resolve is None:
                rsvLogger.error('@odata.id of ReferenceableMember does not contain a valid JSON pointer for this payload: {}'.format(odata_id))
                counts['badOdataIdResolution'] += 1
            elif payload_resolve != propResourceObj.jsondata:
                rsvLogger.error('@odata.id of ReferenceableMember does not point to the correct object: {}'.format(odata_id))
                counts['badOdataIdResolution'] += 1
        else:
            rsvLogger.warn('No parent found with which to test @odata.id of ReferenceableMember')

    if not successPayload:
        counts['failPayloadError'] += 1
        rsvLogger.error(str(URI) + ': payload error, @odata property non-conformant',)


    # if URI was sampled, get the notation text from rst.uri_sample_map
    sample_string = rst.uri_sample_map.get(URI)
    sample_string = sample_string + ', ' if sample_string is not None else ''

    results[uriName]['uri'] = (str(URI))
    results[uriName]['samplemapped'] = (str(sample_string))
    results[uriName]['rtime'] = propResourceObj.rtime
    results[uriName]['rcode'] = propResourceObj.status
    results[uriName]['payload'] = propResourceObj.jsondata
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
            rsvLogger.error('{}: Could not finish check on this property ({})'.format(prop.name, str(ex)))
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

    # If this is our first called URI
    top = allLinks is None
    if top:
        allLinks = set()
    allLinks.add(URI)

    def executeLink(linkItem, parent=None):
        linkURI, autoExpand, linkType, linkSchema, innerJson, original_name = linkItem

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
            if any(x in links[linkName].origin_property for x in ['RelatedItem', 'Redundancy', 'Links', 'OriginOfCondition']):
                refLinks[linkName] = (links[linkName], thisobj)
                continue
            if links[linkName].uri in allLinks:
                counts['repeat'] += 1
                continue
            elif links[linkName].uri is None:
                errmsg = 'URI for NavigationProperty is missing {} {}'.format(uriName, links[linkName].linktype)
                traverseLogger.error(errmsg)
                results[uriName]['errors'] += '\n' + errmsg
                counts['errorMissingOdata'] += 1
                continue
            elif links[linkName].uri.split('#')[0].endswith('/'):
                # (elegantly) add warn message to resource html
                warnmsg = 'URI acquired ends in slash: {}'.format(links[linkName].uri)
                traverseLogger.warning(warnmsg)
                results[uriName]['warns'] += '\n' + warnmsg
                counts['warnTrailingSlashLink'] += 1
                newLink = ''.join(links[linkName].uri.split('/')[:-1])
                if newLink in allLinks:
                    counts['repeat'] += 1
                    continue

            success, linkCounts, linkResults, xlinks, xobj = executeLink(links[linkName], thisobj)
            refLinks.update(xlinks)
            if not success:
                counts['unvalidated'] += 1
            results.update(linkResults)

    if top:
        for linkName in refLinks:
            ref_link, refparent = refLinks[linkName]
            if ref_link.uri is None:
                errmsg = 'URI for ReferenceLink is missing {} {}'.format(uriName, ref_link.linktype)
                traverseLogger.error(errmsg)
                results[uriName]['errors'] += '\n' + errmsg
                counts['errorMissingReferenceOdata'] += 1
                continue
            elif ref_link.uri.split('#')[0].endswith('/'):
                # (elegantly) add warn message to resource html
                warnmsg = 'Referenced URI acquired ends in slash: {}'.format(ref_link.uri)
                traverseLogger.warning(warnmsg)
                results[uriName]['warns'] += '\n' + warnmsg
                counts['warnTrailingSlashRefLink'] += 1
                new_ref_link = ''.join(ref_link.uri.split('/')[:-1])
                if new_ref_link in allLinks:
                    counts['repeat'] += 1
                    continue

            if ref_link.uri not in allLinks:
                traverseLogger.verboseout('{}, {}'.format(linkName, ref_link))
                counts['reflink'] += 1
            else:
                continue

            success, linkCounts, linkResults, xlinks, xobj = executeLink(ref_link, refparent)
            if not success:
                counts['unvalidatedRef'] += 1
                if 'OriginOfCondition' in ref_link.origin_property:
                    traverseLogger.info('Link was unsuccessful, but non mandatory')
                    pass
                else:
                    results.update(linkResults)
            else:
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
    argget.add_argument('--debug_logging', action="store_const", const=True, default=None,
            help='Output debug statements to text log, otherwise it only uses INFO (parameter-only)')
    argget.add_argument('--verbose_checks', action="store_const", const=True, default=None,
            help='Show all checks in logging (parameter-only)')
    argget.add_argument('--nooemcheck', action='store_const', const=True, default=None, help='Don\'t check OEM items')
    argget.add_argument('--csv_report', action='store_true', help='print a csv report at the end of the log')

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
    rst.ch.setLevel(VERBO_NUM if args.verbose_checks else logging.INFO if not args.v else logging.DEBUG)
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
        rsvLogger.info('The tool will, by default, attempt to download and store XML files to relieve traffic from DMTF/service')
    elif config['preferonline']:
        rsvLogger.info('Using option PreferOnline, retrieving solely from online sources may be slow...')


    fmt = logging.Formatter('%(levelname)s - %(message)s')
    fh = logging.FileHandler(datetime.strftime(startTick, os.path.join(logpath, "ConformanceLog_%m_%d_%Y_%H%M%S.txt")))
    fh.setLevel(min(logging.INFO if not args.debug_logging else logging.DEBUG, logging.INFO if not args.verbose_checks else VERBO_NUM ))
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
            success, counts, results, xlinks, topobj = validateURITree('/redfish/v1/', 'ServiceRoot', expectedJson=jsonData)
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

    error_lines, finalCounts = count_errors(results)

    for line in error_lines:
        rsvLogger.error(line)

    finalCounts.update(metadata.get_counter())

    fails = 0
    for key in [key for key in finalCounts.keys()]:
        if finalCounts[key] == 0:
            del finalCounts[key]
            continue
        if any(x in key for x in ['problem', 'fail', 'bad', 'exception']):
            fails += finalCounts[key]

    html_str = renderHtml(results, tool_version, startTick, nowTick, currentService, args.csv_report)

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
