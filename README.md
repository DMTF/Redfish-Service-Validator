Copyright 2016-2025 DMTF.  All rights reserved.

# Redfish Service Validator

## About

The Redfish Service Validator is a Python3 tool for checking conformance of any Redfish service against Redfish CSDL schema.
The tool is designed to be implementation-agnostic and is driven based on the Redfish specifications and schema.
The scope of this tool is to only perform GET requests and verify their respective responses.

## Installation

From PyPI:

    pip install redfish_service_validator

From GitHub:

    git clone https://github.com/DMTF/Redfish-Service-Validator.git
    cd Redfish-Service-Validator
    python setup.py sdist
    pip install dist/redfish_service_validator-x.x.x.tar.gz

## Requirements

The Redfish Service Validator requires Python3.

Required external packages:

```
redfish>=3.1.5
requests
colorama
```

If installing from GitHub, you may install the external packages by running:

    pip install -r requirements.txt

## Usage

```
usage: rf_service_validator [-h] --user USER --password PASSWORD --rhost RHOST
                            [--authtype {Basic,Session}]
                            [--ext_http_proxy EXT_HTTP_PROXY]
                            [--ext_https_proxy EXT_HTTPS_PROXY]
                            [--serv_http_proxy SERV_HTTP_PROXY]
                            [--serv_https_proxy SERV_HTTPS_PROXY]
                            [--logdir LOGDIR]
                            [--schema_directory SCHEMA_DIRECTORY]
                            [--payload PAYLOAD PAYLOAD] [--mockup MOCKUP]
                            [--collectionlimit COLLECTIONLIMIT [COLLECTIONLIMIT ...]]
                            [--nooemcheck] [--debugging]

Validate Redfish services against schemas; Version 3.0.0

options:
  -h, --help            show this help message and exit
  --user USER, -u USER, -user USER, --username USER
                        The username for authentication
  --password PASSWORD, -p PASSWORD
                        The password for authentication
  --rhost RHOST, -r RHOST, --ip RHOST, -i RHOST
                        The address of the Redfish service (with scheme)
  --authtype {Basic,Session}
                        The authorization type
  --ext_http_proxy EXT_HTTP_PROXY
                        The URL of the HTTP proxy for accessing external sites
  --ext_https_proxy EXT_HTTPS_PROXY
                        The URL of the HTTPS proxy for accessing external
                        sites
  --serv_http_proxy SERV_HTTP_PROXY
                        The URL of the HTTP proxy for accessing the Redfish
                        service
  --serv_https_proxy SERV_HTTPS_PROXY
                        The URL of the HTTPS proxy for accessing the Redfish
                        service
  --logdir LOGDIR, --report-dir LOGDIR
                        The directory for generated report files; default:
                        'logs'
  --schema_directory SCHEMA_DIRECTORY
                        Directory for local schema files; default:
                        'SchemaFiles'
  --payload PAYLOAD PAYLOAD
                        Controls how much of the data model to test; option is
                        followed by the URI of the resource from which to
                        start
  --mockup MOCKUP       Path to directory containing mockups to override
                        responses from the service
  --collectionlimit COLLECTIONLIMIT [COLLECTIONLIMIT ...]
                        Applies a limit to testing resources in collections;
                        format: RESOURCE1 COUNT1 RESOURCE2 COUNT2 ...
  --nooemcheck          Don't check OEM items
  --debugging           Controls the verbosity of the debugging output; if not
                        specified only INFO and higher are logged
```


Example:

    rf_service_validator -r https://192.168.1.100 -u USERNAME -p PASSWORD

### Payload Option

The `payload` option controls how much of the data model to test.
It takes two parameters as strings.

The first parameter specifies the scope for testing the service.
`Single` will test a specified resource.
`Tree` will test a specified resource and every subordinate URI discovered from it.

The second parameter specifies the URI of a resource to test.

Example: test `/redfish/v1/AccountService` and no other resources.

    `--payload Single /redfish/v1/AccountService`

Example: test `/redfish/v1/Systems/1` and all subordinate resources.

    `--payload Tree /redfish/v1/Systems/1`

### Mockup Option

The `mockup` option allows a tester to override responses from the service with a local mockup.
This allows a tester to debug and provide local fixes to resources without needing to rebuild the service under test.

This option takes a single string parameter.
The parameter specifies a local directory path to the `ServiceRoot` resource of a Redfish mockup tree.

The mockup files follow the Redfish mockup style, with the directory tree matching the URI segments under `/redfish/v1`, and with a single `index.json` file in each subdirectory as desired.
For examples of full mockups, see the Redfish Mockup Bundle (DSP2043) at https://www.dmtf.org/sites/default/files/standards/documents/DSP2043_2024.1.zip.

Populate the mockup directory tree with `index.json` files wherever problematic resources need to be replaced.
Any replaced resource will report a Warning in the report to indicate a workaround was used.

### Collection Limit Option

The `collectionlimit` option allows a tester to limit the number of collection members to test.
This is useful for large collections where testing every member does not provide enough additional test coverage to warrant the increased test time.

This option takes pairs of arguments where the first argument is the resource type to limit and the second argument is the maximum number of members to test.
Whenever a resource collection for the specified resource type is encountered during testing, the validator will only test up to the specified number of members.

If this option is not specified, the validator defaults to applying a limit of 20 members to LogEntry resources.

Example: do not test more than 10 `Sensor` resources and 20 `LogEntry` resources in a given collection

    `--collectionlimit Sensor 10 LogEntry 20`

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
