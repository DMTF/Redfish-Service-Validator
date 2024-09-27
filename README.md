Copyright 2016-2024 DMTF.  All rights reserved.

# Redfish Service Validator

## About

The Redfish Service Validator is a Python3 tool for checking conformance of any "device" with a Redfish interface against Redfish CSDL schema.
The tool is designed to be device-agnostic and is driven based on the Redfish specifications and schema intended to be supported by the device.

## Installation


From PyPI:

    pip install redfish_service_validator

From GitHub:

    git clone https://github.com/DMTF/Redfish-Service-Validator.git
    cd Redfish-Service-Validator
    python setup.py sdist
    pip install dist/redfish_service_validator-x.x.x.tar.gz

## Requirements

External modules:

* beautifulsoup4  - https://pypi.python.org/pypi/beautifulsoup4
* requests  - https://github.com/kennethreitz/requests (Documentation is available at http://docs.python-requests.org/)
* lxml - https://pypi.python.org/pypi/lxml

You may install the prerequisites by running:

    pip3 install -r requirements.txt

If you have a previous beautifulsoup4 installation, use the following command:

    pip3 install beautifulsoup4 --upgrade

There is no dependency based on Windows or Linux OS.
The result logs are generated in HTML format and an appropriate browser, such as Chrome, Firefox, or Edge, is required to view the logs on the client system.

## Usage

Example usage without providing a configuration file:

    rf_service_validator -u root -p root -r https://192.168.1.1

Example usage with a configuration file:

    rf_service_validator -c config/example.ini

The following sections describe the arguments and configuration file options.
The file `config/example.ini` can be used as a template configuration file.
At a minimum, the `ip`, `username`, and `password` options must be modified.

### [Tool]

| Variable   | CLI Argument  | Type    | Definition |
| :---       | :---          | :---    | :---       |
| `verbose`  | `-v`          | integer | Verbosity of tool in stdout; 0 to 3, 3 being the greatest level of verbosity. |

### [Host]

| Variable           | CLI Argument         | Type    | Definition |
| :---               | :---                 | :---    | :---       |
| `ip`               | `-r`                 | string  | The address of the Redfish service (with scheme); example: 'https://123.45.6.7:8000'. |
| `username`         | `-u`                 | string  | The username for authentication. |
| `password`         | `-p`                 | string  | The password for authentication. |
| `description`      | `--description`      | string  | The description of the system for identifying logs; if none is given, a value is produced from information in the service root. |
| `forceauth`        | `--forceauth`        | boolean | Force authentication on unsecure connections; 'True' or 'False'. |
| `authtype`         | `--authtype`         | string  | Authorization type; 'None', 'Basic', 'Session', or 'Token'. |
| `token`            | `--token`            | string  | Token when 'authtype' is 'Token'. |
| `ext_http_proxy`   | `--ext_http_proxy`   | string  | URL of the HTTP proxy for accessing external sites. |
| `ext_https_proxy`  | `--ext_https_proxy`  | string  | URL of the HTTPS proxy for accessing external sites. |
| `serv_http_proxy`  | `--serv_http_proxy`  | string  | URL of the HTTP proxy for accessing the service. |
| `serv_https_proxy` | `--serv_https_proxy` | string  | URL of the HTTPS proxy for accessing the service. |

### [Validator]

| Variable           | CLI Argument         | Type    | Definition |
| :---               | :---                 |:--------| :---       |
| `payload`          | `--payload`          | string  | The mode to validate payloads ('Tree', 'Single', 'SingleFile', or 'TreeFile') followed by resource/filepath; see below. |
| `logdir`           | `--logdir`           | string  | The directory for generated report files; default: 'logs'. |
| `oemcheck`         | `--nooemcheck`       | boolean | Whether to check OEM items on service; 'True' or 'False'. |
| `uricheck`         | `--uricheck`         | boolean | Allow URI checking on services below RedfishVersion 1.6.0; 'True' or 'False'. |
| `debugging`        | `--debugging`        | boolean | Output debug statements to text log, otherwise it only uses INFO; 'True' or 'False'. |
| `schema_directory` | `--schema_directory` | string  | Directory for local schema files. |
| `mockup`           | `--mockup`           | string  | Directory tree for local mockup files.  This option enables insertion of local mockup resources to replace missing, incomplete, or incorrect implementations retrieved from the service that may hinder full validation coverage. |
| `collectionlimit`  | `--collectionlimit`  | string  | Sets a limit to links gathered from collections by type (schema name).<br/>Example 1: `ComputerSystem 20` limits ComputerSystemCollection to 20 links.<br/>Example 2: `ComputerSystem 20 LogEntry 10` limits ComputerSystemCollection to 20 links and LogEntryCollection to 10 links. |
| `requesttimeout`   | `--requesttimeout`   | integer | Timeout in seconds for HTTP request waiting for response. |
| `requestattempts`  | `--requestattempts`  | integer | Number of attempts after failed HTTP requests. |

### Payload Option

The `payload` option takes two parameters as strings.

The first parameter specifies how to test the payload URI given, which can be 'Single', 'SingleFile', 'Tree', or 'TreeFile'.
'Single' and 'SingleFile' will test and give a report on a single resource.
'Tree' and 'TreeFile' will test and give a report on the resource and every link from that resource.

The second parameter specifies a URI of the target payload to test or a filename of a local file to test.

For example, `--payload Single /redfish/v1/AccountService` will perform validation of the URI `/redfish/v1/AccountService` and no other resources.

### Mockup Option

The `mockup` option takes a single parameter as a string.  The parameter specifies a local directory path to the `ServiceRoot` resource of a Redfish mockup tree.

This option provides a powerful debugging tool as is allows local "mockup" JSON payloads to replace those retreived from the unit under test.  This can aid testers by allowing the tool to skip over problematic resources, which may cause the tool to crash, or more likely, miss portions of the implemented resources due to missing or invalid link properties or values.

The mockup files follow the Redfish mockup style, with the directory tree matching the URI segments under /redfish/v1, and with a single `index.json` file in each subdirectory as desired.  For examples of full mockups, see the Redfish Mockup Bundle (DSP2043) at https://www.dmtf.org/sites/default/files/standards/documents/DSP2043_2024.1.zip.

Populate the mockup directory tree with `index.json` files wherever problematic resources need to be replaced.  Any replaced resource will report a Warning in the report to indicate a workaround was used.

## Execution Flow

1. The Redfish Service Validator starts by querying the service root resource from the target service and collections information about the service.
    * Collects all CSDL from the service.
2. For each resource found, it performs the following:
    * Reads all the URIs referenced in the resource.
    * Reads the schema file related to the particular resource and builds a model of expected properties.
    * Tests each property in the resource against the model built from the schema.
3. Step 2 repeats until all resources are covered.

When validating a resource, the following types of tests may occur for each property:

* Verify `@odata` properties against known patterns, such as `@odata.id`.
* Check if the property is defined in the resource's schema.
* Check if the value of the property matches the expected type, such as integer, string, boolean, array, or object.
* Check if the property is mandatory.
* Check if the property is allowed to be `null`.
* For string properties with a regular expression, check if the value passes the regular expression.
* For enumerations, check if the value is within the enumeration list.
* For numeric properties with defined ranges, check if the value is within the specified range.
* For object properties, check the properties inside the object againt the object's schema definition.
* For links, check that the URI referenced matches the expected resource type.

CSDL syntax errors will cause testing to halt and move on to other resources.
The OData CSDL Validator (https://github.com/DMTF/Redfish-Tools/tree/main/odata-csdl-validator) can be used to identify schema errors prior to testing.

## Conformance Logs - Summary and Detailed Conformance Report

The Redfish Service Validator generates an HTML report under the 'logs' folder and is named as 'ConformanceHtmlLog_MM_DD_YYYY_HHMMSS.html', along with a text and config file.
The report gives the detailed view of the individual properties checked, with pass, fail, skip, or warning status for each resource checked for conformance.

Additionally, there is a verbose text log file that may be referenced to diagnose tool or schema problems when the HTML log is insufficient. 

## The Test Status

The test result for each GET operation will be reported as follows:

* PASS: If the operation is successful and returns a success code, such as `200 OK`.
* FAIL: If the operation failed for reasons mentioned in GET method execution, or some configuration.
* SKIP: If the property or method being checked is not mandatory is not supported by the service.

## Limitations

The Redfish Service Validator only performs GET operations on the service.
Below are certain items that are not in scope for the tool.

* Other HTTP methods, such as PATCH, are not covered.
* Query parameters, such as $top and $skip, are not covered.
* Multiple services are not tested simultaneously.

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
