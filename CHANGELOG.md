# Change Log

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
