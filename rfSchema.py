# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

from collections import namedtuple
from bs4 import BeautifulSoup
from functools import lru_cache
from collections import OrderedDict
import re
import difflib
import os.path

from commonRedfish import getType, getNamespace, getNamespaceUnversioned, getVersion, compareMinVersion, splitVersionString
import traverseService as rst
from urllib.parse import urlparse, urlunparse

config = []


def storeSchemaToLocal(xml_data, origin):
    """storeSchemaToLocal

    Moves data pulled from service/online to local schema storage

    Does NOT do so if preferonline is specified

    :param xml_data: data being transferred
    :param origin: origin of xml pulled
    """
    config = rst.config
    SchemaLocation = config['metadatafilepath']
    if not config['preferonline']:
        if not os.path.isdir(SchemaLocation):
            os.makedirs(SchemaLocation)
        if 'localFile' not in origin and '$metadata' not in origin:
            __, xml_name = origin.rsplit('/', 1)
            new_file = os.path.join(SchemaLocation, xml_name)
            if not os.path.isfile(new_file):
                with open(new_file, "w") as filehandle:
                    filehandle.write(xml_data)
                    rst.traverseLogger.info('Writing online XML to file: {}'.format(xml_name))
            else:
                rst.traverseLogger.info('NOT writing online XML to file: {}'.format(xml_name))
    else:
        pass

@lru_cache(maxsize=64)
def getSchemaDetails(SchemaType, SchemaURI):
    """
    Find Schema file for given Namespace.

    param SchemaType: Schema Namespace, such as ServiceRoot
    param SchemaURI: uri to grab schema, given LocalOnly is False
    return: (success boolean, a Soup object, origin)
    """
    rst.traverseLogger.debug('getting Schema of {} {}'.format(SchemaType, SchemaURI))
    currentService = rst.currentService

    if SchemaType is None:
        return False, None, None

    if currentService is None:
        return getSchemaDetailsLocal(SchemaType, SchemaURI)

    elif currentService.active and getNamespace(SchemaType) in currentService.metadata.schema_store:
        result = rst.currentService.metadata.schema_store[getNamespace(SchemaType)]
        if result is not None:
            return True, result.soup, result.origin

    if not currentService.config['preferonline'] and '$metadata' not in SchemaURI:
        success, soup, origin = getSchemaDetailsLocal(SchemaType, SchemaURI)
        if success:
            return success, soup, origin

    xml_suffix = currentService.config['schemasuffix']

    config = rst.currentService.config
    LocalOnly, SchemaLocation, ServiceOnly = config['localonlymode'], config['metadatafilepath'], config['servicemode']

    scheme, netloc, path, params, query, fragment = urlparse(SchemaURI)
    inService = scheme is None and netloc is None

    if (SchemaURI is not None and not LocalOnly) or (SchemaURI is not None and '/redfish/v1/$metadata' in SchemaURI):
        # Get our expected Schema file here
        # if success, generate Soup, then check for frags to parse
        #   start by parsing references, then check for the refLink
        if '#' in SchemaURI:
            base_schema_uri, frag = tuple(SchemaURI.rsplit('#', 1))
        else:
            base_schema_uri, frag = SchemaURI, None
        success, data, status, elapsed = rst.callResourceURI(base_schema_uri)
        if success:
            soup = BeautifulSoup(data, "xml")
            # if frag, look inside xml for real target as a reference
            if frag is not None:
                # prefer type over frag, truncated down
                # using frag, check references
                frag = getNamespace(SchemaType)
                frag = frag.split('.', 1)[0]
                refType, refLink = getReferenceDetails(
                    soup, name=base_schema_uri).get(frag, (None, None))
                if refLink is not None:
                    success, linksoup, newlink = getSchemaDetails(refType, refLink)
                    if success:
                        return True, linksoup, newlink
                    else:
                        rst.traverseLogger.error(
                            "SchemaURI couldn't call reference link {} inside {}".format(frag, base_schema_uri))
                else:
                    rst.traverseLogger.error(
                        "SchemaURI missing reference link {} inside {}".format(frag, base_schema_uri))
                    # error reported; assume likely schema uri to allow continued validation
                    uri = 'http://redfish.dmtf.org/schemas/v1/{}{}'.format(frag, xml_suffix)
                    rst.traverseLogger.info("Continue assuming schema URI for {} is {}".format(SchemaType, uri))
                    return getSchemaDetails(SchemaType, uri)
            else:
                storeSchemaToLocal(data, base_schema_uri)
                return True, soup, base_schema_uri
        if not inService and ServiceOnly:
            rst.traverseLogger.debug("Nonservice URI skipped: {}".format(base_schema_uri))
        else:
            rst.traverseLogger.debug("SchemaURI called unsuccessfully: {}".format(base_schema_uri))
    if LocalOnly:
        rst.traverseLogger.debug("This program is currently LOCAL ONLY")
    if ServiceOnly:
        rst.traverseLogger.debug("This program is currently SERVICE ONLY")
    if not LocalOnly and not ServiceOnly or (not inService and config['preferonline']):
        rst.traverseLogger.warning("SchemaURI {} was unable to be called, defaulting to local storage in {}".format(SchemaURI, SchemaLocation))
    return getSchemaDetailsLocal(SchemaType, SchemaURI)


def getSchemaDetailsLocal(SchemaType, SchemaURI):
    """
    Find Schema file for given Namespace, from local directory

    param SchemaType: Schema Namespace, such as ServiceRoot
    param SchemaURI: uri to grab schem (generate information from it)
    return: (success boolean, a Soup object, origin)
    """
    Alias = getNamespaceUnversioned(SchemaType)
    config = rst.config
    SchemaLocation, SchemaSuffix = config['metadatafilepath'], config['schemasuffix']
    if SchemaURI is not None:
        uriparse = SchemaURI.split('/')[-1].split('#')
        xml = uriparse[0]
    else:
        rst.traverseLogger.warning("SchemaURI was empty, must generate xml name from type {}".format(SchemaType)),
        return getSchemaDetailsLocal(SchemaType, Alias + SchemaSuffix)
    rst.traverseLogger.debug((SchemaType, SchemaURI, SchemaLocation + '/' + xml))
    filestring = Alias + SchemaSuffix if xml is None else xml
    try:
        # get file
        with open(SchemaLocation + '/' + xml, "r") as filehandle:
            data = filehandle.read()

        # get tags
        soup = BeautifulSoup(data, "xml")
        edmxTag = soup.find('edmx:Edmx', recursive=False)
        parentTag = edmxTag.find('edmx:DataServices', recursive=False)
        child = parentTag.find('Schema', recursive=False)
        SchemaNamespace = child['Namespace']
        FoundAlias = SchemaNamespace.split(".")[0]
        rst.traverseLogger.debug(FoundAlias)

        if '/redfish/v1/$metadata' in SchemaURI:
            if len(uriparse) > 1:
                frag = getNamespace(SchemaType)
                frag = frag.split('.', 1)[0]
                refType, refLink = getReferenceDetails(
                    soup, name=SchemaLocation + '/' + filestring).get(frag, (None, None))
                if refLink is not None:
                    rst.traverseLogger.debug('Entering {} inside {}, pulled from $metadata'.format(refType, refLink))
                    return getSchemaDetails(refType, refLink)
                else:
                    rst.traverseLogger.error('Could not find item in $metadata {}'.format(frag))
                    return False, None, None
            else:
                return True, soup, "localFile:" + SchemaLocation + '/' + filestring

        if FoundAlias in Alias:
            return True, soup, "localFile:" + SchemaLocation + '/' + filestring

    except FileNotFoundError:
        # if we're looking for $metadata locally... ditch looking for it, go straight to file
        if '/redfish/v1/$metadata' in SchemaURI and Alias != '$metadata':
            rst.traverseLogger.warning("Unable to find a harddrive stored $metadata at {}, defaulting to {}".format(SchemaLocation, Alias + SchemaSuffix))
            return getSchemaDetailsLocal(SchemaType, Alias + SchemaSuffix)
        else:
            rst.traverseLogger.warn
            (
                "Schema file {} not found in {}".format(filestring, SchemaLocation))
            if Alias == '$metadata':
                rst.traverseLogger.warning(
                    "If $metadata cannot be found, Annotations may be unverifiable")
    except Exception as ex:
        rst.traverseLogger.error("A problem when getting a local schema has occurred {}".format(SchemaURI))
        rst.traverseLogger.warning("output: ", exc_info=True)
    return False, None, None


def check_redfish_extensions_alias(name, namespace, alias):
    """
    Check that edmx:Include for Namespace RedfishExtensions has the expected 'Redfish' Alias attribute
    :param name: the name of the resource
    :param item: the edmx:Include item for RedfishExtensions
    :return: bool
    """
    if alias is None or alias != 'Redfish':
        msg = ("In the resource {}, the {} namespace must have an alias of 'Redfish'. The alias is {}. " +
               "This may cause properties of the form [PropertyName]@Redfish.TermName to be unrecognized.")
        rst.traverseLogger.error(msg.format(name, namespace,
                             'missing' if alias is None else "'" + str(alias) + "'"))
        return False
    return True


def getReferenceDetails(soup, metadata_dict=None, name='xml'):
    """
    Create a reference dictionary from a soup file

    param arg1: soup
    param metadata_dict: dictionary of service metadata, compare with
    return: dictionary
    """
    includeTuple = namedtuple('include', ['Namespace', 'Uri'])
    refDict = {}

    maintag = soup.find("edmx:Edmx", recursive=False)
    reftags = maintag.find_all('edmx:Reference', recursive=False)
    for ref in reftags:
        includes = ref.find_all('edmx:Include', recursive=False)
        for item in includes:
            uri = ref.get('Uri')
            ns, alias = (item.get(x) for x in ['Namespace', 'Alias'])
            if ns is None or uri is None:
                rst.traverseLogger.error("Reference incorrect for: {}".format(item))
                continue
            if alias is None:
                alias = ns
            refDict[alias] = includeTuple(ns, uri)
            # Check for proper Alias for RedfishExtensions
            if name == '$metadata' and ns.startswith('RedfishExtensions.'):
                check_bool = check_redfish_extensions_alias(name, ns, alias)

    cntref = len(refDict)
    if metadata_dict is not None:
        refDict.update(metadata_dict)
    rst.traverseLogger.debug("References generated from {}: {} out of {}".format(name, cntref, len(refDict)))
    return refDict


class rfSchema:
    def __init__(self, soup, context, origin, metadata=None, name='xml'):
        self.soup = soup
        self.refs = getReferenceDetails(soup, metadata, name)
        self.context = context
        self.origin = origin
        self.name = name

    def getSchemaFromReference(self, namespace):
        """getSchemaFromReference

        Get SchemaObj from generated references

        :param namespace: Namespace of reference
        """
        tup = self.refs.get(namespace)
        tupVersionless = self.refs.get(getNamespace(namespace))
        if tup is None:
            if tupVersionless is None:
                rst.traverseLogger.warning('No such reference {} in {}'.format(namespace, self.origin))
                return None
            else:
                tup = tupVersionless
                rst.traverseLogger.warning('No such reference {} in {}, using unversioned'.format(namespace, self.origin))
        typ, uri = tup
        newSchemaObj = getSchemaObject(typ, uri)
        return newSchemaObj

    def getTypeTagInSchema(self, currentType, tagType=['EntityType', 'ComplexType']):
        """getTypeTagInSchema

        Get type tag in schema

        :param currentType: type string
        :param tagType: Array or single string containing the xml tag name
        """
        pnamespace, ptype = getNamespace(currentType), getType(currentType)
        soup = self.soup

        currentSchema = soup.find(
            'Schema', attrs={'Namespace': pnamespace})

        if currentSchema is None:
            return None

        currentEntity = currentSchema.find(tagType, attrs={'Name': ptype}, recursive=False)

        return currentEntity

    def getParentType(self, currentType, tagType=['EntityType', 'ComplexType']):
        """getParentType

        Get parent of this Entity/ComplexType

        :param currentType: type string
        :param tagType: Array or single string containing the xml tag name
        """
        currentType = currentType.replace('#', '')
        typetag = self.getTypeTagInSchema(currentType, tagType)
        if typetag is not None:
            currentType = typetag.get('BaseType')
            if currentType is None:
                return False, None, None
            typetag = self.getTypeTagInSchema(currentType, tagType)
            if typetag is not None:
                return True, self, currentType
            else:
                namespace = getNamespace(currentType)
                schemaObj = self.getSchemaFromReference(namespace)
                if schemaObj is None:
                    return False, None, None
                propSchema = schemaObj.soup.find(
                    'Schema', attrs={'Namespace': namespace})
                if propSchema is None:
                    return False, None, None
                return True, schemaObj, currentType
        else:
            return False, None, None

    def getHighestType(self, acquiredtype: str, limit=None):
        """getHighestType

        get Highest possible version for given type

        :param acquiredtype: Type available
        :param limit: Version string limit (full namespace or just version 'v1_x_x')
        """
        typelist = list()

        if limit is not None:
            if getVersion(limit) is None:
                rst.traverseLogger.warning('Limiting namespace has no version, erasing: {}'.format(limit))
                limit = None
            else:
                limit = getVersion(limit)

        for schema in self.soup.find_all('Schema'):
            newNamespace = schema.get('Namespace')
            if limit is not None:
                if getVersion(newNamespace) is None:
                    continue
                if compareMinVersion(limit, newNamespace):
                    continue
            if schema.find(['EntityType', 'ComplexType'], attrs={'Name': getType(acquiredtype)}, recursive=False):
                typelist.append(splitVersionString(newNamespace))

        if len(typelist) > 1:
            for ns in reversed(sorted(typelist)):
                rst.traverseLogger.debug(
                    "{}   {}".format(ns, getType(acquiredtype)))
                acquiredtype = getNamespaceUnversioned(acquiredtype) + '.v{}_{}_{}'.format(*ns) + '.' + getType(acquiredtype)
                return acquiredtype
        return acquiredtype


@lru_cache(maxsize=64)
def getSchemaObject(typename, uri, metadata=None):
    """getSchemaObject

    Wrapper for getting an rfSchema object

    :param typename: Type with namespace of schema
    :param uri: Context/URI of metadata/schema containing reference to namespace
    :param metadata: parent refs of service
    """
    success, soup, origin = getSchemaDetails(typename, uri)

    return rfSchema(soup, uri, origin, metadata=metadata, name=typename) if success else None


def get_fuzzy_property(newProp, jsondata, allPropList=[]):
    pname = newProp
    possibleMatch = difflib.get_close_matches(newProp, [s for s in jsondata], 1, 0.70)
    if len(possibleMatch) > 0 and possibleMatch[0] not in [s[2] for s in allPropList if s[2] != newProp]:
        val = jsondata.get(possibleMatch[0], 'n/a')
        if val != 'n/a':
            pname = possibleMatch[0]
            rst.traverseLogger.error('{} was not found in payload, attempting closest match: {}'.format(newProp, pname))
    return pname


class PropType:
    robjcache = {}

    def __init__(self, typename, schemaObj):
        # if we've generated this type, use it, else generate type
        self.initiated = False
        self.fulltype = typename
        self.snamespace, self.stype = getNamespace(
            self.fulltype), getType(self.fulltype)
        self.schemaObj = schemaObj

        self.parent = None

        self.propList = []
        self.actionList = []
        self.propPattern = None
        self.additional = False
        self.expectedURI = None

        # get all properties and actions in Type chain
        success, currentSchemaObj, baseType = True, self.schemaObj, self.fulltype
        try:
            newPropList, newActionList, self.additional, self.propPattern, self.expectedURI = getTypeDetails(
                currentSchemaObj, baseType)

            self.propList.extend(newPropList)
            self.actionList.extend(newActionList)

            success, currentSchemaObj, baseType = currentSchemaObj.getParentType(baseType)
            if success:
                self.parent = PropType(baseType, currentSchemaObj)
                if not self.additional:
                    self.additional = self.parent.additional
                if self.expectedURI is None:
                    self.expectedURI = self.parent.expectedURI
        except Exception as ex:
            rst.traverseLogger.debug('Exception caught while creating new PropType', exc_info=1)
            rst.traverseLogger.error(
                '{}:  Getting type failed for {}'.format(str(self.fulltype), str(baseType)))
            raise ex

        self.initiated = True

    def getTypeChain(self):
        if self.fulltype is not None:
            node = self
            tlist = []
            while node is not None:
                tlist.append(node.fulltype)
                yield node.fulltype
                node = node.parent
        return

    def getLinksFromType(self, jsondata, context, propList=None, oemCheck=True, linklimits={}, sample=None):
        node = self
        links = OrderedDict()
        if propList is not None:
            links.update(rst.getAllLinks(jsondata, propList, node.schemaObj, context=context, linklimits=linklimits, sample_size=sample, oemCheck=oemCheck))
        else:
            while node is not None:
                links.update(rst.getAllLinks(jsondata, node.getProperties(jsondata), node.schemaObj, context=context, linklimits=linklimits, sample_size=sample, oemCheck=oemCheck))
                node = node.parent
        return links

    def getProperties(self, jsondata, topVersion=None):
        node = self
        allPropList = []
        # collect all properties
        while node is not None:
            allPropList.extend(node.propList)
            node = node.parent

        props = []
        for prop in allPropList:
            schemaObj, newPropOwner, newProp = prop
            val = jsondata.get(newProp, 'n/a')
            pname = newProp
            # if our val is empty, do fuzzy check for property that exists in payload but not in all properties
            if val == 'n/a':
                pname = get_fuzzy_property(newProp, jsondata, allPropList)
            props.append(PropItem(schemaObj, newPropOwner, newProp, val, topVersion, payloadName=pname))

        return props

    def getActions(self):
        node = self
        while node is not None:
            for prop in node.actionList:
                yield prop
            node = node.parent
        return

    def compareURI(self, uri, my_id):
        expected_uris = self.expectedURI
        if expected_uris is not None:
            regex = re.compile(r"{.*?}")
            for e in expected_uris:
                e_left, e_right = tuple(e.rsplit('/', 1))
                _uri_left, uri_right = tuple(uri.rsplit('/', 1))
                e_left = regex.sub('[a-zA-Z0-9_.-]+', e_left)
                if regex.match(e_right):
                    if my_id is None:
                        rst.traverseLogger.warn('No Id provided by payload')
                    e_right = str(my_id)
                e_compare_to = '/'.join([e_left, e_right])
                success = re.fullmatch(e_compare_to, uri) is not None
                if success:
                    break
        else:
            success = True
        return success


def getTypeDetails(schemaObj, SchemaAlias):
    """
    Gets list of surface level properties for a given SchemaType,
    """
    PropertyList = list()
    ActionList = list()
    PropertyPattern = None
    additional = False

    soup, refs = schemaObj.soup, schemaObj.refs

    SchemaNamespace, SchemaType = getNamespace(
        SchemaAlias), getType(SchemaAlias)

    rst.traverseLogger.debug("Generating type: {}".format(SchemaAlias))
    rst.traverseLogger.debug("Schema is {}, {}".format(
                        SchemaType, SchemaNamespace))

    innerschema = soup.find('Schema', attrs={'Namespace': SchemaNamespace})

    if innerschema is None:
        uri = schemaObj.origin
        rst.traverseLogger.error('getTypeDetails: Schema namespace {} not found in schema file {}. Will not be able to gather type details.'
                             .format(SchemaNamespace, uri))
        return PropertyList, ActionList, False, PropertyPattern, '.*'

    element = innerschema.find(['EntityType', 'ComplexType'], attrs={'Name': SchemaType}, recursive=False)

    if element is None:
        uri = schemaObj.origin
        rst.traverseLogger.error('getTypeDetails: Element {} not found in schema namespace {}. Will not be able to gather type details.'
                             .format(SchemaType, SchemaNamespace))
        return PropertyList, ActionList, False, PropertyPattern, '.*'

    rst.traverseLogger.debug("___")
    rst.traverseLogger.debug(element.get('Name'))
    rst.traverseLogger.debug(element.attrs)
    rst.traverseLogger.debug(element.get('BaseType'))

    additionalElement = element.find(
        'Annotation', attrs={'Term': 'OData.AdditionalProperties'})
    additionalElementOther = element.find(
        'Annotation', attrs={'Term': 'Redfish.DynamicPropertyPatterns'})
    uriElement = element.find(
        'Annotation', attrs={'Term': 'Redfish.Uris'})

    if additionalElement is not None:
        additional = additionalElement.get('Bool', False)
        if additional in ['false', 'False', False]:
            additional = False
        if additional in ['true', 'True']:
            additional = True
    else:
        additional = False

    if additionalElementOther is not None:
        # create PropertyPattern dict containing pattern and type for DynamicPropertyPatterns validation
        rst.traverseLogger.debug('getTypeDetails: Redfish.DynamicPropertyPatterns found, element = {}, SchemaAlias = {}'
                             .format(element, SchemaAlias))
        pattern_elem = additionalElementOther.find("PropertyValue", Property="Pattern")
        pattern = prop_type = None
        if pattern_elem is not None:
            pattern = pattern_elem.get("String")
        type_elem = additionalElementOther.find("PropertyValue", Property="Type")
        if type_elem is not None:
            prop_type = type_elem.get("String")
        rst.traverseLogger.debug('getTypeDetails: pattern = {}, type = {}'.format(pattern, prop_type))
        if pattern is not None and prop_type is not None:
            PropertyPattern = dict()
            PropertyPattern['Pattern'] = pattern
            PropertyPattern['Type'] = prop_type
        additional = True

    expectedURI = None
    if uriElement is not None:
        try:
            all_strings = uriElement.find('Collection').find_all('String')
            expectedURI = [e.contents[0] for e in all_strings]
        except Exception as e:
            rst.traverseLogger.debug('Exception caught while checking URI', exc_info=1)
            rst.traverseLogger.warn('Could not gather info from Redfish.Uris annotation')
            expectedURI = None

    # get properties
    usableProperties = element.find_all(['NavigationProperty', 'Property'], recursive=False)

    for innerelement in usableProperties:
        rst.traverseLogger.debug(innerelement['Name'])
        rst.traverseLogger.debug(innerelement.get('Type'))
        rst.traverseLogger.debug(innerelement.attrs)
        newPropOwner = SchemaAlias if SchemaAlias is not None else 'SomeSchema'
        newProp = innerelement['Name']
        rst.traverseLogger.debug("ADDING :::: {}:{}".format(newPropOwner, newProp))
        PropertyList.append(
             (schemaObj, newPropOwner, newProp))

    # get actions
    usableActions = innerschema.find_all(['Action'], recursive=False)

    for act in usableActions:
        newPropOwner = getNamespace(SchemaAlias) if SchemaAlias is not None else 'SomeSchema'
        newProp = act['Name']
        rst.traverseLogger.debug("ADDING ACTION :::: {}:{}".format(newPropOwner, newProp))
        ActionList.append(
             PropAction(newPropOwner, newProp, act))

    return PropertyList, ActionList, additional, PropertyPattern, expectedURI


def getTypeObject(typename, schemaObj):
    idtag = (typename, schemaObj.origin)
    if idtag in PropType.robjcache:
        return PropType.robjcache[idtag]

    typename = typename.strip('#')
    if schemaObj.getTypeTagInSchema(typename) is None:
        if schemaObj.getTypeTagInSchema(getNamespaceUnversioned(typename)) is None:
            rst.traverseLogger.error("getTypeObject: Namespace appears nonexistent in SchemaXML: {} {}".format(typename, schemaObj.origin))
            return None

    acquiredtype = schemaObj.getHighestType(typename)
    if acquiredtype != typename:
        return getTypeObject(acquiredtype, schemaObj)
    else:
        newType = PropType(typename, schemaObj)
        PropType.robjcache[idtag] = newType
        return newType



class PropItem:
    def __init__(self, schemaObj, propOwner, propChild, val, topVersion=None, customType=None, payloadName=None):
        try:
            self.name = propOwner + ':' + propChild
            self.propOwner, self.propChild = propOwner, propChild
            self.val = val
            self.valid = topVersion is None or \
                    compareMinVersion(topVersion, propOwner)
            self.exists = val != 'n/a'
            self.payloadName = payloadName if payloadName is not None else propChild
            self.propDict = getPropertyDetails(
                schemaObj, propOwner, propChild, val, topVersion, customType)
            self.attr = self.propDict['attrs']

        except Exception as ex:
            rst.traverseLogger.debug('Exception caught while creating new PropItem', exc_info=1)
            rst.traverseLogger.error(
                    '{}:{} :  Could not get details on this property ({})'.format(str(propOwner), str(propChild), str(ex)))
            self.propDict = None
            self.attr = None
            return
        pass


class PropAction:
    def __init__(self, propOwner, propChild, act):
        try:
            self.name = '#{}.{}'.format(propOwner, propChild)
            self.propOwner, self.propChild = propOwner, propChild
            self.actTag = act
        except Exception:
            rst.traverseLogger.debug('Exception caught while creating new PropAction', exc_info=1)
            rst.traverseLogger.error(
                    '{}:{} :  Could not get details on this action'.format(str(propOwner),str(propChild)))
            self.actTag = None


def getPropertyDetails(schemaObj, propertyOwner, propertyName, val, topVersion=None, customType=None):
    """
    Get dictionary of tag attributes for properties given, including basetypes.

    param arg1: soup data
    param arg2: references
    ...
    """

    propEntry = dict()
    propEntry['val'] = val
    if val == 'n/a':
        val = None
    OwnerNamespace, OwnerType = getNamespace(propertyOwner), getType(propertyOwner)
    rst.traverseLogger.debug('___')
    rst.traverseLogger.debug('{}, {}:{}'.format(OwnerNamespace, propertyOwner, propertyName))

    soup, refs = schemaObj.soup, schemaObj.refs

    if customType is None:
        # Get Schema of the Owner that owns this prop
        ownerSchema = soup.find('Schema', attrs={'Namespace': OwnerNamespace})

        if ownerSchema is None:
            rst.traverseLogger.warning(
                "getPropertyDetails: Schema could not be acquired,  {}".format(OwnerNamespace))
            return None

        # Get Entity of Owner, then the property of the Property we're targeting
        ownerEntity = ownerSchema.find(
            ['EntityType', 'ComplexType'], attrs={'Name': OwnerType}, recursive=False)

        # check if this property is a nav property
        # Checks if this prop is an annotation
        success, propertySoup, propertyRefs, propertyFullType = True, soup, refs, OwnerType

        if '@' not in propertyName:
            propEntry['isTerm'] = False  # not an @ annotation
            propertyTag = ownerEntity.find(
                ['NavigationProperty', 'Property'], attrs={'Name': propertyName}, recursive=False)

            # start adding attrs and props together
            propertyInnerTags = propertyTag.find_all(recursive=False)
            for tag in propertyInnerTags:
                if(not tag.get('Term')):
                    rst.traverseLogger.warn(tag, 'does not contain a Term name')
                elif (tag.get('Term') == 'Redfish.Revisions'):
                    propEntry[tag['Term']] = tag.find_all('Record')
                else:
                    propEntry[tag['Term']] = tag.attrs
            propertyFullType = propertyTag.get('Type')
        else:
            propEntry['isTerm'] = True
            ownerEntity = ownerSchema.find(
                ['Term'], attrs={'Name': OwnerType}, recursive=False)
            if ownerEntity is None:
                ownerEntity = ownerSchema.find(
                    ['EntityType', 'ComplexType'], attrs={'Name': OwnerType}, recursive=False)
            propertyTag = ownerEntity
            propertyFullType = propertyTag.get('Type', propertyOwner)

        propEntry['isNav'] = propertyTag.name == 'NavigationProperty'
        propEntry['attrs'] = propertyTag.attrs
        rst.traverseLogger.debug(propEntry)

        propEntry['realtype'] = 'none'

    else:
        propertyFullType = customType
        propEntry['realtype'] = 'none'
        propEntry['attrs'] = dict()
        propEntry['attrs']['Type'] = customType
        serviceRefs = rst.currentService.metadata.get_service_refs()
        serviceSchemaSoup = rst.currentService.metadata.get_soup()
        success, propertySoup, propertyRefs, propertyFullType = True, serviceSchemaSoup, serviceRefs, customType

    # find the real type of this, by inheritance
    while propertyFullType is not None:
        rst.traverseLogger.debug("HASTYPE")
        PropertyNamespace, PropertyType = getNamespace(propertyFullType), getType(propertyFullType)

        rst.traverseLogger.debug('{}, {}'.format(PropertyNamespace, propertyFullType))

        # Type='Collection(Edm.String)'
        # If collection, check its inside type
        if re.match('Collection\(.*\)', propertyFullType) is not None:
            if val is not None and not isinstance(val, list):
                raise TypeError('This collection is not a List: {}'.format(val))
            propertyFullType = propertyFullType.replace('Collection(', "").replace(')', "")
            propEntry['isCollection'] = propertyFullType
            continue
        else:
            if val is not None and isinstance(val, list) and propEntry.get('isCollection') is None:
                raise TypeError('This item should not be a List')

        # If basic, just pass itself
        if 'Edm' in propertyFullType:
            propEntry['realtype'] = propertyFullType
            break

        # get proper soup, check if this Namespace is the same as its Owner, otherwise find its SchemaXml
        if PropertyNamespace.split('.')[0] != OwnerNamespace.split('.')[0]:
            schemaObj = schemaObj.getSchemaFromReference(PropertyNamespace)
            success = schemaObj is not None
            if success:
                uri = schemaObj.origin
                propertySoup = schemaObj.soup
                propertyRefs = schemaObj.refs
        else:
            success, propertySoup, uri = True, soup, 'of parent'

        if not success:
            rst.traverseLogger.warning(
                "getPropertyDetails: Could not acquire appropriate Schema for this item, {} {} {}".format(propertyOwner, PropertyNamespace, propertyName))
            return propEntry

        # traverse tags to find the type
        propertySchema = propertySoup.find(
            'Schema', attrs={'Namespace': PropertyNamespace})
        if propertySchema is None:
            rst.traverseLogger.warning('Schema element with Namespace attribute of {} not found in schema file {}'
                                 .format(PropertyNamespace, uri))
            break
        propertyTypeTag = propertySchema.find(
            ['EnumType', 'ComplexType', 'EntityType', 'TypeDefinition'], attrs={'Name': PropertyType}, recursive=False)
        nameOfTag = propertyTypeTag.name if propertyTypeTag is not None else 'None'

        # perform more logic for each type
        if nameOfTag == 'TypeDefinition': # Basic type
            # This piece of code is rather simple UNLESS this is an "enumeration"
            #   this is a unique deprecated enum, labeled as Edm.String

            propertyFullType = propertyTypeTag.get('UnderlyingType')
            isEnum = propertyTypeTag.find(
                'Annotation', attrs={'Term': 'Redfish.Enumeration'}, recursive=False)

            if propertyFullType == 'Edm.String' and isEnum is not None:
                propEntry['realtype'] = 'deprecatedEnum'
                propEntry['typeprops'] = list()
                memberList = isEnum.find(
                    'Collection').find_all('PropertyValue')

                for member in memberList:
                    propEntry['typeprops'].append(member.get('String'))
                rst.traverseLogger.debug("{}".format(propEntry['typeprops']))
                break
            else:
                continue

        elif nameOfTag == 'ComplexType': # go deeper into this type
            rst.traverseLogger.debug("go deeper in type")

            # We need to find the highest existence of this type vs topVersion schema
            # not ideal, but works for this solution
            success, baseSoup, baseRefs, baseType = True, propertySoup, propertyRefs, propertyFullType

            # If we're outside of our normal Soup, then do something different, otherwise elif
            if PropertyNamespace.split('.')[0] != OwnerNamespace.split('.')[0] and not customType:
                typelist = []
                schlist = []
                for schema in baseSoup.find_all('Schema'):
                    if schema.find('ComplexType', attrs={'Name': PropertyType}) is None:
                        continue
                    newNamespace = schema.get('Namespace')
                    typelist.append(newNamespace)
                    schlist.append(schema)
                for item, schema in reversed(sorted(zip(typelist, schlist))):
                    rst.traverseLogger.debug(
                        "Working backwards: {}   {}".format(item, getType(baseType)))
                    baseType = item + '.' + getType(baseType)
                    break
            elif topVersion is not None and (topVersion > OwnerNamespace):
                currentVersion = topVersion
                currentSchema = baseSoup.find(
                    'Schema', attrs={'Namespace': currentVersion})
                # Working backwards from topVersion schematag,
                #   created expectedType, check if currentTypeTag exists
                #   if it does, use our new expectedType, else continue down parent types
                #   until we exhaust all schematags in file
                while currentSchema is not None:
                    expectedType = currentVersion + '.' + PropertyType
                    currentTypeTag = currentSchema.find(
                        'ComplexType', attrs={'Name': PropertyType})
                    if currentTypeTag is not None:
                        baseType = expectedType
                        rst.traverseLogger.debug('new type: ' + baseType)
                        break
                    else:
                        nextEntity = currentSchema.find(
                            ['EntityType', 'ComplexType'], attrs={'Name': OwnerType})
                        nextType = nextEntity.get('BaseType')
                        currentVersion = getNamespace(nextType)
                        currentSchema = baseSoup.find(
                            'Schema', attrs={'Namespace': currentVersion})
                        continue
            propEntry['realtype'] = 'complex'
            if propEntry.get('isCollection') is None:
                propEntry['typeprops'] = rst.createResourceObject(propertyName, 'complex', val, context=schemaObj.context, typename=baseType, isComplex=True)
            else:
                val = val if val is not None else []
                propEntry['typeprops'] = [rst.createResourceObject(propertyName, 'complex', item, context=schemaObj.context, typename=baseType, isComplex=True) for item in val]
            break

        elif nameOfTag == 'EnumType':  # If enum, get all members
            propEntry['realtype'] = 'enum'
            propEntry['typeprops'] = list()
            for MemberName in propertyTypeTag.find_all('Member'):
                propEntry['typeprops'].append(MemberName['Name'])
            break

        elif nameOfTag == 'EntityType':  # If entity, do nothing special (it's a reference link)
            propEntry['realtype'] = 'entity'
            if val is not None:
                if propEntry.get('isCollection') is None:
                    val = [val]
                val = val if val is not None else []
                for innerVal in val:
                    linkURI = innerVal.get('@odata.id')
                    autoExpand = propEntry.get('OData.AutoExpand', None) is not None or\
                        propEntry.get('OData.AutoExpand'.lower(), None) is not None
                    linkType = propertyFullType
                    linkSchema = propertyFullType
                    innerJson = innerVal
                    propEntry['typeprops'] = linkURI, autoExpand, linkType, linkSchema, innerJson
            else:
                propEntry['typeprops'] = None
            rst.traverseLogger.debug("typeEntityTag found {}".format(propertyTypeTag['Name']))
            break

        else:
            rst.traverseLogger.error('Type {} not found under namespace {} in schema {}'
                                 .format(PropertyType, PropertyNamespace, uri))
            break

    return propEntry
