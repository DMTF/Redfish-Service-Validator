# Copyright Notice:
# Copyright 2016-2025 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

"""
Validate

File : validate.py

Brief : This file contains the definitions and functionalities for validating
        validating Redfish payloads against schema definitions.
"""

import re

from redfish_service_validator import logger
from redfish_service_validator import metadata

ODATA_TYPE_PATTERN = r"^#.+$"  # Not comprehensive, but good enough to ensure we can look up definitions
ACTIONS_PATTERN = r"^/Actions/#[A-Za-z0-9_.]+$"
OEM_ACTIONS_PATTERN = r"^/Actions/Oem/#[A-Za-z0-9_.]+$"
BASIC_TYPES = ["Integer", "Number", "String", "Boolean", "Primitive"]


def validate_response(resource):
    """
    Performs basic validation of a response prior to any detailed JSON inspections

    Args:
        resource: The resource to validate

    Returns:
        A dictionary of the JSON payload contents of the response; None if invalid
        A tuple containing error information; None if no errors
    """
    if resource["Response"] is None:
        # We need a response...
        return None, ("FAIL", "Resource Error: Exception when accessing the URI ({}).".format(resource["Exception"]))
    if resource["Response"].status != 200:
        # The response need to return a 200...
        return None, (
            "FAIL",
            "Resource Error: Received HTTP {} when accessing the URI.".format(resource["Response"].status),
        )
    payload = None
    try:
        payload = resource["Response"].dict
    except:
        # The response needs to pass JSON parsing...
        return None, (
            "FAIL",
            "Resource Error: Invalid JSON received when accessing the URI.".format(resource["Response"].status),
        )
    if not isinstance(payload, dict):
        # The response needs to be a JSON object...
        return None, ("FAIL", "Resource Error: Resource response does not contain a JSON object.")

    return payload, None


def validate_object(sut, uri, payload, resource_type, object_type, excerpt, prop_path):
    """
    Validates the contents of a JSON object in a response

    Args:
        sut: The system under test
        uri: The URI under test
        payload: The JSON object to validate as a dictionary
        resource_type: The original type for the resource containing the object
        object_type: The matching type for the object from schema
        excerpt: For excerpts, the type of excerpt for this object
        prop_path: The property path from the root of the response to this object
    """
    schema_err_result = "FAIL"
    if object_type == "Resource.OemObject":
        # TODO: For now, downgrade bad OEM extensions to warnings...
        schema_err_result = "WARN"
    # Determine the type to lookup
    # If @odata.type is present, use that, otherwise fall back on the generic type provided by the caller
    lookup_object_type, result = get_payload_type(
        payload, False, object_type is None or object_type == "Resource.OemObject"
    )
    if lookup_object_type is None:
        lookup_object_type = object_type
    if lookup_object_type is None or result:
        # No initial mapping or the representation of @odata.type is incorrect
        if object_type == "Resource.OemObject":
            # TODO: For now, downgrade bad OEM extensions to warnings...
            result = ("WARN", result[1])
        sut.add_resource_result(
            uri, prop_path + "/@odata.type", "@odata.type" in payload, payload.get("@odata.type"), result
        )
        return

    # Get the schema definition
    if prop_path == "":
        resource_type = lookup_object_type
    resource_type_name = resource_type.split(".")[-1]
    definition = metadata.get_object_definition(
        resource_type, lookup_object_type, exact_version="@odata.type" in payload
    )
    lookup_object_type_fallback = None
    if definition is None:
        # See if we can find a "best match" to at least perform some level of testing...
        definition, lookup_object_type_fallback = find_fallback_definition(resource_type, lookup_object_type)
    if definition is None:
        # Still can't find a type...
        sut.add_resource_result(
            uri,
            prop_path,
            True,
            payload,
            (
                "WARN",    # TODO: For now, downgrade to warning to cover OEM resources with no CSDL...
                "Schema Error: Unable to locate the schema definition for the '{}' type.".format(lookup_object_type),
            ),
        )
        return

    # Check if the type can be used; this needs to take precedence over logging an error about the fallback type since we do not want to continue here
    if object_type is not None and object_type not in definition["TypeTree"]:
        sut.add_resource_result(
            uri,
            prop_path,
            True,
            payload,
            (
                schema_err_result,
                "Object Type Error: The object '{}' contains a value for '@odata.type' that is not valid for type '{}'.".format(
                    prop_path.split("/")[-1], object_type
                ),
            ),
        )
        if object_type != "Resource.OemObject":
            # TODO: For now, allow OEM extensions to continue testing...
            return

    # Check if we accepted a fallback type; if so, log an error, but continue to test the object
    if lookup_object_type_fallback is not None:
        sut.add_resource_result(
            uri,
            prop_path,
            True,
            payload,
            (
                schema_err_result,
                "Schema Error: Unable to locate the schema definition for the '{}' type; using the type '{}' as a fallback.".format(
                    lookup_object_type, lookup_object_type_fallback
                ),
            ),
        )

    # Allow header check
    if prop_path == "":
        allow_header = sut.get_allow_header(uri)
        if allow_header is not None:
            allow_header_split = [allow.strip().upper() for allow in allow_header.split(",")]
            check_methods = ["POST", "DELETE", "PUT", "PATCH"]
            for method in check_methods:
                if method in ["PATCH", "PUT"] and "Oem" in payload:
                    # PATCH and PUT could be supported for OEM extensions per the spec; ignore for these cases
                    continue
                if method in allow_header_split and method not in definition["AllowedMethods"]:
                    sut.add_resource_result(
                        uri,
                        "/[Allow Header]",
                        True,
                        allow_header,
                        (
                            "FAIL",
                            "Allowed Method Error: The Allow header contains '{}', but the resource does not support this method.".format(
                                method
                            ),
                        ),
                    )

    # Go through each property in the payload
    for prop in payload:
        cur_path = prop_path + "/" + prop
        if prop in definition["Properties"]:
            # Regular property
            # Skip OEM extensions if needed
            if prop == "Oem" and sut.no_oem:
                sut.add_resource_result(
                    uri, cur_path, True, payload[prop], ("SKIP", "Skip: OEM extension checking is disabled.")
                )
                continue
            cur_definition = definition["Properties"][prop]
        elif "@Redfish." in prop or "@odata." in prop:
            # Payload annotation
            # TODO: Add support to verify annotations
            # @Redfish.Copyright is just for mockups (except for MessageRegistry resources)
            if prop == "@Redfish.Copyright" and resource_type_name != "MessageRegistry" and not sut.is_mockup(uri):
                sut.add_resource_result(
                    uri,
                    cur_path,
                    True,
                    payload[prop],
                    (
                        "FAIL",
                        "Copyright Annotation Error: The copyright annotation is only intended for use in mockups.",
                    ),
                )
            continue
        elif re.match(ACTIONS_PATTERN, cur_path) or re.match(OEM_ACTIONS_PATTERN, cur_path):
            # Action
            result = validate_action(sut, uri, prop, payload[prop], resource_type, cur_path)
            sut.add_resource_result(uri, cur_path, True, payload[prop], result)
            continue
        elif definition["DynamicProperties"].get("NamePattern") and re.match(
            definition["DynamicProperties"]["NamePattern"], prop
        ):
            # Dynamic property
            cur_definition = definition["DynamicProperties"]
        else:
            # Unknown property
            sut.add_resource_result(
                uri,
                cur_path,
                True,
                payload[prop],
                (
                    "FAIL",
                    "Unknown Property Error: The property '{}' is not defined in the '{}' type.".format(
                        prop, lookup_object_type
                    ),
                ),
            )
            continue

        # Check if this property is (and should be) an array
        # This controls how we step into the value to test it
        if isinstance(payload[prop], list) and cur_definition["Array"]:
            result = pass_or_deprecated(cur_definition["VersionDeprecated"])
            sut.add_resource_result(uri, cur_path, True, payload[prop], result)
            # An array; validate the members
            for i, array_value in enumerate(payload[prop]):
                curr_array_path = cur_path + "/" + str(i)
                result = validate_value(
                    sut,
                    uri,
                    payload,
                    prop,
                    array_value,
                    resource_type,
                    definition,
                    cur_definition,
                    excerpt,
                    curr_array_path,
                )
                sut.add_resource_result(uri, curr_array_path, True, array_value, result)
        elif not isinstance(payload[prop], list) and not cur_definition["Array"]:
            # Singular; validate the individual property
            result = validate_value(
                sut, uri, payload, prop, payload[prop], resource_type, definition, cur_definition, excerpt, cur_path
            )
            sut.add_resource_result(uri, cur_path, True, payload[prop], result)
        elif isinstance(payload[prop], list) and not cur_definition["Array"]:
            # Mismatch; error
            sut.add_resource_result(
                uri,
                cur_path,
                True,
                payload[prop],
                (
                    "FAIL",
                    "Property Type Error: The property '{}' is not expected to be an array, but found an array.".format(
                        prop
                    ),
                ),
            )
        else:
            # Mismatch; error
            sut.add_resource_result(
                uri,
                cur_path,
                True,
                payload[prop],
                (
                    "FAIL",
                    "Property Type Error: The property '{}' is expected to be an array, but did not find an array.".format(
                        prop
                    ),
                ),
            )

    # Go through each property in the object definition
    for prop in definition["Properties"]:
        if prop in payload:
            # Already tested
            continue
        if definition["Properties"][prop]["VersionDeprecated"] is not None:
            # Skip deprecated properties
            continue

        cur_path = prop_path + "/" + prop

        # Override the required term for @odata.id on registry resources
        # These are not typical resources and vendors may copy the files as-is from the DMTF site
        registry_list = ["MessageRegistry", "PrivilegeRegistry", "AttributeRegistry"]
        if prop == "@odata.id" and resource_type_name in registry_list:
            definition["Properties"][prop]["Required"] = False

        if excerpt is None:
            if definition["Properties"][prop]["ExcerptCopyOnly"]:
                continue
            if definition["Properties"][prop]["Required"] and not sut.is_uri_from_collection_capabilities(uri):
                sut.add_resource_result(
                    uri,
                    cur_path,
                    False,
                    None,
                    (
                        "FAIL",
                        "Required Property Error: The property '{}' is mandatory, but not present in the payload.".format(
                            prop
                        ),
                    ),
                )
            else:
                sut.add_resource_result(uri, cur_path, False, None, ("SKIP", "Skip: The property is not present."))
        else:
            # For excerpts, only report applicable excerpt properties
            if definition["Properties"][prop]["Excerpt"] is None:
                continue
            if excerpt in definition["Properties"][prop]["Excerpt"] or definition["Properties"][prop]["Excerpt"] == []:
                sut.add_resource_result(uri, cur_path, False, None, ("SKIP", "Skip: The property is not present."))

    return


def validate_action(sut, uri, prop_name, value, resource_type, prop_path):
    """
    Validates the contents of an action object in a response

    Args:
        sut: The system under test
        uri: The URI under test
        prop_name: The name of the action property
        value: The action object to validate as a dictionary
        resource_type: The original type for the resource containing the object
        prop_path: The property path from the root of the response to this object

    Returns:
        A tuple containing the results of the testing
    """
    schema_err_result = "FAIL"
    if prop_path.startswith("/Actions/Oem/"):
        # TODO: For now, downgrade bad OEM extensions to warnings...
        schema_err_result = "WARN"
    # Check if it's an object
    if not isinstance(value, dict):
        return (
            "FAIL",
            "Property Type Error: The property '{}' is expected to be an object, but found '{}'.".format(
                prop_name, type(value).__name__
            ),
        )

    # Check if the action is defined
    action_def = metadata.get_action_definition(prop_name[1:])
    if action_def is None:
        return (
            schema_err_result,
            "Schema Error: Unable to locate the schema definition for the '{}' action.".format(prop_name),
        )

    # For standard actions, enforce the resource type matches (including version)
    if not prop_path.startswith("/Actions/Oem/"):
        if prop_name[1:].split(".")[0] != resource_type.split(".")[0]:
            return (
                "FAIL",
                "Unsupported Action Error: The action '{}' is not allowed in the '{}' resource.".format(
                    prop_name, resource_type.split(".")[0]
                ),
            )

        resource_version = metadata.get_version(resource_type)
        if resource_version:
            version_added = metadata.get_version(action_def["VersionAdded"], just_ver=True)
            if version_added and resource_version < version_added:
                return (
                    "FAIL",
                    "Unsupported Action Error: The action '{}' requires the resource version to be '{}.{}.{}' or higher.".format(
                        prop_name, version_added[0], version_added[1], version_added[2]
                    ),
                )
    version_deprecated = metadata.get_version(action_def["VersionDeprecated"], just_ver=True)

    # The action object is valid; step into the object to test individual properties

    # TODO: Would be good refine this so that we pass the remaining checks to validate_object
    # We need to construct schema definitions for the properties in the actions objects so it can follow along with the existing parsing logic

    # target is mandatory
    if "target" not in value:
        sut.add_resource_result(
            uri,
            prop_path + "/target",
            False,
            None,
            (
                "FAIL",
                "Required Property Error: The property 'target' is mandatory, but not present in the action object.",
            ),
        )

    # Check for allowable properties
    action_props = ["target", "title"]
    for prop in value:
        cur_path = prop_path + "/" + prop
        if prop in action_props:
            # Check the data type; all properties are strings
            if not isinstance(value[prop], str):
                sut.add_resource_result(
                    uri,
                    cur_path,
                    True,
                    value[prop],
                    (
                        "FAIL",
                        "Property Type Error: The property '{}' is expected to be a string, but found '{}'.".format(
                            prop, type(value[prop]).__name__
                        ),
                    ),
                )
                continue

            # For target, check the URI
            if prop == "target":
                exp_target = uri.rstrip("/") + prop_path.replace("#", "")
                if value[prop] == exp_target + "/":
                    sut.add_resource_result(
                        uri,
                        cur_path,
                        True,
                        value[prop],
                        (
                            "WARN",
                            "Trailing Slash Warning: The target URI for the action has an unexpected trailing slash.",
                        ),
                    )
                    continue
                elif value[prop] != exp_target:
                    sut.add_resource_result(
                        uri,
                        cur_path,
                        True,
                        value[prop],
                        (
                            "FAIL",
                            "Action URI Error: The target URI for the action is expected to be '{}'.".format(
                                exp_target
                            ),
                        ),
                    )
                    continue
            sut.add_resource_result(uri, cur_path, True, value[prop], ("PASS", "Pass: The property is valid."))
        elif "@Redfish." in prop:
            # Payload annotation
            # TODO: Add support to verify annotations
            continue
        else:
            # Unknown property
            sut.add_resource_result(
                uri,
                cur_path,
                True,
                value[prop],
                ("FAIL", "Unknown Property Error: The property '{}' is not allowed in action objects.".format(prop)),
            )
            continue

    return pass_or_deprecated(version_deprecated)


def validate_value(sut, uri, payload, prop_name, value, resource_type, obj_def, prop_def, excerpt, prop_path):
    """
    Validates a property within a JSON object

    Args:
        sut: The system under test
        uri: The URI under test
        prop_name: The name of the action property
        value: The action object to validate as a dictionary
        resource_type: The original type for the resource containing the object
        obj_def: The schema definition of the object containing the property
        prop_def: The schema definition of the property
        excerpt: For excerpts, the type of excerpt for this object
        prop_path: The property path from the root of the response to this object

    Returns:
        A tuple containing the results of the testing
    """
    # Set up basic parameters from the base definition
    value_type = prop_def["Type"]
    value_type_orig = prop_def["Type"]
    values_allowed_values = None
    values_version_added = None
    values_version_deprecated = None
    value_pattern = prop_def["Pattern"]
    value_minimum = prop_def["Minimum"]
    value_maximum = prop_def["Maximum"]
    value_nullable = prop_def["Nullable"]
    value_permissions = prop_def["Permissions"]
    value_is_nav = prop_def["Navigation"]
    value_auto_expand = prop_def["AutoExpand"]
    value_excerpt_copy = prop_def["ExcerptCopy"]
    value_excerpt = prop_def["Excerpt"]
    value_excerpt_copy_only = prop_def["ExcerptCopyOnly"]
    value_deprecated_ver = prop_def["VersionDeprecated"]

    # Excerpt check
    if excerpt is not None:
        # Inside of an excerpt; check that the current property is applicable
        if value_excerpt is None or (excerpt not in value_excerpt and value_excerpt != []):
            # The property is not part of an excerpt
            return (
                "FAIL",
                "Unknown Property Error: The property '{}' is not part of the excerpt usage.".format(prop_name),
            )
    else:
        # Not an excerpt; check that the current property is not flagged as excerpt-only
        if value_excerpt_copy_only:
            return ("FAIL", "Unknown Property Error: The property '{}' is only allowed in excerpts.".format(prop_name))

    # Null check
    if value is None:
        if value_nullable:
            return pass_or_deprecated(value_deprecated_ver)
        return (
            "FAIL",
            "Null Error: The property '{}' contains null, but null is not allowed.".format(prop_name),
        )

    if value_type not in BASIC_TYPES:
        # Check if this is an object or a typedef
        obj_definition = metadata.get_object_definition(resource_type, value_type)
        type_definition = metadata.get_type_definition(value_type)
        if obj_definition:
            # Object
            if not isinstance(value, dict):
                return (
                    "FAIL",
                    "Property Type Error: The property '{}' is expected to be an object, but found '{}'.".format(
                        prop_name, type(value).__name__
                    ),
                )

            # Handle type-checking of navigation properties
            # Auto-expanded navigation properties are treated like any other object
            if value_is_nav:
                if value_excerpt_copy is not None:
                    # Excerpt

                    # Pass it down to verify like typical objects
                    excerpt = value_excerpt_copy
                elif not value_auto_expand:
                    # Reference object

                    # Verify it contains @odata.id and it's the correct type
                    if "@odata.id" not in value:
                        return (
                            "FAIL",
                            "Reference Object Error: The navigation property '{}' does not contain '@odata.id'.".format(
                                prop_name
                            ),
                        )
                    if not isinstance(value["@odata.id"], str):
                        return (
                            "FAIL",
                            "Reference Object Error: The navigation property '{}' does not contain a string for its '@odata.id' value.".format(
                                prop_name
                            ),
                        )

                    # Verify the referenced link contains the correct type of resource
                    if value["@odata.id"].startswith("/") and "#" not in value["@odata.id"]:
                        # Get the referenced resource
                        resource = sut.get_resource(value["@odata.id"])
                        link_payload, result = validate_response(resource)
                        if link_payload is None:
                            return result
                        # Lookup its schema definition
                        link_type, result = get_payload_type(link_payload, True, True)
                        if link_type is None:
                            return result
                        link_def = metadata.get_object_definition(link_type, link_type, True)
                        if link_def is None:
                            # See if we can find a fallback version; don't penalize this resource for it
                            link_def, _ = find_fallback_definition(link_type, link_type)
                        if link_def is None:
                            return (
                                "FAIL",
                                "Schema Error: Unable to locate the schema definition for the '{}' type.".format(
                                    link_type
                                ),
                            )
                        # Check if the navigation property type is found in the type tree of the resource
                        if value_type not in link_def["TypeTree"]:
                            return (
                                "FAIL",
                                "Reference Object Error: The navigation property '{}' does not reference a resource of type '{}'.".format(
                                    prop_name, value_type
                                ),
                            )

                    # TODO: Verify referencenced referenceable members

                    # Verify no other properties are present
                    if len(value) != 1:
                        return (
                            "FAIL",
                            "Reference Object Error: The navigation property '{}' contains extra properties.".format(
                                prop_name
                            ),
                        )

                    return pass_or_deprecated(value_deprecated_ver)

            # Validate the object's contents
            validate_object(sut, uri, value, resource_type, value_type, excerpt, prop_path)
            return pass_or_deprecated(value_deprecated_ver)
        elif type_definition:
            # Typedef
            # Copy over attributes
            value_type = type_definition["Type"]
            values_allowed_values = type_definition["Values"]
            values_version_added = type_definition["ValuesVersionAdded"]
            values_version_deprecated = type_definition["ValuesVersionDeprecated"]
            value_pattern = type_definition["Pattern"]
            value_minimum = type_definition["Minimum"]
            value_maximum = type_definition["Maximum"]
        else:
            # Could not resolve the type
            return (
                "FAIL",
                "Schema Error: Unable to locate the schema definition for the '{}' type.".format(value_type),
            )

    # Permission check
    # Write-only properties always show null; should not have gotten this far
    if value_permissions == "None" or value_permissions == "Write":
        return (
            "FAIL",
            "Null Error: The property '{}' is write-only and is expected to be null in responses.".format(
                prop_name
            ),
        )

    # Basic type check
    allowed_types = [value_type]
    if value_type == "Number":
        allowed_types.append("Integer")  # Floats can come in as integers
    elif value_type == "Primitive":
        allowed_types = BASIC_TYPES  # Primitive can map to anything
    if (
        (type(value) is str and "String" not in allowed_types)
        or (type(value) is bool and "Boolean" not in allowed_types)
        or (type(value) is int and "Integer" not in allowed_types)
        or (type(value) is float and "Number" not in allowed_types)
    ):
        return (
            "FAIL",
            "Property Type Error: The property '{}' is expected to be a {}, but found '{}'.".format(
                prop_name, value_type, type(value).__name__
            ),
        )

    # Special case testing for when properties are cross-coupled or not covered by schema

    # @odata.id needs to match one of the patterns allowed by the resource
    # Report warnings for OEM usage, trailing slashes, or if deprecated
    if prop_path == "/@odata.id" and not sut.is_uri_from_annotation(value):
        uri_pattern, check = find_uri_pattern(value, obj_def)
        if check:
            if uri_pattern is None:
                if "/Oem/" in value:
                    return ("WARN", "Undefined URI Warning: The resource is being used in an OEM-extension.")
                return ("FAIL", "Undefined URI Error: The URI is not in the list of allowed URIs for the resource.")
            if obj_def["DeprecatedURIs"] is not None:
                if uri_pattern in obj_def["DeprecatedURIs"]:
                    return ("WARN", "Deprecated URI Warning: The URI is allowed, but deprecated for this resource.")
        if value.endswith("/") and value != "/redfish/v1/":
            return ("WARN", "Trailing Slash Warning: The URI for the resource has an unexpected trailing slash.")

    # Id needs to match the last segment of the URI if part of a collection
    if prop_path == "/Id" and not sut.is_uri_from_annotation(uri):
        uri_pattern, check = find_uri_pattern(payload.get("@odata.id"), obj_def)
        if uri_pattern is not None:
            if uri_pattern.endswith("+/?$") and payload["@odata.id"].strip("/").split("/")[-1] != value:
                return (
                    "FAIL",
                    "Invalid Identifier Error: The identifier '{}' does not match the last URI segment for the resource.".format(
                        value
                    ),
                )

    # @odata.id for embedded objects need to match the property path
    if prop_name == "@odata.id" and "MemberId" in payload:
        expected_value = uri + "#" + prop_path
        expected_value = expected_value.rsplit("/", 1)[0]
        if value != expected_value:
            return (
                "FAIL",
                "JSON Pointer Error: The property '{}' does not contain a valid RFC6901 JSON pointer; expected the value '{}'.".format(
                    prop_name,
                    expected_value,
                ),
            )

    # MemberId needs to match the index position in the payload
    if prop_name == "MemberId":
        expected_value = prop_path.split("/")[-2]
        if value != expected_value:
            return (
                "FAIL",
                "Invalid Identifier Error: The property '{}' does not contain the last segment of the JSON path of the object; expected the value '{}'.".format(
                    prop_name,
                    expected_value,
                ),
            )

    # DurableName will have a pattern applied based on DurableNameFormat
    if prop_name == "DurableName":
        durable_name_format = payload.get("DurableNameFormat")
        if durable_name_format == "NAA":
            value_pattern = r"^(([0-9A-Fa-f]{2}){8}){1,2}$"
        elif durable_name_format == "FC_WWN":
            value_pattern = r"^([0-9A-Fa-f]{2}[:-]){7}([0-9A-Fa-f]{2})$"
        elif durable_name_format == "UUID":
            value_pattern = r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
        elif durable_name_format == "EUI":
            value_pattern = r"^([0-9A-Fa-f]{2}[:-]){7}([0-9A-Fa-f]{2})$"
        elif durable_name_format == "NGUID":
            value_pattern = r"^([0-9A-Fa-f]{2}){16}$"
        elif durable_name_format == "MACAddress":
            value_pattern = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"

    # String-specific checks
    if isinstance(value, str):
        # Regex pattern
        if value_pattern is not None and not re.match(value_pattern, value):
            return (
                "FAIL",
                "Property Value Error: The property '{}' does not follow the regular expression pattern '{}'.".format(
                    prop_name, value_pattern
                ),
            )

        # Allowable values
        if values_allowed_values is not None:
            # Check if the value is even defined
            if value not in values_allowed_values:
                return (
                    "FAIL",
                    "Property Value Error: The property '{}' is not one of the listed allowable values: {}.".format(
                        prop_name, ", ".join(values_allowed_values)
                    ),
                )
            value_index = values_allowed_values.index(value)

            # Check versioning if the definition is from the same schema
            resource_version = metadata.get_version(resource_type)
            if (resource_type.split(".")[0] == value_type_orig.split(".")[0]) and resource_version is not None:
                version_added = metadata.get_version(values_version_added[value_index], just_ver=True)
                if version_added and resource_version < version_added:
                    return (
                        "FAIL",
                        "Property Value Error: The value '{}' for the property '{}' requires the resource version to be '{}.{}.{}' or higher.".format(
                            value, prop_name, version_added[0], version_added[1], version_added[2]
                        ),
                    )

            # For deprecated values, always log
            # TODO: May want to consider a version check if the value is defined in the same schema as the resource
            version_deprecated = metadata.get_version(values_version_deprecated[value_index], just_ver=True)
            if version_deprecated:
                return (
                    "WARN",
                    "Deprecated Value Warning: The value '{}' for the property '{}' was deprecated in version '{}.{}.{}' of the resource.".format(
                        value, prop_name, version_deprecated[0], version_deprecated[1], version_deprecated[2]
                    ),
                )

        # Empty-string check
        # Read-only strings shouldn't be empty; high chance this is a mistake
        if value_permissions == "Read" and value == "":
            return (
                "WARN",
                "Empty String Warning: The property '{}' contains an empty string; services should omit properties that are not supported.".format(
                    prop_name
                ),
            )

    # Number-specific checks
    if isinstance(value, int) or isinstance(value, float):
        # Min value check
        if value_minimum is not None and value < value_minimum:
            return (
                "FAIL",
                "Numeric Range Error: The property '{}' is below the minimum allowed value '{}'.".format(
                    prop_name, value_minimum
                ),
            )

        # Max value check
        if value_maximum is not None and value > value_maximum:
            return (
                "FAIL",
                "Numeric Range Error: The property '{}' is above the maximum allowed value '{}'.".format(
                    prop_name, value_maximum
                ),
            )

    return pass_or_deprecated(value_deprecated_ver)


def get_payload_type(payload, link_check, required):
    """
    Gets the type for the payload (from @odata.type)

    Args:
        payload: The object to inspect
        link_check: Indicates if this lookup is for reference link validation
        required: Indicates if @odata.type is mandatory for this usage

    Returns:
        The payload type from the @odata.type property; None if not found
        A tuple containing error information; None if no errors
    """
    link_msg = " "
    if link_check:
        link_msg = " in the referenced resource "

    # Check if there's an @odata.type property present
    if "@odata.type" not in payload:
        if required:
            return None, (
                "FAIL",
                "Required Property Error: The property '@odata.type'{}is mandatory, but not present in the payload.".format(
                    link_msg
                ),
            )
        return None, None

    # Check @odata.type contains something valid
    # "Valid" in this case just means it's syntactically correct; not that it means it maps to a schema definition
    if not isinstance(payload["@odata.type"], str):
        return None, (
            "FAIL",
            "Property Type Error: The property '@odata.type'{}is expected to be a string, but found '{}'.".format(
                link_msg, type(payload["@odata.type"]).__name__
            ),
        )
    if not re.match(ODATA_TYPE_PATTERN, payload["@odata.type"]):
        return None, (
            "FAIL",
            "Property Value Error: The property '@odata.type'{}does not follow the regular expression pattern '{}'.".format(
                link_msg, ODATA_TYPE_PATTERN
            ),
        )

    # Found; remove the leading # character
    return payload["@odata.type"][1:], None


def pass_or_deprecated(deprecated):
    """
    Builds common results for PASS and deprecation warnings

    Args:
        deprecated: The deprecation status of the property under test

    Returns:
        A tuple containing the results of the testing
    """
    if deprecated:
        return ("WARN", "Deprecated Property Warning: The property is deprecated.")
    else:
        return ("PASS", "Pass: The property is valid.")


def find_uri_pattern(uri, obj_def):
    """
    Looks up URI pattern information for a URI

    Args:
        uri: The URI under test
        obj_def: The object definition with URI terms

    Returns:
        The matching URI pattern from the schema; None if not found
        Indicates whether to continue testing
    """
    if not isinstance(uri, str):
        # Not even a valid URI... Need to stop
        return None, False
    if obj_def["AllowedURIs"] is None:
        # Object definition does not specify URI patterns
        # Either we're in an embedded object where URIs aren't relevant, or the schema author never defined valid URIs
        return None, False
    # See if the URI maps to one of the patterns
    for allowed_uri in obj_def["AllowedURIs"]:
        if re.match(allowed_uri, uri):
            # Match!
            return allowed_uri, True
    return None, True


def find_fallback_definition(resource_type, object_type):
    """
    Attempts to find a fallback object definition

    Args:
        resource_type: The original type for the resource containing the object
        object_type: The object type originally used for lookup

    Returns:
        An dictionary with the fallback object's definition
        The typename of the fallback object
    """
    # Try to look up the best match based on the version presented
    # Walk the versions back by first using 0 for the errata version, and then decrement the minor version as much as possible
    object_ver = metadata.get_version(object_type)
    if object_ver:
        object_type_split = object_type.split(".")
        for version_test in range(object_ver[1], -1, -1):
            object_type_fallback = "{}.v{}_{}_0.{}".format(
                object_type_split[0], object_ver[0], version_test, object_type_split[-1]
            )
            definition = metadata.get_object_definition(resource_type, object_type_fallback, exact_version=True)
            if definition:
                # Found a fallback
                return definition, object_type_fallback
    return None, None
