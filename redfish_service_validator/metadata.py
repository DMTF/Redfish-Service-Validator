# Copyright Notice:
# Copyright 2016-2025 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

"""
Metadata

File : metadata.py

Brief : This file contains the definitions and functionalities for building
        the data model definitions from the schema cache.
"""

import copy
import os
import re
import xml.etree.ElementTree as ET

from redfish_service_validator import logger

# OData markup strings
ODATA_TAG_REFERENCE = "{http://docs.oasis-open.org/odata/ns/edmx}Reference"
ODATA_TAG_INCLUDE = "{http://docs.oasis-open.org/odata/ns/edmx}Include"
ODATA_TAG_SCHEMA = "{http://docs.oasis-open.org/odata/ns/edm}Schema"
ODATA_TAG_ENTITY = "{http://docs.oasis-open.org/odata/ns/edm}EntityType"
ODATA_TAG_COMPLEX = "{http://docs.oasis-open.org/odata/ns/edm}ComplexType"
ODATA_TAG_ENUM = "{http://docs.oasis-open.org/odata/ns/edm}EnumType"
ODATA_TAG_ACTION = "{http://docs.oasis-open.org/odata/ns/edm}Action"
ODATA_TAG_TYPE_DEF = "{http://docs.oasis-open.org/odata/ns/edm}TypeDefinition"
ODATA_TAG_ANNOTATION = "{http://docs.oasis-open.org/odata/ns/edm}Annotation"
ODATA_TAG_PROPERTY = "{http://docs.oasis-open.org/odata/ns/edm}Property"
ODATA_TAG_NAV_PROPERTY = "{http://docs.oasis-open.org/odata/ns/edm}NavigationProperty"
ODATA_TAG_PARAMETER = "{http://docs.oasis-open.org/odata/ns/edm}Parameter"
ODATA_TAG_MEMBER = "{http://docs.oasis-open.org/odata/ns/edm}Member"
ODATA_TAG_RECORD = "{http://docs.oasis-open.org/odata/ns/edm}Record"
ODATA_TAG_PROP_VAL = "{http://docs.oasis-open.org/odata/ns/edm}PropertyValue"
ODATA_TAG_COLLECTION = "{http://docs.oasis-open.org/odata/ns/edm}Collection"
ODATA_TAG_STRING = "{http://docs.oasis-open.org/odata/ns/edm}String"
ODATA_TAG_RETURN = "{http://docs.oasis-open.org/odata/ns/edm}ReturnType"

URI_ID_REGEX = r"\{[A-Za-z0-9]+\}"
VALID_ID_REGEX = r"([A-Za-z0-9.!#$&-;=?\[\]_~])+"

VERSION_REGEX = r"\.v([0-9]+)_([0-9]+)_([0-9]+)\."
VERSION_REGEX_SM = r"v([0-9]+)_([0-9]+)_([0-9]+)"

parsed_schemas = []

class Metadata:
    """
    Class for describing the data  model for a single schema file

    Args:
        root: The ET object of the schema file
        name: The name of the schema file
    """

    def __init__(self, root, name):
        self._root = root
        self._name = name.replace("_v1", "").replace(".xml", "")
        self._namespace_under_process = ""
        self._versions = []
        self._objects = {}
        self._typedefs = {}
        self._actions = {}

        # Go through each namespace and pull out definitions
        for schema in self._root.iter(ODATA_TAG_SCHEMA):
            self._namespace_under_process = self._get_attrib(schema, "Namespace")

            # Go through each element in the namespace
            for child in schema:
                if (child.tag == ODATA_TAG_ENTITY) or (child.tag == ODATA_TAG_COMPLEX):
                    self._add_object(child)
                elif child.tag == ODATA_TAG_ACTION:
                    self._add_action(child)
                elif (child.tag == ODATA_TAG_ENUM) or (child.tag == ODATA_TAG_TYPE_DEF):
                    self._add_typedef(child)


    def get_name(self):
        """
        Gets the schema name

        Returns:
            The name of the schema
        """
        return self._name


    def find_object(self, typename, highest_version, exact_version=False):
        """
        Finds the definition of a specified object

        Args:
            typename: The name of the object to locate
            highest_version: The highest version of the object allowed
            exact_version: If an exact match is required

        Returns:
            The matching object definition
        """
        matched_def = None
        found_name = None
        if exact_version:
            # Exact match required
            matched_def = self._objects.get(typename, None)
            found_name = typename
        else:
            # Find the best definition based on the version info
            matched_ver = None
            space = typename.split(".")[0]
            name = typename.split(".")[-1]
            for obj in self._objects:
                if (obj.split(".")[0]) == space and (obj.split(".")[-1] == name):
                    # Matching object; inspect versions
                    obj_version = get_version(obj)
                    if obj_version is None and matched_def is None:
                        # Unversioned; still a potential match...
                        matched_def = self._objects[obj]
                        found_name = obj
                    elif highest_version is None:
                        # Get the absolute highest version from the schema; no capping
                        if matched_ver is None or (obj_version > matched_ver):
                            matched_def = self._objects[obj]
                            found_name = obj
                    elif (obj_version <= highest_version):
                        # Within the version range
                        # Needs to be newer than what we've already matched
                        if matched_ver is None or (obj_version > matched_ver):
                            matched_def = self._objects[obj]
                            found_name = obj
        if matched_def is None:
            return matched_def

        # Append previous versions if available from this schema
        matched_def = copy.deepcopy(matched_def)
        matched_def["TypeTree"] = [found_name]
        while matched_def["BaseType"] is not None:
            base_type = matched_def["BaseType"]
            if base_type not in self._objects:
                # Either the definition jumps schema files (ideally) or it's a bad reference...
                break
            # The update will bring over the next base type to inspect
            matched_def["TypeTree"].append(base_type)
            matched_def["BaseType"] = self._objects[base_type]["BaseType"]
            matched_def["Properties"].update(self._objects[base_type]["Properties"])
            matched_def["DynamicProperties"].update(self._objects[base_type]["DynamicProperties"])
            if matched_def["AllowedURIs"] is None:
                matched_def["AllowedURIs"] = self._objects[base_type]["AllowedURIs"]
            if matched_def["DeprecatedURIs"] is None:
                matched_def["DeprecatedURIs"] = self._objects[base_type]["DeprecatedURIs"]
            if matched_def["AllowedMethods"] is None:
                matched_def["AllowedMethods"] = self._objects[base_type]["AllowedMethods"]

        # Check other schema files for additional definitions...
        if matched_def["BaseType"] is not None:
            additional_defs = get_object_definition("", matched_def["BaseType"], exact_version=True)
            if additional_defs is not None:
                matched_def["TypeTree"] = matched_def["TypeTree"] + additional_defs["TypeTree"]
                matched_def["BaseType"] = additional_defs["BaseType"]
                matched_def["Properties"].update(additional_defs["Properties"])
                matched_def["DynamicProperties"].update(additional_defs["DynamicProperties"])
                if matched_def["AllowedURIs"] is None:
                    matched_def["AllowedURIs"] = additional_defs["AllowedURIs"]
                if matched_def["DeprecatedURIs"] is None:
                    matched_def["DeprecatedURIs"] = additional_defs["DeprecatedURIs"]
                if matched_def["AllowedMethods"] is None:
                    matched_def["AllowedMethods"] = additional_defs["AllowedMethods"]

        return matched_def


    def find_typedef(self, typename):
        """
        Finds the definition of a specified type

        Args:
            typename: The name of the type definition to locate

        Returns:
            The matching type definition
        """
        return self._typedefs.get(typename, None)


    def find_action(self, action_name):
        """
        Finds the definition of a specified action

        Args:
            action_name: The name of the action to locate

        Returns:
            The matching action
        """
        return self._actions.get(action_name, None)


    def _get_attrib(self, element, name, required=True, default=None):
        """
        Gets a given attribute from an ET element in a safe manner

        Args:
            element: The element with the attribute
            name: The name of the attribute
            required: Flag indicating if the attribute is expected to be present
            default: The value to return if not found

        Returns:
            The attribute value
        """
        if name in element.attrib:
            return element.attrib[name]
        else:
            if required:
                logger.critical("Missing '{}' attribute for tag '{}'".format(name, element.tag.split("}")[-1]))
        return default


    def _get_version_details(self, object):
        """
        Gets the version info for a given object

        Args:
            object: The object to parse

        Returns:
            The version added string
            The version deprecated string
        """
        version_added = None
        version_deprecated = None

        # Go through each annotation and find the Redfish.Revisions term
        for child in object:
            if child.tag == ODATA_TAG_ANNOTATION:
                term = self._get_attrib(child, "Term")
                if term == "Redfish.Revisions":
                    for collection in child.iter(ODATA_TAG_COLLECTION):
                        for record in collection.iter(ODATA_TAG_RECORD):
                            revision_kind = None
                            revision_string = None
                            for prop_val in record.iter(ODATA_TAG_PROP_VAL):
                                property = self._get_attrib(prop_val, "Property")
                                if property == "Kind":
                                    revision_kind = self._get_attrib(prop_val, "EnumMember")
                                elif property == "Version":
                                    revision_string = self._get_attrib(prop_val, "String")
                            if revision_string is not None:
                                if revision_kind == "Redfish.RevisionKind/Added":
                                    version_added = revision_string
                                elif revision_kind == "Redfish.RevisionKind/Deprecated":
                                    version_deprecated = revision_string
        return version_added, version_deprecated

    def _get_type_info(self, csdl_type):
        """
        Performs mapping of a CSDL type to the validator's type with a potential pattern

        Args:
            csdl_type: The CSDL data type to map

        Returns:
            The data type
            The pattern for a string type, if applicable
        """
        return_type = None
        return_pattern = None

        # Type mapping
        if (csdl_type == "Edm.SByte") or (csdl_type == "Edm.Int16") or (csdl_type == "Edm.Int32") or (csdl_type == "Edm.Int64"):
            return_type = "Integer"
        elif (csdl_type == "Edm.Decimal") or (csdl_type == "Edm.Double"):
            return_type = "Number"
        elif (csdl_type == "Edm.String") or (csdl_type == "Edm.DateTimeOffset") or (csdl_type == "Edm.Duration") or (csdl_type == "Edm.TimeOfDay") or (csdl_type == "Edm.Guid"):
            return_type = "String"
        elif (csdl_type == "Edm.Boolean"):
            return_type = "Boolean"
        elif (csdl_type == "Edm.PrimitiveType") or (csdl_type == "Edm.Primitive"):
            return_type = "Primitive"
        else:
            # Other types are tracked in the data model
            return_type = csdl_type

        # Type-specific patterns
        if csdl_type == "Edm.DateTimeOffset":
            return_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|(\+|-)\d{2}:\d{2})$"
        elif csdl_type == "Edm.Duration":
            return_pattern = r"^P(\d+D)?(T(\d+H)?(\d+M)?(\d+(.\d+)?S)?)?$"
        elif csdl_type == "Edm.TimeOfDay":
            return_pattern = r"^([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])(.[0-9]{1,12})?$"
        elif csdl_type == "Edm.Guid":
            return_pattern = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

        return return_type, return_pattern


    def _create_default_property_obj(self):
        """
        Creates a new property template with default data

        Returns:
            A dictionary of the new property template
        """
        new_prop = {
            "Array": False,
            "Nullable": True,
            "Required": False,
            "Pattern": None,
            "Minimum": None,
            "Maximum": None,
            "Permissions": None,
            "AutoExpand": False,
            "Navigation": False,
            "VersionAdded": "v1_0_0",
            "VersionDeprecated": None,
            "Type": None,
            "ExcerptCopy": None,
            "Excerpt": None,
            "ExcerptCopyOnly": None,
        }
        return new_prop


    def _add_object(self, object):
        """
        Adds an object definition to the data model

        Args:
            object: The object definition to add
        """
        obj_name = self._get_attrib(object, "Name")
        if obj_name is None:
            return
        obj_name = self._namespace_under_process + "." + obj_name

        # Base object definition
        self._objects[obj_name] = {}
        self._objects[obj_name]["BaseType"] = self._get_attrib(object, "BaseType", required=False, default=None)
        self._objects[obj_name]["Abstract"] = self._get_attrib(object, "Abstract", required=False, default=False)
        if self._objects[obj_name]["Abstract"] == "true":
            self._objects[obj_name]["Abstract"] = True
        self._objects[obj_name]["Properties"] = {}
        self._objects[obj_name]["DynamicProperties"] = {}
        self._objects[obj_name]["AllowedURIs"] = None
        self._objects[obj_name]["DeprecatedURIs"] = None
        self._objects[obj_name]["AllowedMethods"] = None

        # Add OData properties based on the reported type
        odata_props = []
        if (obj_name == "Resource.v1_0_0.Resource") or (obj_name == "Resource.v1_0_0.ResourceCollection"):
            odata_props = ["@odata.id", "@odata.etag", "@odata.type", "@odata.context"]
        elif obj_name == "Resource.v1_0_0.ReferenceableMember":
            odata_props = ["@odata.id"]
        elif obj_name == "Resource.OemObject":
            odata_props = ["@odata.type"]
        for prop in odata_props:
            required = False
            pattern = None
            if (prop == "@odata.id") or (prop == "@odata.type"):
                required = True
            if prop == "@odata.context":
                # Very loose pattern; doesn't necessarily map to all proper OData usage, but the value in Redfish is low
                pattern = r"^/redfish/v1/\$metadata#.+$"
            self._objects[obj_name]["Properties"][prop] = self._create_default_property_obj()
            self._objects[obj_name]["Properties"][prop]["Type"] = "String"
            self._objects[obj_name]["Properties"][prop]["Required"] = required
            self._objects[obj_name]["Properties"][prop]["Pattern"] = pattern
            self._objects[obj_name]["Properties"][prop]["Permissions"] = "Read"
            self._objects[obj_name]["Properties"][prop]["Nullable"] = False

        # Go through each property
        for prop in object:
            if (prop.tag != ODATA_TAG_PROPERTY) and (prop.tag != ODATA_TAG_NAV_PROPERTY):
                continue
            prop_name = self._get_attrib(prop, "Name")
            prop_type = self._get_attrib(prop, "Type")
            if (prop_name is None) or (prop_type is None):
                continue

            # Basic property info
            self._objects[obj_name]["Properties"][prop_name] = self._create_default_property_obj()
            if prop_type.startswith("Collection("):
                self._objects[obj_name]["Properties"][prop_name]["Array"] = True
                prop_type = prop_type[11:-1]
            if self._get_attrib(prop, "Nullable", False, "true") == "false":
                self._objects[obj_name]["Properties"][prop_name]["Nullable"] = False
            self._objects[obj_name]["Properties"][prop_name]["Navigation"] = prop.tag == ODATA_TAG_NAV_PROPERTY
            self._objects[obj_name]["Properties"][prop_name]["VersionAdded"] = self._namespace_under_process.split(".")[-1]
            _, self._objects[obj_name]["Properties"][prop_name]["VersionDeprecated"] = self._get_version_details(prop)

            # Type mapping
            self._objects[obj_name]["Properties"][prop_name]["Type"], self._objects[obj_name]["Properties"][prop_name]["Pattern"] = self._get_type_info(prop_type)

            # Extract other info about the property for from annotations
            for annotation in prop.iter(ODATA_TAG_ANNOTATION):
                term = self._get_attrib(annotation, "Term")
                if term is None:
                    continue
                if term == "Redfish.Required":
                    self._objects[obj_name]["Properties"][prop_name]["Required"] = True
                elif (term == "OData.AutoExpand") and (prop.tag == ODATA_TAG_NAV_PROPERTY):
                    self._objects[obj_name]["Properties"][prop_name]["AutoExpand"] = True
                elif term == "Validation.Pattern":
                    self._objects[obj_name]["Properties"][prop_name]["Pattern"] = self._get_attrib(annotation, "String")
                elif term == "Validation.Minimum":
                    self._objects[obj_name]["Properties"][prop_name]["Minimum"] = int(self._get_attrib(annotation, "Int"))
                elif term == "Validation.Maximum":
                    self._objects[obj_name]["Properties"][prop_name]["Maximum"] = int(self._get_attrib(annotation, "Int"))
                elif term == "OData.Permissions":
                    self._objects[obj_name]["Properties"][prop_name]["Permissions"] = self._get_attrib(annotation, "EnumMember").split("/")[-1]
                elif term == "Redfish.ExcerptCopy":
                    self._objects[obj_name]["Properties"][prop_name]["ExcerptCopy"] = self._get_attrib(annotation, "String", required=False, default="")
                elif term == "Redfish.Excerpt":
                    excerpt = self._get_attrib(annotation, "String", required=False, default="")
                    if excerpt == "":
                        excerpt = []
                    else:
                        excerpt = excerpt.split(",")
                    self._objects[obj_name]["Properties"][prop_name]["Excerpt"] = excerpt
                elif term == "Redfish.ExcerptCopyOnly":
                    self._objects[obj_name]["Properties"][prop_name]["ExcerptCopyOnly"] = True
                    self._objects[obj_name]["Properties"][prop_name]["Excerpt"] = []

            # Special cases for Members@odata.count and Members@odata.nextLink
            if (prop_name == "Members") and (self._objects[obj_name]["BaseType"] == "Resource.v1_0_0.ResourceCollection"):
                self._objects[obj_name]["Properties"]["Members@odata.count"] = self._create_default_property_obj()
                self._objects[obj_name]["Properties"]["Members@odata.count"]["Required"] = True
                self._objects[obj_name]["Properties"]["Members@odata.count"]["Type"] = "Integer"
                self._objects[obj_name]["Properties"]["Members@odata.count"]["Minimum"] = 0
                self._objects[obj_name]["Properties"]["Members@odata.count"]["Nullable"] = False
                self._objects[obj_name]["Properties"]["Members@odata.nextLink"] = self._create_default_property_obj()
                self._objects[obj_name]["Properties"]["Members@odata.nextLink"]["Type"] = "String"
                self._objects[obj_name]["Properties"]["Members@odata.nextLink"]["Nullable"] = False

        # Check for other terms
        for annotation in object.iter(ODATA_TAG_ANNOTATION):
            # Dynamic Properties
            # NOTE: Currently assumes ONE pattern allowed per object.  Technically it's possible to have multiple patterns, but this does not seem realistic
            if self._get_attrib(annotation, "Term") == "Redfish.DynamicPropertyPatterns":
                for collection in annotation.iter(ODATA_TAG_COLLECTION):
                    for record in collection.iter(ODATA_TAG_RECORD):
                        dynamic_pattern = None
                        dynamic_type = None
                        for prop_val in record.iter(ODATA_TAG_PROP_VAL):
                            if self._get_attrib(prop_val, "Property") == "Pattern":
                                dynamic_pattern = self._get_attrib(prop_val, "String")
                            elif self._get_attrib(prop_val, "Property") == "Type":
                                dynamic_type = self._get_attrib(prop_val, "String")
                        if dynamic_pattern and dynamic_type:
                            # Found a valid definition
                            self._objects[obj_name]["DynamicProperties"] = self._create_default_property_obj()
                            self._objects[obj_name]["DynamicProperties"]["NamePattern"] = dynamic_pattern
                            if dynamic_type.startswith("Collection("):
                                self._objects[obj_name]["DynamicProperties"]["Array"] = True
                                dynamic_type = dynamic_type[11:-1]
                            self._objects[obj_name]["DynamicProperties"]["VersionAdded"] = self._namespace_under_process.split(".")[-1]
                            self._objects[obj_name]["DynamicProperties"]["Type"], self._objects[obj_name]["DynamicProperties"]["Pattern"] = self._get_type_info(dynamic_type)

            # Allowed URIs
            if self._get_attrib(annotation, "Term") == "Redfish.Uris":
                self._objects[obj_name]["AllowedURIs"] = []
                for collection in annotation.iter(ODATA_TAG_COLLECTION):
                    for string in collection.iter(ODATA_TAG_STRING):
                        self._objects[obj_name]["AllowedURIs"].append(re.sub(URI_ID_REGEX, VALID_ID_REGEX, r"^{}/?$".format(string.text)))

            # Deprecated URIs
            if self._get_attrib(annotation, "Term") == "Redfish.DeprecatedUris":
                self._objects[obj_name]["DeprecatedURIs"] = []
                for collection in annotation.iter(ODATA_TAG_COLLECTION):
                    for string in collection.iter(ODATA_TAG_STRING):
                        self._objects[obj_name]["DeprecatedURIs"].append(re.sub(URI_ID_REGEX, VALID_ID_REGEX, r"^{}/?$".format(string.text)))

            # Capabilities
            if self._get_attrib(annotation, "Term").startswith("Capabilities."):
                if self._objects[obj_name]["AllowedMethods"] is None:
                    self._objects[obj_name]["AllowedMethods"] = []
                for record in annotation.iter(ODATA_TAG_RECORD):
                    for prop_val in record.iter(ODATA_TAG_PROP_VAL):
                        capability_type = self._get_attrib(prop_val, "Property")
                        capability_allowed = self._get_attrib(prop_val, "Bool")
                        if capability_allowed == "true":
                            if capability_type == "Insertable":
                                self._objects[obj_name]["AllowedMethods"].append("POST")
                            elif capability_type == "Updatable":
                                self._objects[obj_name]["AllowedMethods"].append("PATCH")
                                self._objects[obj_name]["AllowedMethods"].append("PUT")
                            elif capability_type == "Deletable":
                                self._objects[obj_name]["AllowedMethods"].append("DELETE")


    def _add_action(self, action):
        """
        Adds an action definition to the data model

        Args:
            action: The action definition to add
        """
        action_name = self._get_attrib(action, "Name")
        if action_name is None:
            return
        action_name = self._namespace_under_process + "." + action_name

        self._actions[action_name] = {}
        self._actions[action_name]["VersionAdded"], self._actions[action_name]["VersionDeprecated"] = self._get_version_details(action)

        # TODO: Parameters (for annotation checks)


    def _add_typedef(self, typedef):
        """
        Adds a type definition to the data model

        Args:
            typedef: The type definition to add
        """
        typedef_name = self._get_attrib(typedef, "Name")
        if typedef_name is None:
            return
        typedef_name = self._namespace_under_process + "." + typedef_name

        # Base definition
        self._typedefs[typedef_name] = {}
        self._typedefs[typedef_name]["Type"] = None
        self._typedefs[typedef_name]["Values"] = None
        self._typedefs[typedef_name]["ValuesVersionAdded"] = None
        self._typedefs[typedef_name]["ValuesVersionDeprecated"] = None
        self._typedefs[typedef_name]["Pattern"] = None
        self._typedefs[typedef_name]["Minimum"] = None
        self._typedefs[typedef_name]["Maximum"] = None

        if typedef.tag == ODATA_TAG_ENUM:
            # Enums are strings with specific values
            self._typedefs[typedef_name]["Type"] = "String"
            self._typedefs[typedef_name]["Values"] = []
            self._typedefs[typedef_name]["ValuesVersionAdded"] = []
            self._typedefs[typedef_name]["ValuesVersionDeprecated"] = []
            for member in typedef.iter(ODATA_TAG_MEMBER):
                member_name = self._get_attrib(member, "Name")
                if member_name is not None:
                    self._typedefs[typedef_name]["Values"].append(member_name)
                    ver_added, ver_deprecated = self._get_version_details(member)
                    self._typedefs[typedef_name]["ValuesVersionAdded"].append(ver_added)
                    self._typedefs[typedef_name]["ValuesVersionDeprecated"].append(ver_deprecated)
        else:
            # Full type definitions use annotations to describe what's allowed
            underlying_type = self._get_attrib(typedef, "UnderlyingType")
            if underlying_type is None:
                # Remove the type... Can't use it
                self._typedefs.pop(typedef_name)
                return

            self._typedefs[typedef_name]["Type"], self._typedefs[typedef_name]["Pattern"] = self._get_type_info(underlying_type)

            for annotation in typedef.iter(ODATA_TAG_ANNOTATION):
                term = self._get_attrib(annotation, "Term")
                if term is None:
                    continue
                if term == "Validation.Pattern":
                    self._typedefs[typedef_name]["Pattern"] = self._get_attrib(annotation, "String")
                elif term == "Validation.Minimum":
                    self._typedefs[typedef_name]["Minimum"] = int(self._get_attrib(annotation, "Int"))
                elif term == "Validation.Maximum":
                    self._typedefs[typedef_name]["Maximum"] = int(self._get_attrib(annotation, "Int"))
                elif term == "Redfish.Enumeration":
                    self._typedefs[typedef_name]["Values"] = []
                    self._typedefs[typedef_name]["ValuesVersionAdded"] = []
                    self._typedefs[typedef_name]["ValuesVersionDeprecated"] = []
                    for record in annotation.iter(ODATA_TAG_RECORD):
                        member_name = None
                        for prop_val in record.iter(ODATA_TAG_PROP_VAL):
                            if self._get_attrib(prop_val, "Property") == "Member":
                                member_name = self._get_attrib(prop_val, "String")
                        if member_name is not None:
                            self._typedefs[typedef_name]["Values"].append(member_name)
                            ver_added, ver_deprecated = self._get_version_details(record)
                            self._typedefs[typedef_name]["ValuesVersionAdded"].append(ver_added)
                            self._typedefs[typedef_name]["ValuesVersionDeprecated"].append(ver_deprecated)


def parse_schema_files(schema_dir):
    """
    Parse the schema files to build the data model definitions

    Args:
        schema_dir: The local schema repository
    """
    logger.debug("Parsing schema files")
    for filename in os.listdir(schema_dir):
        if not filename.lower().endswith(".xml"):
            # Skip non-XML files
            continue

        logger.debug("Parsing {}...".format(filename))

        # Read the schema file into an ET object
        try:
            tree = ET.parse(schema_dir + os.path.sep + filename)
            root = tree.getroot()
        except ET.ParseError:
            logger.critical("{} is a malformed XML document".format(filename))
        except Exception as err:
            logger.critical("Could not open {}; {}".format(filename, err))

        # Parse the schema file and update the data model list
        try:
            new_schema = Metadata(root, filename)
            parsed_schemas.append(new_schema)
        except Exception as err:
            logger.critical("Could not build data model definitions for {}; {}".format(filename, err))
    logger.debug("Done parsing schema files\n")


def get_object_definition(resource_type, object_type, exact_version=False):
    """
    Gets the definition for an object based on its typename and inheritance tree

    Args:
        resource_type: The type reported from the root of the resource
        object_type: The type referenced from the property definition in schema
        exact_version: Indicates if an exact match it required for this lookup

    Returns:
        An dictionary with the object's definition
    """
    logger.debug("Locating {} for {} (Exact = {})".format(object_type, resource_type, exact_version))

    # If the object type is in the same schema as the resource, need to find the latest applicable version
    highest_version = None
    if not exact_version:
        if resource_type.split(".")[0] == object_type.split(".")[0]:
            highest_version = get_version(resource_type)

    # Find the object definition
    for schema in parsed_schemas:
        object_def = schema.find_object(object_type, highest_version, exact_version)
        if object_def:
            return object_def

    return None


def get_type_definition(typename):
    """
    Gets the type definition for a typename

    Args:
        typename: The type referenced from the property definition in schema

    Returns:
        An dictionary with the type definition's information
    """
    logger.debug("Locating {}".format(typename))

    # Find the type definition
    for schema in parsed_schemas:
        type_def = schema.find_typedef(typename)
        if type_def:
            return type_def

    return None


def get_action_definition(action_name):
    """
    Gets the definition for an action based on its name

    Args:
        action_name: The name of the action

    Returns:
        An dictionary with the action definition's information
    """
    logger.debug("Locating {}".format(action_name))

    # Find the action
    for schema in parsed_schemas:
        action_def = schema.find_action(action_name)
        if action_def:
            return action_def

    return None


def get_version(typename, just_ver=False):
    """
    Pulls the version numbers from a typename

    Args:
        typename: The typename containing the version
        just_ver: Indicates if the typename parameter only contains the version segment

    Returns:
        A tuple with the version numbers if found
    """
    regex_str = VERSION_REGEX
    if just_ver:
        regex_str = VERSION_REGEX_SM
    try:
        groups = re.search(regex_str, typename)
        return (int(groups.group(1)), int(groups.group(2)), int(groups.group(3)))
    except:
        pass
    return None
