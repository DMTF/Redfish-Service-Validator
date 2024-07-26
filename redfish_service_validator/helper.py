# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import re
import logging
from types import SimpleNamespace

# TODO: Replace logger with custom logger with custom verbose levels, remove verbose1 and verbose2 
my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)

"""
 Power.1.1.1.Power , Power.v1_0_0.Power
"""

versionpattern = 'v[0-9]+_[0-9]+_[0-9]+'

LOG_ENTRY = ('name', 'value', 'type', 'exists', 'result')

def create_entry(name, value, type, exists, result):
    return SimpleNamespace(**{
        "name": name,
        "value": value,
        "type": type,
        "exists": exists,
        "result": result
    })


def splitVersionString(v_string):
    """
    Split x.y.z and Namespace.vX_Y_Z, vX_Y_Z type version strings into tuples of integers

    :return: tuple of integers
    """
    if(re.match(r'([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*', v_string) is not None):
        new_string = getVersion(v_string)
        if new_string is not None:
            v_string = new_string
    if ('_' in v_string):
        v_string = v_string.replace('v', '')
        payload_split = v_string.split('_')
    else:
        payload_split = v_string.split('.')
    if len(payload_split) != 3:
        return tuple([0, 0, 0])
    return tuple([int(v) for v in payload_split])


def stripCollection(typename):
    """
    Remove "Collection()" from a type string
    """
    if 'Collection(' in typename:
        typename = typename.replace('Collection(', "").replace(')', "")
    return typename


def navigateJsonFragment(decoded, URILink):
    if '#' in URILink:
        URIfragless, frag = tuple(URILink.rsplit('#', 1))
        fragNavigate = frag.split('/')
        for item in fragNavigate:
            if item == '':
                continue
            if isinstance(decoded, dict):
                decoded = decoded.get(item)
            elif isinstance(decoded, list):
                if not item.isdigit():
                    my_logger.error("This URI ({}) is accessing an array, but this is not an index: {}".format(URILink, item))
                    return None
                if int(item) >= len(decoded):
                    my_logger.error("This URI ({}) is accessing an array, but the index is too large for an array of size {}: {}".format(URILink, len(decoded), item))
                    return None
                decoded = decoded[int(item)]
            else:
                my_logger.error("This URI ({}) has resolved to an invalid object that is neither an array or dictionary".format(URILink))
                return None
    return decoded


def getNamespace(string: str):
    """getNamespace

    Gives namespace of a type string, version included

    :param string:  A type string
    :type string: str
    """
    if '#' in string:
        string = string.rsplit('#', 1)[1]
    return string.rsplit('.', 1)[0]


def getVersion(string: str):
    """getVersion

    Gives version stripped from type/namespace string, if possible

    :param string:  A type/namespace string
    :type string: str
    """
    regcap = re.search(versionpattern, string)
    return regcap.group() if regcap else None


def getNamespaceUnversioned(string: str):
    """getNamespaceUnversioned

    Gives namespace of a type string, version NOT included

    :param string:
    :type string: str
    """
    if '#' in string:
        string = string.rsplit('#', 1)[1]
    return string.split('.', 1)[0]


def getType(string: str):
    """getType

    Gives type of a type string (right hand side)

    :param string:
    :type string: str
    """
    if '#' in string:
        string = string.rsplit('#', 1)[1]
    return string.rsplit('.', 1)[-1]


def createContext(typestring: str):
    """createContext

    Create an @odata.context string from a type string

    :param typestring:
    :type string: str
    """
    ns_name = getNamespaceUnversioned(typestring)
    type_name = getType(typestring)
    context = '/redfish/v1/$metadata' + '#' + ns_name + '.' + type_name
    return context


def checkPayloadConformance(jsondata, uri):
    """
    checks for @odata entries and their conformance
    These are not checked in the normal loop
    """
    info = {}
    decoded = jsondata
    success = True
    for key in [k for k in decoded if '@odata' in k]:
        paramPass = False

        property_name, odata_name = tuple(key.rsplit('@', maxsplit=1))

        if odata_name == 'odata.id':
            paramPass = isinstance(decoded[key], str)
            paramPass = re.match(
                r'(\/.*)+(#([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*)?', decoded[key]) is not None
            if not paramPass:
                my_logger.error("{} {}: Expected format is /path/to/uri, but received: {}".format(uri, key, decoded[key]))
            else:
                if uri != '' and decoded[key] != uri and not (uri == "/redfish/v1/" and decoded[key] == "/redfish/v1"):
                    my_logger.warning("{} {}: Expected @odata.id to match URI link {}".format(uri, key, decoded[key]))
        elif odata_name == 'odata.count':
            paramPass = isinstance(decoded[key], int)
            if not paramPass:
                my_logger.error("{} {}: Expected an integer, but received: {}".format(uri, key, decoded[key]))
        elif odata_name == 'odata.context':
            paramPass = isinstance(decoded[key], str)
            paramPass = re.match(
                r'/redfish/v1/\$metadata#([a-zA-Z0-9_.-]*\.)[a-zA-Z0-9_.-]*', decoded[key]) is not None
            if not paramPass:
                my_logger.warning("{} {}: Expected format is /redfish/v1/$metadata#ResourceType, but received: {}".format(uri, key, decoded[key]))
                info[key] = (decoded[key], 'odata', 'Exists', 'WARN')
                continue
        elif odata_name == 'odata.type':
            paramPass = isinstance(decoded[key], str)
            paramPass = re.match(
                r'#([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*', decoded[key]) is not None
            if not paramPass:
                my_logger.error("{} {}: Expected format is #Namespace.Type, but received: {}".format(uri, key, decoded[key]))
        else:
            paramPass = True

        success = success and paramPass

        info[key] = (decoded[key], 'odata', 'Exists', 'PASS' if paramPass else 'FAIL')
        
    return success, info
