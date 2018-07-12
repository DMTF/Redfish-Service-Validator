
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

import rfSchema
import traverseService as rst
from bs4 import BeautifulSoup

rsvLogger = rst.getLogger()
rsvLogger.disabled = True

class SchemaTest(TestCase):

    """
    Tests for functions setup_operation() and run_systems_operation()
    """
    def test_no_test(self):
        self.assertTrue(True,'Huh?')
        
    def test_get_reference_details(self):
        with open('tests/testdata/Chassis_v1.xml') as f:
            example_soup = BeautifulSoup(f, "xml")

        genrefs = rfSchema.getReferenceDetails(example_soup)

        maintag = example_soup.find("edmx:Edmx", recursive=False)
        reftags = maintag.find_all('edmx:Reference', recursive=False)
        includes = [i for ref in reftags for i in ref.find_all('edmx:Include', recursive=False)]

        self.assertTrue(len(includes) == len(genrefs), 'ok')


