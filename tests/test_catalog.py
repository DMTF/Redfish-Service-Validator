# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md
#
# Unit tests for RedfishServiceValidator.py
#

import unittest
import sys
import pprint

sys.path.append('../')

import redfish_service_validator.catalog as catalog

import logging

logging.Logger.verbose1 =  logging.Logger.debug
logging.Logger.verbose2 =  logging.Logger.debug

class TestCatalog(unittest.TestCase):
    def test_fuzzy(self):
        print('\n')
        val = catalog.get_fuzzy_property('PropertyA', {'Name': 'Payload', 'PropertyB': False})
        self.assertEqual(val, 'PropertyB')
        val = catalog.get_fuzzy_property('PropertyA', {'Name': 'Payload', 'PropertyB': False, 'PropertyA': False})
        self.assertEqual(val, 'PropertyA')
        val = catalog.get_fuzzy_property('PropertyA', {'Name': 'Payload'}, [])
        self.assertEqual(val, 'PropertyA')
        val = catalog.get_fuzzy_property('PropertyA', {'Name': 'Payload'}, ['PropertyB'])
        self.assertEqual(val, 'PropertyA')
        # OK

    def test_catalog(self):
        print('\n')
        my_catalog = catalog.SchemaCatalog('./tests/testdata/schemas/')

        my_schema_doc = my_catalog.getSchemaDocByClass('Example')

        self.assertRaises(catalog.MissingSchemaError, my_catalog.getSchemaDocByClass, 'NotExample')

        my_schema = my_catalog.getSchemaInCatalog('Example.v1_0_0')

        my_type = my_catalog.getTypeInCatalog('Example.v1_7_0.Example')

        my_type = my_catalog.getTypeInCatalog('Example.v1_2_0.Links')
        # OK
    
    def test_schema_doc(self):
        print('\n')
        my_catalog = catalog.SchemaCatalog('./tests/testdata/schemas/')
        with open('./tests/testdata/schemas/Example_v1.xml') as f:
            my_doc = catalog.SchemaDoc(f.read(), my_catalog, 'Example_v1.xml')
        
        ref = my_doc.getReference('ExampleResource')
        ref = my_doc.getReference('ExampleResource.v1_0_0')
        ref = my_doc.getReference('ExampleResource.v1_0_1')
        ref = my_doc.getReference('ExampleResource.v1_9_9')
        ref = my_doc.getReference('Redfish')
        ref = my_doc.getReference('RedfishExtension.v1_0_0')
    
        my_type = my_doc.getTypeInSchemaDoc('Example.v1_0_0.Example')
        my_type = my_doc.getTypeInSchemaDoc(my_type)
        my_type = my_doc.getTypeInSchemaDoc('Example.v1_9_9.Example')
        my_type = my_doc.getTypeInSchemaDoc('Example.v1_0_0.Actions')
        my_type = my_doc.getTypeInSchemaDoc('ExampleResource.v1_0_0.ExampleResource')
        self.assertRaises(catalog.MissingSchemaError, my_doc.getTypeInSchemaDoc, 'NoExample.v1_0_0.NoExample')

    def test_schema_class(self):
        print('\n')
        my_catalog = catalog.SchemaCatalog('./tests/testdata/schemas/')
        my_doc = my_catalog.getSchemaDocByClass('Example.v1_0_0')
        my_schema = my_catalog.getSchemaInCatalog('Example.v1_0_0')
    
    def test_basic_properties(self):
        print('\nTesting basic types as json')
        prop = catalog.RedfishProperty("Edm.Int").populate(1)
        print(prop.as_json())
        prop = catalog.RedfishProperty("Edm.Decimal").populate(1.1)
        print(prop.as_json())
        prop = catalog.RedfishProperty("Edm.Guid").populate("123")
        print(prop.as_json())
        prop = catalog.RedfishProperty("Edm.Guid").populate(catalog.REDFISH_ABSENT)
        print(prop.as_json())

    def test_basic_properties_check(self):
        print('\nTesting check values')
        prop = catalog.RedfishProperty("Edm.Int").populate(1, check=True)
        prop = catalog.RedfishProperty("Edm.Int").populate(1.1, check=True)
        prop = catalog.RedfishProperty("Edm.Int").populate("1", check=True)
        prop = catalog.RedfishProperty("Edm.Decimal").populate(1.1, check=True)
        prop = catalog.RedfishProperty("Edm.Decimal").populate("1.1", check=True)
        prop = catalog.RedfishProperty("Edm.String").populate("1", check=True)
        prop = catalog.RedfishProperty("Edm.String").populate(1, check=True)
        prop = catalog.RedfishProperty("Edm.Guid").populate("123", check=True)
        prop = catalog.RedfishProperty("Edm.Guid").populate(catalog.REDFISH_ABSENT, check=True)
    
    def test_object(self):
        print('\nTesting object values')
        my_catalog = catalog.SchemaCatalog('./tests/testdata/schemas/')
        my_schema_doc = my_catalog.getSchemaDocByClass("ExampleResource.v1_0_0.ExampleResource")
        my_type = my_schema_doc.getTypeInSchemaDoc("ExampleResource.v1_0_0.ExampleResource")
        object = catalog.RedfishObject( my_type )
        pprint.pprint(object.as_json(), indent=2)
        dct = object.as_json()
        dct = object.getLinks()
        object = catalog.RedfishObject( my_type ).populate({"Id": None, "Description": None})
        pprint.pprint(object.as_json(), indent=2)
        dct = object.as_json()
        dct = object.getLinks()

    def test_capabilities(self):
        my_catalog = catalog.SchemaCatalog('./tests/testdata/schemas/')
        my_schema_doc = my_catalog.getSchemaDocByClass("Example.v1_0_0.Example")
        my_type = my_schema_doc.getTypeInSchemaDoc("Example.v1_0_0.Example")
        my_capabilities = my_type.getCapabilities()

        self.assertTrue(my_capabilities['CanUpdate'])
        self.assertFalse(my_capabilities['CanInsert'])
        self.assertFalse(my_capabilities['CanDelete'])

        self.assertTrue(my_type.CanUpdate)
        self.assertFalse(my_type.CanInsert)
        self.assertFalse(my_type.CanDelete)
    
    def test_expected_uris(self):
        print('\nTesting expected Uris')
        my_catalog = catalog.SchemaCatalog('./tests/testdata/schemas/')
        my_schema_doc = my_catalog.getSchemaDocByClass("Example.v1_0_0.Example")
        my_type = my_schema_doc.getTypeInSchemaDoc("Example.v1_0_0.Example")
        object = catalog.RedfishObject( my_type )

        arr = object.Type.getUris()
        self.assertEqual(len(arr), 3)


        object = catalog.RedfishObject( my_type ).populate({
            "@odata.id": "/redfish/v1/Example",
            "Id": "Example",
            "Description": None
            })
        self.assertTrue(object.HasValidUri)

        object = catalog.RedfishObject( my_type ).populate({
            "@odata.id": "/redfish/v1/Examples",
            "Id": "Examples",
            "Description": None
            })
        self.assertFalse(object.HasValidUri)

        object = catalog.RedfishObject( my_type ).populate({
            "@odata.id": "/redfish/v1/Examples/FunnyId",
            "Id": 'FunnyId',
            "Description": None
            })
        self.assertTrue(object.HasValidUri)
        self.assertTrue(object.HasValidUriStrict)

        object = catalog.RedfishObject( my_type ).populate({
            "@odata.id": "/redfish/v1/Examples/SubObject/FunnyId",
            "Id": 'FunnyId',
            "Description": None
            })
        self.assertTrue(object.HasValidUri)
        self.assertTrue(object.HasValidUriStrict)

        object = catalog.RedfishObject( my_type ).populate({
            "@odata.id": "/redfish/v1/Examples/SubObject/FunnyId",
            "Description": None
            })
        self.assertTrue(object.HasValidUri)
        self.assertTrue(object.HasValidUriStrict)

        object = catalog.RedfishObject( my_type ).populate({
            "@odata.id": "/redfish/v1/Examples/WrongId",
            "Id": 'FunnyId',
            "Description": None
            })
        self.assertTrue(object.HasValidUri)
        self.assertFalse(object.HasValidUriStrict)

        object = catalog.RedfishObject( my_type ).populate({
            "@odata.id": "/redfish/v1/Examples/NoId",
            "Id": None,
            "Description": None
            })
        self.assertTrue(object.HasValidUri)
        self.assertTrue(object.HasValidUriStrict)



if __name__ == '__main__':
    unittest.main()