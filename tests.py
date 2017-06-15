
# Copyright Notice:
# Copyright 2017 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Usecase-Checkers/LICENSE.md
#
# Unit tests for RedfishServiceValidator.py
#

from unittest import TestCase
from unittest import mock
import datetime

import RedfishServiceValidator as rsv

class ValidatorTest(TestCase):

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
            minx, maxx = rang
            paramPass = rsv.validateNumber("TestNum", num,  minx, maxx)
            self.assertTrue(paramPass,'This number has failed, {} {}'.format(num,  (minx, maxx)))

    def test_validate_int(self):
        empty = (None, None)
        numbers = [0, 10000, 20, 20, 23e-1, 23.0]
        ranges = [empty, empty, (0, None), (None, 21), empty, empty] 
        for num, rang in zip(numbers, ranges):
            minx, maxx = rang
            paramPass = rsv.validateInt("TestNum", num,  minx, maxx)
            self.assertTrue(paramPass == isinstance(num, int),'This number has failed, {} {}'.format(num,  (minx, maxx)))
    
    def test_validate_string(self):
        name, string, pattern = "tst", "TestString", None
        self.assertTrue(rsv.validateString(name, string, pattern),'This string/pattern has failed, {} {}'.format(string,pattern))
        name, string, pattern = "tst", "Test_String", "Test.String"
        self.assertTrue(rsv.validateString(name, string, pattern),'This string/pattern has failed, {} {}'.format(string,pattern))
        name, string, pattern = "tst", "100.97.143.52", "^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
        self.assertTrue(rsv.validateString(name, string, pattern),'This string/pattern has failed, {} {}'.format(string,pattern))
    
    def test_validate_badstring(self):
        name, string, pattern = "tst", 1, None
        self.assertFalse(rsv.validateString(name, string, pattern),'This string/pattern has failed, {} {}'.format(string,pattern))
        name, string, pattern = "tst", "Test__String", "Test.String"
        self.assertFalse(rsv.validateString(name, string, pattern),'This string/pattern has failed, {} {}'.format(string,pattern))
    
    def test_validate_datetime(self):
        name, string = 'date', "2017-05-11T16:30:46-05:00"
        self.assertTrue(rsv.validateDatetime(name, string),'This datetime has failed: {}'.format(string))
        name, string = 'baddate', "baddate"
        self.assertFalse(rsv.validateDatetime(name, string),'This datetime has failed: {}'.format(string))
         
    def test_validate_guid(self):
        name, string = 'guid', "deadb33f-0048-3310-8039-01004f003432" 
        self.assertTrue(rsv.validateGuid(name, string),'This guid has failed: {}'.format(string))
        name, string = 'badguid', "badguid"
        self.assertFalse(rsv.validateGuid(name, string),'This guid has failed: {}'.format(string))
    
    def test_validate_enum(self):
        enums = ['OK','Not OK']
        name, string = 'enum', 'OK'
        self.assertTrue(rsv.validateEnum(name, string, enums),'This enum has failed: {} {}'.format(string, enums))
        name, string = 'enum', 'Not OK'
        self.assertTrue(rsv.validateEnum(name, string, enums),'This enum has failed: {} {}'.format(string, enums))
        name, string = 'badenum', 'DNE'
        self.assertFalse(rsv.validateEnum(name, string, enums),'This enum has failed: {} {}'.format(string, enums))
        name, string = 'badenum', 'Ok'
        self.assertFalse(rsv.validateEnum(name, string, enums),'This enum has failed: {} {}'.format(string, enums))
    
    def test_validate_denum(self):
        enums = ['OK','Not OK']
        name, string = 'enum', 'OK'
        self.assertTrue(rsv.validateDeprecatedEnum(name, string, enums),'This enum has failed: {} {}'.format(string, enums))
        name, string = 'enum', [{'Member':'Not OK'}]
        self.assertTrue(rsv.validateDeprecatedEnum(name, string, enums),'This enum has failed: {} {}'.format(string, enums))
        name, string = 'badenum', 'DNE'
        self.assertFalse(rsv.validateDeprecatedEnum(name, string, enums),'This enum has failed: {} {}'.format(string, enums))
        name, string = 'badenum', [{'Member':'Ok'}]
        self.assertFalse(rsv.validateDeprecatedEnum(name, string, enums),'This enum has failed: {} {}'.format(string, enums))
    
    def test_validate_complex(self):
        self.assertTrue(True,'Huh?')
    
    def test_validate_entity(self):
        self.assertTrue(True,'Huh?')
    
