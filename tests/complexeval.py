
# Copyright Notice:
# Copyright 2017 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md
#
# Unit tests for RedfishServiceValidator.py
#

from unittest import TestCase
from unittest import mock
import datetime
import sys

sys.path.append('../')

import json, os
import traverseService as rst
import RedfishServiceValidator as rsv 
from bs4 import BeautifulSoup

rsvLogger = rst.getLogger()
rsvLogger.disabled = True
rst.config['metadatafilepath'] = './tests/testdata/schemas'

class ValidatorTest(TestCase):

    """
    Tests for functions setup_operation() and run_systems_operation()
    """
    def test_example(self):
        with open('tests/testdata/payloads/simple.json') as f:
            example_json = json.load(f) 
        
        rsc = rst.ResourceObj('test', 'test', example_json, None, None, None, False)
        for prop in rsc.getResourceProperties(): 
                propMessages, propCounts = rsv.checkPropertyConformance(rsc.schemaObj, prop.name, prop.propDict, rsc.jsondata, parentURI='')
                print(propMessages)
                print(propCounts)

    def test_example_bad(self):
        with open('tests/testdata/payloads/simple_bad.json') as f:
            example_json = json.load(f) 
        
        rsc = rst.ResourceObj('test', 'test', example_json, None, None, None, False)
        for prop in rsc.getResourceProperties(): 
                propMessages, propCounts = rsv.checkPropertyConformance(rsc.schemaObj, prop.name, prop.propDict, rsc.jsondata, parentURI='')
                print(propMessages)
                print(propCounts)
