# Copyright Notice:
# Copyright 2016-2020 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import re
import traverseService as rst


"""
 Power.1.1.1.Power , Power.v1_0_0.Power
"""

versionpattern = 'v[0-9]+_[0-9]+_[0-9]+'


def splitVersionString(version):
    v_payload = version
    if(re.match('([a-zA-Z0-9_.-]*\.)+[a-zA-Z0-9_.-]*', version) is not None):
        new_payload = getVersion(version)
        if new_payload is not None:
            v_payload = new_payload
    if ('_' in v_payload):
        v_payload = v_payload.replace('v', '')
        payload_split = v_payload.split('_')
    else:
        payload_split = v_payload.split('.')
    if len(payload_split) != 3:
        return [0, 0, 0]
    return [int(v) for v in payload_split]


def compareMinVersion(version, min_version):
    """
    Checks for the minimum version of a resource's type
    """
    # If version doesn't contain version as is, try it as v#_#_#
    # get version from payload
    min_split = splitVersionString(min_version)
    payload_split = splitVersionString(version)

    # use array comparison, which compares each sequential number
    return min_split < payload_split

def navigateJsonFragment(decoded, URILink):
    traverseLogger = rst.getLogger()
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
                    traverseLogger.error("This URI ({}) is accessing an array, but this is not an index: {}".format(URILink, item))
                    return None
                if int(item) >= len(decoded):
                    traverseLogger.error("This URI ({}) is accessing an array, but the index is too large for an array of size {}: {}".format(URILink, len(decoded), item))
                    return None
                decoded = decoded[int(item)]
            else:
                traverseLogger.error("This URI ({}) has resolved to an invalid object that is neither an array or dictionary".format(URILink))
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
