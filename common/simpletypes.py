# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import re
import logging

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)

def validateDeprecatedEnum(name: str, val, listEnum: list):
    """validateDeprecatedEnum

    Validates a DeprecatedEnum

    :param name: Name of property (printing purposes) Property Name
    :type name: str
    :param val: Value for a given property
    :param listEnum: List of expected enum values
    :type listEnum: list
    """
    paramPass = True
    if isinstance(val, list):
        display_val = []
        for enumItem in val:
            display_val.append(dict(enumItem))
            for k, v in enumItem.items():
                paramPass = paramPass and str(v) in listEnum
        if not paramPass:
            my_logger.error("{}: Invalid DeprecatedEnum value '{}' found, expected {}"
                            .format(str(name), display_val, str(listEnum)))
    elif isinstance(val, str):
        paramPass = str(val) in listEnum
        if not paramPass:
            my_logger.error("{}: Invalid DeprecatedEnum value '{}' found, expected {}"
                            .format(str(name), val, str(listEnum)))
    else:
        my_logger.error("{}: Expected list or string value for DeprecatedEnum, got {}".format(str(name), str(type(val)).strip('<>')))
    return paramPass


def validateEnum(name: str, val, listEnum: list):
    """validateEnum

    Validate an enum value

    :param name: Name of property (printing purposes)
    :type name: str
    :param val: Value for a given property
    :param listEnum: List of expected enum values
    :type listEnum: list
    """
    paramPass = isinstance(val, str)
    if paramPass:
        paramPass = val in listEnum
        if not paramPass:
            my_logger.error("{}: Invalid Enum value '{}' found, expected {}".format(str(name), val, str(listEnum)))
    else:
        my_logger.error("{}: Expected string value for Enum, got {}".format(str(name), str(type(val)).strip('<>')))
    return paramPass



