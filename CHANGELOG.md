# Change Log

## [2.4.9] - 2024-09-27
- Added 'requesttimeout' and 'requestattempts' arguments

## [2.4.8] - 2024-07-26
- Fixed link verification to ensure the linked resource is of the expected data type
- Fixed usage of collection limiting to apply limits for all aspects of validation
- Fixed URI cache handling for nested JSON objects that contain URI fragments

## [2.4.7] - 2024-06-28
- Corrected handling of 'collectionlimit' when specified in a config file

## [2.4.6] - 2024-06-14
- Hide password and token parameters from console output when running the tool from a config file

## [2.4.5] - 2024-05-10
- Updated action testing to allow for '@Redfish.AllowablePattern' and '@Redfish.AllowableNumbers' annotations on action parameters

## [2.4.4] - 2024-05-03
- Added test to ensure write-only properties are null in responses

## [2.4.3] - 2024-04-12
- Reduced severity of missing schema for an action from error to warning to be consistent with other warnings

## [2.4.2] - 2024-03-22
- Made corrections to skipping OEM checks when '--nooemcheck' is specified

## [2.4.1] - 2024-02-09
- Added 'collectionlimit' argument to limit the number of entries checked in a collection

## [2.4.0] - 2024-01-26
- Added missing break out of object schema mapping if discovered property is not an object

## [2.3.9] - 2024-01-19
- Minor changes to fix Python 3.12 warnings with usage of raw strings
- Added warning and failure totals

## [2.3.8] - 2023-11-03
- Added breakout condition when tracing a definition's type tree to prevent hangs due to invalid schemas with type loops

## [2.3.7] - 2023-10-06
- Added exception handling when traversing links if the schema definition for the link is invalid

## [2.3.6] - 2023-09-22
- Updated regex used to determine if a property is an array to not collide with the collection capabilities term

## [2.3.5] - 2023-09-08
- Made change to allow for action names to be annotated

## [2.3.4] - 2023-08-11
- Corrected array testing to show errors when array properties are not represented as arrays and vice versa

## [2.3.3] - 2023-08-04
- Added check to ensure the '@odata.id' value is a string before trying to follow the link

## [2.3.2] - 2023-07-14
- Corrected the usage of return values for script entry points

## [2.3.1] - 2023-04-21
- Corrected object mapping logic to handle cases where a common base definition is used for multiple object definitions

## [2.3.0] - 2023-03-17
- Corrected the regex pattern for duration properties to not allow for negative durations
- Added validation of action name in responses against the action definitions in schema

## [2.2.9] - 2023-03-10
- Added handling of cases where a payload annotation's definition cannot be located in schema files

## [2.2.8] - 2023-03-03
- Added deprecated version info to results

## [2.2.7] - 2023-02-16
- Corrected URI checking for resources referenced by payload annotations

## [2.2.6] - 2023-02-14
- Additional fixes to 'Id' property validation with the URI of the resource

## [2.2.5] - 2023-02-13
- Made fixes to 'Id' property validation with the URI of the resource

## [2.2.4] - 2023-02-05
- Added validation of the last segment of the URI to ensure it matches the Id property or MemberId property where appropriate

## [2.2.3] - 2023-01-27
- Added checking for the presence of '@odata.id' at the root of resources and referenceable members
- Corrected return code from the script to show failures

## [2.2.2] - 2022-11-07
- Removed certificate checks when downloading schema files referenced by the service

## [2.2.1] - 2022-08-12
- Corrected link traversal logic when objects or arrays of objects are 'null'

## [2.2.0] - 2022-08-05
- Removed conditional import statements

## [2.1.9] - 2022-07-28
- Fixed import statement in schema pack module

## [2.1.8] - 2022-07-22
- Modified project for PyPI publication

## [2.1.8] - 2022-07-22
- Modified project for PyPI publication

## [2.1.8] - 2022-07-22
- Modified project for PyPI publication

## [2.1.8] - 2022-07-22
- Modified project for PyPI publication

## [2.1.7] - 2022-07-15
- Added check to on URIs for validation for external reference to ensure it does not go through the Redfish library
- Added scrollbars to the 'Edit Config' window
- Added check to ensure an action is shown in the response as an object before trying to discover if it has action info

## [2.1.6] - 2022-05-19
- Added shebang statements at the beginning of the tool in order to execute it directly
- Added support for verifying the data type of '@odata.count' annotations
- Minor enhancements to debug statements

## [2.1.5] - 2022-04-08
- Added check to ensure array properties are returned as arrays before iterating over their values
- Added context-driven pattern checking for 'DurableName'
- Added proxy arguments for controlling proxy usage with external sites and the service

## [2.1.4] - 2022-04-01
- Corrected parent reference to allow for '@odata.id' testing on referenceable members
- Extended argument usage to allow for argument forms used in other tools, such as 'rhost' instead of 'ip'

## [2.1.3] - 2022-03-25
- Corrected order of operations for initializing the tool to collect additional schema files from $metadata before building the data model for payload validation
- Suppress warning messages for deprecated properties when the property is also marked as required
- Added support for Unix sockets

## [2.1.2] - 2022-03-21
- Added '--mockup' option to override payloads from a service with a mockup in a directory
- Added support for ensuring properties that are JSON objects that are marked as 'required' are present in payloads

## [2.1.1] - 2022-03-04
- Added check to ensure a reference object is an object prior to attempting to extract the link information

## [2.1.0] - 2022-02-05
- Added 'Accept-Encoding' header to allow for any encoding in responses
- Corrected '@odata.id' inspection to not crash the tool if the string is empty

## [2.0.9] - 2022-01-14
- Removed statements that prevented building models for objects contained within OEM extensions
- Some configuration fixes for handling '--nooemcheck'

## [2.0.8] - 2022-01-10
- Several enhancements and fixes to CSV handling

## [2.0.7] - 2021-12-01
- Corrected validation of null objects
- Added checks to ensure URIs match patterns defined in schema
- Added checks to ensure the 'Allow' HTTP header does not go beyond the capabilities definitions in schema
- Added validation of registries if discovered via the 'Uri' property in 'MessageRegistryFile' resources

## [2.0.6] - 2021-10-27
- Corrected use of iterators to be compatible with versions of Python older than 3.8

## [2.0.5] - 2021-10-15
- Corrected namespace referencing for objects nested in objects

## [2.0.4] - 2021-10-04
- Updated schema pack link to point to the latest DSP8010 bundle

## [2.0.3] - 2021-09-07
- Refactored code to make schema parsing and structure building for resource definitions to be modular

## [2.0.2] - 2021-08-30
- Corrected usage of the 'oemcheck' flag to not skip over OEM object validation when enabled

## [2.0.1] - 2021-08-09
- Various fixes from previous changes to refactor the arguments with the tool

## [2.0.0] - 2021-08-06
- Significant changes to the CLI arguments with the tool to reduce complexity for users
- Added support for validating excerpts

## [1.4.1] - 2021-06-18
- Modified calls to requests package to reuse HTTP sessions for better performance

## [1.4.0] - 2021-04-16
- Fixed 'is' and 'is not' comparisions that are not allowed in Python3.8+

## [1.3.9] - 2020-09-16
- Several fixes in handling of detection of a proper version of a JSON object within a resource

## [1.3.8] - 2020-07-06
- Added exception in link validation for `Resource.Resource` to allow for any type of resource to be found

## [1.3.7] - 2020-06-13
- Additional fixes to handling of version detection of resources

## [1.3.6] - 2020-05-15
- Corrected handling of version detection of resources

## [1.3.5] - 2020-03-21
- Added more descriptive text to `@odata.type` format errors
- Downgraded `@odata.context` format errors to warnings

## [1.3.4] - 2019-11-08
- Fixed handling of null objects in arrays of objects

## [1.3.3] - 2019-11-01
- Additional fixes for handling schema version checking

## [1.3.2] - 2019-10-18
- Clarified error message when a JSON pointer in an `@odata.id` property is invalid
- Fixed some handling of properties than cannot be resolved in order to have better error messages
- Enhanced schema version checking to allow for double digits

## [1.3.1] - 2019-08-09
- Added special handling with `OriginOfCondition` to allow for the Resource to not exist

## [1.3.0] - 2019-07-19
- Downgraded messages related to not finding `@odata.type` within nested objects of a resource
- Fixed parent validation for registry resources

## [1.2.9] - 2019-06-28
- Added special handling with `EventDestination` to allow for `HttpHeaders` to be null per description in the schema
- Made change to make `@odata.context` optional in responses

## [1.2.8] - 2019-05-31
- Updated schema bundle reference to 2019.1
- Improved error messages for GET failures
- Removed warnings for @odata.etag properties
- Removed deprecated StopIteration exception

## [1.2.7] - 2019-04-26
- Added enhancement to verify `@odata.id` is present when following a navigation property

## [1.2.6] - 2019-04-11
- Added missing @odata.context initialization for Message Registries
- Fix to counter for reference links ending in trailing slash

## [1.2.5] - 2019-02-01
- Updated schema bundle reference to 2018.3
- Fixed handling of Edm.Duration
- Fixed handling of Redfish.Revision term

## [1.2.4] - 2018-11-09
- Fixed check for empty strings to only report warnings if the property is writable
- Added JSON output to expandable tag in the HTML report
- Cleanup of the summary section of the HTML report

## [1.2.3] - 2018-10-19
- Fixed regex usage when verifying URIs

## [1.2.2] - 2018-10-11
- Added automatic file caching of schemca pulled from the DMTF website and the Service
- Added proper error message for navigating links to Entities with incorrect types
- Added logic to verify that an @odata.id property with a JSON fragment resolves properly
- Updated current schema pack zip to 2018.2
- Fixed missing default option for usessl

## [1.2.1] - 2018-10-04
- Made fix to send traceback to debug logging only, not to HTML report

## [1.2.0] - 2018-09-21
- Added option to enable/disable protocol version checking
- Various cleanup to error messages

## [1.1.9] - 2018-09-14
- Added fixes to OEM checks
- Added support for URI checking as an option with the tool

## [1.1.8] - 2018-09-07
- Added additional sanity checking for managing cases where a type cannot be found

## [1.1.7] - 2018-08-31
- Added support for following `@odata.id` reference for auto expanded resources
- Added handling for trying to resolve the proper schema file if it's not found
- Added support for following `@odata.nextLink` in collections
- Added handling for resolving the proper ComplexType version based on the reported `@odata.type` value for the a resource
- Added case insensitive checking on invalid properties for giving hints in error messages
- Added warnings for empty strings in payloads if the property is read only
- Added hints in error messages for unknown properties
- Added hint in the error message for enum values if the service returns the string "null" rather than the JSON value null

## [1.1.6] - 2018-08-17
- Fixed several cases where exception tracebacks were being printed in the output

## [1.1.5] - 2018-08-03
- Added missing start session
- Added exceptions for bad credentials
- Modified the report output to improve readability
- Refactor areas of code to enable automated unit testing

## [1.1.4] - 2018-07-06
- Additional fixes to OEM object handling within Actions

## [1.1.3] - 2018-06-29
- Fixed annotations being treated as unknown properties
- Fixed handling of dynamic properties patterns that was introduced as part of the OEM object validation

## [1.1.2] - 2018-06-22
- Added support for verifying OEM objects in responses

## [1.1.1] - 2018-06-01
- Added option to force authentication if using an unsecure connection
- Added error checking for @Redfish.Copyright in payloads

## [1.1.0] - 2018-05-11
- Allow for text/xml in schema responses from external sites
- Added console output when running the test via the GUI
- Added Schema Pack option
- Downgraded several messages from Error to Warning

## [1.0.9] - 2018-05-04
- Corrected problem when reading metadata from local cache
- Made changes to clean the standard output

## [1.0.8] - 2018-04-27
- Enhanced $metadata validation to check if a referenced namespace exists in the referenced schema file
- Enhanced handling of properties found in payloads that are not defined in the schema file
- Added new configuration options to the GUI to make it easier to save/load other configuration files

## [1.0.7] - 2018-04-20
- Enhanced authentication error handling for basic and session authentication
- Changed term "collection" in the report to say "array"
- Added method for running the tool via a GUI
- Fixed the Action object validation to allow for the "title" property
- Added support for allowing dynamic properties with @Redfish, @Message, and @odata terms

## [1.0.6] - 2018-04-13
- Enhanced validation of Action objects; allow for annotations and Action Info resources, and require the target property
- Added $metadata validation report
- Fixed handling of the Location header when creating a Session to allow for both absolute and relative URIs

## [1.0.5] - 2018-03-09
- Changed deprecated property reporting from error to warning

## [1.0.4] - 2018-03-02
- Enhanced URI handling in MessageRegistryFile validation

## [1.0.3] - 2018-02-15
- Improved display of array members in the HTML report
- Added text in the report to point to other payload reports when testing Referenceable Members

## [1.0.2] - 2018-02-09
- Made fixes to proxy support
- Added better handling for when incorrect namespaces are referenced
- Improvements to error messages
- Fixed handling of resolving external ComplexType definitions
- Added argument to control debug output

## [1.0.1] - 2018-02-02
- Fixed the display of null types in the report
- Fixed the display of data types found in registries
- Added validation of primitive types

## [1.0.0] - 2018-01-26
- Various bug fixes; getting into standard release cadence

## [0.9.0] - 2016-09-06
- Initial Public Release
