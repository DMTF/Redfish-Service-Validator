# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import os
import sys
import argparse
import logging
import json
from datetime import datetime
import traceback
from redfish_service_validator.metadata import getSchemaDetails
from redfish_service_validator.config import convert_config_to_args, convert_args_to_config
from redfish_service_validator.validateResource import validateSingleURI, validateURITree
from redfish_service_validator import tohtml, schema_pack, traverse
from urllib.parse import urlparse
from collections import Counter

tool_version = '2.4.9'

# Set up the custom debug levels
VERBOSE1 = logging.INFO-1
VERBOSE2 = logging.INFO-2

logging.addLevelName(VERBOSE1, "VERBOSE1")
logging.addLevelName(VERBOSE2, "VERBOSE2")


def print_verbose_1(self, msg, *args, **kwargs):
    if self.isEnabledFor(VERBOSE1):
        self._log(VERBOSE1, msg, args, **kwargs)


def print_verbose_2(self, msg, *args, **kwargs):
    if self.isEnabledFor(VERBOSE2):
        self._log(VERBOSE2, msg, args, **kwargs)
        

logging.Logger.verbose1 = print_verbose_1
logging.Logger.verbose2 = print_verbose_2

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)
standard_out = logging.StreamHandler(sys.stdout)
standard_out.setLevel(logging.INFO)
my_logger.addHandler(standard_out)


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
    startTick = datetime.now()

    standard_out.setLevel(logging.INFO - args.verbose if args.verbose < 3 else logging.DEBUG)

    logpath = args.logdir

    if not os.path.isdir(logpath):
        os.makedirs(logpath)

    fmt = logging.Formatter('%(levelname)s - %(message)s')
    file_handler = logging.FileHandler(datetime.strftime(startTick, os.path.join(logpath, "ConformanceLog_%m_%d_%Y_%H%M%S.txt")))
    file_handler.setLevel(min(logging.INFO if not args.debugging else logging.DEBUG, standard_out.level))
    file_handler.setFormatter(fmt)
    my_logger.addHandler(file_handler)

    # begin logging
    my_logger.info("Redfish Service Validator, version {}".format(tool_version))
    my_logger.info("")

    # config verification
    if args.ip is None and configfile is None:
        my_logger.error('No IP or Config Specified')
        argget.print_help()
        return 1, None, 'Configuration Incomplete'

    if configfile:
        convert_config_to_args(args, configfile)
    else:
        my_logger.info('Writing config file to log directory')
        configfilename = datetime.strftime(startTick, os.path.join(logpath, "ConfigFile_%m_%d_%Y_%H%M%S.ini"))
        my_config = convert_args_to_config(args)
        with open(configfilename, 'w') as f:
            my_config.write(f)

    scheme, netloc, path, params, query, fragment = urlparse(args.ip)
    if scheme not in ['http', 'https', 'http+unix']:
        my_logger.error('IP is missing http or https or http+unix')
        return 1, None, 'IP Incomplete'

    if netloc == '':
        my_logger.error('IP is missing ip/host')
        return 1, None, 'IP Incomplete'

    if len(args.collectionlimit) % 2 != 0:
        my_logger.error('Collection Limit requires two arguments per entry (ResourceType Count)')
        return 1, None, 'Collection Limit Incomplete'

    # start printing config details, remove redundant/private info from print
    my_logger.info('Target URI: ' + args.ip)
    my_logger.info('\n'.join(
        ['{}: {}'.format(x, vars(args)[x] if x not in ['password'] else '******') for x in sorted(list(vars(args).keys() - set(['description']))) if vars(args)[x] not in ['', None]]))
    my_logger.info('Start time: ' + startTick.strftime('%x - %X'))
    my_logger.info("")

    # schema and service init
    schemadir = args.schema_directory

    if not os.path.isdir(schemadir):
        my_logger.info('Downloading initial schemas from online')
        my_logger.info('The tool will, by default, attempt to download and store XML files to relieve traffic from DMTF/service')
        schema_pack.my_logger.addHandler(file_handler)
        schema_pack.setup_schema_pack('latest', args.schema_directory, args.ext_http_proxy, args.ext_https_proxy)

    try:
        currentService = traverse.rfService(vars(args))
    except Exception as ex:
        traceback.print_exc()
        my_logger.verbose1('Exception caught while creating Service', exc_info=1)
        my_logger.error("Service could not be started: {}".format(repr(ex)))
        my_logger.error("Try running the Redfish Protocol Validator to ensure the service meets basic protocol conformance")
        return 1, None, 'Service Exception'
    
    if args.description is None and currentService.service_root:
        my_version = currentService.service_root.get('RedfishVersion', 'No Version')
        my_name = currentService.service_root.get('Name', '')
        my_uuid = currentService.service_root.get('UUID', 'No UUID')
        setattr(args, 'description', 'My Target System {}, version {}, {}'.format(my_name, my_version, my_uuid))
    
    my_logger.info('Description of service: {}'.format(args.description))

    # Start main
    status_code = 1
    jsonData = None

    if args.payload:
        pmode, ppath = args.payload
    else:
        pmode, ppath = 'Default', ''
    pmode = pmode.lower()

    if pmode not in ['tree', 'single', 'singlefile', 'treefile', 'default']:
        pmode = 'Default'
        my_logger.error('PayloadMode or path invalid, using Default behavior')
    if 'file' in pmode:
        if ppath is not None and os.path.isfile(ppath):
            with open(ppath) as f:
                jsonData = json.load(f)
                f.close()
        else:
            my_logger.error('File not found for payload: {}'.format(ppath))
            return 1, None, 'File not found for payload: {}'.format(ppath)
    try:
        if 'single' in pmode:
            success, counts, results, xlinks, topobj = validateSingleURI(currentService, ppath, 'Target', expectedJson=jsonData)
        elif 'tree' in pmode:
            success, counts, results, xlinks, topobj = validateURITree(currentService, ppath, 'Target', expectedJson=jsonData)
        else:
            success, counts, results, xlinks, topobj = validateURITree(currentService, '/redfish/v1/', 'ServiceRoot', expectedJson=jsonData)
    except traverse.AuthenticationError as e:
        # log authentication error and terminate program
        my_logger.error('{}'.format(e))
        return 1, None, 'Failed to authenticate with the service'

    currentService.close()

    # get final counts
    metadata = currentService.metadata
    my_logger.verbose1('\nMetadata: Namespaces referenced in service: {}'.format(metadata.get_service_namespaces()))
    my_logger.info('Metadata: Namespaces missing from $metadata: {}'.format(metadata.get_missing_namespaces()))

    if len(metadata.get_missing_namespaces()) > 0:
        my_logger.error('Metadata is missing Namespaces that are referenced by the service.')

    finalCounts = Counter()
    nowTick = datetime.now()
    my_logger.info('\nElapsed time: {}'.format(str(nowTick-startTick).rsplit('.', 1)[0]))

    error_lines, finalCounts = tohtml.count_errors(results)

    for line in error_lines:
        my_logger.error(line)

    finalCounts.update(metadata.get_counter())

    fails = 0
    for key in [key for key in finalCounts.keys()]:
        if finalCounts[key] == 0:
            del finalCounts[key]
            continue
        if any(x in key for x in ['problem', 'fail', 'bad', 'exception']):
            fails += finalCounts[key]

    html_str = tohtml.renderHtml(results, tool_version, startTick, nowTick, currentService)

    lastResultsPage = datetime.strftime(startTick, os.path.join(logpath, "ConformanceHtmlLog_%m_%d_%Y_%H%M%S.html"))

    tohtml.writeHtml(html_str, lastResultsPage)

    success = success and not (fails > 0)
    my_logger.info("\n".join('{}: {}   '.format(x, y) for x, y in sorted(finalCounts.items())))

    # dump cache info to debug log
    my_logger.debug('getSchemaDetails() -> {}'.format(getSchemaDetails.cache_info()))
    my_logger.debug('callResourceURI() -> {}'.format(currentService.cache_order))

    if not success:
        my_logger.error("Validation has failed: {} problems found".format(fails))
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
        my_logger.exception("Program finished prematurely: %s", e)
        raise
