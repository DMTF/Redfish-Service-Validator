import difflib
import glob, copy
import logging
import re
from collections import namedtuple
from enum import Enum, auto
from os import path

from bs4 import BeautifulSoup

from common.redfish import (
    compareMinVersion,
    getNamespace,
    getNamespaceUnversioned,
    getType,
    getVersion,
    splitVersionString,
)

includeTuple = namedtuple("include", ["Namespace", "Uri"])

my_logger = logging.getLogger(__name__)

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

def get_fuzzy_property(prop_name: str, jsondata: dict, allPropList=[]):
    """Get property closest to the discovered property

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
    """Missing Schema Error """
    pass


class SchemaCatalog:
    """Catalog for holding Schema files"""

    def __init__(self, filepath: str, metadata: object = None, logger: logging.Logger = None):
        """Init

        Args:
            filepath (str): Directory of metadata
            metadata (object, optional): Preestablished metadata. Defaults to None.
            logger (logger, optional): Logging object. Defaults to None.
        """
        self.filepath = filepath
        self.logger = logger if logger is not None else my_logger
        self.catalog = {}
        self.catalog_by_class = {}
        self.logger.debug("Creating Schema catalog from filepath {}".format(filepath))

        # create SchemaDoc objects
        for x in glob.glob(path.join(filepath, "*")):
            with open(x) as f:
                my_name = path.split(x)[-1]
                self.catalog[my_name] = SchemaDoc(f.read(), self, my_name, self.logger)

        # catagorize by classes in schema
        for c, schema in self.catalog.items():
            bonus = [getNamespaceUnversioned(x) for x in schema.classes if getNamespaceUnversioned(x) not in schema.classes]
            for item in list(schema.classes.keys()) + bonus:
                if item not in self.catalog_by_class:
                    self.catalog_by_class[item] = [schema]
                else:
                    self.catalog_by_class[item].append(schema)

    def getSchemaDocByClass(self, typename, uri=None, metadata=None):
        """get SchemaDoc by Class

        Args:
            typename (string): name of type
            uri ([type], optional): [description]. Defaults to None.
            metadata ([type], optional): [description]. Defaults to None.

        Raises:
            MissingSchemaError: Doesn't exist in catalog

        Returns:
            SchemaDoc: schema doc
        
        rtype: SchemaDoc
        """
        typename = getNamespaceUnversioned(typename)
        if typename in self.catalog_by_class:
            return self.catalog_by_class[typename][0]
        raise MissingSchemaError(
            "Could not find any Schema with these parameters {}".format(typename)
        )

    # def getSchemaSoup(self, SchemaType, SchemaURI=None):
    #     """
    #     Find Schema file as soup for given Namespace, from local directory

    #     param SchemaType: Schema Namespace, such as ServiceRoot
    #     param SchemaURI: uri to grab schema (generate information from it)
    #     return: (success boolean, a Soup object, origin)
    #     """
    #     Alias = getNamespaceUnversioned(SchemaType)

    #     if SchemaURI is not None:
    #         uriparse = SchemaURI.split('/')[-1].split('#')
    #         xml = uriparse[0]
    #     else:
    #         self.logger.warning("SchemaURI was empty, must generate xml name from type {}".format(SchemaType)),
    #         return self.getSchemaSoup(SchemaType, Alias + "_v1.xml")

    #     if xml in self.catalog:
    #         return self.catalog[xml].soup

    #     raise MissingSchemaError('Could not find any Schema with these parameters {} {}'.format(SchemaType, SchemaURI))

    # if '/redfish/v1/$metadata' in SchemaURI:
    #     if len(uriparse) > 1:
    #         frag = getNamespace(SchemaType)
    #         frag = frag.split('.', 1)[0]
    #         refType, refLink = getReferenceDetails(
    #             soup, name=SchemaLocation + '/' + filestring).get(frag, (None, None))
    #         if refLink is not None:
    #             self.logger.debug('Entering {} inside {}, pulled from $metadata'.format(refType, refLink))
    #             return self.getSchemaDoc(refType, refLink)
    #         else:
    #             self.logger.error('Could not find item in $metadata {}'.format(frag))
    #             return False, None, None
    #     else:
    #         return True, soup, "localFile:" + SchemaLocation + '/' + filestring

    # except FileNotFoundError:
    #     # if we're looking for $metadata locally... ditch looking for it, go straight to file
    #     if '/redfish/v1/$metadata' in SchemaURI and Alias != '$metadata':
    #         self.logger.warning("Unable to find a harddrive stored $metadata at {}, defaulting to {}".format(SchemaLocation, Alias + "_v1.xml"))
    #         return self.getSchemaFile(SchemaType, Alias + "_v1.xml")
    #     else:
    #         self.logger.warn
    #         (
    #             "Schema file {} not found in {}".format(filestring, SchemaLocation))
    #         if Alias == '$metadata':
    #             self.logger.warning(
    #                 "If $metadata cannot be found, Annotations may be unverifiable")
    # except Exception as ex:
    #     self.logger.error("A problem when getting a local schema has occurred {}".format(SchemaURI))
    #     self.logger.warning("output: ", exc_info=True)


REDFISH_ABSENT = "n/a"


class SchemaDoc:
    """Represents a schema document"""

    def __init__(self, data: str, catalog: SchemaCatalog = None, name: str = None, logger: logging.Logger = None):
        # set up document
        self.soup = BeautifulSoup(data, "xml")
        self.name = str(name)
        self.origin = "local"
        self.catalog = catalog
        self.classes = {}
        self.logger = logger if logger is not None else logger

        edmxTag = self.soup.find("edmx:Edmx", recursive=False)
        reftags = edmxTag.find_all("edmx:Reference", recursive=False)
        self.refs = {}
        for ref in reftags:
            includes = ref.find_all("edmx:Include", recursive=False)
            for item in includes:
                uri = ref.get("Uri")
                ns, alias = (item.get(x) for x in ["Namespace", "Alias"])
                if ns is None or uri is None:
                    self.logger.error("Reference incorrect for: {}".format(item))
                    continue
                if alias is None:
                    alias = ns
                self.refs[alias] = includeTuple(ns, uri)
                # Check for proper Alias for RedfishExtensions
                # if name == '$metadata' and ns.startswith('RedfishExtensions.'):
                #     check_bool = check_redfish_extensions_alias(name, ns, alias)

        cntref = len(self.refs)

        parentTag = edmxTag.find("edmx:DataServices", recursive=False)
        children = parentTag.find_all("Schema", recursive=False)
        self.classes = {}
        for child in children:
            self.classes[child["Namespace"]] = SchemaClass(child, self, self.logger)
        # if metadata_dict is not None:
        #     self.refDict.update(metadata_dict)
        self.logger.debug(
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
                self.logger.warning('No such reference {} in {}'.format(namespace, self.origin))
                return None
            else:
                tup = tupVersionless
                self.logger.warning('No such reference {} in {}, using unversioned'.format(namespace, self.origin))
        return tup

    def getTypeInSchema(self, currentType, tagType=["EntityType", "ComplexType"]):
        """getTypeTagInSchema

        Get type tag in schema

        :param currentType: type string
        :param tagType: Array or single string containing the xml tag name
        
        rtype: SchemaClass
        """
        pnamespace, ptype = getNamespace(currentType), getType(currentType)
        pbase = getNamespaceUnversioned(currentType)

        if pbase in self.classes:
            if pnamespace not in self.classes:
                ns_obj = self.classes[pbase]
                pnamespace = getNamespace(ns_obj.getHighestType(currentType))
            currentNamespace = self.classes[pnamespace]
            return currentNamespace.my_types[ptype]
        elif pnamespace in self.refs:
            new_doc = self.catalog.getSchemaDocByClass(pnamespace)
            return new_doc.getTypeInSchema(currentType)
        else:
            new_doc = self.catalog.getSchemaDocByClass('Resource')
            return new_doc.getTypeInSchema('Resource.Item')


class SchemaClass:
    def __init__(self, soup, owner: SchemaDoc, logger: logging.Logger = None):
        super().__init__()
        self.class_soup = soup
        self.class_name = soup["Namespace"]
        self.logger = logger if logger is not None else logger
        self.entity_types = {
            x["Name"]: RedfishType(x, self, self.logger)
            for x in self.class_soup.find_all(["EntityType"], recursive=False)
        }
        self.complex_types = {
            x["Name"]: RedfishType(x, self, self.logger)
            for x in self.class_soup.find_all(["ComplexType"], recursive=False)
        }
        self.enum_types = {
            x["Name"]: RedfishType(x, self, self.logger)
            for x in self.class_soup.find_all(["EnumType"], recursive=False)
        }
        self.def_types = {
            x["Name"]: RedfishType(x, self, self.logger)
            for x in self.class_soup.find_all(["TypeDefinition"], recursive=False)
        }
        self.my_types = {**self.entity_types, **self.complex_types, **self.enum_types, **self.def_types}
        self.parent_doc = owner

    def getEntityType(self, my_type, limit=None):
        my_type = getType(my_type)
        return self.entity_types[my_type]

    def getHighestType(self, my_type, limit=None):
        """getHighestType

        get Highest possible version for given type

        :param acquiredtype: Type available
        :param limit: Version string limit (full namespace or just version 'v1_x_x')
        """
        typelist = []
        my_type = getType(my_type)

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
                self.logger.debug("{}   {}".format(ns, getType(my_type)))
                my_type = getNamespaceUnversioned(my_type) + ".v{}_{}_{}".format(*ns) + "." + getType(my_type)
                return my_type
        return my_type


class RedfishType:
    def __repr__(self):
        return self.fulltype
    
    def __init__(self, soup: str, owner: SchemaClass, logger: logging.Logger = None):

        self.owner = owner

        self.type_soup = soup
        self.logger = logger if logger is not None else my_logger
        self.tag_type = soup.name
        self.parent_type = (
            soup["UnderlyingType"]
            if self.tag_type == "TypeDefinition"
            else soup.get("BaseType", soup.get("Type", None))
        )

        self.fulltype = ".".join([self.owner.class_name, str(self.parent_type)])

        self.tags = {}
        for tag in self.type_soup.find_all(recursive=False):
            if(not tag.get('Term')):
                my_logger.debug((tag, 'does not contain a Term name'))
            else:
                self.tags[tag['Term']] = tag.attrs
            if (tag.get('Term') == 'Redfish.Revisions'):
                self.tags[tag['Term']] = tag.find_all('Record')

        dynamic = self.type_soup.find("Annotation", attrs={"Term": "Redfish.DynamicPropertyPatterns"})
        additionalElement = self.type_soup.find("Annotation", attrs={"Term": "OData.AdditionalProperties"})
        uriElement = self.type_soup.find("Annotation", attrs={"Term": "Redfish.Uris"})
        propPermissions = self.tags.get('OData.Permissions')

        # if re.match('Collection\(.*\)', propertyFullType) is not None:

        self.Namespace, self.Type = self.owner.class_name, getType(self.fulltype)

        self.IsMandatory = self.tags.get('Redfish.Required') is not None
        self.IsNullable = self.type_soup.get("Nullable", "false") in ["false", False, "False"]
        self.AutoExpand = self.tags.get('OData.AutoExpand', None) is not None or self.tags.get('OData.AutoExpand'.lower(), None) is not None
        self.Deprecated = self.tags.get('Redfish.Deprecated')
        self.Revisions = self.tags.get('Redfish.Revisions')
        self.Excerpt = False

        self.Permissions = propPermissions['EnumMember'] if propPermissions is not None else None
        self.HasAdditional = ( False if additionalElement is None else (
                True if additionalElement.get("Bool", False) in ["True", "true", True]
                else False))

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
            self.unique_properties[prop_name] = RedfishType(innerelement, self.owner, self.logger)
        
    def getBaseType(self, is_collection=False):
        if self.parent_type:
            if re.match('Collection\(.*\)', self.parent_type) is not None:
                is_collection=True
                my_real_type = self.parent_type.replace('Collection(', "").replace(')', "")
                if 'Edm.' not in self.parent_type:
                    type_obj = self.owner.parent_doc.catalog.getSchemaDocByClass(my_real_type).getTypeInSchema(my_real_type)
                    return type_obj.getBaseType(is_collection)
                else:
                    return self.parent_type, is_collection
            if 'Edm.' in self.parent_type:
                return self.parent_type, is_collection
            if self.tag_type in ["Property", "NavigationProperty"]:
                my_real_type = self.parent_type
                type_obj = self.owner.parent_doc.catalog.getSchemaDocByClass(my_real_type).getTypeInSchema(my_real_type)
                return type_obj.getBaseType(is_collection)
        if self.tag_type == "EnumType":
            return 'enum', is_collection
        if self.tag_type == "ComplexType":
            return 'complex', is_collection
        if self.tag_type == "EntityType":
            return 'entity', is_collection
        return 'none', is_collection

    def getProperties(self):
        def yield_parent(x):
            while x is not None:
                yield x
                if x.parent_type is None: break
                doc = x.owner.parent_doc
                x = doc.getTypeInSchema(x.parent_type)

        all_properties = {}
        for type_obj in yield_parent(self):
            all_properties.update(type_obj.unique_properties)
        return all_properties

    def validate(self, val):
        self.logger.debug((self, val, self.fulltype, self.tag_type, self.parent_type))
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
        if self.parent_type:
            if re.match('Collection\(.*\)', self.parent_type) is not None:
                if not isinstance(val, list): raise ValueError('Should be a List')
                my_real_type = self.parent_type.replace('Collection(', "").replace(')', "")
                if 'Edm.' not in self.parent_type:
                    type_obj = self.owner.parent_doc.catalog.getSchemaDocByClass(my_real_type).getTypeInSchema(my_real_type)
                else:
                    type_obj = self
                for x in val:
                    return type_obj.validate(x)
            else:
                if isinstance(val, list): raise ValueError('Should not be a List')
            if 'Edm.' in self.parent_type:
                validPatternAttr = self.type_soup.find('Annotation', attrs={'Term': 'Validation.Pattern'})
                validMinAttr = self.type_soup.find('Annotation', attrs={'Term': 'Validation.Minimum'})
                validMaxAttr = self.type_soup.find('Annotation', attrs={'Term': 'Validation.Maximum'})
                validMin, validMax = int(validMinAttr['Int']) if validMinAttr is not None else None, \
                    int(validMaxAttr['Int']) if validMaxAttr is not None else None
                validPattern = validPatternAttr.get('String', '') if validPatternAttr is not None else None
                my_real_type = self.parent_type.replace('Collection(', "").replace(')', "")
                return RedfishProperty.validate_basic(val, my_real_type, validPattern, validMin, validMax)
            if self.tag_type in ["Property", "NavigationProperty"]:
                my_real_type = self.parent_type
                type_obj = self.owner.parent_doc.catalog.getSchemaDocByClass(my_real_type).getTypeInSchema(my_real_type)
                return type_obj.validate(val)
        if self.tag_type == "EnumType":
            my_enums = [x["Name"] for x in self.type_soup.find_all("Member")]
            if val not in my_enums:
                raise ValueError("Enum not found")
        if self.tag_type == "ComplexType":
            if not isinstance(val, dict):
                raise ValueError("Complex value is not Dict")
            my_complex = self.createObject().populate(val)
        if self.tag_type == "EntityType":
            return True
            if not isinstance(val, str) or not isinstance(val, dict):
                raise ValueError("Entity value is not Dict or Str")
        return True
    
    def createObject(self):
        return RedfishObject(self)

    # def compareURI(self, uri, my_id):
    #     expected_uris = self.expectedURI
    #     if expected_uris is not None:
    #         regex = re.compile(r"{.*?}")
    #         for e in expected_uris:
    #             e_left, e_right = tuple(e.rsplit('/', 1))
    #             _uri_left, uri_right = tuple(uri.rsplit('/', 1))
    #             e_left = regex.sub('[a-zA-Z0-9_.-]+', e_left)
    #             if regex.match(e_right):
    #                 if my_id is None:
    #                     pass
    #                     # logger.warn('No Id provided by payload')
    #                 e_right = str(my_id)
    #             e_compare_to = '/'.join([e_left, e_right])
    #             success = re.fullmatch(e_compare_to, uri) is not None
    #             if success:
    #                 break
    #     else:
    #         success = True
    #     return success


class RedfishObject:
    def __init__(self, redfish_type: RedfishType, logger: logging.Logger = None):
        self.logger = logger if logger is not None else my_logger
        self.Type = redfish_type
        self.properties = {}
        for prop, typ in redfish_type.getProperties().items():
            self.properties[prop] = RedfishProperty(prop, typ)

        self.Populated = False

    def populate(self, payload, parent=None):
        eval_obj = copy.copy(self)
        eval_obj.parent = parent
        eval_obj.Populated = True
        eval_obj.properties = {x:y.populate(payload.get(x, REDFISH_ABSENT)) for x, y in eval_obj.properties.items()}
        if eval_obj.Type.HasAdditional:
            if eval_obj.Type.property_pattern:
                my_real_type = eval_obj.Type.property_pattern.get('Type', 'Resource.OemObject')
                prop_pattern = eval_obj.Type.property_pattern.get('Pattern', '.*')
            else:
                my_real_type = 'Resource.OemObject'
                prop_pattern = '.*'
            type_obj = eval_obj.Type.owner.parent_doc.catalog.getSchemaDocByClass(my_real_type).getTypeInSchema(my_real_type)
            my_property_names = [x for x in payload if x not in eval_obj.properties if re.match(prop_pattern, x)]
            eval_obj.properties = {x: RedfishProperty(x, type_obj).populate(payload.get(x, REDFISH_ABSENT)) for x in my_property_names}
        for prop_name, prop in eval_obj.properties.items():
            my_val = prop.Value
            typ = prop.Type
            self.logger.debug((prop, typ.fulltype, my_val, typ.parent_type))
            self.logger.debug(prop)
            if my_val == REDFISH_ABSENT and prop.IsValid:
                self.logger.debug("(but I'm absent...)")
            else:
                self.logger.debug("Im Valid" if prop.IsValid else 'NOT VALID')
        return eval_obj

    def as_json(self):
        if self.Populated:
            return {a: b.as_json() for a, b in self.properties.items() if b.Exists or not b.IsValid}
        else:
            return {a: b.as_json() for a, b in self.properties.items()}

    def getLinks(self):
        links = []
        if self.Populated:
            for n, item in self.properties.items():
                if not item.Exists:
                    continue
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
        return(links)

                
class RedfishProperty:
    def __init__(self, name, my_type):
        self.Name = name
        self.Type = my_type
        self.Populated = False

    def populate(self, val, check=False):
        eval_prop = copy.copy(self)
        eval_prop.Populated = True
        eval_prop.Value = val
        eval_prop.IsValid = True
        eval_prop.SchemaExists = True
        eval_prop.Exists = val != REDFISH_ABSENT
        if 'OemObject' in eval_prop.Type.fulltype:
            my_real_type = val.get('@odata.type', 'Resource.OemObject')
            eval_prop.Type = eval_prop.Type.owner.parent_doc.catalog.getSchemaDocByClass(my_real_type).getTypeInSchema(my_real_type)
        if isinstance(eval_prop.Type, str) and 'Edm' in eval_prop.Type and check:
            try:
                eval_prop.IsValid = eval_prop.Exists and RedfishProperty.validate_basic(
                    val, eval_prop.Type
                )
            except ValueError as e:
                print(e)  # log this
                eval_prop.IsValid = False
        elif isinstance(eval_prop.Type, RedfishType) and check:
            try:
                eval_prop.IsValid = eval_prop.Type.validate(val)
            except ValueError as e:
                print(e)  # log this
                eval_prop.IsValid = False
        return eval_prop

    def as_json(self):
        my_dict = {x: y for x, y in vars(self).items() if x != 'Populated'}
        if isinstance(self.Type, RedfishType):
            my_dict['IsRequired'] = self.Type.mandatory
            my_dict['IsNullable'] = self.Type.nullable
            my_dict['HasAdditional'] = self.Type.additional
            pass
        return my_dict
    
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
            for cnt, item in enumerate(val):
                try:
                    RedfishProperty.validate_basic(item, my_collection_type, validPattern, min, max)
                except ValueError as e:
                    raise ValueError('{} invalid'.format(cnt))

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
