# Copyright Notice:
# Copyright 2017-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md
#
# Unit tests for RedfishServiceValidator.py
#

from unittest import TestCase
from unittest import mock
import datetime
import sys
import os

sys.path.append('../')

import traverseService as rst
import rfSchema
from bs4 import BeautifulSoup

rsvLogger = rst.getLogger()
rsvLogger.disabled = True
rst.config['metadatafilepath'] = './tests/testdata/schemas'

class SchemaTest(TestCase):

    """
    Tests for functions setup_operation() and run_systems_operation()
    """
    def test_get_reference_details(self):
        # todo: consider bad tags, prebaked results
        with open('tests/testdata/schemas/Example_v1.xml') as f:
            example_soup = BeautifulSoup(f, "xml")

        genrefs = rfSchema.getReferenceDetails(example_soup)

        maintag = example_soup.find("edmx:Edmx", recursive=False)
        reftags = maintag.find_all('edmx:Reference', recursive=False)
        includes = [i for ref in reftags for i in ref.find_all('edmx:Include', recursive=False)]

        self.assertTrue(len(includes) == len(genrefs), 'getReferenceDetails results do not match actual results')

    def test_schema_object(self):
        # todo: consider no schema, consider service
        rfo = rfSchema.getSchemaObject('Example.Example', '/redfish/v1/$metadata#Example.Example')
        self.assertTrue(rfo is not None, 'SchemaObject not created')

    def test_highest_type(self):
        rfo = rfSchema.getSchemaObject('Example.Example', '/redfish/v1/$metadata#Example.Example')
        assert rfo

        self.assertTrue(rfo.getHighestType('Example.Example') == 'Example.v1_7_0.Example')
        self.assertTrue(rfo.getHighestType('Example.Example', 'Newark.v1_2_1') == 'Example.v1_2_1.Example')
        self.assertTrue(rfo.getHighestType('Example.Example', 'Newark.v0_0_0') == 'Example.Example')
        self.assertTrue(rfo.getHighestType('Example.Example', 'Newark') == 'Example.v1_7_0.Example')
        self.assertTrue(rfo.getHighestType('Example.Links') == 'Example.v1_7_0.Links')
        self.assertTrue(rfo.getHighestType('Example.Links', 'Example.v1_1_1') == 'Example.v1_0_0.Links')

    def test_get_from_reference(self):
        # todo: consider no schema, consider service
        rfo = rfSchema.getSchemaObject('Example.Example', '/redfish/v1/$metadata#Example.Example')
        assert rfo

        self.assertTrue(rfo.getSchemaFromReference('ExampleResource') is not None)
        self.assertTrue(rfo.getSchemaFromReference('ExampleResource.v1_0_0') is not None)
        self.assertTrue(rfo.getSchemaFromReference('ExampleResource.v1_0_1') is not None)
        self.assertFalse(rfo.getSchemaFromReference('Resource.v1_0_1') is not None)

    def test_get_type_tag(self):
        rfo = rfSchema.getSchemaObject('Example.Example', '/redfish/v1/$metadata#Example.Example')
        assert rfo

        self.assertTrue(rfo.getTypeTagInSchema('Example.v1_0_0.Example') is not None)
        self.assertFalse(rfo.getTypeTagInSchema('Example.v1_0_9.Example') is not None)
        self.assertTrue(rfo.getTypeTagInSchema('Example.Example') is not None)
        self.assertFalse(rfo.getTypeTagInSchema('Example.v1_0_0.ExampleEnum') is not None)
        self.assertTrue(rfo.getTypeTagInSchema('Example.v1_0_0.ExampleEnum', 'EnumType') is not None)
        self.assertTrue(rfo.getTypeTagInSchema('Example') is not None)

    def test_get_parent_type(self):
        # todo: consider unusual parent situations (?)
        rfo = rfSchema.getSchemaObject('Example.Example', '/redfish/v1/$metadata#Example.Example')
        assert rfo

        self.assertTrue(rfo.getParentType('Example.v1_0_0.Example'))
        self.assertTrue(rfo.getParentType('Example.Example'))







