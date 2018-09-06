
import re

"""
 Power.1.1.1.Power , Power.v1_0_0.Power
"""

versionpattern = 'v[0-9]_[0-9]_[0-9]'


def navigateJsonFragment(decoded, URILink):
    if '#' in URILink:
        URILink, frag = tuple(URILink.rsplit('#', 1))
        fragNavigate = frag.split('/')
        for item in fragNavigate:
            if item == '':
                continue
            if isinstance(decoded, dict):
                decoded = decoded.get(item)
            elif isinstance(decoded, list):
                if not item.isdigit():
                    traverseLogger.error("This is an Array, but this is not an index, aborting: {} {}".format(URILink, item))
                    return None
                decoded = decoded[int(item)] if int(item) < len(decoded) else None
        if not isinstance(decoded, dict):
            traverseLogger.error(
                "Decoded object no longer a dictionary {}".format(URILink))
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
