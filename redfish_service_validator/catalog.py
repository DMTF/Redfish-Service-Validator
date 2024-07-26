import glob, copy, difflib
import logging
import re
from collections import namedtuple
from enum import Enum, auto
from os import path

from bs4 import BeautifulSoup

from redfish_service_validator.helper import (
    getNamespace,
    getNamespaceUnversioned,
    getType,
    getVersion,
    splitVersionString,
    stripCollection
)

includeTuple = namedtuple("include", ["Namespace", "Uri"])

my_logger = logging.getLogger(__name__)

REDFISH_ABSENT = "n/a"

URI_ID_REGEX = r'\{[A-Za-z0-9]*Id\}'

VALID_ID_REGEX = r'([A-Za-z0-9.!#$&-;=?\[\]_~])+'


# Excerpt definitions
class ExcerptTypes(Enum):
    NEUTRAL = auto()
    CONTAINS = auto()
    ALLOWED = auto()
    EXCLUSIVE = auto()


excerpt_info_by_type = {
    'Redfish.ExcerptCopy': ExcerptTypes.CONTAINS,
    'Redfish.Excerpt': ExcerptTypes.ALLOWED,
    'Redfish.ExcerptCopyOnly': ExcerptTypes.EXCLUSIVE
}


allowed_annotations = ['odata', 'Redfish', 'Privileges', 'Message']


def get_fuzzy_property(prop_name: str, jsondata: dict, allPropList=[]):
    """
    Get property closest to the discovered property.

    Args:
        prop_name (str): Key of property
        jsondata (dict): Dictionary of payload
        allPropList (list, optional): List of possible properties of this particular payload. Defaults to [].

    Returns:
        prop_name: Closest match
        rtype: str
    """
    possibleMatch = difflib.get_close_matches(prop_name, list(jsondata), 1, 0.70)
    if len(possibleMatch) > 0 and possibleMatch[0] not in [
        s[2] for s in allPropList if s[2] != prop_name
    ]:
        val = jsondata.get(possibleMatch[0], "n/a")
        if val != "n/a":
            return possibleMatch[0]
            # .error('{} was not found in payload, attempting closest match: {}'.format(newProp, pname))
    return prop_name


class MissingSchemaError(Exception):
    """
    Missing Schema Error.
    
    Raise when Catalog is unable to find a Schema
    """

    pass


class SchemaCatalog:
    """
    Catalog for holding Schema files.
    
    From Catalog, you can get any Schema by it's filename, or its classes
    """
    # TODO: Generate documents on demand, not all at once

    def __init__(self, filepath: str, metadata: object = None):
        """Init

        Args:
            filepath (str): Directory of metadata
            metadata (object, optional): Preestablished metadata. Defaults to None.
        """
        self.filepath = filepath
        self.alias = {}
        self.catalog = {}
        self.catalog_by_class = {}
        self.flags = {
            'ignore_uri_checks': False
        }
        my_logger.debug("Creating Schema catalog from filepath {}".format(filepath))

        # create SchemaDoc objects
        for x in glob.glob(path.join(filepath, "*")):
            with open(x) as f:
                my_name = path.split(x)[-1]
                schema = SchemaDoc(f.read(), self, my_name)
                self.catalog[my_name] = schema

            base_names = [getNamespaceUnversioned(x) for x in schema.classes if getNamespaceUnversioned(x) not in schema.classes]
            for item in list(schema.classes.keys()) + base_names:
                if item not in self.catalog_by_class:
                    self.catalog_by_class[item] = [schema]
                else:
                    self.catalog_by_class[item].append(schema)
        
        for _, schema in self.catalog.items():
            self.alias.update(schema.alias)

    def getSchemaDocByClass(self, typename):
        """
        Get Document by class

        :param typename: type string
        :type typename: str
        :raises MissingSchemaError: Missing schema in Catalog
        :return: Schema Document
        :rtype: SchemaDoc
        """
        typename = getNamespaceUnversioned(stripCollection(typename))
        typename = self.alias.get(typename, typename)
        if typename in self.catalog_by_class:
            return self.catalog_by_class[typename][0]
        else:
            raise MissingSchemaError( "Could not find any Schema with these parameters {}".format(typename))

    def getSchemaInCatalog(self, typename):
        """
        Get Schema by class

        :param typename: type string
        :type typename: str
        :raises MissingSchemaError: Missing schema in Catalog
        :return: Schema Document
        :rtype: SchemaClass
        """

        typename = getNamespace(typename)
        typename = self.alias.get(typename, typename)
        my_doc = self.getSchemaDocByClass(typename)
        return my_doc.classes[typename]

    def getTypeInCatalog(self, fulltype):
        """
        Get Type via type string

        :param typename: type string
        :type typename: str
        :raises MissingSchemaError: Missing schema in Catalog
        :return: Schema Document
        :rtype: RedfishType
        """
        typename = getNamespaceUnversioned(fulltype)
        typename = self.alias.get(typename, typename)
        my_doc = self.getSchemaDocByClass(typename)
        return my_doc.getTypeInSchemaDoc(fulltype)
        

class SchemaDoc:
    """Represents a schema document."""

    def __init__(self, data: str, catalog: SchemaCatalog = None, name: str = None):
        # set up document
        self.soup = BeautifulSoup(data, "xml")
        self.name = str(name)
        self.origin = "local"
        self.catalog = catalog
        self.classes = {}
        self.alias = {}

        edmxTag = self.soup.find("Edmx", recursive=False)
        reftags = edmxTag.find_all("Reference", recursive=False)
        self.refs = {}
        for ref in reftags:
            includes = ref.find_all("Include", recursive=False)
            for item in includes:
                uri = ref.get("Uri")
                ns, alias = (item.get(x) for x in ["Namespace", "Alias"])
                if ns is None or uri is None:
                    my_logger.error("Reference incorrect for: {}".format(item))
                    continue
                if alias is None:
                    alias = ns
                else:
                    self.alias[alias] = ns

                self.refs[alias] = includeTuple(ns, uri)
                # Check for proper Alias for RedfishExtensions
                # if name == '$metadata' and ns.startswith('RedfishExtensions.'):
                #     check_bool = check_redfish_extensions_alias(name, ns, alias)

        cntref = len(self.refs)

        parentTag = edmxTag.find("DataServices", recursive=False)
        children = parentTag.find_all("Schema", recursive=False)
        self.classes = {}
        for child in children:
            self.classes[child["Namespace"]] = SchemaClass(child, self)
        my_logger.debug(
            "References generated from {}: {} out of {}".format(
                name, cntref, len(self.refs)
            )
        )

    def getReference(self, namespace):
        """getSchemaFromReference

        Get tuple from generated references

        :param namespace: Namespace of reference
        """
        tup = self.refs.get(namespace)
        tupVersionless = self.refs.get(getNamespace(namespace))
        if tup is None:
            if tupVersionless is None:
                my_logger.warning('No such reference {} in {}, returning None...'.format(namespace, self.origin))
                return None
            else:
                tup = tupVersionless
                my_logger.warning('No such reference {} in {}, using unversioned...'.format(namespace, self.origin))
        return tup

    def getTypeInSchemaDoc(self, currentType, tagType=["EntityType", "ComplexType"]):
        """getTypeTagInSchema

        Get type tag in schema

        :param currentType: type string
        :param tagType: Array or single string containing the xml tag name
        
        rtype: SchemaClass
        """
        if isinstance(currentType, RedfishType):
            currentType = currentType.fulltype

        currentType = stripCollection(currentType)

        pnamespace, ptype = getNamespace(currentType), getType(currentType)
        pnamespace = self.catalog.alias.get(pnamespace, pnamespace)
        pbase = getNamespaceUnversioned(pnamespace)

        if pnamespace not in self.classes:
            if pbase in self.classes:
                my_logger.error("Namespace of type {} appears missing from SchemaXML {}, attempting highest type: {}".format(pnamespace, self.name, currentType))
                ns_obj = self.classes[pbase]
                pnamespace = getNamespace(ns_obj.getHighestType(currentType))
                my_logger.error("New namespace: {}".format(pnamespace))
            elif pnamespace in self.refs or pbase in self.refs:
                new_doc = self.catalog.getSchemaDocByClass(pnamespace)
                return new_doc.getTypeInSchemaDoc(currentType)
        if pnamespace in self.classes:
            currentNamespace = self.classes[pnamespace]
            return currentNamespace.my_types[ptype]
        else:
            my_logger.error("Namespace of type {} appears missing from SchemaXML {}...".format(pnamespace, self.name))
            raise MissingSchemaError('No such schema referenced in this document')
    

class SchemaClass:
    def __init__(self, soup, owner: SchemaDoc):
        super().__init__()
        self.parent_doc = owner
        self.catalog = owner.catalog
        self.class_soup = soup
        self.class_name = soup["Namespace"]
        self.entity_types, self.complex_types, self.enum_types, self.def_types = {}, {}, {}, {}

        for x in self.class_soup.find_all(["EntityType"], recursive=False):
            self.entity_types[x["Name"]] = RedfishType(x, self)

        for x in self.class_soup.find_all(["ComplexType"], recursive=False):
            self.complex_types[x["Name"]] = RedfishType(x, self)

        for x in self.class_soup.find_all(["EnumType"], recursive=False):
            self.enum_types[x["Name"]] = RedfishType(x, self)

        for x in self.class_soup.find_all(["TypeDefinition"], recursive=False):
            self.def_types[x["Name"]] = RedfishType(x, self)
        
        self.actions = {}
        for x in self.class_soup.find_all(["Action"], recursive=False):
            self.actions[x["Name"]] = x

        self.terms = {}
        for x in self.class_soup.find_all(["Term"], recursive=False):
            self.terms[x["Name"]] = RedfishType(x, self)

        self.my_types = {**self.entity_types, **self.complex_types, **self.enum_types, **self.def_types}

    def getHighestType(self, my_full_type, limit=None):
        """
        Get Highest possible version for given type.

        :param acquiredtype: Type available
        :param limit: Version string limit (full namespace or just version 'v1_x_x')
        """
        typelist = []
        my_type = getType(my_full_type)

        if limit is not None:
            if getVersion(limit) is None:
                # logger.warning('Limiting namespace has no version, erasing: {}'.format(limit))
                limit = None
            else:
                limit = getVersion(limit)

        for _, schema in self.parent_doc.classes.items():
            newNamespace = schema.class_name
            if limit is not None:
                if getVersion(newNamespace) is None:
                    continue
                if splitVersionString(newNamespace) > splitVersionString(limit):
                    continue
            if (my_type in self.my_types):
                typelist.append(splitVersionString(newNamespace))

        if len(typelist) > 1:
            for ns in reversed(sorted(typelist)):
                my_logger.debug("{}   {}".format(ns, getType(my_type)))
                my_type = getNamespaceUnversioned(my_full_type) + ".v{}_{}_{}".format(*ns) + "." + getType(my_full_type)
                return my_type
        return my_type


class RedfishType:
    """Redfish Type

    Represents tags of 'Property', 'NavigationProperty' in an EntityType/ComplexType
    And also represents EntityType/ComplexType/EnumType/TypeDefinitions, not basic types like Edm
    """
    def __eq__(self, other):
        if isinstance(other, str):
            return other == str(self)
        else:
            return self == other

    def __repr__(self):
        return self.fulltype
    
    def __init__(self, soup, owner: SchemaClass):

        self.owner = owner
        self.catalog = owner.catalog

        self.type_soup = soup
        self.tag_type = soup.name

        if self.tag_type in ['NavigationProperty', 'Property', 'Term']:
            self.IsPropertyType = True
            self.IsNav = self.tag_type in ['NavigationProperty']
            self.fulltype = self.parent_type
        else:
            self.IsPropertyType = False
            self.IsNav = False
            self.fulltype = self.owner.class_name + '.' + soup['Name']

        if 'Collection(' in self.fulltype:
            my_fulltype = self.fulltype.replace('Collection(', "").replace(')', "")
            self.Namespace, self.TypeName = getNamespace(my_fulltype), getType(my_fulltype)
        else:
            self.Namespace, self.TypeName = getNamespace(self.fulltype), getType(self.fulltype)

        self.tags = {}
        for tag in self.type_soup.find_all(recursive=False):
            if tag.get('Term'):
                self.tags[tag['Term']] = tag.attrs
                if (tag.get('Term') == 'Redfish.Revisions'):
                    self.tags[tag['Term']] = tag.find_all('Record')

        propPermissions = self.tags.get('OData.Permissions')

        self.IsMandatory = self.tags.get('Redfish.Required') is not None
        self.IsNullable = self.type_soup.get("Nullable", "true") not in ["false", False, "False"]
        self.AutoExpand = (self.tags.get('OData.AutoExpand') or self.tags.get('OData.AutoExpand'.lower())) is not None
        self.Deprecated = self.tags.get('Redfish.Deprecated')
        self.Revisions = self.tags.get('Redfish.Revisions')
        self.Excerpt = False

        self.Permissions = propPermissions['EnumMember'] if propPermissions is not None else None

        self.excerptType = ExcerptTypes.NEUTRAL
        self.excerptTags = []

        for annotation, val in excerpt_info_by_type.items():
            if annotation in self.tags:
                self.excerptTags = self.tags.get(annotation).get('String', '').split(',')
                self.excerptTags = [x.strip(' ') for x in self.excerptTags] if self.excerptTags != [''] else []
                self.excerptType = val
        
        self.Excerpt = self.excerptType != ExcerptTypes.NEUTRAL

        self.property_pattern = None

        # get properties
        prop_tags = self.type_soup.find_all( ["NavigationProperty", "Property"], recursive=False)
    
        self.unique_properties = {}

        for innerelement in prop_tags:
            prop_name = innerelement["Name"]
            self.unique_properties[prop_name] = RedfishType(innerelement, self.owner)
    
    @property
    def HasAdditional(self):
        my_parents = self.getTypeTree()
        for my_type in my_parents:
            if not isinstance(my_type, RedfishType): continue
            if 'Bios' in str(my_type) and 'Attributes' in str(my_type):
                return True
            if my_type == 'MessageRegistry.v1_0_0.MessageProperty':
                return True
            additionalElement = my_type.type_soup.find("Annotation", attrs={"Term": "OData.AdditionalProperties"})
            HasAdditional = ( False if additionalElement is None else (
                    True if additionalElement.get("Bool", False) in ["True", "true", True]
                    else False))
            if HasAdditional:  
                return True
        return False

    @property
    def CanUpdate(self):
        return self.getCapabilities()['CanUpdate']

    @property
    def CanDelete(self):
        return self.getCapabilities()['CanDelete']

    @property
    def CanInsert(self):
        return self.getCapabilities()['CanInsert']

    def getCapabilities(self):
        my_dict = {'CanUpdate': False,
                   'CanInsert': False,
                   'CanDelete': False}

        my_parents = self.getTypeTree()
        for my_type in reversed(my_parents):
            if not isinstance(my_type, RedfishType): continue
            try:
                element = my_type.type_soup.find("Annotation", attrs={"Term": "Capabilities.InsertRestrictions"})
                if element:
                    my_dict['CanInsert'] = element.find("PropertyValue").get('Bool', 'False').lower() == 'true'
                element = my_type.type_soup.find("Annotation", attrs={"Term": "Capabilities.UpdateRestrictions"})
                if element:
                    my_dict['CanUpdate'] = element.find("PropertyValue").get('Bool', 'False').lower() == 'true'
                element = my_type.type_soup.find("Annotation", attrs={"Term": "Capabilities.DeleteRestrictions"})
                if element:
                    my_dict['CanDelete'] = element.find("PropertyValue").get('Bool', 'False').lower() == 'true'
            except Exception as e:
                my_logger.debug('Exception caught while checking Uri', exc_info=1)
                my_logger.warning('Could not gather info from Capabilities annotation')
                return {'CanUpdate': False, 'CanInsert': False, 'CanDelete': False}

        return my_dict

    @property
    def DynamicProperties(self):
        my_parents = self.getTypeTree()
        for my_type in reversed(my_parents):
            if not isinstance(my_type, RedfishType): continue
            try:
                dynamic = my_type.type_soup.find("Annotation", attrs={"Term": "Redfish.DynamicPropertyPatterns"})
                if dynamic: 
                    # create PropertyPattern dict containing pattern and type for DynamicPropertyPatterns validation
                    pattern_elem = dynamic.find("PropertyValue", Property="Pattern")
                    type_elem = dynamic.find("PropertyValue", Property="Type")
                    if pattern_elem and type_elem:
                        return {
                            "Pattern": pattern_elem.get("String"),
                            "Type": type_elem.get("String"),
                        }
                    if pattern_elem and not type_elem or type_elem and not pattern_elem:
                        raise ValueError('Cannot have pattern with Type in DynamicProperty annotation')

            except Exception as e:
                my_logger.debug('Exception caught while checking Dynamic', exc_info=1)
                my_logger.warning('Could not gather info from DynamicProperties annotation')
                return None 
        
        return None

    def getUris(self):
        """
        Return Redfish.Uris annotation values

        :return: Array of Uris
        :rtype: list
        """
        my_parents = self.getTypeTree()
        expectedUris = []
        for my_type in my_parents:
            if not isinstance(my_type, RedfishType): continue
            uriElement = my_type.type_soup.find("Annotation", attrs={"Term": "Redfish.Uris"})
            if uriElement is not None:
                try:
                    all_strings = uriElement.find("Collection").find_all("String")
                    expectedUris += [e.contents[0] for e in all_strings]
                except Exception as e:
                    my_logger.debug('Exception caught while checking Uri', exc_info=1)
                    my_logger.warning('Could not gather info from Redfish.Uris annotation')
                    expectedUris = []
        return expectedUris

    @property
    def parent_type(self):
        """
        Returns string of the parent type

        Returns:
            string of type
        """
        soup = self.type_soup
        parent_type = (
            soup["UnderlyingType"] if self.tag_type == "TypeDefinition"
            else soup.get("BaseType", soup.get("Type", None))
        )
        return parent_type
        
    def getTypeTree(self):
        """
        Returns tree of RedfishType/string of parent types
        """
        tree = [self]
        my_type = self.parent_type
        # 1000 seems to be a reasonable number to handle cases where a schema has lots of minor and errata versions in its tree (like Chassis or ComputerSystem)
        break_out = 1000
        while my_type and break_out != 0:
            break_out = break_out - 1
            if 'Edm.' not in my_type:
                type_obj = self.owner.parent_doc.catalog.getSchemaDocByClass(my_type).getTypeInSchemaDoc(my_type)
                tree.append(type_obj)
                my_type = type_obj.parent_type
            else:
                return tree + [my_type]
        if break_out == 0:
            my_logger.error("Schema definition for '{}' contained too many base type references; check its schema definition for loops".format(self.fulltype))
        return tree

    def getBaseType(self):
        """
        Returns string representing our tag type, and if that type is a collection

        TODO:  This should be an enum
            possible values ["complex", "enum", "entity", "Edm.String", "Edm.Int"...]

        Returns:
            string, boolean
            None, False
        """
        if self.tag_type == "EnumType":
            return 'enum'
        if self.tag_type == "ComplexType":
            return 'complex'
        if self.tag_type == "EntityType":
            return 'entity'

        my_type = self.parent_type
        if 'Edm.' in my_type:
            return my_type
        if self.IsPropertyType:
            type_obj = self.owner.parent_doc.catalog.getSchemaDocByClass(my_type).getTypeInSchemaDoc(my_type)
            return type_obj.getBaseType()
        return 'none'
    
    def IsCollection(self):
        tree = [self.fulltype]
        my_type = self.parent_type
        while my_type:
            if isinstance(my_type, RedfishType):
                tree.append(my_type.fulltype)
                my_type = self.parent_type
            else:
                tree.append(my_type)
                break
        return any([re.match(r'Collection\((.*)', typ) for typ in tree])
    
    def getCollectionType(self):
        my_new_type = stripCollection(self.fulltype)
        new_type_obj = self.catalog.getSchemaDocByClass(getNamespace(my_new_type)).getTypeInSchemaDoc(my_new_type)
        return new_type_obj

    def getProperties(self):
        """
        Returns all our properties from our current type and its parents
        """
        all_properties = {}
        for type_obj in self.getTypeTree():
            all_properties.update(type_obj.unique_properties)
        return all_properties

    def validate(self, val, added_pattern=None):
        """
        Returns True if validation succeeds, else raises a ValueError
        """
        my_logger.debug((self, val, self.fulltype, self.tag_type, self.parent_type))
        if val == REDFISH_ABSENT:
            if self.IsMandatory:
                raise ValueError("Should not be absent")
            else:
                return True
        if val is None:
            if not self.IsNullable:
                raise ValueError("Should not be null")
            else:
                return True
        # recurse parent_types until we get a basic type...
        if self.tag_type == "EnumType":
            my_enums = [x["Name"] for x in self.type_soup.find_all("Member")]
            if val not in my_enums:
                raise ValueError("Value {} Enum not found in {}".format(val, my_enums))
        if self.tag_type == "ComplexType":
            if not isinstance(val, dict):
                raise ValueError("Complex value is not Dict")
            my_complex = self.createObject().populate(val)
        if self.tag_type == "EntityType":
            return True
        my_type = self.parent_type
        if my_type:
            if 'Edm.' not in my_type:
                type_obj = self.owner.parent_doc.catalog.getSchemaDocByClass(my_type).getTypeInSchemaDoc(my_type)
                return type_obj.validate(val)
            else:
                enum_annotation = self.type_soup.find('Annotation', attrs={'Term': 'Redfish.Enumeration'}, recursive=False)
                validPatternAttr = self.type_soup.find('Annotation', attrs={'Term': 'Validation.Pattern'})
                validMinAttr = self.type_soup.find('Annotation', attrs={'Term': 'Validation.Minimum'})
                validMaxAttr = self.type_soup.find('Annotation', attrs={'Term': 'Validation.Maximum'})
                validMin, validMax = int(validMinAttr['Int']) if validMinAttr is not None else None, \
                    int(validMaxAttr['Int']) if validMaxAttr is not None else None
                validPattern = validPatternAttr.get('String', '') if validPatternAttr is not None else None
                if added_pattern is not None:
                    validPattern = added_pattern

                if my_type == 'Edm.String' and enum_annotation is not None:
                    memberList = enum_annotation.find('Collection').find_all('PropertyValue', attrs={'Property': 'Member'})
                    validPattern = '|'.join([re.escape(x.get('String')) for x in memberList if x.get('String')])

                return RedfishProperty.validate_basic(val, my_type, validPattern, validMin, validMax)
        return True
    
    def as_json(self):
        return self.createObject().as_json()
    
    def createObject(self, name='Object'):
        return RedfishObject(self, name)
                

class RedfishProperty(object):
    """Property in a resource
    Represents all Types given, however, ComplexTypes are better suited to be RedfishObjects
    """
    def __repr__(self):
        if self.Populated:
            return "{}--{}, Value: {}".format(self.Name, self.Type, self.Value)
        else:
            return "{}--{}".format(self.Name, self.Type)

    def __init__(self, my_type, name="Property", parent=None):
        self.Name = name
        self.Type = my_type
        self.HasSchema = self.Type != REDFISH_ABSENT
        self.Populated = False
        self.Value = None
        self.IsValid = False
        self.IsCollection = False
        self.InAnnotation = False
        self.IsAutoExpanded = False
        self.IsExcerpt = False
        self.SchemaExists = False
        self.Exists = False
        self.parent = parent
        self.added_pattern = None

    def populate(self, val, check=False):
        eval_prop = copy.copy(self)
        eval_prop.Populated = True
        eval_prop.Value = val
        eval_prop.IsCollection = isinstance(val, list)
        eval_prop.InAnnotation = False
        eval_prop.SchemaExists = True
        eval_prop.Exists = val != REDFISH_ABSENT

        eval_prop.IsValid = True

        if isinstance(eval_prop.Type, str):
            is_type_collection = 'Collection(' in eval_prop.Type
        elif isinstance(eval_prop.Type, RedfishType):
            is_type_collection = eval_prop.Type.IsCollection()
        else:
            raise ValueError('Type is not String or RedfishType')
        if eval_prop.IsCollection and not is_type_collection:
            my_logger.error('Property {} should not be a List'.format(self.Name))
            eval_prop.IsValid = False
        elif not eval_prop.IsCollection and is_type_collection and val not in [None, REDFISH_ABSENT]:
            my_logger.error('Collection Property {} is not a List'.format(self.Name))
            eval_prop.IsValid = False

        if isinstance(eval_prop.Type, str) and 'Edm.' in eval_prop.Type and check:
            try:
                eval_prop.IsValid = eval_prop.Exists and RedfishProperty.validate_basic(eval_prop.Value, eval_prop.Type)
            except ValueError as e:
                my_logger.error('{}: {}'.format(eval_prop.Name, e))  # log this
                eval_prop.IsValid = False
        elif isinstance(eval_prop.Type, RedfishType) and check:
            try:
                eval_prop.IsValid = eval_prop.Type.validate(eval_prop.Value, eval_prop.added_pattern)
            except ValueError as e:
                my_logger.error('{}: {}'.format(eval_prop.Name, e))  # log this
                eval_prop.IsValid = False
        return eval_prop

    def as_json(self):
        my_dict = {x: y for x, y in vars(self).items() if x in ['Name', 'Type', 'Value', 'IsValid', 'Exists', 'SchemaExists']}
        if isinstance(self.Type, RedfishType):
            my_dict['IsRequired'] = self.Type.IsMandatory
            my_dict['IsNullable'] = self.Type.IsNullable
            my_dict['HasAdditional'] = self.Type.HasAdditional
        return my_dict
    
    def getLinks(self):
        return []
    
    @staticmethod
    def validate_string(val, pattern):
        """validateString

        Validates a string, given a value and a pattern
        """
        if not isinstance(val, str):
            raise ValueError(
                "Expected string value, got type {}".format(str(type(val)).strip("<>"))
            )
        if pattern is not None:
            match = re.fullmatch(pattern, val)
            if match is None:
                raise ValueError(
                    "String '{}' does not match pattern '{}'".format(
                        str(val), repr(pattern)
                    )
                )
        return True

    @staticmethod
    def validate_number(val, minVal=None, maxVal=None):
        """validateNumber

        Validates a Number and its min/max values
        """

        if not isinstance(val, (int, float)):
            raise ValueError(
                "Expected integer or float, got type {}".format(
                    str(type(val)).strip("<>")))
        if minVal is not None:
            if not minVal <= val:
                raise ValueError(
                    "Value out of assigned min range, {} > {}".format(
                        str(val), str(minVal)))
        if maxVal is not None:
            if not maxVal >= val:
                raise ValueError(
                    "Value out of assigned max range, {} > {}".format(
                        str(val), str(maxVal)))
        return True

    @staticmethod
    def validate_basic(val, my_type, validPattern=None, min=None, max=None):
        if "Collection(" in my_type:
            my_type = my_type.replace("Collection(", "").replace(")", "")

        if isinstance(val, list):
            return all([RedfishProperty.validate_basic(sub_val, my_type, validPattern, min, max) for sub_val in val])

        elif my_type == "Edm.Boolean":
            if not isinstance(val, bool):
                raise ValueError(
                    "Expected bool, got type {}".format(str(type(val)).strip("<>")))
            return True

        elif my_type == "Edm.DateTimeOffset":
            return RedfishProperty.validate_string(
                val, r".*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])")

        elif my_type == "Edm.Duration":
            return RedfishProperty.validate_string(
                val, r"P([0-9]+D)?(T([0-9]+H)?([0-9]+M)?([0-9]+(\.[0-9]+)?S)?)?")

        elif my_type == "Edm.Guid":
            return RedfishProperty.validate_string(
                val, r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

        elif my_type == "Edm.String":
            return RedfishProperty.validate_string(val, validPattern)

        elif my_type in ["Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Int"]:
            if not isinstance(val, int):
                raise ValueError("Expected int, got type {}".format(str(type(val)).strip("<>")))
            return RedfishProperty.validate_number(val, min, max)

        elif my_type == "Edm.Decimal" or my_type == "Edm.Double":
            return RedfishProperty.validate_number(val, min, max)

        elif my_type == "Edm.Primitive" or my_type == "Edm.PrimitiveType":
            if not isinstance(val, (int, float, str, bool)):
                raise ValueError("Expected primitive, got type {}".format(str(type(val)).strip("<>")))
            return True

        else:
            return False

class RedfishObject(RedfishProperty):
    """Represents Redfish as they are represented as Resource/ComplexTypes

    Can be indexed with []
    Can be populated with Data
    If Populated, can be grabbed for Links
    Can get json representation of type properties with as_json
    """
    def __getitem__(self, index):
        return self.properties[index]

    def __contains__(self, item):
        if self.Populated:
            return item in self.properties and self.properties[item].Exists
        else:
            return item in self.properties

    def __init__(self, redfish_type: RedfishType, name="Object", parent=None):
        super().__init__(redfish_type, name, parent)
        self.payload = None
        self.HasValidUri = False
        self.HasValidUriStrict = False
        self.properties = {}
        for prop, typ in redfish_type.getProperties().items():
            try:
                base = typ.getBaseType()
                if base == 'complex':
                    self.properties[prop] = RedfishObject(typ, prop, self)
                else:
                    self.properties[prop] = RedfishProperty(typ, prop, self)
            except MissingSchemaError:
                self.properties[prop] = RedfishProperty(REDFISH_ABSENT, prop, self)
                my_logger.warning('Schema not found for {}'.format(typ))

    def populate(self, payload, uri_check=False, casted=False):
        """
        Return a populated object, or list of objects
        """
        populated_object = super().populate(payload)
        populated_object.payload = payload

        if isinstance(payload, list):
            populated_object.IsValid = populated_object.Type.IsCollection()
            if not populated_object.IsValid:
                my_logger.error("This object's type {} should be a Collection, but it's of type {}...".format(populated_object.Name, populated_object.Type))
                return populated_object
            populated_object.IsCollection = True

            my_new_type = stripCollection(populated_object.Type.fulltype)

            new_type_obj = populated_object.Type.catalog.getSchemaDocByClass(getNamespace(my_new_type)).getTypeInSchemaDoc(my_new_type)

            new_rf_object = RedfishObject(new_type_obj, populated_object.Name, populated_object.parent)

            populated_object.Value = [new_rf_object.populate(sub_item, uri_check, casted) for sub_item in payload]
            return populated_object
        else:
            if populated_object.Type.IsCollection():
                if payload in [REDFISH_ABSENT, None]:
                    populated_object.Value = payload
                    return populated_object
                else:
                    my_logger.error("This object {} should be a list, but it's of type {}...".format(populated_object.Name, type(payload).__name__))
                    return populated_object

        # todo: redesign objects to have consistent variables, not only when populated
        # if populated, should probably just use another python class?
        # remember that populated RedfishObjects may have more objects embedded in them
        # i.e. OEM or complex or arrays
        if payload == REDFISH_ABSENT or payload is None:
            populated_object.HasValidUri = True
            populated_object.HasValidUriStrict = False
            populated_object.properties = {x: y.populate(REDFISH_ABSENT) for x, y in populated_object.properties.items()}
            return populated_object

        populated_object.IsValid = isinstance(payload, dict)

        # Only valid if we are a dictionary...
        # todo: see above None/REDFISH_ABSENT block
        if not populated_object.IsValid:
            my_logger.error("This complex object {} should be a dictionary or None, but it's of type {}...".format(populated_object.Name, type(payload).__name__))
            populated_object.HasValidUri = True
            populated_object.HasValidUriStrict = False
            populated_object.properties = {x: y.populate(REDFISH_ABSENT) for x, y in populated_object.properties.items()}
            return populated_object

        # Cast types if they're below their parent or are OemObjects
        # Don't cast objects with odata.type that matches their current object type
        already_typed = False
        sub_payload = payload
        my_odata_type = sub_payload.get('@odata.type')
        if my_odata_type is not None and str(populated_object.Type) == my_odata_type.strip('#'):
            already_typed = True
        if populated_object.Type.IsNav:
            already_typed = True

        # If our item is an OemObject type and hasn't been casted to a type, then cast it
        if 'Resource.OemObject' in populated_object.Type.getTypeTree() and not casted:
            my_logger.verbose1(('Morphing OemObject', my_odata_type, populated_object.Type))
            if my_odata_type:
                my_odata_type = my_odata_type.strip('#')
                try:
                    type_obj = populated_object.Type.catalog.getSchemaDocByClass(my_odata_type).getTypeInSchemaDoc(my_odata_type)
                    populated_object = RedfishObject(type_obj, populated_object.Name, populated_object.parent).populate(sub_payload, uri_check=uri_check, casted=True)
                except MissingSchemaError:
                    my_logger.warning("Couldn't get schema for object, skipping OemObject {}".format(populated_object.Name))
                except Exception as e:
                    my_logger.warning("Couldn't get schema for object (?), skipping OemObject {} : {}".format(populated_object.Name, e))
                return populated_object
        # Otherwise, if we're not casted, or we don't have an odata type, then cast it
        elif not casted and not already_typed:
            my_ns, my_ns_unversioned = populated_object.Type.Namespace, getNamespaceUnversioned(populated_object.Type.Namespace)
            # if we have an odata type, use it as our upper limit
            if my_odata_type:
                my_limit = getNamespace(my_odata_type).strip('#')
            else:
                my_limit = 'v9_9_9'
            # If our item is not a Resource.Resource type, determine its parent's version limit for later...
            # NOTE: Resource items always seem to be cast to highest type, not determined by its parent's type
            #       not sure where this is backed up in documentation
            if populated_object.parent and my_ns_unversioned not in ['Resource']:
                parent = populated_object
                while parent.parent and parent.parent.Type.Namespace.startswith(my_ns_unversioned + '.'):
                    parent = parent.parent
                    my_limit = parent.Type.Namespace

            my_type = populated_object.Type.TypeName
            top_ns = my_ns

            # get type order from bottom up of SchemaDoc
            for top_ns, schema in reversed(list(populated_object.Type.catalog.getSchemaDocByClass(my_ns).classes.items())):
                # if our object type is in schema... check for limit
                if my_type in schema.my_types:
                    if splitVersionString(top_ns) <= splitVersionString(my_limit):
                        my_ns = top_ns
                        break
            # ISSUE: We can't cast under v1_0_0, get the next best Type
            if my_ns == my_ns_unversioned:
                my_ns = top_ns
            if my_ns not in populated_object.Type.Namespace:
                # NOTE: This returns a Type object without IsPropertyType
                my_logger.verbose1(('Morphing Complex', my_ns, my_type, my_limit))
                new_type_obj = populated_object.Type.catalog.getSchemaDocByClass(my_ns).getTypeInSchemaDoc('.'.join([my_ns, my_type]))
                populated_object = RedfishObject(new_type_obj, populated_object.Name, populated_object.parent).populate(sub_payload, uri_check=uri_check, casted=True)
                return populated_object

        # Validate our Uri
        populated_object.HasValidUri = True
        populated_object.HasValidUriStrict = True
        allowable_uris = populated_object.Type.getUris()
        # If we have expected URIs and @odata.id
        # And we AREN'T a navigation property
        if not populated_object.Type.catalog.flags['ignore_uri_checks'] and len(allowable_uris) and '@odata.id' in sub_payload:
            # Strip our URI and warn if that's the case
            my_odata_id = sub_payload['@odata.id']
            if my_odata_id != '/redfish/v1/' and my_odata_id.endswith('/'):
                # NOTE: uri_check is only used to suppress this message, look into better message suppression
                if uri_check:
                    my_logger.warning('Stripping end of URI... {}'.format(my_odata_id))
                my_odata_id = my_odata_id.rstrip('/')

            # Initial check if our URI matches our format at all
            # Setup REGEX...
            my_uri_regex = "^{}$".format("|".join(allowable_uris))
            my_uri_regex = re.sub(URI_ID_REGEX, VALID_ID_REGEX, my_uri_regex)
            populated_object.HasValidUri = re.fullmatch(my_uri_regex, my_odata_id) is not None
            populated_object.HasValidUriStrict = populated_object.HasValidUri

            if 'Resource.Resource' in populated_object.Type.getTypeTree():
                if '#' in my_odata_id:
                    my_logger.warning('Found uri with fragment, which Resource.Resource types do not use {}'.format(my_odata_id))
            elif 'Resource.ReferenceableMember' in populated_object.Type.getTypeTree():
                if '#' not in my_odata_id:
                    my_logger.warning('No fragment in URI, but ReferenceableMembers require it {}'.format(my_odata_id))

            # check that our ID is matching
            # this won't check NavigationProperties but the Resources will
            if populated_object.HasValidUri and not populated_object.Type.IsNav:
                # pair our type, Id value, and odata.id value
                my_odata_split = my_odata_id.split('/')
                my_type, my_id, my_uri_id = populated_object.Type.TypeName, sub_payload.get('Id'), my_odata_split[-1]

                for schema_uri in allowable_uris:
                    # regex URI check to confirm which URI 
                    my_uri_regex = re.sub(URI_ID_REGEX, VALID_ID_REGEX, "^{}$".format(schema_uri))
                    if re.fullmatch(my_uri_regex, my_odata_id):
                        # pair our uri with the current resource
                        schema_uri_end = schema_uri.rsplit('/')[-1]
                        # if our Uri is expecting an Id, then check if they match, otherwise we are already passing
                        if re.match(URI_ID_REGEX, schema_uri_end):
                            if my_id is not None:
                                populated_object.HasValidUriStrict = my_id == my_uri_id
                        break

        # TODO: Oem support is able, but it is tempermental for Actions and Additional properties
        #if 'Resource.OemObject' in sub_obj.Type.getTypeTree():
        #    evals.append(sub_obj)
        #    continue

        # populate properties
        if populated_object.Name == 'Actions':
            populated_object.properties = {x: y.populate(sub_payload.get(x, REDFISH_ABSENT)) for x, y in populated_object.properties.items() if x != 'Oem'}
        else:
            populated_object.properties = {x: y.populate(sub_payload.get(x, REDFISH_ABSENT)) for x, y in populated_object.properties.items()}

        # additional_props
        if populated_object.Type.DynamicProperties:
            my_dynamic = populated_object.Type.DynamicProperties
            my_odata_type = my_dynamic.get('Type', 'Resource.OemObject')
            prop_pattern = my_dynamic.get('Pattern', '.*')
            allow_property_generation = populated_object.Name != 'Actions'
        else:
            my_odata_type = 'Resource.OemObject'
            prop_pattern = '.*'
            allow_property_generation = populated_object.Type.HasAdditional and populated_object.Name != 'Actions'

        if allow_property_generation:
            my_property_names = [x for x in sub_payload if x not in populated_object.properties if re.match(prop_pattern, x) and '@' not in x]
            for add_name in my_property_names:
                if 'Edm.' in my_odata_type:
                    my_new_term = '<Term Name="{}" Type="{}"> </Term>'.format(add_name, my_odata_type) # Make a pseudo tag because RedfishType requires it...
                    new_soup = BeautifulSoup(my_new_term, "xml").find('Term')
                    type_obj = RedfishType(new_soup, populated_object.Type.owner)
                else:
                    type_obj = populated_object.Type.catalog.getSchemaDocByClass(my_odata_type).getTypeInSchemaDoc(my_odata_type)
                if type_obj.getBaseType() == 'complex':
                    object = RedfishObject(type_obj, name=add_name, parent=populated_object)
                else:
                    object = RedfishProperty(type_obj, name=add_name, parent=populated_object)
                my_logger.debug('Populated {} with {}'.format(my_property_names, object.as_json()))
                my_logger.verbose1(('Adding Additional', add_name, my_odata_type, populated_object.Type))
                populated_object.properties[add_name] = object.populate(sub_payload.get(add_name, REDFISH_ABSENT))

        my_annotations = [x for x in sub_payload if x not in populated_object.properties if '@' in x and '@odata' not in x]
        for key in my_annotations:
            splitKey = key.split('@', 1)
            fullItem = splitKey[1]
            if getNamespace(fullItem) not in allowed_annotations:
                my_logger.warning("getAnnotations: {} is not an allowed annotation namespace, please check spelling/capitalization.".format(fullItem))
                continue
            try:
                type_obj = populated_object.Type.catalog.getSchemaInCatalog(fullItem).terms[getType(fullItem)]
                if type_obj.getBaseType() == 'complex':
                    object = RedfishObject(type_obj, name=key, parent=populated_object)
                else:
                    object = RedfishProperty(type_obj, name=key, parent=self)
                my_logger.verbose1(('Adding Additional', key, my_odata_type, populated_object.Type))
                populated_object.properties[key] = object.populate(sub_payload[key])
            except:
                my_logger.error("Unable to locate the definition of the annotation '@{}'.".format(fullItem))

        return populated_object

    def as_json(self):
        if self.Populated:
            return {'Properties' : {a: b.as_json() for a, b in self.properties.items() if (b.Exists or not b.IsValid)}}
        else:
            # base = {'Self': super().as_json()}
            base = super().as_json()
            base.update({'Properties': {a: b.as_json() for a, b in self.properties.items()}})
            return base

    def getLinks(self, collectionlimit={}):
        """Grab links from our Object
        """
        links = []
        # if we're populated...
        if self.Populated:
            for n, property in self.properties.items():
                # if we don't exist or our type is Basic
                if not isinstance(property, list):
                    property = [property]
                for item in property:
                    if not item.Exists: continue
                    if not isinstance(item.Type, RedfishType): continue
                    if n == 'Actions':
                        new_type = item.Type.catalog.getTypeInCatalog('ActionInfo.ActionInfo')
                        for act in item.Value.values():
                            if isinstance(act, dict):
                                uri = act.get('@Redfish.ActionInfo')
                                if isinstance(uri, str):
                                    my_link = RedfishObject(new_type, 'ActionInfo', item).populate({'@odata.id': uri})
                                    my_link.InAnnotation = True
                                    links.append(my_link)
                    if item.Type.IsNav:
                        if isinstance(item.Value, list):
                            for num, val in enumerate(item.Value):
                                # TODO: Along with example Excerpt and RedfishObject, replace following code with hypothetical RedfishType.getCollectionType
                                if item.Type.TypeName in collectionlimit:
                                    link_limit = collectionlimit[item.Type.TypeName]
                                    if num >= link_limit:
                                        my_logger.verbose1('Removing link via limit: {} {}'.format(item.Type.TypeName, val))
                                        continue
                                try:
                                    new_type_obj = item.Type.getCollectionType()
                                    new_link = RedfishObject(new_type_obj, item.Name, item.parent).populate(val)
                                    new_link.Name = new_link.Name + '#{}'.format(num)
                                    if item.Type.AutoExpand:
                                        new_link.IsAutoExpanded = True
                                    if item.Type.Excerpt:
                                        new_link.IsExcerpt = True
                                    links.append(new_link)
                                except Exception as e:
                                    my_logger.error('Unable to build definition for URI {}; check its schema definition or the schema making the reference to the URI for schema errors: {}'.format(val, repr(e)))
                        else:
                            links.append(item)
                    elif item.Type.getBaseType() == 'complex':
                        if item.Value is None:
                            continue
                        InAnnotation = item.Name in ['@Redfish.Settings', '@Redfish.ActionInfo', '@Redfish.CollectionCapabilities']
                        my_links = item.getLinks()
                        for sub_item in my_links:
                            sub_item.InAnnotation = InAnnotation
                        links.extend(my_links)
        return links
