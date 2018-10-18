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
import commonRedfish


class ValidatorTest(TestCase):
    def test_fragment(self):
        commonRedfish.navigateJsonFragment({'Temperatures':[{}]}, "/redfish/v1/x#/Temperatures/0")
        try:
            commonRedfish.navigateJsonFragment({'Temperatures': [{}]}, "/redfish/v1/x#/Temperatures/1")
        except ValueError as e:
            pass
        try:
            commonRedfish.navigateJsonFragment({'Temperatures': 'Ok'}, "/redfish/v1/x#/Temperatures/1")
        except ValueError as e:
            pass
        try:
            commonRedfish.navigateJsonFragment({'Temperatures': [{}]}, "/redfish/v1/x#/Temperatures/ok")
        except ValueError as e:
            pass

    def test_get_type(self):
        pass

