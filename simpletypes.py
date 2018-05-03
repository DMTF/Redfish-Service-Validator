
# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import re
import traverseService as rst

rsvLogger = rst.getLogger()

def validateDeprecatedEnum(name, val, listEnum):
    """
    Validates a DeprecatedEnum
    """
    paramPass = True
    if isinstance(val, list):
        display_val = []
        for enumItem in val:
            display_val.append(dict(enumItem))
            for k, v in enumItem.items():
                paramPass = paramPass and str(v) in listEnum
        if not paramPass:
            rsvLogger.error("{}: Invalid DeprecatedEnum value '{}' found, expected {}"
                            .format(str(name), display_val, str(listEnum)))
    elif isinstance(val, str):
        paramPass = str(val) in listEnum
        if not paramPass:
            rsvLogger.error("{}: Invalid DeprecatedEnum value '{}' found, expected {}"
                            .format(str(name), val, str(listEnum)))
    else:
        rsvLogger.error("{}: Expected list or string value for DeprecatedEnum, got {}".format(str(name), str(type(val)).strip('<>')))
    return paramPass


def validateEnum(name, val, listEnum):
    paramPass = isinstance(val, str)
    if paramPass:
        paramPass = val in listEnum
        if not paramPass:
            rsvLogger.error("{}: Invalid Enum value '{}' found, expected {}".format(str(name), val, str(listEnum)))
    else:
        rsvLogger.error("{}: Expected string value for Enum, got {}".format(str(name), str(type(val)).strip('<>')))
    return paramPass


def validateString(name, val, pattern=None):
    """
    Validates a string, given a value and a pattern
    """
    paramPass = isinstance(val, str)
    if paramPass:
        if pattern is not None:
            match = re.fullmatch(pattern, val)
            paramPass = match is not None
            if not paramPass:
                rsvLogger.error("{}: String '{}' does not match pattern '{}'".format(name, str(val), str(pattern)))
        else:
            paramPass = True
    else:
        rsvLogger.error("{}: Expected string value, got type {}".format(name, str(type(val)).strip('<>')))
    return paramPass


def validateDatetime(name, val):
    """
    Validates a Datetime, given a value (pattern predetermined)
    """
    paramPass = validateString(name, val, '.*(Z|(\+|-)[0-9][0-9]:[0-9][0-9])')
    if not paramPass:
        rsvLogger.error("\t...: Malformed DateTimeOffset")
    return paramPass


def validateGuid(name, val):
    """
    Validates a Guid, given a value (pattern predetermined)
    """
    paramPass = validateString(name, val, "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    if not paramPass:
        rsvLogger.error("\t...: Malformed Guid")
    return paramPass


def validateInt(name, val, minVal=None, maxVal=None):
    """
    Validates a Int, then passes info to validateNumber
    """
    if not isinstance(val, int):
        rsvLogger.error("{}: Expected integer, got type {}".format(name, str(type(val)).strip('<>')))
        return False
    else:
        return validateNumber(name, val, minVal, maxVal)


def validateNumber(name, val, minVal=None, maxVal=None):
    """
    Validates a Number and its min/max values
    """
    paramPass = isinstance(val, (int, float))
    if paramPass:
        if minVal is not None:
            paramPass = paramPass and minVal <= val
            if not paramPass:
                rsvLogger.error("{}: Value out of assigned min range, {} < {}".format(name, str(val), str(minVal)))
        if maxVal is not None:
            paramPass = paramPass and maxVal >= val
            if not paramPass:
                rsvLogger.error("{}: Value out of assigned max range, {} > {}".format(name, str(val), str(maxVal)))
    else:
        rsvLogger.error("{}: Expected integer or float, got type {}".format(name, str(type(val)).strip('<>')))
    return paramPass


def validatePrimitive(name, val):
    """
    Validates a Primitive
    """
    if isinstance(val, (int, float, str, bool)):
        return True
    else:
        rsvLogger.error("{}: Expected primitive type, got type {}".format(name, str(type(val)).strip('<>')))
        return False
