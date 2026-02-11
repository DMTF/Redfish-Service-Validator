# Copyright Notice:
# Copyright 2016-2025 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

"""
Redfish Validator Console Scripts

File : console_scripts.py

Brief : This file contains the definitions and functionalities for invoking
        the service validator.
"""

import argparse
import colorama
import logging
import redfish
import sys
from datetime import datetime
from pathlib import Path

from redfish_service_validator.system_under_test import SystemUnderTest
from redfish_service_validator import logger
from redfish_service_validator import metadata
from redfish_service_validator import report
from redfish_service_validator import schema_pack

tool_version = "2.5.1"


def main():
    """
    Entry point for the service validator
    """

    # Get the input arguments
    argget = argparse.ArgumentParser(
        description="Validate Redfish services against schemas; Version {}".format(tool_version)
    )
    argget.add_argument(
        "--user", "-u", "-user", "--username", type=str, required=True, help="The username for authentication"
    )
    argget.add_argument("--password", "-p", type=str, required=True, help="The password for authentication")
    argget.add_argument(
        "--rhost", "-r", "--ip", "-i", type=str, required=True, help="The address of the Redfish service (with scheme)"
    )
    argget.add_argument(
        "--authtype", type=str, default="Session", choices=["Basic", "Session"], help="The authorization type"
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
        default="logs",
        help="The directory for generated report files; default: 'logs'",
    )
    argget.add_argument(
        "--schema_directory",
        type=str,
        default="SchemaFiles",
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
        default=["LogEntry", "20"],
        help="Applies a limit to testing resources in collections; format: RESOURCE1 COUNT1 RESOURCE2 COUNT2 ...",
        nargs="+",
    )
    argget.add_argument("--nooemcheck", action="store_true", help="Don't check OEM items")
    argget.add_argument(
        "--debugging",
        action="store_true",
        help="Controls the verbosity of the debugging output; if not specified only INFO and higher are logged",
    )
    args = argget.parse_args()
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

    # Create report directory if needed
    report_dir = Path(args["logdir"])
    if not report_dir.is_dir():
        report_dir.mkdir(parents=True)

    # Get the current time for report files
    test_time = datetime.now()

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
    schema_pack.update_dsp8010_files(args["schema_directory"], proxies)
    schema_pack.update_service_metadata(args["schema_directory"], sut.session, proxies)

    # Build the schema database
    metadata.parse_schema_files(args["schema_directory"])

    # Validate the service
    sut.validate(traverse_mode, starting_uri, starting_uri)
    sut.logout()

    # Results
    logger.log_print("")
    print_summary(sut)
    results_file = report.html_report(sut, report_dir, test_time, tool_version)
    logger.log_print("HTML Report: {}".format(results_file))

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
    logger.log_print(
        "Summary - %sPASS: %s%s, %sWARN: %s%s, %sFAIL: %s%s, %sNOT TESTED: %s%s"
        % (
            pass_start,
            passed,
            pass_end,
            warn_start,
            warned,
            warn_end,
            fail_start,
            failed,
            fail_end,
            no_test_start,
            not_tested,
            no_test_end,
        )
    )
    colorama.deinit()
