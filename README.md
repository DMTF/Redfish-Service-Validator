Copyright 2017-2021 _DMTF_. All rights reserved.

# Redfish Service Validator

## About

The `Redfish Service Validator` is a python3 tool for checking conformance of any "device" with a _Redfish_ service interface against _Redfish_ CSDL schema.  The tool is designed to be device agnostic and is driven based on the _Redfish_ specifications and schema intended to be supported by the device.

## Introduction

The `Redfish Service Validator` is an open source framework for checking conformance of any generic device with _Redfish_ interface enabled against the _DMTF_ defined _Redfish_ schema and specifications. The tool is designed to be device agnostic and is driven purely based on the _Redfish_ specifications intended to be supported by the device.

## Pre-requisites

The `Redfish Service Validator` is based on Python 3 and the client system is required to have the Python framework installed before the tool can be installed and executed on the system. Additionally, the following packages are required to be installed and accessible from the python environment:
* beautifulsoup4  - https://pypi.python.org/pypi/beautifulsoup4
* requests  - https://github.com/kennethreitz/requests (Documentation is available at http://docs.python-requests.org/)
* lxml - https://pypi.python.org/pypi/lxml

You may install the prerequisites by running:

    pip3 install -r requirements.txt

If you have a previous beautifulsoup4 installation, please use the following command:

    pip3 install beautifulsoup4 --upgrade

There is no dependency based on Windows or Linux OS. The result logs are generated in HTML format and an appropriate browser (Chrome, Firefox, IE, etc.) is required to view the logs on the client system.

## Installation

Place the RedfishServiceValidator folder into the desired directory.  Create the following subdirectories in the tool root directory: "config", "logs", "SchemaFiles".  Place the example config.ini file in the "config" directory.  Place the CSDL Schema files to be used by the tool in the root of the schema directory, or the directory given in config.ini.

## Execution Steps

The `Redfish Service Validator` is designed to execute as a purely command line interface tool with no intermediate inputs expected during tool execution. However, the tool requires various inputs regarding system details, _DMTF_ schema files etc. which are consumed by the tool during execution to generate the conformance report logs. Below are the step by step instructions on setting up the tool for execution on any identified _Redfish_ device for conformance test:

An example command line to run:

    python RedfishServiceValidator.py -c config/example.ini

Modify the `config/example.ini` file to enter the system details, under the below sections. At a minimum, `ip` should be modified.

### [Tool]

Variable   | Type   | Definition
--         |--      |--
Version    | string | Internal config version (optional)
Copyright  | string | _DMTF_ copyright (optional)
verbose    | int    | level of verbosity (0-3) 

### [Host]

Variable         | Type    | Definition
--               |--       |--
ip               | string  | Host of testing system, formatted as https:// ip : port (can use http as well)
username         | string  | Username for Basic authentication
password         | string  | Password for Basic authentication (removed from logs)
description      | string  | Description of system being tested (optional)
forceauth        | boolean | Force authentication even on http servers
authtype         | string  | Authorization type (Basic | Session | Token | None)
token            | string  | Token string for Token authentication
ext_http_proxy   | string | URL of the HTTP proxy for accessing external sites
ext_https_proxy  | string | URL of the HTTPS proxy for accessing external sites
serv_http_proxy  | string | URL of the HTTP proxy for accessing the service
serv_https_proxy | string | URL of the HTTPS proxy for accessing the service

### [Validator]

Variable        | Type    | Definition
--              |--       |--
payload         | string  | Option to test a specific payload or resource tree (see below)
logdir          | string  | Place to save logs and run configs
oemcheck        | boolean | Whether to check Oem items on service
uricheck        | boolean | Allow URI checking on services below RedfishVersion 1.6.0
debugging       | boolean | Whether to print debug to log
schema_directory| string  | Where schema is located/saved on system
mockup          | string  | Enables insertion of local mockup resources to replace missing, incomplete, or incorrect implementations retrieved from the service that may hinder full validation coverage

### Payload options

The payload option takes two parameters as "option uri"

(Single, SingleFile, Tree, TreeFile)
How to test the payload URI given.  Single tests will only give a report on a single resource, while Tree will report on every link from that resource

([Filename], [uri])

URI of the target payload, or filename of a local file.

## Execution flow

1. `Redfish Service Validator` starts with the Service root Resource Schema by querying the service with the service root URI and getting all the device information, the resources supported and their links. Once the response of the Service root query is verified against its schema, the tool traverses through all the collections and Navigation properties returned by the service.
    * From the Metadata, collect all XML specified possible from the service, and store them in a tool-specified directory
2. For each navigation property/Collection of resource returned, it does following operations:
    * Reads all the Navigation/collection of resources from the respective resource collection schema file.
    * Reads the schema file related to the particular resource, collects all the information about individual properties from the resource schema file and stores them into a dictionary
    * Queries the service with the individual resource uri and validates all the properties returned against the properties collected from the schema file using a GET method making sure all the Mandatory properties are supported
3. Step 2 repeats until all of the URIs and resources are covered.

Upon validation of a resource, the following types of tests may occur:
* Upon reaching any resource, validate its @odata entries inside of its payload with regex.  If it fails, return a "failPayloadError".
* Attempt to initiate a Resource object, which requires an @odata.type and Schema of a valid JSON payload, otherwise return a "problemResource" or "exceptionResource" and terminate, otherwise "passGet"
* With the Resource initiated, begin to validate each Property available based on its Schema definition (sans annotations, additional props, is Case-Sensitive):
    * Check whether a Property is at first able to be nulled or is mandatory, and pass based on its Requirement or Nullability
    * For collections, validate each property inside of itself, and expects a list rather than a single Property, otherwise validate normally:
        * For basic types such as Int, Bool, DateTime, GUID, String, etc, check appropriate types, regex and ranges.
        * For Complex types, validate each property inside of the Complex, including annotations and additional properties
        * For Enum types, check and see if the given value exists in Schema's defined EnumType (Case-Sensitive)
        * For Entity types, check if the link given by @odata.id sends the client to an appropriate resource by the correct type, by performing a GET
* After reaching completion, perform the same routine with all Annotations available in the payload.
* If any unvalidated entries exist in the payload, determine whether or not additional properties are legitimate for this resource, otherwise throw a "failAdditional" error. 
 
## Conformance Logs - Summary and Detailed Conformance Report

The `Redfish Service Validator` generates an html report under the “logs” folder, named as ConformanceHtmlLog_MM_DD_YYYY_HHMMSS.html, along with a text and config file.  The report gives the detailed view of the individual properties checked, with the Pass/Fail/Skip/Warning status for each resource checked for conformance.

Additionally, there is a verbose log file that may be referenced to diagnose tool or schema problems when the HTML log is insufficient. 

## The Test Status

The test result for each GET operation will be reported as follows:
* PASS: If the operation is successful and returns a success code (E.g. 200, 204)
* FAIL: If the operation failed for reasons mentioned in GET method execution, or some configuration.
* SKIP: If the property or method being checked is not mandatory is not supported by the service.

## Limitations

`Redfish Service Validator` covers all the GET execution on the service. Below are certain points which are not in this scope.
* Patch/Post/Skip/Top/Head is not covered as part of `Redfish Service Validator` due to dependency on internal factor of the service.
* `Redfish Service Validator` does not cover testing of multiple service at once. To execute this, we have to re-run the tool by running it separately.
* Tool doesn't support @odata.context which use complex $entity path

## Building a Standalone Windows Executable

The module pyinstaller is used to package the environment as a standlone executable file; this can be installed with the following command:

    pip3 install pyinstaller

From a Windows system, the following command can be used to build a Windows executable file named `RedfishServiceValidator.exe`, which will be found in dist folder:

    pyinstaller -F -w -i redfish.ico -n RedfishServiceValidator.exe RedfishServiceValidatorGui.py

## Release Process

1. Go to the "Actions" page
2. Select the "Release and Publish" workflow
3. Click "Run workflow"
4. Fill out the form
5. Click "Run workflow"
