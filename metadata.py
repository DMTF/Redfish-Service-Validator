# Copyright Notice:
# Copyright 2018 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import traverseService as rst


class Metadata(object):
    metadata_uri = '/redfish/v1/$metadata'
    schema_type = '$metadata'

    def __init__(self, logger):
        self.service_refs = dict()
        self.metadata_namespaces = set()
        self.service_namespaces = set()
        self.logger = logger
        self.redfish_extensions_alias_ok = False

        success, soup, uri = rst.getSchemaDetails(Metadata.schema_type, Metadata.metadata_uri)
        if success:
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
        else:
            logger.debug('Metadata: getSchemaDetails() did not return success')

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
