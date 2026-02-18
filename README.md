# Redfish Service Validator

Copyright 2016-2025 DMTF.  All rights reserved.

[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md)
[![PyPI](https://img.shields.io/pypi/v/redfish-service-validator)](https://pypi.org/project/redfish-service-validator/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg?style=flat)](https://github.com/psf/black)
[![GitHub stars](https://img.shields.io/github/stars/DMTF/Redfish-Service-Validator.svg?style=flat-square&label=github%20stars)](https://github.com/DMTF/Redfish-Service-Validator)
[![GitHub Contributors](https://img.shields.io/github/contributors/DMTF/Redfish-Service-Validator.svg?style=flat-square)](https://github.com/DMTF/Redfish-Service-Validator/graphs/contributors)

## About

The Redfish Service Validator is a Python3 tool for checking conformance of any Redfish service against Redfish CSDL schema.
The tool is designed to be implementation-agnostic and is driven based on the Redfish specifications and schema.
The scope of this tool is to only perform `GET` requests and verify their respective responses.

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

Validate Redfish services against schemas

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
For examples of full mockups, see the Redfish Mockups Bundle (DSP2043) at https://www.dmtf.org/dsp/DSP2043.

Populate the mockup directory tree with `index.json` files wherever problematic resources need to be replaced.
Any replaced resource will report a warning in the report to indicate a workaround was used.

### Collection Limit Option

The `collectionlimit` option allows a tester to limit the number of collection members to test.
This is useful for large collections where testing every member does not provide enough additional test coverage to warrant the increased test time.

This option takes pairs of arguments where the first argument is the resource type to limit and the second argument is the maximum number of members to test.
Whenever a resource collection for the specified resource type is encountered during testing, the validator will only test up to the specified number of members.

If this option is not specified, the validator defaults to applying a limit of 20 members to LogEntry resources.

Example: do not test more than 10 `Sensor` resources and 20 `LogEntry` resources in a given collection

    `--collectionlimit Sensor 10 LogEntry 20`

## Test Results: Types of Errors and Warnings

This section details the various types of error or warning messages that the tool can produce as a result of the testing process.

### Resource Error

Indicates the validator was unable to receive a proper response from the service.  There are several reasons this can happen.

* A network error occurred when performing a `GET` operation to access the resource.
* The service returned a non-200 HTTP status code for the `GET` request.
* The `GET` response for the resource did not return a JSON document, or the JSON document was invalid.

### Schema Error

Indicates the validator was not able to locate the schema definition for the resource, object, or action.  There are several things to check in these cases.

For objects and resources, ensure the `@odata.type` property contains the correct value.
`@odata.type` is a string formatted as `#<Namespace>.<TypeName>`.

For actions, ensure the name of the action is correct.
Action names are formatted as `#<Namespace>.<ActionName>`.

Ensure all necessary schema files are available to the tool.
By default, the validator will attempt to download the latest DSP8010 bundle from the DMTF's publication site to cover standard definitions.
A valid download location for any OEM extensions need to be specified in the service at the `/redfish/v1/$metadata` URI so the validator is able to download and resolve these definitions.

For OEM extensions, verify the construction of the OEM schema is correct.

### Object Type Error

Indicates the service is not using the correct data type for an object.

This can happen when the service specifies an `@odata.type` value that doesn't match what's permitted by the schema definition.
For example, if the schema calls out `Resource.Status` for the common status object, but the service is attempting to overload it with `Resource.Location`.

This can also happen when an OEM object is not defined properly.
All OEM objects are required to be defined with the `ComplexType` definition in CSDL and specify `Resource.OemObject` as its base type.

### Allowed Method Error

Indicates an incorrect method, according to the schema definition, is shown as supported for the resource in the value of the `Allow` header.
For example, if a `ComputerSystem` resource contains `POST` in its `Allow` header.  This is not allowed per the schema definition.

Each schema file contains allowable capabilities for the resource.

* `Capabilities.InsertRestrictions` shows if `POST` is allowed.
* `Capabilities.UpdateRestrictions` shows if `PATCH` and `PUT` are allowed.
* `Capabilities.DeleteRestrictions` shows if `DELETE` is allowed.

### Copyright Annotation Error

Indicates the resource contains the `@Redfish.Copyright` annotation.
This term is only allowed in mockups.
Live services are not permitted to use this term.

### Unknown Property Error

Indicates a property is not defined in the schema definition for the resource or object.

* Check that the spelling and casing of the letters in the property are correct.
* Check that the version of the resource or object is correct.
* For excerpts, check that the property is allowed in the excerpt usage.

### Required Property Error

Indicates a property is marked in the schema as required, using the `Redfish.Required` annotation, but the response does not contain the property.

### Property Type Error

Indicates the property is using an incorrect data type.
Some examples:

* An array property contains a single value, not contained as a JSON array.  For example, "Blue" instead of ["Blue"]
* An object property contains a string, as if it was a simple property, not a JSON object.
* A string property contains a number.  For example, `5754` instead of `"5754"`.

### Unsupported Action Error

Indicates the validator was able to locate the action definition, but the action is not supported by the resource.

For standard actions, ensure the action belongs to the matching resource.
For example, it's not allowed to use `#ComputerSystem.Reset` in a `Manager` resource.

For standard actions, ensure the resource's version, as specified in `@odata.type` is high enough for the action.
For example, the `#ComputerSystem.Decommission` action was added in version 1.21.0 of the `ComputerSystem` schema, so the version of the resource needs to be 1.21.0 or higher.

### Action URI Error

Indicates the URI for performing the action, specified by the `target` property, is not constructed properly.

For standard actions, the 'POST (action)' clause of the Redfish Specification dictates action URIs take the form of `<ResourceURI>/Actions/<QualifiedActionName>`, where:

* `<ResourceURI>` is the URI of the resource that supports the action.
* `<QualifiedActionName>` is the qualified name of the action, including the resource type.

For OEM actions, the 'OEM actions' clause of the Redfish Specification dictates OEM action URIs take the form of `<ResourceURI>/Actions/Oem/<OEMSchemaName>.<Action>`, where:

* `<ResourceURI>` is the URI of the resource that supports invoking the action.
* `<OEMSchemaName>.<Action>` is the name of the schema containing the OEM extension followed by the action name.

### Null Error

Indicates an unexpected usage of `null`, or `null` was the expected property value.

* Check the nullable term on the property in the schema definition to see if `null` is allowed.
* Properties with write-only permissions, such as `Password`, are required to be `null` in responses.

### Reference Object Error

Indicates a reference object is not used properly.
Reference objects provide links to other resources.
Each reference object contains a single `@odata.id` property to link to another resource.

* Ensure that only `@odata.id` is present in the object.  No other properties are allowed.
* Ensure the URI specified by `@odata.id` is valid and references a resource of the correct type.

### Undefined URI Error

Indicates the URI of the resource is not listed as a supported URI in the schema file for the resource.
To conform with the 'Resource URI patterns annotation' clause of the Redfish Specification, URIs are required to match the patterns defined for the resource.

### Invalid Identifier Error

Indicates either `Id` or `MemberId` do not contain expected values as defined by the 'Resource URI patterns annotation' clause of the Redfish Specification.
For `Id` properties, members of resource collections are required to use the last segment of the URI for the property value.
For `MemberId` properties in referenceable member objects, the value is required to be the last segment of the JSON property path to the object.

### JSON Pointer Error

Indicates the `@odata.id` property for a referenceable member object does not contain a valid JSON pointer.
To conform with the 'Universal Resource Identifiers' clause of the Redfish Specification, `@odata.id` is expected to contain an RFC6901-defined URI fragment that points to the object in the payload.

### Property Value Error

Indicates that a string property does not contain a valid value as defined in the schema for that property.

Some properties specify a regular expression or a regular expression is inferred based on the data type of the property.
Ensure the value matches the regular expression requirements.
Date-time and duration properties need to follow ISO8601 requirements.

Some properties are defined as enumerations with a set of allowed values.
Ensure the value belongs to the enumeration list for the property.
Check that the spelling and casing of the letters of the value are correct.
Check that the version of the resource is high enough for the value.

### Numeric Range Error

Indicates that a numeric property is out of range based on the definition in the schema for that property.
The `Redfish.Minimum` and `Redfish.Maximum` annotations of the property define the bounds for the range.

### Trailing Slash Warning

Indicates the URI contains a trailing slash.
To conform with the 'Resource URI patterns annotation' clause of the Redfish Specification, trailing slashes are not expected, except for `/redfish/v1/`.

### Deprecated URI Warning

Indicates the URI is valid, but marked as deprecated in the schema of the resource.
Unless needed for supporting existing clients, it's recommended to use the replacement URI.

### Undefined URI Warning

Indicates the URI of the resource is not defined in the schema file for the resource, but is being used in an OEM-manner.
To conform with the 'Resource URI patterns annotation' clause of the Redfish Specification, URIs are required to match the patterns defined for the resource.
OEM usage of standard resources is permitted, but it's expected that the schema is updated to include the OEM usage, as allowed by the 'Schema modification rules' clause of the Redfish Specification.

### Deprecated Value Warning

Indicates that a string property is using a deprecated enumeration value.
Unless needed for supporting existing clients, it's recommended to use the replacement value as specified in the schema.

### Empty String Warning

Indicates a read-only string is empty and removing the property should be considered.
For example, it's better to remove a property like `SerialNumber` entirely if the resource does not support reporting a serial number rather than using an empty string.

### Deprecated Property Warning

Indicates the property is deprecated.
Unless needed for supporting existing clients, it's recommended to use the replacement property.

### Mockup Used Warning

Indicates the resource that was tested used response data from a mockup that was provided by the `--mockup` argument.

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
