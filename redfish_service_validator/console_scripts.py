# Copyright Notice:
# Copyright 2016-2026 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

"""
Redfish Validator Console Scripts

File : console_scripts.py

Brief : This file contains the definitions and functionalities for invoking
        the service validator.
"""

import argparse
import colorama
import configparser
import logging
import os
import redfish
import sys
from datetime import datetime
from pathlib import Path

from redfish_service_validator.system_under_test import SystemUnderTest
from redfish_service_validator import logger
from redfish_service_validator import metadata
from redfish_service_validator import report
from redfish_service_validator import schema_pack

tool_version = "3.1.6"


def load_config(config_file):
    """
    Load configuration from a config.ini file

    Args:
        config_file: Path to the configuration file

    Returns:
        A dictionary containing the configuration values
    """
    config = configparser.ConfigParser()
    config_values = {}

    try:
        if not os.path.isfile(config_file):
            return config_values

        config.read(config_file)

        # Authentication section
        if config.has_section('Authentication'):
            if config.has_option('Authentication', 'user'):
                user = config.get('Authentication', 'user').strip()
                if user:
                    config_values['user'] = user
            if config.has_option('Authentication', 'password'):
                password = config.get('Authentication', 'password').strip()
                if password:
                    config_values['password'] = password
            if config.has_option('Authentication', 'authtype'):
                authtype = config.get('Authentication', 'authtype').strip()
                if authtype:
                    config_values['authtype'] = authtype

        # Connection section
        if config.has_section('Connection'):
            if config.has_option('Connection', 'rhost'):
                rhost = config.get('Connection', 'rhost').strip()
                if rhost:
                    config_values['rhost'] = rhost
            if config.has_option('Connection', 'timeout'):
                timeout = config.get('Connection', 'timeout').strip()
                if timeout:
                    config_values['timeout'] = int(timeout)

        # Proxy section
        if config.has_section('Proxy'):
            if config.has_option('Proxy', 'ext_http_proxy'):
                ext_http_proxy = config.get('Proxy', 'ext_http_proxy').strip()
                if ext_http_proxy:
                    config_values['ext_http_proxy'] = ext_http_proxy
            if config.has_option('Proxy', 'ext_https_proxy'):
                ext_https_proxy = config.get('Proxy', 'ext_https_proxy').strip()
                if ext_https_proxy:
                    config_values['ext_https_proxy'] = ext_https_proxy
            if config.has_option('Proxy', 'serv_http_proxy'):
                serv_http_proxy = config.get('Proxy', 'serv_http_proxy').strip()
                if serv_http_proxy:
                    config_values['serv_http_proxy'] = serv_http_proxy
            if config.has_option('Proxy', 'serv_https_proxy'):
                serv_https_proxy = config.get('Proxy', 'serv_https_proxy').strip()
                if serv_https_proxy:
                    config_values['serv_https_proxy'] = serv_https_proxy

        # Paths section
        if config.has_section('Paths'):
            if config.has_option('Paths', 'logdir'):
                logdir = config.get('Paths', 'logdir').strip()
                if logdir:
                    config_values['logdir'] = logdir
            if config.has_option('Paths', 'schema_directory'):
                schema_directory = config.get('Paths', 'schema_directory').strip()
                if schema_directory:
                    config_values['schema_directory'] = schema_directory
            if config.has_option('Paths', 'mockup'):
                mockup = config.get('Paths', 'mockup').strip()
                if mockup:
                    config_values['mockup'] = mockup

        # Validation section
        if config.has_section('Validation'):
            # Handle payload (scope and uri)
            if config.has_option('Validation', 'payload_scope') and config.has_option('Validation', 'payload_uri'):
                payload_scope = config.get('Validation', 'payload_scope').strip()
                payload_uri = config.get('Validation', 'payload_uri').strip()
                if payload_scope and payload_uri:
                    config_values['payload'] = [payload_scope, payload_uri]

            # Handle collection limit
            if config.has_option('Validation', 'collectionlimit'):
                collectionlimit = config.get('Validation', 'collectionlimit').strip()
                if collectionlimit:
                    config_values['collectionlimit'] = collectionlimit.split()

            # Boolean flags
            if config.has_option('Validation', 'nooemcheck'):
                config_values['nooemcheck'] = config.getboolean('Validation', 'nooemcheck')
            if config.has_option('Validation', 'skipschema'):
                config_values['skipschema'] = config.getboolean('Validation', 'skipschema')
            if config.has_option('Validation', 'debugging'):
                config_values['debugging'] = config.getboolean('Validation', 'debugging')

    except Exception as err:
        print("WARNING: Error reading config file {}: {}".format(config_file, err))
        return {}

    return config_values


def main():
    """
    Entry point for the service validator
    """

    # Get the input arguments
    argget = argparse.ArgumentParser(description="Validate Redfish services against schemas")
    argget.add_argument(
        "--config", "-c", type=str, default="config.ini", help="Path to configuration file; default: 'config.ini'"
    )
    argget.add_argument(
        "--user", "-u", "-user", "--username", type=str, help="The username for authentication"
    )
    argget.add_argument("--password", "-p", type=str, help="The password for authentication")
    argget.add_argument(
        "--rhost", "-r", "--ip", "-i", type=str, help="The address of the Redfish service (with scheme)"
    )
    argget.add_argument(
        "--authtype", type=str, choices=["Basic", "Session"], help="The authorization type"
    )
    argget.add_argument("--ext_http_proxy", type=str, help="The URL of the HTTP proxy for accessing external sites")
    argget.add_argument("--ext_https_proxy", type=str, help="The URL of the HTTPS proxy for accessing external sites")
    argget.add_argument(
        "--serv_http_proxy", type=str, help="The URL of the HTTP proxy for accessing the Redfish service"
    )
    argget.add_argument(
        "--serv_https_proxy", type=str, help="The URL of the HTTPS proxy for accessing the Redfish service"
    )
    argget.add_argument(
        "--logdir",
        "--report-dir",
        type=str,
        help="The directory for generated report files; default: 'logs'",
    )
    argget.add_argument(
        "--schema_directory",
        type=str,
        help="Directory for local schema files; default: 'SchemaFiles'",
    )
    argget.add_argument(
        "--payload",
        type=str,
        help="Controls how much of the data model to test; option is followed by the URI of the resource from which to start",
        nargs=2,
    )
    argget.add_argument(
        "--mockup", type=str, help="Path to directory containing mockups to override responses from the service"
    )
    argget.add_argument(
        "--collectionlimit",
        type=str,
        help="Applies a limit to testing resources in collections; format: RESOURCE1 COUNT1 RESOURCE2 COUNT2 ...",
        nargs="+",
    )
    argget.add_argument("--nooemcheck", action="store_true", help="Don't check OEM items")
    argget.add_argument(
        "--timeout",
        "-timeout",
        type=int,
        help="The timeout, in seconds, for the service to respond to HTTP requests",
    )
    argget.add_argument(
        "--skipschema",
        action="store_true",
        help="Skip downloading schema files and use only cached schemas in the schema directory",
    )
    argget.add_argument(
        "--debugging",
        action="store_true",
        help="Controls the verbosity of the debugging output; if not specified only INFO and higher are logged",
    )

    # Parse command-line arguments
    args = argget.parse_args()

    # Load configuration from file
    config_values = load_config(args.config)

    # Required arguments: rhost, user, password
    if args.rhost is None:
        args.rhost = config_values.get('rhost')
    if args.user is None:
        args.user = config_values.get('user')
    if args.password is None:
        args.password = config_values.get('password')

    # Check if required arguments are present
    if args.rhost is None:
        print("ERROR: Redfish service host is required (provide via --rhost or config file)")
        sys.exit(1)
    if args.user is None:
        print("ERROR: Username is required (provide via --user or config file)")
        sys.exit(1)
    if args.password is None:
        print("ERROR: Password is required (provide via --password or config file)")
        sys.exit(1)

    # Optional string arguments
    if args.authtype is None:
        args.authtype = config_values.get('authtype', 'Session')
    if args.logdir is None:
        args.logdir = config_values.get('logdir', 'logs')
    if args.schema_directory is None:
        args.schema_directory = config_values.get('schema_directory', 'SchemaFiles')
    if args.mockup is None:
        args.mockup = config_values.get('mockup')
    if args.timeout is None:
        args.timeout = config_values.get('timeout')
    if args.ext_http_proxy is None:
        args.ext_http_proxy = config_values.get('ext_http_proxy')
    if args.ext_https_proxy is None:
        args.ext_https_proxy = config_values.get('ext_https_proxy')
    if args.serv_http_proxy is None:
        args.serv_http_proxy = config_values.get('serv_http_proxy')
    if args.serv_https_proxy is None:
        args.serv_https_proxy = config_values.get('serv_https_proxy')
    if args.payload is None:
        args.payload = config_values.get('payload')
    if args.collectionlimit is None:
        args.collectionlimit = config_values.get('collectionlimit', ['LogEntry', '20'])

    # Optional Boolean arguments
    if not args.nooemcheck and 'nooemcheck' in config_values:
        args.nooemcheck = config_values['nooemcheck']
    if not args.skipschema and 'skipschema' in config_values:
        args.skipschema = config_values['skipschema']
    if not args.debugging and 'debugging' in config_values:
        args.debugging = config_values['debugging']

    code, file = run_validator(vars(args))
    if code != 0:
        sys.exit(code)


def run_validator(args):
    # Set up the traversal mode
    if args["payload"]:
        traverse_mode, starting_uri = args["payload"]
    else:
        traverse_mode, starting_uri = None, "/redfish/v1/"

    # Set up external proxy info
    proxies = None
    if args["ext_http_proxy"] or args["ext_https_proxy"]:
        proxies = {}
        if args["ext_http_proxy"]:
            proxies["http"] = args["ext_http_proxy"]
        if args["ext_https_proxy"]:
            proxies["https"] = args["ext_https_proxy"]

    # Create schema directory if needed
    schema_dir = Path(args["schema_directory"])
    if not schema_dir.is_dir():
        schema_dir.mkdir(parents=True)

    # Get the current time for report files
    test_time = datetime.now()

    # Create report directory with timestamped subfolder (YYYY-MM-DD-HHMMSS)
    report_dir = Path(args["logdir"]) / test_time.strftime("%Y-%m-%d-%H%M%S")
    report_dir.mkdir(parents=True, exist_ok=True)

    # Set the logging level
    log_level = logging.INFO
    if args["debugging"]:
        log_level = logging.DEBUG
    log_file = report_dir / "RedfishServiceValidatorDebug_{}.log".format(test_time.strftime("%m_%d_%Y_%H%M%S"))
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logger.logger = redfish.redfish_logger(log_file, log_format, log_level)
    logger.log_print("Redfish Service Validator, Version {}\n".format(tool_version))
    logger.info("System: {}".format(args["rhost"]))
    logger.info("User: {}".format(args["user"]))

    # Set up the system
    try:
        sut = SystemUnderTest(
            args["rhost"],
            args["user"],
            args["password"],
            args["timeout"],
            args["authtype"],
            args["serv_http_proxy"],
            args["serv_https_proxy"],
            args["mockup"],
            args["collectionlimit"],
            args["nooemcheck"],
        )
    except Exception as err:
        logger.critical("Could not set up the service: {}".format(err))
        return 1, None

    # Update the schema cache
    if not args["skipschema"]:
        schema_pack.update_dsp8010_files(args["schema_directory"], proxies)
        schema_pack.update_service_metadata(args["schema_directory"], sut.session, proxies)
    else:
        logger.log_print("Skipping schema download; using cached schemas only\n")

    # Build the schema database
    metadata.parse_schema_files(args["schema_directory"])

    # Validate the service
    sut.validate(traverse_mode, starting_uri, starting_uri)

    # Results
    logger.log_print("")
    print_summary(sut)
    logger.log_print("")
    results_file = report.html_report(sut, report_dir, test_time, tool_version, args)
    xlsx_file = report.xlsx_report(sut, report_dir, test_time, tool_version, args)
    logger.log_print("HTML Report:  {}".format(results_file))
    logger.log_print("Excel Report: {}".format(xlsx_file))
    logger.log_print("Debug Log:    {}".format(log_file))
    logger.log_print("")

    sut.logout()

    return int(sut.fail_count > 0), str(results_file)


def summary_format(result, result_count):
    """
    Returns a color-coded result format

    Args:
        result: The type of result
        result_count: The number of results for that type
    """
    color_map = {
        "PASS": (colorama.Fore.GREEN, colorama.Style.RESET_ALL),
        "WARN": (colorama.Fore.YELLOW, colorama.Style.RESET_ALL),
        "FAIL": (colorama.Fore.RED, colorama.Style.RESET_ALL),
    }
    start, end = ("", "")
    if result_count:
        start, end = color_map.get(result, ("", ""))
    return start, result_count, end


def print_summary(sut):
    """
    Prints a stylized summary of the test results

    Args:
        sut: The system under test
    """
    colorama.init()
    pass_start, passed, pass_end = summary_format("PASS", sut.pass_count)
    warn_start, warned, warn_end = summary_format("WARN", sut.warn_count)
    fail_start, failed, fail_end = summary_format("FAIL", sut.fail_count)
    no_test_start, not_tested, no_test_end = summary_format("SKIP", sut.skip_count)

    col_w = 14
    sep = "+" + ("-" * col_w + "+") * 4
    header = "| {:^{w}} | {:^{w}} | {:^{w}} | {:^{w}} |".format("PASS", "WARN", "FAIL", "NOT TESTED", w=col_w - 2)
    values = "| {}{:^{w}}{} | {}{:^{w}}{} | {}{:^{w}}{} | {}{:^{w}}{} |".format(
        pass_start,
        str(passed),
        pass_end,
        warn_start,
        str(warned),
        warn_end,
        fail_start,
        str(failed),
        fail_end,
        no_test_start,
        str(not_tested),
        no_test_end,
        w=col_w - 2,
    )
    logger.log_print("")
    logger.log_print(sep)
    logger.log_print(header)
    logger.log_print(sep)
    logger.log_print(values)
    logger.log_print(sep)
    logger.log_print("")
    colorama.deinit()
