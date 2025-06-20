# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import sys
import os
import argparse
import logging
import json
from datetime import datetime
from urllib.parse import urlparse
from collections import Counter

from redfish_service_validator.metadata import getSchemaDetails
from redfish_service_validator.config import convert_config_to_args, convert_args_to_config
from redfish_service_validator.validateResource import validateSingleURI, validateURITree
from redfish_service_validator import tohtml, schema_pack, traverse, logger

tool_version = '2.4.9'

def validate(argslist=None, configfile=None):
    """Main command

    Args:
        argslist ([type], optional): List of arguments in the form of argv. Defaults to None.
    """
    argget = argparse.ArgumentParser(description='DMTF tool to test a service against a collection of Schema, version {}'.format(tool_version))

    # base tool
    argget.add_argument('-v', '--verbose', action='count', default=0, help='Verbosity of tool in stdout')
    argget.add_argument('-c', '--config', type=str, help='Configuration for this tool')

    # host info
    argget.add_argument('-i', '--ip', '--rhost', '-r', type=str, help='The address of the Redfish service (with scheme); example: \'https://123.45.6.7:8000\'')
    argget.add_argument('-u', '--username', '-user', type=str, help='The username for authentication')
    argget.add_argument('-p', '--password', type=str, help='The password for authentication')
    argget.add_argument('--description', type=str, help='The description of the system for identifying logs; if none is given, a value is produced from information in the service root')
    argget.add_argument('--forceauth', action='store_true', help='Force authentication on unsecure connections')
    argget.add_argument('--authtype', type=str, default='Basic', help='Authorization type; \'None\', \'Basic\', \'Session\', or \'Token\'')
    argget.add_argument('--token', type=str, help='Token when \'authtype\' is \'Token\'')
    argget.add_argument('--ext_http_proxy', type=str, default='', help='URL of the HTTP proxy for accessing external sites')
    argget.add_argument('--ext_https_proxy', type=str, default='', help='URL of the HTTPS proxy for accessing external sites')
    argget.add_argument('--serv_http_proxy', type=str, default='', help='URL of the HTTP proxy for accessing the service')
    argget.add_argument('--serv_https_proxy', type=str, default='', help='URL of the HTTPS proxy for accessing the service')

    # validator options
    argget.add_argument('--payload', type=str, help='The mode to validate payloads (\'Tree\', \'Single\', \'SingleFile\', or \'TreeFile\') followed by resource/filepath', nargs=2)
    argget.add_argument('--logdir', '--report-dir', type=str, default='./logs', help='The directory for generated report files; default: \'logs\'')
    argget.add_argument('--nooemcheck', action='store_false', dest='oemcheck', help='Don\'t check OEM items')
    argget.add_argument('--debugging', action="store_true", help='Output debug statements to text log, otherwise it only uses INFO')
    argget.add_argument('--uricheck', action="store_true", help='Allow URI checking on services below RedfishVersion 1.6.0')
    argget.add_argument('--schema_directory', type=str, default='./SchemaFiles/metadata', help='Directory for local schema files')
    argget.add_argument('--mockup', type=str, default='', help='Enables insertion of local mockup resources to replace missing, incomplete, or incorrect implementations retrieved from the service that may hinder full validation coverage')
    argget.add_argument('--collectionlimit', type=str, default=['LogEntry', '20'], help='apply a limit to collections (format: RESOURCE1 COUNT1 RESOURCE2 COUNT2...)', nargs='+')
    argget.add_argument('--requesttimeout', type=int, default=10, help='Timeout in seconds for HTTP requests waiting for response')
    argget.add_argument('--requestattempts', type=int, default=10, help='Number of attempts after failed HTTP requests')

    # parse...
    args = argget.parse_args(argslist)

    if configfile is None:
        configfile = args.config

    # set logging file
    start_tick = datetime.now()

    logger.set_standard_out(logger.Level.INFO - args.verbose if args.verbose < 3 else logger.Level.DEBUG)

    logpath = args.logdir

    if not os.path.isdir(logpath):
        os.makedirs(logpath)

    log_level = logger.Level.INFO if not args.debugging else logger.Level.DEBUG
    file_name = datetime.strftime(start_tick, os.path.join(logpath, "ConformanceLog_%m_%d_%Y_%H%M%S.txt"))

    logger.create_logging_file_handler(log_level, file_name)

    my_logger = logging.getLogger('rsv')
    my_logger.setLevel(logging.DEBUG)

    # begin logging
    my_logger.info("Redfish Service Validator, version {}".format(tool_version))
    my_logger.info("")

    # config verification
    if args.ip is None and configfile is None:
        my_logger.error('Configuration Error: No IP or Config Specified')
        argget.print_help()
        return 1, None, 'Configuration Incomplete'

    if configfile:
        convert_config_to_args(args, configfile)
    else:
        my_logger.info('Writing config file to log directory')
        configfilename = datetime.strftime(start_tick, os.path.join(logpath, "ConfigFile_%m_%d_%Y_%H%M%S.ini"))
        my_config = convert_args_to_config(args)
        with open(configfilename, 'w') as f:
            my_config.write(f)

    scheme, netloc, _path, _params, _query, _fragment = urlparse(args.ip)
    if scheme not in ['http', 'https', 'http+unix']:
        my_logger.error('Configuration Error: IP is missing http or https or http+unix')
        return 1, None, 'IP Incomplete'

    if netloc == '':
        my_logger.error('Configuration Error: IP is missing ip/host')
        return 1, None, 'IP Incomplete'

    if len(args.collectionlimit) % 2 != 0:
        my_logger.error('Configuration Error: Collection Limit requires two arguments per entry (ResourceType Count)')
        return 1, None, 'Collection Limit Incomplete'

    # start printing config details, remove redundant/private info from print
    my_logger.info('Target URI: {}'.format(args.ip))
    my_logger.info('\n'.join(
        ['{}: {}'.format(x, vars(args)[x] if x not in ['password'] else '******') for x in sorted(list(vars(args).keys() - set(['description']))) if vars(args)[x] not in ['', None]]))
    my_logger.info('Start time: {}'.format(start_tick.strftime('%x - %X')))
    my_logger.info("")

    # schema and service init
    schemadir = args.schema_directory

    if not os.path.isdir(schemadir):
        my_logger.info('Downloading initial schemas from online')
        my_logger.info('The tool will, by default, attempt to download and store XML files to relieve traffic from DMTF/service')
        schema_pack.setup_schema_pack('latest', args.schema_directory, args.ext_http_proxy, args.ext_https_proxy)

    try:
        currentService = traverse.rfService(vars(args))
    except Exception as ex:
        my_logger.verbose1('Exception caught while creating Service', exc_info=1)
        my_logger.error("Redfish Service Error: Service could not be started: {}".format(repr(ex)))
        my_logger.error("Try running the Redfish Protocol Validator to ensure the service meets basic protocol conformance")
        return 1, None, 'Service Exception'

    if args.description is None and currentService.service_root:
        my_version = currentService.service_root.get('RedfishVersion', 'No Given Version')
        my_name = currentService.service_root.get('Name', '')
        my_uuid = currentService.service_root.get('UUID', 'No Given UUID')
        setattr(args, 'description', 'System Under Test - {} version {}, {}'.format(my_name, my_version, my_uuid))

    my_logger.info('Description of service: {}'.format(args.description))

    # Start main
    status_code = 1
    json_data = None

    if args.payload:
        pmode, ppath = args.payload
    else:
        pmode, ppath = 'Default', ''
    pmode = pmode.lower()

    if pmode not in ['tree', 'single', 'singlefile', 'treefile', 'default']:
        pmode = 'Default'
        my_logger.error('Configuration Error: PayloadMode or path invalid, using Default behavior')
    if 'file' in pmode:
        if ppath is not None and os.path.isfile(ppath):
            with open(ppath) as f:
                json_data = json.load(f)
                f.close()
        else:
            my_logger.error('Configuration Error: File not found for payload: {}'.format(ppath))
            return 1, None, 'File not found for payload: {}'.format(ppath)
    try:
        if 'single' in pmode:
            my_logger.push_uri(ppath)
            success, my_result, reference_only_links, top_object = validateSingleURI(currentService, ppath, expectedJson=json_data)
            results = {'Target': my_result}
            my_logger.pop_uri()
        elif 'tree' in pmode:
            success, results, reference_only_links, top_object = validateURITree(currentService, ppath, 'Target', expectedJson=json_data)
        else:
            success, results, reference_only_links, top_object = validateURITree(currentService, '/redfish/v1/', 'ServiceRoot', expectedJson=json_data)
    except traverse.AuthenticationError as e:
        # log authentication error and terminate program
        my_logger.error('Authetication Error: {}'.format(e))
        return 1, None, 'Failed to authenticate with the service'

    currentService.close()

    # get final counts
    metadata = currentService.metadata
    my_logger.verbose1('\nMetadata: Namespaces referenced in service: {}'.format(metadata.get_service_namespaces()))
    my_logger.info('Metadata: Namespaces missing from $metadata: {}'.format(metadata.get_missing_namespaces()))

    if len(metadata.get_missing_namespaces()) > 0:
        my_logger.error('Metadata Error: Metadata is missing Namespaces that are referenced by the service.')

    nowTick = datetime.now()
    my_logger.info('\nElapsed time: {}'.format(str(nowTick-start_tick).rsplit('.', 1)[0]))

    final_counts = Counter()

    my_logger.info('\nListing any warnings and errors: ')

    for k, my_result in results.items():

        for record in my_result['records']:
            if record.result:
                final_counts[record.result] += 1

        warns = [x for x in my_result['records'] if x.levelno == logger.Level.WARN]
        errors = [x for x in my_result['records'] if x.levelno == logger.Level.ERROR]
        if len(warns + errors):
            my_logger.info(" ")
            my_logger.info(my_result['uri'])

            if len(warns):
                my_logger.info("Warnings")
                for record in warns:
                    final_counts[record.levelname.lower()] += 1
                    my_logger.log(record.levelno, ", ".join([x for x in [record.msg, record.result] if x])) 

            if len(errors):
                my_logger.info("Errors")
                for record in errors:
                    final_counts[record.levelname.lower()] += 1
                    my_logger.log(record.levelno, ", ".join([x for x in [record.msg, record.result] if x])) 

    final_counts.update({x: k for x, k in metadata.get_counter().items() if k > 0})

    html_str = tohtml.renderHtml(results, tool_version, start_tick, nowTick, currentService)

    lastResultsPage = datetime.strftime(start_tick, os.path.join(logpath, "ConformanceHtmlLog_%m_%d_%Y_%H%M%S.html"))

    tohtml.writeHtml(html_str, lastResultsPage)

    my_logger.info("\nResults Summary:")
    my_logger.info(", ".join([
        'Pass: {}'.format(final_counts['pass']),
        'Fail: {}'.format(final_counts['error']),
        'Warning: {}'.format(final_counts['warning']),
        ]))

    # dump cache info to debug log
    my_logger.debug('getSchemaDetails() -> {}'.format(getSchemaDetails.cache_info()))
    my_logger.debug('callResourceURI() -> {}'.format(currentService.cache_order))

    success = final_counts['error'] == 0

    if not success:
        my_logger.error("Validation has failed: {} problems found".format(final_counts['error']))
    else:
        my_logger.info("Validation has succeeded.")
        status_code = 0
    
    return status_code, lastResultsPage, 'Validation done'


def main():
    """
    Entry point for the program.
    """
    status_code, _, _ = validate()
    return status_code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        logger.my_logger.exception("Program finished prematurely: %s", e)
        raise
