# Copyright Notice:
# Copyright 2016-2021 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import os
import sys
import argparse
import logging
from datetime import datetime

tool_version = '1.4.1'

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)
standard_out = logging.StreamHandler(sys.stdout)
standard_out.setLevel(logging.INFO)
my_logger.addHandler(standard_out)

def main(argslist=None):
    """Main command

    Args:
        argslist ([type], optional): List of arguments in the form of argv. Defaults to None.
    """    
    argget = argparse.ArgumentParser(description='DMTF tool to test a service against a collection of Schema, version {}'.format(tool_version))

    # base tool
    argget.add_argument('-v', '--verbose', action='count', default=0, help='Verbosity of tool in stdout')

    # host info
    argget.add_argument('-i', '--ip', type=str, help='Address of host to test against, using http or https (example: https://123.45.6.7:8000)')
    argget.add_argument('-u', '--user', type=str, help='Username for Authentication')
    argget.add_argument('-p', '--password', type=str, help='Password for Authentication')
    argget.add_argument('--description', type=str, help='sysdescription for identifying logs, if none is given, draw from serviceroot')
    argget.add_argument('--nochkcert', action='store_true', help='Ignore check for HTTPS certificate')
    argget.add_argument('--forceauth', action='store_true', help='Force authentication on unsecure connections')
    argget.add_argument('--authtype', type=str, default='Basic', help='authorization type (None|Basic|Session|Token)')
    argget.add_argument('--token', type=str, help='bearer token for authtype Token')

    # validator options
    argget.add_argument('--payload', type=str, help='mode to validate payloads [Tree, Single, SingleFile, TreeFile] followed by resource/filepath', nargs=2)
    argget.add_argument('--logdir', type=str, default='./logs', help='directory for log files')
    argget.add_argument('--nooemcheck', action='store_const', const=True, default=None, help='Don\'t check OEM items')
    argget.add_argument('--debugging', action="store_true", help='Output debug statements to text log, otherwise it only uses INFO')
    argget.add_argument('--schema_directory', type=str, default='./SchemaFiles/metadata', help='directory for local schema files')
    argget.add_argument('--schema_origin', type=str, default='local', help='Preferred location of schemafiles.  Can be local, for a local directory, online or only from the host service itself [local, online, service]')
    argget.add_argument('--schema_pack', type=str, help='Deploy DMTF schema from zip distribution, for use with --localonly (Specify url or type "latest", overwrites current schema)')

    args = argget.parse_args(argslist)

    startTick = datetime.now()

    # set logging file
    standard_out.setLevel(logging.INFO - args.verbose if args.verbose < 3 else logging.DEBUG)

    logpath = args.logdir

    if not os.path.isdir(logpath):
        os.makedirs(logpath)

    fmt = logging.Formatter('%(levelname)s - %(message)s')
    file_handler = logging.FileHandler(datetime.strftime(startTick, os.path.join(logpath, "ConformanceLog_%m_%d_%Y_%H%M%S.txt")))
    file_handler.setLevel(min(logging.INFO if not args.debugging else logging.DEBUG, standard_out.level))
    file_handler.setFormatter(fmt)
    my_logger.addHandler(file_handler)

    my_logger.info("Redfish Service Validator, version {}".format(tool_version))

    # start printing config details, remove redundant/private info from print
    my_logger.info('Target URI: ' + args.ip)
    my_logger.info('\n'.join(
        ['{}: {}'.format(x, vars(args)[x] if x not in ['password'] else '******') for x in sorted(list(vars(args).keys() - set(['description']))) if vars(args)[x] not in ['', None]]))
    my_logger.info('Start time: ' + startTick.strftime('%x - %X'))

    if args.ip is None:
        my_logger.error('No IP or Config Specified')
        argget.print_help()
        return 1, None, 'Config Incomplete'
    else:
        print(args.ip)

    if args.schema_pack not in ['', None]:
        import schema_pack
        schema_pack.my_logger.addHandler(file_handler)
        schema_pack.setup_schema_pack(args.schema_pack, args.schema_directory)

    schemadir = args.schema_directory

    if not os.path.isdir(schemadir) and args.schema_origin.lower() not in ['online']:
        my_logger.info('First run suggested to create and own local schema files, please download manually or use --schema_pack latest')
        my_logger.info('Alternatively, use the option --prefer_online to skip local schema file checks')
        my_logger.info('The tool will, by default, attempt to download and store XML files to relieve traffic from DMTF/service')
    elif args.schema_origin.lower() in ['online']:
        my_logger.info('Using option PreferOnline, retrieving solely from online sources may be slow...')

    try:
        import traverseService as rst
        rst.my_logger.addHandler(file_handler)
        currentService = rst.startService(vars(args))
    except Exception as ex:
        my_logger.debug('Exception caught while creating Service', exc_info=1)
        my_logger.error("Service could not be started: {}".format(ex))
        return 1, None, 'Service Exception'

    # Start main
    status_code = 1
    jsonData = None

    # pmode, ppath = config.get('payloadmode', 'Default'), config.get('payloadfilepath')
    # if pmode not in ['Tree', 'Single', 'SingleFile', 'TreeFile', 'Default']:
    #     pmode = 'Default'
    #     rsvLogger.error('PayloadMode or path invalid, using Default behavior')
    # if 'File' in pmode:
    #     if ppath is not None and os.path.isfile(ppath):
    #         with open(ppath) as f:
    #             jsonData = json.load(f)
    #             f.close()
    #     else:
    #         rsvLogger.error('File not found: {}'.format(ppath))
    #         return 1, None, 'File not found: {}'.format(ppath)
    # try:
    #     if 'Single' in pmode:
    #         success, counts, results, xlinks, topobj = validateSingleURI(ppath, 'Target', expectedJson=jsonData)
    #     elif 'Tree' in pmode:
    #         success, counts, results, xlinks, topobj = validateURITree(ppath, 'Target', expectedJson=jsonData)
    #     else:
    #         success, counts, results, xlinks, topobj = validateURITree('/redfish/v1/', 'ServiceRoot', expectedJson=jsonData)
    # except AuthenticationError as e:
    #     # log authentication error and terminate program
    #     rsvLogger.error('{}'.format(e))
    #     return 1, None, 'Failed to authenticate with the service'

    currentService.close()

    # rsvLogger.debug('Metadata: Namespaces referenced in service: {}'.format(metadata.get_service_namespaces()))
    # rsvLogger.debug('Metadata: Namespaces missing from $metadata: {}'.format(metadata.get_missing_namespaces()))

    # finalCounts = Counter()
    # nowTick = datetime.now()
    # rsvLogger.info('Elapsed time: {}'.format(str(nowTick-startTick).rsplit('.', 1)[0]))

    # error_lines, finalCounts = count_errors(results)

    # for line in error_lines:
    #     rsvLogger.error(line)

    # finalCounts.update(metadata.get_counter())

    # fails = 0
    # for key in [key for key in finalCounts.keys()]:
    #     if finalCounts[key] == 0:
    #         del finalCounts[key]
    #         continue
    #     if any(x in key for x in ['problem', 'fail', 'bad', 'exception']):
    #         fails += finalCounts[key]

    # html_str = renderHtml(results, tool_version, startTick, nowTick, currentService, args.csv_report)

    # lastResultsPage = datetime.strftime(startTick, os.path.join(logpath, "ConformanceHtmlLog_%m_%d_%Y_%H%M%S.html"))

    # writeHtml(html_str, lastResultsPage)

    # success = success and not (fails > 0)
    # rsvLogger.info(finalCounts)

    # # dump cache info to debug log
    # rsvLogger.debug('getSchemaDetails() -> {}'.format(rst.rfSchema.getSchemaDetails.cache_info()))
    # rsvLogger.debug('callResourceURI() -> {}'.format(currentService.callResourceURI.cache_info()))

    # if not success:
    #     rsvLogger.error("Validation has failed: {} problems found".format(fails))
    # else:
    #     rsvLogger.info("Validation has succeeded.")
    #     status_code = 0

    return status_code, lastResultsPage, 'Validation done'


if __name__ == '__main__':
    status_code, lastResultsPage, exit_string = main()
    sys.exit(status_code)
