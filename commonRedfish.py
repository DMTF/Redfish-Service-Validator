# ex: #Power.1.1.1.Power , #Power.v1_0_0.Power

versionpattern = 'v[0-9]_[0-9]_[0-9]'
def getNamespace(string):
    if '#' in string:
        string = string.rsplit('#', 1)[1]
    return string.rsplit('.', 1)[0]

def getVersion(string):
    return re.search(versionpattern, item).group()


def getNamespaceUnversioned(string):
    if '#' in string:
        string = string.rsplit('#', 1)[1]
    return string.split('.', 1)[0]
    
    # alt version concatenation, unused
    version = getVersion(string) 
    if version not in [None, '']:
        return getNamespace(string)
    return '{}.{}'.format(getNamespace(string), version)


def getType(string):
    if '#' in string:
        string = string.rsplit('#', 1)[1]
    return string.rsplit('.', 1)[-1]


def createContext(typestring):
    ns_name = getNamespaceUnversioned(typestring)
    type_name = getType(typestring)
    context = '/redfish/v1/$metadata' + '#' + ns_name + '.' + type_name
    return context
