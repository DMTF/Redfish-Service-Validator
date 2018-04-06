# Copyright Notice:
# Copyright 2018 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import traverseService as rst

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


class Metadata(object):
    metadata_uri = '/redfish/v1/$metadata'
    schema_type = '$metadata'

    def __init__(self, logger):
        self.soup = None
        self.service_refs = dict()
        self.metadata_namespaces = set()
        self.service_namespaces = set()
        self.bad_tags = dict()
        self.bad_tag_ns = dict()
        self.logger = logger
        self.redfish_extensions_alias_ok = False

        success, soup, uri = rst.getSchemaDetails(Metadata.schema_type, Metadata.metadata_uri)
        if success:
            self.soup = soup
            self.service_refs = rst.getReferenceDetails(soup, name=Metadata.schema_type)
            self.metadata_namespaces = {k for k in self.service_refs.keys()}
            logger.debug('Metadata: uri = {}'.format(uri))
            # logger.debug('Metadata: service_refs: {} = {}'.format(type(self.service_refs), self.service_refs))
            logger.debug('Metadata: metadata_namespaces: {} = {}'
                         .format(type(self.metadata_namespaces), self.metadata_namespaces))
            ref = self.service_refs.get('Redfish')
            if ref is not None and ref[0] == 'RedfishExtensions.v1_0_0':
                self.redfish_extensions_alias_ok = True
            logger.debug('Metadata: redfish_extensions_alias_ok = {}'.format(self.redfish_extensions_alias_ok))
            self.check_tags(soup)
            logger.debug('Metadata: bad_tags = {}'.format(self.bad_tags))
            logger.debug('Metadata: bad_tag_ns = {}'.format(self.bad_tag_ns))
        else:
            logger.debug('Metadata: getSchemaDetails() did not return success')

    def get_soup(self):
        return self.soup

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

    def redfish_extensions_alias_ok(self):
        return self.redfish_extensions_alias_ok

    def check_tags(self, soup):
        try:
            for tag in soup.find_all(bad_edm_tags):
                tag_name = tag.name if tag.prefix is None else tag.prefix + ':' + tag.name
                self.bad_tags[tag_name] = self.bad_tags.get(tag_name, 0) + 1
            for tag in soup.find_all(bad_edmx_tags):
                tag_name = tag.name if tag.prefix is None else tag.prefix + ':' + tag.name
                self.bad_tags[tag_name] = self.bad_tags.get(tag_name, 0) + 1
            for tag in soup.find_all(other_ns_tags):
                tag_name = tag.name if tag.prefix is None else tag.prefix + ':' + tag.name
                tag_ns = 'xmlns{}="{}"'.format(':' + tag.prefix if tag.prefix is not None else '', tag.namespace)
                tag_name = tag_name + ' ' + tag_ns
                self.bad_tag_ns[tag_name] = self.bad_tag_ns.get(tag_name, 0) + 1
            # TODO: add check for misspelled/missing attributes:
            #     <edmx:Reference Uri="/redfish/v1/Schemas/ServiceRoot_v1.xml">
            #     <edmx:Include Namespace="ServiceRoot.v1_0_0"/>
            #     <edmx:Include Namespace="RedfishExtensions.v1_0_0" Alias="Redfish"/>
        except Exception as e:
            self.logger.warning('Error parsing document with BeautifulSoup4, error: {}'.format(e))