import glob, copy, difflib
import logging
import re
from collections import namedtuple
from enum import Enum, auto
from os import path

from bs4 import BeautifulSoup

from common.helper import (
    compareMinVersion,
    getNamespace,
    getNamespaceUnversioned,
    getType,
    getVersion,
    splitVersionString,
)

includeTuple = namedtuple("include", ["Namespace", "Uri"])

my_logger = logging.getLogger(__name__)

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
    possibleMatch = difflib.get_close_matches(prop_name, [s for s in jsondata], 1, 0.70)
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
        typename = getNamespaceUnversioned(typename)
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
        

REDFISH_ABSENT = "n/a"


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

        edmxTag = self.soup.find("edmx:Edmx", recursive=False)
        reftags = edmxTag.find_all("edmx:Reference", recursive=False)
        self.refs = {}
        for ref in reftags:
            includes = ref.find_all("edmx:Include", recursive=False)
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

        parentTag = edmxTag.find("edmx:DataServices", recursive=False)
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
            currentType = getType(currentType.parent_type[0]) if currentType.IsPropertyType else currentType.fulltype
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
                if compareMinVersion(newNamespace, limit):
                    continue
            if (my_type in self.my_types):
                typelist.append(splitVersionString(newNamespace))

        if len(typelist) > 1:
            for ns in reversed(sorted(typelist)):
                my_logger.debug("{}   {}".format(ns, getType(my_type)))
                my_type = getNamespaceUnversioned(my_full_type) + ".v{}_{}_{}".format(*ns) + "." + getType(my_full_type)
                return my_type
        return my_type


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
            self.fulltype = self.owner.class_name + ':' + soup['Name']
            self.Namespace, self.Type = getNamespace(self.fulltype), getType(self.fulltype)
        else:
            self.IsPropertyType = False
            self.fulltype = self.owner.class_name + '.' + soup['Name']
            self.Namespace, self.Type = getNamespace(self.fulltype), getType(self.fulltype)

        self.tags = {}
        for tag in self.type_soup.find_all(recursive=False):
            if(not tag.get('Term')):
                my_logger.debug((tag, 'does not contain a Term name'))
            else:
                self.tags[tag['Term']] = tag.attrs
            if (tag.get('Term') == 'Redfish.Revisions'):
                self.tags[tag['Term']] = tag.find_all('Record')



        dynamic = self.type_soup.find("Annotation", attrs={"Term": "Redfish.DynamicPropertyPatterns"})
        uriElement = self.type_soup.find("Annotation", attrs={"Term": "Redfish.Uris"})
        propPermissions = self.tags.get('OData.Permissions')

        self.IsMandatory = self.tags.get('Redfish.Required') is not None
        self.IsNullable = self.type_soup.get("Nullable", "true") not in ["false", False, "False"]
        self.AutoExpand = self.tags.get('OData.AutoExpand', None) is not None or self.tags.get('OData.AutoExpand'.lower(), None) is not None
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

        if dynamic is not None:
            # create PropertyPattern dict containing pattern and type for DynamicPropertyPatterns validation
            pattern_elem = dynamic.find("PropertyValue", Property="Pattern")
            type_elem = dynamic.find("PropertyValue", Property="Type")
            if pattern_elem and type_elem:
                self.property_pattern = {
                    "Pattern": pattern_elem.get("String"),
                    "Type": type_elem.get("String"),
                }

        self.expectedURI = None
        if uriElement is not None:
            try:
                all_strings = uriElement.find("Collection").find_all("String")
                self.expectedURI = [e.contents[0] for e in all_strings]
            except Exception as e:
                # logger.debug('Exception caught while checking URI', exc_info=1)
                # logger.warn('Could not gather info from Redfish.Uris annotation')
                self.expectedURI = None
            uriElement = self.type_soup.find(
                "Annotation", attrs={"Term": "Redfish.Uris"}
            )

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
            additionalElement = my_type.type_soup.find("Annotation", attrs={"Term": "OData.AdditionalProperties"})
            HasAdditional = ( False if additionalElement is None else (
                    True if additionalElement.get("Bool", False) in ["True", "true", True]
                    else False))
            if HasAdditional: return True
        return False
     
    @property 
    def parent_type(self):
        soup = self.type_soup
        parent_type = (
            soup["UnderlyingType"] if self.tag_type == "TypeDefinition"
            else soup.get("BaseType", soup.get("Type", None))
        )
        if parent_type is not None:
            IsCollection = re.match('Collection\(.*\)', parent_type) is not None
            return parent_type.replace('Collection(', "").replace(')', ""), IsCollection
        else:
            return None, False
        
    def getTypeTree(self, tree=None):
        if not tree: tree = [self]
        my_type, collection = self.parent_type
        if my_type:
            if 'Edm.' not in my_type:
                my_real_type = my_type
                type_obj = self.owner.parent_doc.catalog.getSchemaDocByClass(my_real_type).getTypeInSchemaDoc(my_real_type)
                return type_obj.getTypeTree(tree + [type_obj])
            else:
                return tree + [my_type]
        return tree

    def getBaseType(self, is_collection=False):
        if self.tag_type == "EnumType":
            return 'enum', is_collection
        if self.tag_type == "ComplexType":
            return 'complex', is_collection
        if self.tag_type == "EntityType":
            return 'entity', is_collection
        if self.IsPropertyType:
            my_type, parent_collection = self.parent_type
            is_collection=parent_collection or is_collection
            if 'Edm.' in my_type:
                return my_type, is_collection
            type_obj = self.owner.parent_doc.catalog.getSchemaDocByClass(my_type).getTypeInSchemaDoc(my_type)
            return type_obj.getBaseType(is_collection)
        return 'none', is_collection

    def getProperties(self):
        all_properties = {}
        for type_obj in self.getTypeTree():
            all_properties.update(type_obj.unique_properties)
        return all_properties

    def validate(self, val):
        my_logger.debug((self, val, self.fulltype, self.tag_type, self.parent_type))
        if val == REDFISH_ABSENT:
            if self.type_soup.find("Annotation", attrs={"Term": "Redfish.Required"}):
                raise ValueError("Should not be absent")
            else:
                return True
        if val is None: 
            if self.type_soup.get("Nullable") in ["false", "False", False]:
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
        my_type, collection = self.parent_type
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

                if my_type == 'Edm.String' and enum_annotation is not None:
                    memberList = enum_annotation.find('Collection').find_all('PropertyValue', attrs={'Property': 'Member'})
                    validPattern = '|'.join([re.escape(x.get('String')) for x in memberList if x.get('String')])

                return RedfishProperty.validate_basic(val, my_type, validPattern, validMin, validMax)
        return True
    
    def as_json(self):
        return self.createObj().as_json()
    
    def createObject(self):
        return RedfishObject(self)
                
        # if 'OemObject' in eval_prop.Type.fulltype:
        #     my_real_type = val.get('@odata.type', 'Resource.OemObject')
        #     eval_prop.Type = eval_prop.Type.owner.parent_doc.catalog.getSchemaDocByClass(my_real_type).getTypeInSchemaDoc(my_real_type)
class RedfishProperty(object):
    """Property in a resource
    Represents all Types given, however, ComplexTypes are better suited to be RedfishObjects
    """
    def __repr__(self):
        return "{}--{}".format(self.Name, self.Type)

    def __init__(self, my_type, name="Property", parent=None):
        self.Name = name
        self.Type = my_type
        self.HasSchema = self.Type != REDFISH_ABSENT
        self.Populated = False
        self.parent = parent

    def populate(self, val, check=False):
        eval_prop = copy.copy(self)
        eval_prop.Populated = True
        eval_prop.Value = val
        eval_prop.IsValid = True
        eval_prop.SchemaExists = True
        eval_prop.Exists = val != REDFISH_ABSENT
        if isinstance(eval_prop.Type, str) and 'Edm.' in eval_prop.Type and check:
            try:
                eval_prop.IsValid = eval_prop.Exists and RedfishProperty.validate_basic(
                    val, eval_prop.Type
                )
            except ValueError as e:
                my_logger.error('{}: {}'.format(self.Name, e))  # log this
                eval_prop.IsValid = False
        elif isinstance(eval_prop.Type, RedfishType) and check:
            try:
                eval_prop.IsValid = eval_prop.Type.validate(val)
            except ValueError as e:
                my_logger.error('{}: {}'.format(self.Name, e))  # log this
                eval_prop.IsValid = False
        return eval_prop

    def as_json(self):
        my_dict = {x: y for x, y in vars(self).items() if x in ['Name', 'Type', 'Value', 'IsValid', 'Exists', 'SchemaExists']}
        if isinstance(self.Type, RedfishType):
            my_dict['IsRequired'] = self.Type.IsMandatory
            my_dict['IsNullable'] = self.Type.IsNullable
            my_dict['HasAdditional'] = self.Type.HasAdditional
            pass
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
            if not isinstance(val, list):
                raise ValueError("Collection is not list")
            my_collection_type = my_type.replace("Collection(", "").replace(")", "")
            paramPass = True
            for cnt, item in enumerate(val):
                try:
                    paramPass = paramPass and RedfishProperty.validate_basic(item, my_collection_type, validPattern, min, max)
                except ValueError as e:
                    paramPass = False
                    raise ValueError('{} invalid'.format(cnt))
            return paramPass

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
                val, r"-?P([0-9]+D)?(T([0-9]+H)?([0-9]+M)?([0-9]+(\.[0-9]+)?S)?)?")

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

allowed_annotations = ['odata', 'Redfish', 'Privileges', 'Message']
# class RedfishAnnotation(RedfishProperty):
#     def populate(self, val, check=False):
#         eval_prop = copy.copy(self)
#         eval_prop.Populated = True
#         eval_prop.Value = val
#         eval_prop.IsValid = True
#         eval_prop.SchemaExists = True
#         eval_prop.Exists = val != REDFISH_ABSENT

class RedfishObject(RedfishProperty):
    """Represents Redfish as they are represented as Resource/ComplexTypes

    Can be indexed with []
    Can be populated with Data
    If Populated, can be grabbed for Links
    Can get json representation of type properties with as_json
    """
    def __getitem__(self, index):
        return self.properties[index]

    def __init__(self, redfish_type: RedfishType, name="Object", parent=None):
        super().__init__(redfish_type, name, parent)
        self.properties = {}
        for prop, typ in redfish_type.getProperties().items():
            try:
                base, collection = typ.getBaseType()
                if base == 'complex':
                    self.properties[prop] = RedfishObject(typ, prop, self)
                else:
                    self.properties[prop] = RedfishProperty(typ, prop, self)
            except MissingSchemaError:
                self.properties[prop] = RedfishProperty(REDFISH_ABSENT, prop, self)
                my_logger.warn('Schema not found for {}'.format(typ))

    def populate(self, payload, check=False, casted=False):
        eval_obj = super().populate(payload)
        eval_obj.payload = payload

        if payload == REDFISH_ABSENT:
            eval_obj.Collection = []
            eval_obj.IsValid = eval_obj.Type.IsNullable
            eval_obj.properties = {x:y.populate(REDFISH_ABSENT) for x, y in eval_obj.properties.items()}
            return eval_obj

        # Representation for Complexes as Collection, unless it is not a list
        # If an list object changes when populated, it will be represented properly here
        evals = []
        payloads = [payload]
        if isinstance(payload, list):
            payloads = payload
        for load in payloads:
            sub_obj = copy.copy(eval_obj)
            # Cast types if they're below their parent or are OemObjects
            already_typed = False
            my_odata_type = load.get('@odata.type')
            if my_odata_type is not None and str(sub_obj.Type) == my_odata_type.strip('#'):
                already_typed = True

            # we can only cast if we have an odata type and valid schema
            if 'Resource.OemObject' in sub_obj.Type.getTypeTree() and not casted:
                my_logger.log(logging.INFO-1,('Morphing OemObject', my_odata_type, sub_obj.Type))
                if my_odata_type:
                    my_odata_type = my_odata_type.strip('#')
                    try:
                        type_obj = sub_obj.Type.catalog.getSchemaDocByClass(my_odata_type).getTypeInSchemaDoc(my_odata_type)
                        sub_obj = RedfishObject(type_obj, sub_obj.Name, sub_obj.parent).populate(load, check=check, casted=True)
                    except MissingSchemaError:
                        my_logger.warn("Couldn't get schema for object, skipping OemObject {}".format(sub_obj.Name))
                    except Exception as e:
                        my_logger.warn("Couldn't get schema for object (?), skipping OemObject {} : {}".format(sub_obj.Name, e))
                    evals.append(sub_obj)
                    continue
            # or if we're a Resource or unversioned or v1_0_0 type
            elif not casted and not already_typed:
                my_ns = getNamespace(sub_obj.Type.parent_type[0]) if sub_obj.Type.IsPropertyType else sub_obj.Type.Namespace
                sub_base = getNamespaceUnversioned(my_ns)
                try:
                    min_version = min([tuple(splitVersionString(x.Namespace)) for x in sub_obj.Type.getTypeTree() if not x.IsPropertyType and sub_base in x.Namespace])
                    min_version = 'v' + '_'.join([str(x) for x in min_version])
                except:
                    my_logger.debug('Issue getting minimum version', exc_info=1)
                    min_version = 'v1_0_0'
                if my_ns in [sub_base, sub_base + '.v1_0_0', '.'.join([sub_base, min_version])] or my_odata_type:
                    my_limit = 'v9_9_9'
                    if my_odata_type:
                        my_limit = getNamespace(my_odata_type).strip('#')
                    if sub_obj.parent and sub_base not in 'Resource': # we always cast Resource objects
                        parent = sub_obj.parent
                        while True:
                            my_limit = parent.Type.Namespace
                            if not parent.parent or not parent.parent.Type.Namespace.startswith(sub_base + '.'):
                                break
                            parent = parent.parent
                    my_type = getType(sub_obj.Type.parent_type[0]) if sub_obj.Type.IsPropertyType else sub_obj.Type.Type
                    # get type order from bottom up of schema, check if my_type in that schema
                    top_ns = None
                    for new_ns, schema in reversed(list(sub_obj.Type.catalog.getSchemaDocByClass(my_ns).classes.items())):
                        if my_type in schema.my_types:
                            if top_ns is None:
                                top_ns = new_ns
                            if not compareMinVersion(new_ns, my_limit):
                                my_ns = new_ns
                                break
                    # ISSUE: We can't cast under v1_0_0, get the next best Type
                    if my_ns == sub_base:
                        my_ns = top_ns
                    if my_ns not in sub_obj.Type.Namespace:
                        my_logger.log(logging.INFO-1, ('Morphing Complex', my_ns, my_type, my_limit))
                        new_type_obj = sub_obj.Type.catalog.getSchemaDocByClass(my_ns).getTypeInSchemaDoc('.'.join([my_ns, my_type]))
                        sub_obj = RedfishObject(new_type_obj, sub_obj.Name, sub_obj.parent).populate(load, check=check, casted=True)
                        evals.append(sub_obj)
                        continue

            sub_obj.IsValid = isinstance(load, dict)

            if 'Resource.OemObject' in sub_obj.Type.getTypeTree():
                evals.append(sub_obj)
                continue
            # populate properties
            if sub_obj.Name == 'Actions':
                sub_obj.properties = {x:y.populate(load.get(x, REDFISH_ABSENT)) for x, y in sub_obj.properties.items() if x != 'Oem'}
            else:
                sub_obj.properties = {x:y.populate(load.get(x, REDFISH_ABSENT)) for x, y in sub_obj.properties.items()}

            # additional_props
            if sub_obj.Type.HasAdditional and sub_obj.Name != 'Actions':
                if sub_obj.Type.property_pattern:
                    my_odata_type = sub_obj.Type.property_pattern.get('Type', 'Resource.OemObject')
                    prop_pattern = sub_obj.Type.property_pattern.get('Pattern', '.*')
                else:
                    my_odata_type = 'Resource.OemObject'
                    prop_pattern = '.*'

                my_property_names = [x for x in load if x not in sub_obj.properties if re.match(prop_pattern, x) and '@' not in x]
                for add_name in my_property_names:
                    if 'Edm.' in my_odata_type:
                        my_new_term = '<Term Name="{}" Type="{}"> </Term>'.format(add_name, my_odata_type)
                        new_soup = BeautifulSoup(my_new_term, "xml").find('Term')
                        type_obj = RedfishType(new_soup, sub_obj.Type.owner)
                    else:
                        type_obj = sub_obj.Type.catalog.getSchemaDocByClass(my_odata_type).getTypeInSchemaDoc(my_odata_type)
                    if type_obj.getBaseType()[0] == 'complex':
                        object = RedfishObject(type_obj, name=add_name, parent=self)
                    else:
                        object = RedfishProperty(type_obj, name=add_name, parent=self)
                    my_logger.debug('Populated {} with {}'.format(my_property_names, object.as_json()))
                    sub_obj.properties[add_name] = object.populate(load.get(add_name, REDFISH_ABSENT))

            my_annotations = [x for x in load if x not in sub_obj.properties if '@' in x and '@odata' not in x]
            for key in my_annotations:
                splitKey = key.split('@', 1)
                fullItem = splitKey[1]
                if getNamespace(fullItem) not in allowed_annotations:
                    my_logger.error("getAnnotations: {} is not an allowed annotation namespace, please check spelling/capitalization.".format(fullItem))
                    continue
                type_obj = sub_obj.Type.catalog.getSchemaInCatalog(fullItem).terms[getType(fullItem)]
                if type_obj.getBaseType()[0] == 'complex':
                    object = RedfishObject(type_obj, name=key, parent=self)
                else:
                    object = RedfishProperty(type_obj, name=key, parent=self)
                sub_obj.properties[key] = object.populate(load[key])

            evals.append(sub_obj)
        if not isinstance(payload, list):
            sub_obj.Collection = evals
            return sub_obj
        else:
            for e, v in zip(evals, eval_obj.Value):
                e.Value = v
            eval_obj.Collection = evals
            return eval_obj

    def as_json(self):
        if self.Populated:
            return {'Properties' : {a: b.as_json() for a, b in self.properties.items() if (b.Exists or not b.IsValid)}}
        else:
            # base = {'Self': super().as_json()}
            base = super().as_json()
            base.update({'Properties': {a: b.as_json() for a, b in self.properties.items()}})
            return base

    def getLinks(self):
        """Grab links from our Object
        """
        links = []
        # if we're populated...
        if self.Populated:
            for n, item in self.properties.items():
                # if we don't exist or our type is Basic
                if not item.Exists: continue
                if not isinstance(item.Type, RedfishType): continue
                if n == 'Actions':
                    new_type = item.Type.catalog.getTypeInCatalog('ActionInfo.ActionInfo')
                    for act in item.Value.values():
                        uri = act.get('@Redfish.ActionInfo')
                        if isinstance(uri, str):
                            links.append(RedfishObject(new_type, 'ActionInfo', item).populate({'@odata.id': uri}))
                if item.Type.tag_type == 'NavigationProperty':
                    if isinstance(item.Value, list):
                        for num, val in enumerate(item.Value):
                            new_link = item.populate(val)
                            new_link.Name = new_link.Name + '#{}'.format(num)
                            links.append(new_link)
                    else:
                        links.append(item)
                elif item.Type.getBaseType()[0] == 'complex':
                    if isinstance(item.Value, list): target = item.Value
                    else: target = [item.Value]
                    for sub in target:
                        my_complex = item.Type.createObject().populate(sub)
                        links.extend(my_complex.getLinks())
        return links

    # if 'Resource.Resource' in allTypes:
    #     else:
    #         if original_jsondata is None:
    #             traverseLogger.warn('Acquired Resource.Resource type with fragment, could cause issues  {}'.format(uri_item))
    #         else:
    #             traverseLogger.warn('Found uri with fragment, which Resource.Resource types do not use {}'.format(uri_item))
    #     if not fragment_odata == '':
    #         traverseLogger.warn('@odata.id should not have a fragment {}'.format(odata_id))

    # elif 'Resource.ReferenceableMember' in allTypes:
    #     if not fragment != '':
    #         traverseLogger.warn('No fragment, but ReferenceableMembers require it {}'.format(uri_item))
    #     if not fragment_odata != '':
