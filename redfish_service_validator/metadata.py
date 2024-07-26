# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import os
import time
from collections import Counter, OrderedDict, defaultdict
from collections import namedtuple
from bs4 import BeautifulSoup
from functools import lru_cache
import os.path

from redfish_service_validator.helper import getNamespace, getNamespaceUnversioned

import logging
my_logger = logging.getLogger(__name__)


EDM_NAMESPACE = "http://docs.oasis-open.org/odata/ns/edm"
EDMX_NAMESPACE = "http://docs.oasis-open.org/odata/ns/edmx"
EDM_TAGS = ['Action', 'Annotation', 'Collection', 'ComplexType', 'EntityContainer', 'EntityType', 'EnumType', 'Key',
            'Member', 'NavigationProperty', 'Parameter', 'Property', 'PropertyRef', 'PropertyValue', 'Record',
            'Schema', 'Singleton', 'Term', 'TypeDefinition']
EDMX_TAGS = ['DataServices', 'Edmx', 'Include', 'Reference']


def bad_edm_tags(tag):
    return tag.namespace == EDM_NAMESPACE and tag.name not in EDM_TAGS


def bad_edmx_tags(tag):
    return tag.namespace == EDMX_NAMESPACE and tag.name not in EDMX_TAGS


def other_ns_tags(tag):
    return tag.namespace != EDM_NAMESPACE and tag.namespace != EDMX_NAMESPACE


def reference_missing_uri_attr(tag):
    return tag.name == 'Reference' and tag.get('Uri') is None


def include_missing_namespace_attr(tag):
    return tag.name == 'Include' and tag.get('Namespace') is None


def format_tag_string(tag):
    tag_name = tag.name if tag.prefix is None else tag.prefix + ':' + tag.name
    tag_attr = ''
    for attr in tag.attrs:
        tag_attr += '{}="{}" '.format(attr, tag.attrs[attr])
    return (tag_name + ' ' + tag_attr).strip()


def list_html(entries):
    html_str = '<ul>'
    for entry in entries:
        html_str += '<li>{}</li>'.format(entry)
    html_str += '</ul>'
    return html_str


def tag_list_html(tags_dict):
    html_str = '<ul>'
    for tag in tags_dict:
        html_str += '<li>{} {}</li>' \
            .format(tag, '(' + str(tags_dict[tag]) + ' occurrences)' if tags_dict[tag] > 1 else '')
    html_str += '</ul>'
    return html_str


class Metadata(object):
    metadata_uri = '/redfish/v1/$metadata'
    schema_type = '$metadata'

    def __init__(self, data, service, logger):
        logger.info('Constructing metadata...')
        self.success_get = False
        self.service = service
        self.uri_to_namespaces = defaultdict(list)
        self.elapsed_secs = 0
        self.metadata_namespaces = set()
        self.service_namespaces = set()
        self.schema_store = dict()
        self.bad_tags = dict()
        self.bad_tag_ns = dict()
        self.refs_missing_uri = dict()
        self.includes_missing_ns = dict()
        self.bad_schema_uris = set()
        self.bad_namespace_include = set()
        self.counter = OrderedCounter()
        self.logger = logger
        self.redfish_extensions_alias_ok = False

        start = time.time()
        self.md_soup = None
        self.service_refs = None
        uri = Metadata.metadata_uri

        self.elapsed_secs = time.time() - start
        self.schema_obj = None
        if data:
            self.md_soup = BeautifulSoup(data, "xml")
            self.service_refs = getReferenceDetails(self.md_soup)
            self.success_get = True
            # set of namespaces included in $metadata
            self.metadata_namespaces = {k for k in self.service_refs.keys()}
            # create map of schema URIs to namespaces from $metadata
            for k in self.service_refs.keys():
                self.uri_to_namespaces[self.service_refs[k][1]].append(self.service_refs[k][0])
            logger.debug('Metadata: uri = {}'.format(uri))
            logger.debug('Metadata: metadata_namespaces: {} = {}'
                         .format(type(self.metadata_namespaces), self.metadata_namespaces))
            # check for Redfish alias for RedfishExtensions.v1_0_0
            ref = self.service_refs.get('Redfish')
            if ref is not None and ref[0] == 'RedfishExtensions.v1_0_0':
                self.redfish_extensions_alias_ok = True
            logger.debug('Metadata: redfish_extensions_alias_ok = {}'.format(self.redfish_extensions_alias_ok))
            # check for XML tag problems
            self.check_tags()
            # check that all namespace includes are found in the referenced schema
            self.check_namespaces_in_schemas()
            logger.debug('Metadata: bad_tags = {}'.format(self.bad_tags))
            logger.debug('Metadata: bad_tag_ns = {}'.format(self.bad_tag_ns))
            logger.debug('Metadata: refs_missing_uri = {}'.format(self.refs_missing_uri))
            logger.debug('Metadata: includes_missing_ns = {}'.format(self.includes_missing_ns))
            logger.debug('Metadata: bad_schema_uris = {}'.format(self.bad_schema_uris))
            logger.debug('Metadata: bad_namespace_include = {}'.format(self.bad_namespace_include))
            for ref in self.service_refs:
                name, uri = self.service_refs[ref]
                success, soup, origin = getSchemaDetails(service, name, uri)
                self.schema_store[name] = soup
        else:
            logger.warning('Metadata: getSchemaDetails() did not return success')

    def get_schema_obj(self):
        return self.schema_obj

    def get_soup(self):
        return self.md_soup

    def get_service_refs(self):
        return self.service_refs

    def get_metadata_namespaces(self):
        return self.metadata_namespaces

    def get_service_namespaces(self):
        return self.service_namespaces

    def add_service_namespace(self, namespace):
        self.service_namespaces.add(namespace)

    def get_missing_namespaces(self):
        return self.service_namespaces - self.metadata_namespaces

    def get_schema_uri(self, namespace):
        ref = self.service_refs.get(namespace)
        if ref is not None:
            return ref[1]
        else:
            return None

    def check_tags(self):
        """
        Perform some checks on the tags in the $metadata XML looking for unrecognized tags,
        tags missing required attributes, etc.
        """
        try:
            for tag in self.md_soup.find_all(bad_edm_tags):
                tag_str = format_tag_string(tag)
                self.bad_tags[tag_str] = self.bad_tags.get(tag_str, 0) + 1
            for tag in self.md_soup.find_all(bad_edmx_tags):
                tag_str = format_tag_string(tag)
                self.bad_tags[tag_str] = self.bad_tags.get(tag_str, 0) + 1
            for tag in self.md_soup.find_all(reference_missing_uri_attr):
                tag_str = format_tag_string(tag)
                self.refs_missing_uri[tag_str] = self.refs_missing_uri.get(tag_str, 0) + 1
            for tag in self.md_soup.find_all(include_missing_namespace_attr):
                tag_str = format_tag_string(tag)
                self.includes_missing_ns[tag_str] = self.includes_missing_ns.get(tag_str, 0) + 1
            for tag in self.md_soup.find_all(other_ns_tags):
                tag_str = tag.name if tag.prefix is None else tag.prefix + ':' + tag.name
                tag_ns = 'xmlns{}="{}"'.format(':' + tag.prefix if tag.prefix is not None else '', tag.namespace)
                tag_str = tag_str + ' ' + tag_ns
                self.bad_tag_ns[tag_str] = self.bad_tag_ns.get(tag_str, 0) + 1
        except Exception as e:
            self.logger.warning('Metadata: Problem parsing $metadata document: {}'.format(e))

    def check_namespaces_in_schemas(self):
        """
        Check that all namespaces included from a schema URI are actually in that schema
        """
        for k in self.uri_to_namespaces.keys():
            schema_uri = k
            if '#' in schema_uri:
                schema_uri, frag = k.split('#', 1)
            schema_type = os.path.basename(os.path.normpath(k)).strip('.xml').strip('_v1')
            success, soup, _ = getSchemaDetails(self.service, schema_type, schema_uri)
            if success:
                for namespace in self.uri_to_namespaces[k]:
                    if soup.find('Schema', attrs={'Namespace': namespace}) is None:
                        msg = 'Namespace {} not found in schema {}'.format(namespace, k)
                        self.logger.debug('Metadata: {}'.format(msg))
                        self.bad_namespace_include.add(msg)
            else:
                self.logger.error('Metadata: failure opening schema {} of type {}'.format(schema_uri, schema_type))
                self.bad_schema_uris.add(schema_uri)

    def get_counter(self):
        """
        Create a Counter instance containing the counts of any errors found
        """
        counter = OrderedCounter()
        # informational counters
        counter['metadataNamespaces'] = len(self.metadata_namespaces)
        counter['serviceNamespaces'] = len(self.service_namespaces)
        # error counters
        counter['missingRedfishAlias'] = 0 if self.redfish_extensions_alias_ok else 1
        counter['missingNamespaces'] = len(self.get_missing_namespaces())
        counter['badTags'] = len(self.bad_tags)
        counter['missingUriAttr'] = len(self.refs_missing_uri)
        counter['missingNamespaceAttr'] = len(self.includes_missing_ns)
        counter['badTagNamespaces'] = len(self.bad_tag_ns)
        counter['badSchemaUris'] = len(self.bad_schema_uris)
        counter['badNamespaceInclude'] = len(self.bad_namespace_include)
        self.counter = counter
        return self.counter

    def to_html(self):
        """
        Convert the $metadata validation results to HTML
        """
        time_str = 'response time {0:.6f}s'.format(self.elapsed_secs)
        section_title = '{} ({})'.format(Metadata.metadata_uri, time_str)

        counter = self.get_counter()

        html_str = ''
        html_str += '<tr><th class="titlerow bluebg"><b>{}</b></th></tr>'\
            .format(section_title)
        html_str += '<tr><td class="titlerow"><table class="titletable"><tr>'
        html_str += '<td class="title" style="width:40%"><div>{}</div>\
                        <div class="button warn" onClick="document.getElementById(\'resMetadata\').classList.toggle(\'resultsShow\');">Show results</div>\
                        </td>'.format(section_title)
        html_str += '<td class="titlesub log" style="width:30%"><div><b>Schema File:</b> {}</div><div><b>Resource Type:</b> {}</div></td>'\
            .format(Metadata.metadata_uri, Metadata.schema_type)
        html_str += '<td style="width:10%"' + \
            ('class="pass"> GET Success' if self.success_get else 'class="fail"> GET Failure') + '</td>'
        html_str += '<td style="width:10%">'

        errors_found = False
        for count_type in counter.keys():
            style = 'class=log'
            if 'bad' in count_type or 'missing' in count_type:
                if counter[count_type] > 0:
                    errors_found = True
                    style = 'class="fail log"'
            html_str += '<div {style}>{p}: {q}</div>'.format(
                    p=count_type, q=counter.get(count_type, 0), style=style)

        html_str += '</td></tr>'
        html_str += '</table></td></tr>'
        html_str += '<tr><td class="results" id=\'resMetadata\'><table><tr><th>$metadata validation results</th></tr>'

        if self.success_get and not errors_found:
            html_str += '<tr><td class="pass log">Validation successful</td></tr>'
        elif not self.success_get:
            html_str += '<tr><td class="fail log">ERROR - Unable to retrieve $metadata resource at {}</td></tr>'\
                .format(Metadata.metadata_uri)
        else:
            if not self.redfish_extensions_alias_ok:
                html_str += '<tr><td class="fail log">ERROR - $metadata does not include the required "RedfishExtensions.v1_0_0" namespace with an alias of "Redfish"</td></tr>'
            if len(self.get_missing_namespaces()) > 0:
                html_str += '<tr><td class="fail log">ERROR - The following namespaces are referenced by the service, but are not included in $metadata:<ul>'
                for ns in self.get_missing_namespaces():
                    html_str += '<li>{}</li>'.format(ns)
                html_str += '</ul></td></tr>'
            if len(self.bad_tags) > 0:
                html_str += '<tr><td class="fail log">ERROR - The following tag names in $metadata are unrecognized (check spelling or case):'
                html_str += tag_list_html(self.bad_tags)
                html_str += '</td></tr>'
            if len(self.refs_missing_uri) > 0:
                html_str += '<tr><td class="fail log">ERROR - The following Reference tags in $metadata are missing the expected Uri attribute (check spelling or case):'
                html_str += tag_list_html(self.refs_missing_uri)
                html_str += '</td></tr>'
            if len(self.includes_missing_ns) > 0:
                html_str += '<tr><td class="fail log">ERROR - The following Include tags in $metadata are missing the expected Namespace attribute (check spelling or case):'
                html_str += tag_list_html(self.includes_missing_ns)
                html_str += '</td></tr>'
            if len(self.bad_tag_ns) > 0:
                html_str += '<tr><td class="fail log">ERROR - The following tags in $metadata have an unexpected namespace:'
                html_str += tag_list_html(self.bad_tag_ns)
                html_str += '</td></tr>'
            if len(self.bad_schema_uris) > 0:
                html_str += '<tr><td class="fail log">ERROR - The following schema URIs referenced from $metadata could not be retrieved:'
                html_str += list_html(self.bad_schema_uris)
                html_str += '</td></tr>'
            if len(self.bad_namespace_include) > 0:
                html_str += '<tr><td class="fail log">ERROR - The following namespaces included in $metadata could not be found in the referenced schema URI:'
                html_str += list_html(self.bad_namespace_include)
                html_str += '</td></tr>'
        html_str += '</table>'

        return html_str


class OrderedCounter(Counter, OrderedDict):
    """Counter that remembers the order elements are first encountered"""

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, OrderedDict(self))

    def __reduce__(self):
        return self.__class__, (OrderedDict(self),)

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
    my_logger.debug("METADATA: References generated from {}: {} out of {}".format(name, cntref, len(refDict)))
    return refDict