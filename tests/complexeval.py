# Copyright Notice:
# Copyright 2017-2018 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md
#
# Unit tests for RedfishServiceValidator.py
#

from unittest import TestCase
from unittest import mock
from collections import Counter, OrderedDict
import datetime
import sys

sys.path.append('../')

import json
import traverseService as rst
import RedfishServiceValidator as rsv
from bs4 import BeautifulSoup

rsvLogger = rst.getLogger()
rsvLogger.disabled = False
rst.config['metadatafilepath'] = './tests/testdata/schemas'

class ValidatorTest(TestCase):
    """
    Tests for functions setup_operation() and run_systems_operation()
    """
    def printResult(self, results, columns):
        length = len(columns)
        fstring = ' '.join(['{:12.10}' for x in range(length)])
        print(fstring.format(*columns))
        for x in results:
            print(fstring.format(str(x), *[str(l) for l in results[x][:5]]))

    def test_example(self):
        with open('tests/testdata/payloads/simple.json') as f:
            example_json = json.load(f)

        rsc = rst.ResourceObj('test', 'test', example_json, None, None, None, False)
        allM, allC = {}, Counter()
        for prop in rsc.getResourceProperties():
            propMessages, propCounts = rsv.checkPropertyConformance(rsc.schemaObj, prop.name, prop, rsc.jsondata, parentURI='')
            allM.update(propMessages)
            allC.update(propCounts)
        self.printResult(allM, ['Name', 'Item', 'Type', 'Exists', 'Result'])
        print(allC)

    def test_example_bad(self):
        with open('tests/testdata/payloads/simple_bad.json') as f:
            example_json = json.load(f)

        rsc = rst.ResourceObj('test', 'test', example_json, None, None, None, False)
        allM, allC = {}, Counter()
        for prop in rsc.getResourceProperties():
            propMessages, propCounts = rsv.checkPropertyConformance(rsc.schemaObj, prop.name, prop, rsc.jsondata, parentURI='')
            allM.update(propMessages)
            allC.update(propCounts)
        self.printResult(allM, ['Name', 'Item', 'Type', 'Exists', 'Result'])
        print(allC)

    def test_example_complex(self):
        with open('tests/testdata/payloads/simple_complex.json') as f:
            example_json = json.load(f)

        rsc = rst.ResourceObj('test', 'test', example_json, None, None, None, False)
        allM, allC = {}, Counter()
        for prop in rsc.getResourceProperties():
            propMessages, propCounts = rsv.checkPropertyConformance(rsc.schemaObj, prop.name, prop, rsc.jsondata, parentURI='')
            allM.update(propMessages)
            allC.update(propCounts)
        self.printResult(allM, ['Name', 'Item', 'Type', 'Exists', 'Result'])
        print(allC)
