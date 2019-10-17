# Copyright Notice:
# Copyright 2016-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import re
import traverseService as rst


"""
 Power.1.1.1.Power , Power.v1_0_0.Power
"""

versionpattern = 'v[0-9]_[0-9]_[0-9]'


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
