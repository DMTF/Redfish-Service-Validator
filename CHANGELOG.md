# Change Log

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
