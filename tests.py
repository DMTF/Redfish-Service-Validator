
# Copyright Notice:
# Copyright 2017 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Usecase-Checkers/LICENSE.md
#
# Unit tests for RedfishServiceValidator.py
#

from unittest import TestCase
from unittest import mock

import RedfishServiceValidator as rsv

class OneTimeBootTest(TestCase):

    """
    Tests for functions setup_operation() and run_systems_operation()
    """
    def test_no_test(self):
        self.assertTrue(True,'Huh?')
        
    def test_validate_number(self):
        empty = (None, None)
        numbers = [0, 10000, 20, 20, 23e-1, 23.0, 14.0, 999.0]
        ranges = [empty, empty, (0, None), (None, 21), empty, empty, (0, 15), empty] 
        for num, rang in zip(numbers, ranges):
            if isinstance( num, int):
                typeNum = 'Edm.Int64'
            else:
                typeNum = 'Edm.Decimal'
            minx, maxx = rang
            paramPass = rsv.validateNumber("TestNum", num, typeNum, minx, maxx)
            self.assertTrue(paramPass,'This number has failed, {} {} {}'.format(num, typeNum, (minx, maxx)))
    
    def test_validate_string(self):
        self.assertTrue(True,'Huh?')
    
    def test_validate_date(self):
        self.assertTrue(True,'Huh?')
    
    def test_validate_guid(self):
        self.assertTrue(True,'Huh?')
    
    def test_validate_enum(self):
        self.assertTrue(True,'Huh?')
    
    def test_validate_denum(self):
        self.assertTrue(True,'Huh?')
    
    def test_validate_complex(self):
        self.assertTrue(True,'Huh?')
    
    def test_validate_entity(self):
        self.assertTrue(True,'Huh?')
    
