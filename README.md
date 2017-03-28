Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# Redfish Service Validator - Version 0.9

## About
The Redfish Service Validator is a python2.7 tool for checking conformance of any "device" with a Redfish service interface against Redfish CSDL schema.  The tool is designed to be device agnostic and is driven based on the Redfish specifications and schema intended to be supported by the device.

## Introduction
The Redfish Service Validator is an open source framework for checking conformance of any generic device with Redfish interface enabled against the DMTF defined Redfish schema and specifications. The tool is designed to be device agnostic and is driven purely based on the Redfish specifications intended to be supported by the device.

## Pre-requisites
The Redfish Service Validator is based on Python 2.7 and the client system is required to have the Python framework installed before the tool can be installed and executed on the system. Additionally, the following packages are required to be installed and accessible from the python environment:
* beautifulsoup4  - https://pypi.python.org/pypi/beautifulsoup4/4.1.3
* html  - https://pypi.python.org/pypi/html/
* requests  - https://github.com/kennethreitz/requests (Documentation is available at http://docs.python-requests.org/)

There is no dependency based on Windows or Linux OS. The result logs are generated in HTML format and an appropriate browser (Chrome, Firefox, IE, etc.) is required to view the logs on the client system.

## Installation
The RedfishServiceValidator.py into the desired tool root directory.  Create the following subdirectories in the tool root directory: "config", "logs", "SchemaFiles".  Place the example config.ini file in the "config" directory.  Place the CSDL Schema files to be used by the tool in the root of the schema directory, or the directory given in config.ini.

## Execution Steps
The Redfish Service Validator is designed to execute as a purely command line interface tool with no intermediate inputs expected during tool execution. However, the tool requires various inputs regarding system details, DMTF schema files etc. which are consumed by the tool during execution to generate the conformance report logs. Below are the step by step instructions on setting up the tool for execution on any identified Redfish device for conformance test:
* 1.	Modify the config\config.ini file to enter the system details under below section
[SystemInformation]
TargetIP = <<IPv4 address of the system under test>>
UserName = <<User ID of Administrator on the system>>
Password = <<Password of the Administrator>>
* 2.	The Tool has an option to ignore SSL certificate check if certificate is not installed on the client system. The certificate check can be switched on or off using the below parameter of the config.ini file. By default the parameter is set to ‘Off’.  UseSSL determines whether or not the https protocol is used.  If it is `Off`, it will also disable certification.
[Options]
UseSSL = <<On / Off>>
CertificateCheck = <<On / Off>>
* 3.	Other  attributes under the “[Options]” section have schema specific implementations as described below
GetOnlyMode - Only test properties that require GET responses, ignoring PATCH, PUT and other modifying requests.
MetadataFilePath – This attribute points to the location of the DMTF schema file location. This need not be modified and defaults to .\SchemaFiles\*
SystemState – This attribute value is used in specific schemas where Power or Reset actions are checked for conformance. Set this value to ‘On’ if system should be powered up after each test or ‘Off’ if system should be shut down after each test.
Session_UserName & Session_Password – These attributes are used to create a session in addition to the default UserName/Password combination available under [SystemInformation] section. Leave these attributes blank if only Administrator credentials are to be used for session specific tests.
* 4.	Once the above details are updated for the system under test, the Redfish Service Validator can be triggered from a command prompt by typing the below command:
[InstallationFolderPath]> Python RedfishConformanceTool_v1.py

## Execution flow
* 1.	Redfish Service Validator starts with the Service root Resource Schema by querying the service with the service root URI and getting all the device information, the resources supported and their links. Once the response of the Service root query is verified against its schema, the tool traverses through all the collections and Navigation properties returned by the service.
* 2.	For each navigation property/Collection of resource returned, it does following operations:
** i.	Reads all the Navigation/collection of resources from the respective resource collection schema file.
** ii.	Reads the schema file related to the particular resource, collects all the information about individual properties from the resource schema file and stores them into a dictionary
** iii.	Queries the service with the individual resource uri and validates all the properties returned against the properties collected from the schema file using a GET method making sure all the Mandatory properties are supported
** iv.	Validates the modification of properties for each writable using the PATCH method
* 3.	Step 2 repeats till all the URIs and resources are covered.
 
## GET method execution
For every property from service URI, the Redfish Service Validator performs the below operations:
* 1.	If resource schema specifies a property as required (Mandatory), the tool expects the property to be supported and returned by the service. Else, conformance check fails for that property. 
* 2.	If resource schema specifies a property as Nullable=false, the Redfish Service Validator expects the property to be retuned with some value and fails the conformance check if the service returns a NULL value 
* 3.	The Tool checks for the conformance of data type for every property against resource schema file. For ex. If property data type is “edm.Boolean” in resource schema file, and the service returns a string, conformance check will fail for that property.
* 4.	If a property is an optional one and it is not supported by the service, the conformance check skips the property. The same will be reported as a ‘SKIP’ in the conformance report
* 5.	The GET method will Pass the test if the status code returned is 200 or 204

## PATCH method execution
For every property that is a read/write, the tool will perform the following operations:
* 1.	Redfish Service Validator checks the values supported for each property. If specified, it picks a value from the list to configure the property. If supported values are not specified, the tool generated a value based on the data type and performs the PATCH operation   
* 2.	A PATCH operation is reported as success if status code returned is 200/204, else the result for that operation is reported as FAIL. If the status code for the PATCH operation is 400/405, the result will be WARNING.
* 3.	Once status code is successful, tool cross verifies whether the new value is configured successfully. If yes, result will be reported as PASS else as WARNING.
* 4.	Once the PATCH operation is completed, the tool resets the property to the original value.

## Conformance Logs – Summary and Detailed Conformance Report
The Redfish Service Validator generates 2 distinct reports under the “logs” folder, named as <ConformanceTestSummary_MM_DD_YYYY_HHMMSS.html> and <ConformanceTestDetailedResult_ MM_DD_YYYY_HHMMSS.html>. The Summary Report has summarized details about the system IP under test, User and timestamp of execution along with the list of Resources checked with Pass/Fail/Skipped conformance numbers. The Detailed Report gives the detailed view of the individual properties checked, with the Pass/Fail/Skip/Warning status for each resource checked for conformance.

## The Test Status
The test result for each GET and PATCH operation will be reported as follows:
* PASS: If the operation is successful and returns a success code (E.g. 200, 204)
* FAIL: If the operation failed for reasons mentioned in GET and PATCH method execution.
* SKIP: If the property or method being checked is not mandatory is not supported by the service.
* WARNING: If the operation returned a success but the change is not reflected. This can be the case when a manual intervention such as a power cycle is required to complete the action.

## Limitations
Redfish Service Validator covers all the GET, PATCH execution on the service. Below are certain points which are not in this scope.
* 1.	Post/Skip/Top/Head is not covered as part of Redfish Service Validator due to dependency on internal factor of the service.
* 2.	Redfish Service Validator does not cover testing of multiple service at once. To execute this, we have to re-run the tool by running it separately.
* 3.	Redfish Service Validator execution may fail if certain PATCH method impacts directly or indirectly on the execution by changing parameters like account lock, NIC configuration settings etc.
* 4.	Redfish Service Validator skips the PATCH for username, password, HTTP related attributes which may impact tool execution to halt.
* 5.	Redfish Service Validator does check all the attributes from the resource schema but it will not check the existence of Navigation property with respect to resource schema. It does continue with the links if it exist.

