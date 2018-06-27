"""
 Power.1.1.1.Power , Power.v1_0_0.Power
"""

versionpattern = 'v[0-9]_[0-9]_[0-9]'

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
    return re.search(versionpattern, item).group()


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
