# Copyright Notice:
# Copyright 2016-2025 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

"""
System Under Test

File : system_under_test.py

Brief : This file contains the definitions for tracking data for the test
        system.
"""

import re
import redfish
from pathlib import Path

from redfish_service_validator import logger
from redfish_service_validator import validate


class SystemUnderTest(object):
    def __init__(self, rhost, username, password, authtype, http_proxy, https_proxy, mockup, collection_limits, no_oem):
        """
        Constructor for new system under test

        Args:
            rhost: The address of the Redfish service (with scheme)
            username: The username for authentication
            password: The password for authentication
            authtype: The authorization type to use
            http_proxy: The HTTP proxy for accessing the service
            https_proxy: The HTTPS proxy for accessing the service
            mockup: The mockup directory
            collection_limits: Limits for validating members in a collection
            no_oem: Indicator to skip OEM extensions
        """
        self._rhost = rhost
        self._username = username
        proxies = None
        if http_proxy or https_proxy:
            proxies = {}
            if http_proxy:
                proxies["http"] = http_proxy
            if https_proxy:
                proxies["https"] = https_proxy
        self._redfish_obj = redfish.redfish_client(
            base_url=rhost, username=username, password=password, proxies=proxies, timeout=15, max_retry=3
        )
        self._redfish_obj.login(auth=authtype.lower())
        self._mockup_dir = mockup
        self._no_oem = no_oem
        self._service_root = self._redfish_obj.root_resp.dict
        self._pass_count = 0
        self._warn_count = 0
        self._fail_count = 0
        self._skip_count = 0
        self._error_classes = {}
        self._warning_classes = {}

        # Find the manager to populate service info
        self._product = None
        self._product = self._service_root.get("Product", "N/A")
        self._fw_version = None
        self._model = None
        self._manufacturer = None
        if "Managers" in self._service_root:
            try:
                manager_ids = redfish_utilities.get_manager_ids(self._redfish_obj)
                if len(manager_ids) > 0:
                    manager = redfish_utilities.get_manager(self._redfish_obj, manager_ids[0])
                    self._fw_version = manager.dict.get("FirmwareVersion", "N/A")
                    self._model = manager.dict.get("Model", "N/A")
                    self._manufacturer = manager.dict.get("Manufacturer", "N/A")
            except:
                pass

        # Set up the resource cache
        self._resources = {}
        self._annotation_uris = []

        # Build collection limits
        self._collection_limits = {}
        for resource_type, limit in zip(collection_limits[::2], collection_limits[1::2]):
            try:
                limit = int(limit)
            except:
                continue
            self._collection_limits[resource_type] = limit

    @property
    def rhost(self):
        """
        Accesses the address of the Redfish service

        Returns:
            The address of the Redfish service
        """
        return self._rhost

    @property
    def username(self):
        """
        Accesses the username for authentication

        Returns:
            The username for authentication
        """
        return self._username

    @property
    def firmware_version(self):
        """
        Accesses the firmware version of the service

        Returns:
            The firmware version of the service
        """
        return self._fw_version

    @property
    def model(self):
        """
        Accesses the model of the service

        Returns:
            The model of the service
        """
        return self._model

    @property
    def product(self):
        """
        Accesses the product of the service

        Returns:
            The product of the service
        """
        return self._product

    @property
    def manufacturer(self):
        """
        Accesses the manufacturer of the service

        Returns:
            The manufacturer of the service
        """
        return self._manufacturer

    @property
    def session(self):
        """
        Accesses the Redfish session

        Returns:
            The Redfish client object
        """
        return self._redfish_obj

    @property
    def service_root(self):
        """
        Accesses the service root data

        Returns:
            The service root data as a dictionary
        """
        return self._service_root

    @property
    def no_oem(self):
        """
        Indicator to skip OEM extensions

        Returns:
            Boolean indicator to skip OEM extensions
        """
        return self._no_oem

    @property
    def pass_count(self):
        """
        Accesses the pass count

        Returns:
            The pass count
        """
        return self._pass_count

    @property
    def warn_count(self):
        """
        Accesses the warning count

        Returns:
            The warning count
        """
        return self._warn_count

    @property
    def fail_count(self):
        """
        Accesses the fail count

        Returns:
            The fail count
        """
        return self._fail_count

    @property
    def skip_count(self):
        """
        Accesses the skip count

        Returns:
            The skip count
        """
        return self._skip_count

    def logout(self):
        """
        Logs out of the Redfish service
        """
        self._redfish_obj.logout()

    def is_uri_from_annotation(self, uri):
        """
        Checks if a URI was discovered from an annotation

        Args:
            uri: The URI to check

        Returns:
            A boolean indicating if the URI is from an annotation
        """
        return uri in self._annotation_uris

    def get_resource(self, uri):
        """
        Gets a resource for a URI

        Args:
            uri: The URI to get

        Returns:
            An object containing resource information about the URI
        """
        # Check if we attempted this URI
        if uri in self._resources:
            return self._resources[uri]

        # Not cached; go read it
        logger.debug("Caching {}...".format(uri))
        self._resources[uri] = {
            "Response": None,
            "Validated": False,
            "Exception": None,
            "Results": {},
            "Pass": 0,
            "Warn": 0,
            "Fail": 0,
            "Skip": 0,
            "Mockup": False,
        }
        try:
            if self._mockup_dir:
                # If a mockup directory was given, see if the resource exists in it
                uri_dirs = [uri.rstrip("/"), uri.rstrip("/")]
                uri_dirs[1] = uri_dirs[1].replace("/redfish/v1", "")
                for directory in uri_dirs:
                    mockup_file = Path(self._mockup_dir + directory + "/index.json")
                    if mockup_file.is_file():
                        # Mockup found; use its contents
                        with open(mockup_file) as mockup_data:
                            logger.debug("Found mockup of {}...".format(uri))
                            mockup_resp = {"Status": 200, "Content": mockup_data.read()}
                            self._resources[uri]["Response"] = redfish.rest.v1.StaticRestResponse(**mockup_resp)
                            self._resources[uri]["Mockup"] = True
                            return self._resources[uri]
            self._resources[uri]["Response"] = self._redfish_obj.get(uri)
            if self._resources[uri]["Response"].status != 200:
                logger.critical(
                    "Could not access {}; HTTP status: {}".format(uri, self._resources[uri]["Response"].status)
                )
        except Exception as err:
            self._resources[uri]["Exception"] = err
            logger.critical("Could not access {}; {}".format(uri, err))
        return self._resources[uri]

    def get_allow_header(self, uri):
        """
        Gets the Allow header for a resource

        Args:
            uri: The URI to get

        Returns:
            A string containing the Allow header
        """
        if uri not in self._resources:
            return None
        if self._resources[uri]["Response"] is None:
            return None
        if self._resources[uri]["Mockup"]:
            return None
        return self._resources[uri]["Response"].getheader("Allow")

    def is_mockup(self, uri):
        """
        Determines if a URI came from a mockup

        Args:
            uri: The URI to get

        Returns:
            A boolean indicating if the response is from a mockup
        """
        if uri not in self._resources:
            return False
        return self._resources[uri]["Mockup"]

    def add_resource_result(self, uri, prop, present, value, result):
        """
        Adds test results to a resource

        Args:
            uri: The URI of the resource
            prop: The property path of the property tested
            present: Indicates if the property was found in the payload
            value: The value of the property that was tested
            result: A tuple containing the test results
        """
        if uri in self._resources:
            if prop in self._resources[uri]["Results"]:
                # Only log the first results request
                return
            # Add the results
            self._resources[uri]["Results"][prop] = {"Result": result[0], "Value": None, "Message": result[1]}
            # Build up a test report-friendly value to uses
            if prop != "":
                if present:
                    if isinstance(value, dict):
                        if len(value) == 1 and "@odata.id" in value:
                            value_str = "[Link to: {}]".format(value["@odata.id"])
                        else:
                            value_str = "[Object]"
                    elif isinstance(value, list):
                        value_str = "[Array]"
                    elif isinstance(value, str) and len(value) == 0:
                        value_str = "[Empty String]"
                    elif value is None:
                        value_str = "[null]"
                    else:
                        value_str = str(value)
                else:
                    value_str = "[Not Present]"
                self._resources[uri]["Results"][prop]["Value"] = value_str
                combined_msg = "{} - {} ({}): {}".format(result[0], prop, value_str, result[1])
            else:
                self._resources[uri]["Results"][prop]["Value"] = "[Resource-level]"
                combined_msg = "{} - {}".format(result[0], result[1])
            # Tally the results
            if result[0] == "FAIL":
                self._fail_count += 1
                self._resources[uri]["Fail"] += 1
                logger.error(combined_msg)
            elif result[0] == "WARN":
                self._warn_count += 1
                self._resources[uri]["Warn"] += 1
                logger.warning(combined_msg)
            elif result[0] == "SKIP":
                self._skip_count += 1
                self._resources[uri]["Skip"] += 1
                logger.info(combined_msg)
            else:
                self._pass_count += 1
                self._resources[uri]["Pass"] += 1
                logger.info(combined_msg)
            # Update the error bucket
            if result[0] == "FAIL" or result[0] == "WARN":
                try:
                    error_type = result[1].split(":")[0]
                    dest = self._error_classes
                    if result[0] == "WARN":
                        dest = self._warning_classes
                    if error_type not in dest:
                        dest[error_type] = 0
                    dest[error_type] += 1
                except:
                    logger.critical("Error message string '{}' is not formatted correctly".format(result[1]))

    def set_resource_validated(self, uri):
        """
        Marks a resource as validated to indicate testing is complete

        Args:
            uri: The URI of the resource
        """
        if uri in self._resources:
            self._resources[uri]["Validated"] = True
            logger.log_print(
                "  - Pass: {}, Warn: {}, Fail: {}, Skip: {}".format(
                    self._resources[uri]["Pass"],
                    self._resources[uri]["Warn"],
                    self._resources[uri]["Fail"],
                    self._resources[uri]["Skip"],
                )
            )

    def find_uris(self, payload, uri_list, from_annotation):
        """
        Finds URIs in a payload

        Args:
            payload: The payload to scan
            uri_list: The list of URIs to update with any URIs found
            from_annotation: Indicates if we're stepping through an annotation that can contain URIs
        """
        if isinstance(payload, dict) and payload.get("@odata.type", "").startswith("#JsonSchemaFile."):
            # Don't go to URIs for JSON Schemas
            return
        for item in payload:
            if isinstance(payload, dict):
                # Skip OEM extensions if needed
                if item == "Oem" and self._no_oem:
                    continue

                # If the item is a reference, go to the resource
                if (
                    item == "@odata.id"
                    or item == "Uri"
                    or item == "Members@odata.nextLink"
                    or item == "@Redfish.ActionInfo"
                    or item == "DataSourceUri"
                    or item == "TargetComponentURI"
                ):
                    if isinstance(payload[item], str):
                        if payload[item].startswith("/") and "#" not in payload[item]:
                            uri_list.append(payload[item])
                            if from_annotation and payload[item] not in self._annotation_uris:
                                self._annotation_uris.append(payload[item])

                # If the item is an object or array, scan one level deeper
                elif isinstance(payload[item], dict) or isinstance(payload[item], list):
                    if item == "CapabilitiesObject" or item == "SettingsObject":
                        from_annotation = True
                    self.find_uris(payload[item], uri_list, from_annotation)

            # If the object is a list, see if the member needs to be scanned
            elif isinstance(payload, list):
                if isinstance(item, dict) or isinstance(item, list):
                    self.find_uris(item, uri_list, from_annotation)

    def validate(self, mode, start_uri, uri):
        """
        Performs validation of the service, recursively

        Args:
            mode: The traversal mode for the service
            start_uri: The starting URI for validation
            uri: The URI to test
        """
        # Get the URI
        resource = self.get_resource(uri)
        if resource["Validated"]:
            # Already tested
            return
        logger.log_print("Validating {}...".format(uri))

        # Check for exception cases that would fail the entire resource
        payload, result = validate.validate_response(resource)
        if payload is None:
            # Can't perform validation; stop here
            self.add_resource_result(uri, "", False, None, result)
            self.set_resource_validated(uri)
            return

        # For resource collection, apply collection limits by removing members from the payload
        resource_type = payload.get("@odata.type")
        if isinstance(resource_type, str):
            match = re.match(r"^#(.+)Collection\..+Collection$", resource_type)
            if match and match[1] in self._collection_limits:
                if "Members" in payload and isinstance(payload["Members"], list):
                    payload["Members"] = payload["Members"][: self._collection_limits[match[1]]]
                payload.pop("Members@odata.nextLink", None)

        # Validate the payload
        validate.validate_object(self, uri, payload, None, None, None, "")
        if resource["Mockup"]:
            self.add_resource_result(
                uri, "", False, None, ("WARN", "Mockup Used Warning: Response was populated from a mockup file.")
            )
        self.set_resource_validated(uri)

        # Go through its contents and get the next URIs to test
        if mode == "Single":
            # Nothing else to do; don't scan deeper
            return
        next_uris = []
        self.find_uris(payload, next_uris, False)
        for next_uri in next_uris:
            if mode == "Tree" and not next_uri.startswith(start_uri):
                # In 'Tree' mode, skip URIs that are not subordinate to the starting URI
                continue
            self.validate(mode, start_uri, next_uri)
