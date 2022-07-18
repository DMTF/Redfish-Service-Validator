# Copyright Notice:
# Copyright 2016-2020 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

from collections import namedtuple
from re import split
from bs4 import BeautifulSoup
from functools import lru_cache
import os.path

from redfish_service_validator.helper import getType, getNamespace, getNamespaceUnversioned, getVersion, splitVersionString

import logging
my_logger = logging.getLogger(__name__)


def storeSchemaToLocal(xml_data, origin, service):
    """storeSchemaToLocal

    Moves data pulled from service/online to local schema storage

    Does NOT do so if preferonline is specified

    :param xml_data: data being transferred
    :param origin: origin of xml pulled
    """
    config = service.config
    SchemaLocation = config['metadatafilepath']
    if not os.path.isdir(SchemaLocation):
        os.makedirs(SchemaLocation)
    if 'localFile' not in origin and '$metadata' not in origin:
        __, xml_name = origin.rsplit('/', 1)
        new_file = os.path.join(SchemaLocation, xml_name)
        if not os.path.isfile(new_file):
            with open(new_file, "w") as filehandle:
                filehandle.write(xml_data)
                my_logger.info('Writing online XML to file: {}'.format(xml_name))
        else:
            my_logger.info('NOT writing online XML to file: {}'.format(xml_name))


@lru_cache(maxsize=64)
def getSchemaDetails(service, SchemaType, SchemaURI):
    """
    Find Schema file for given Namespace.

    param SchemaType: Schema Namespace, such as ServiceRoot
    param SchemaURI: uri to grab schema, given LocalOnly is False
    return: (success boolean, a Soup object, origin)
    """
    my_logger.debug('getting Schema of {} {}'.format(SchemaType, SchemaURI))

    if SchemaType is None:
        return False, None, None

    if service is None:
        return getSchemaDetailsLocal(SchemaType, SchemaURI, {})
    

    elif service.active and getNamespace(SchemaType) in service.metadata.schema_store:
        result = service.metadata.schema_store[getNamespace(SchemaType)]
        if result is not None:
            return True, result.soup, result.origin

    success, soup, origin = getSchemaDetailsLocal(SchemaType, SchemaURI, service.config)
    if success:
        return success, soup, origin

    xml_suffix = '_v1.xml'

    if (SchemaURI is not None) or (SchemaURI is not None and '/redfish/v1/$metadata' in SchemaURI):
        # Get our expected Schema file here
        # if success, generate Soup, then check for frags to parse
        #   start by parsing references, then check for the refLink
        if '#' in SchemaURI:
            base_schema_uri, frag = tuple(SchemaURI.rsplit('#', 1))
        else:
            base_schema_uri, frag = SchemaURI, None
        success, data, response, elapsed = service.callResourceURI(base_schema_uri)
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
                    success, linksoup, newlink = getSchemaDetails(service, refType, refLink)
                    if success:
                        return True, linksoup, newlink
                    else:
                        my_logger.error(
                            "SchemaURI couldn't call reference link {} inside {}".format(frag, base_schema_uri))
                else:
                    my_logger.error(
                        "SchemaURI missing reference link {} inside {}".format(frag, base_schema_uri))
                    # error reported; assume likely schema uri to allow continued validation
                    uri = 'http://redfish.dmtf.org/schemas/v1/{}{}'.format(frag, xml_suffix)
                    my_logger.info("Continue assuming schema URI for {} is {}".format(SchemaType, uri))
                    return getSchemaDetails(service, SchemaType, uri)
            else:
                storeSchemaToLocal(data, base_schema_uri, service)
                return True, soup, base_schema_uri
        else:
            my_logger.debug("SchemaURI called unsuccessfully: {}".format(base_schema_uri))
    return getSchemaDetailsLocal(SchemaType, SchemaURI, service.config)


def getSchemaDetailsLocal(SchemaType, SchemaURI, config):
    """
    Find Schema file for given Namespace, from local directory

    param SchemaType: Schema Namespace, such as ServiceRoot
    param SchemaURI: uri to grab schem (generate information from it)
    return: (success boolean, a Soup object, origin)
    """
    Alias = getNamespaceUnversioned(SchemaType)
    SchemaLocation, SchemaSuffix = config['metadatafilepath'], '_v1.xml'
    if SchemaURI is not None:
        uriparse = SchemaURI.split('/')[-1].split('#')
        xml = uriparse[0]
    else:
        my_logger.warning("SchemaURI was empty, must generate xml name from type {}".format(SchemaType)),
        return getSchemaDetailsLocal(SchemaType, Alias + SchemaSuffix, config)
    my_logger.debug(('local', SchemaType, SchemaURI, SchemaLocation + '/' + xml))
    filestring = Alias + SchemaSuffix if xml is None else xml
    try:
        # get file
        with open(SchemaLocation + '/' + xml, "r") as filehandle:
            data = filehandle.read()

        # get tags
        soup = BeautifulSoup(data, "xml")
        edmxTag = soup.find('Edmx', recursive=False)
        parentTag = edmxTag.find('DataServices', recursive=False)
        child = parentTag.find('Schema', recursive=False)
        SchemaNamespace = child['Namespace']
        FoundAlias = SchemaNamespace.split(".")[0]
        my_logger.debug(FoundAlias)

        if FoundAlias in Alias:
            return True, soup, "localFile:" + SchemaLocation + '/' + filestring

    except FileNotFoundError:
        # if we're looking for $metadata locally... ditch looking for it, go straight to file
        if '/redfish/v1/$metadata' in SchemaURI and Alias != '$metadata':
            my_logger.debug("Unable to find a xml of {} at {}, defaulting to {}".format(SchemaURI, SchemaLocation, Alias + SchemaSuffix))
            return getSchemaDetailsLocal(SchemaType, Alias + SchemaSuffix, config)
        else:
            my_logger.warning("Schema file {} not found in {}".format(filestring, SchemaLocation))
            if Alias == '$metadata':
                my_logger.warning("If $metadata cannot be found, Annotations may be unverifiable")
    except Exception as ex:
        my_logger.error("A problem when getting a local schema has occurred {}".format(SchemaURI))
        my_logger.warning("output: ", exc_info=True)
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
        my_logger.error(msg.format(name, namespace,
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

    maintag = soup.find("Edmx", recursive=False)
    reftags = maintag.find_all('Reference', recursive=False)
    for ref in reftags:
        includes = ref.find_all('Include', recursive=False)
        for item in includes:
            uri = ref.get('Uri')
            ns, alias = (item.get(x) for x in ['Namespace', 'Alias'])
            if ns is None or uri is None:
                my_logger.error("Reference incorrect for: {}".format(item))
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
    my_logger.debug("References generated from {}: {} out of {}".format(name, cntref, len(refDict)))
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
                my_logger.warning('No such reference {} in {}'.format(namespace, self.origin))
                return None
            else:
                tup = tupVersionless
                my_logger.warning('No such reference {} in {}, using unversioned'.format(namespace, self.origin))
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
                if 'Collection' not in limit:
                    my_logger.warning('Limiting namespace has no version, erasing: {}'.format(limit))
                else:
                    my_logger.info('Limiting namespace has no version, erasing: {}'.format(limit))
                limit = None
            else:
                limit = getVersion(limit)

        for schema in self.soup.find_all('Schema'):
            newNamespace = schema.get('Namespace')
            if limit is not None:
                if getVersion(newNamespace) is None:
                    continue
                if splitVersionString(newNamespace) > splitVersionString(limit):
                    continue
            if schema.find(['EntityType', 'ComplexType'], attrs={'Name': getType(acquiredtype)}, recursive=False):
                typelist.append(splitVersionString(newNamespace))

        if len(typelist) > 1:
            for ns in reversed(sorted(typelist)):
                my_logger.debug(
                    "{}   {}".format(ns, getType(acquiredtype)))
                acquiredtype = getNamespaceUnversioned(acquiredtype) + '.v{}_{}_{}'.format(*ns) + '.' + getType(acquiredtype)
                return acquiredtype
        return acquiredtype


@lru_cache(maxsize=64)
def getSchemaObject(service, typename, uri, metadata=None):
    """getSchemaObject

    Wrapper for getting an rfSchema object

    :param typename: Type with namespace of schema
    :param uri: Context/URI of metadata/schema containing reference to namespace
    :param metadata: parent refs of service
    """
    success, soup, origin = getSchemaDetails(service, typename, uri)

    return rfSchema(soup, uri, origin, metadata=metadata, name=typename) if success else None
