
import traverseService as rst

@lru_cache(maxsize=64)
def getSchemaDetails(SchemaType, SchemaURI):
    """
    Find Schema file for given Namespace.

    param arg1: Schema Namespace, such as ServiceRoot
    param SchemaURI: uri to grab schema, given LocalOnly is False
    return: (success boolean, a Soup object)
    """
    rst.traverseLogger.debug('getting Schema of {} {}'.format(SchemaType, SchemaURI))

    if SchemaType is None:
        return False, None, None

    if currentService.active and getNamespace(SchemaType) in currentService.metadata.schema_store:
        result = currentService.metadata.schema_store[getNamespace(SchemaType)]
        if result is not None:
            return True, result.soup, result.origin

    config = currentService.config
    LocalOnly, SchemaLocation, ServiceOnly = config['localonlymode'], config['metadatafilepath'], config['servicemode']

    if (SchemaURI is not None and not LocalOnly) or (SchemaURI is not None and '/redfish/v1/$metadata' in SchemaURI):
        # Get our expected Schema file here
        # if success, generate Soup, then check for frags to parse
        #   start by parsing references, then check for the refLink
        if '#' in SchemaURI:
            base_schema_uri, frag = tuple(SchemaURI.rsplit('#', 1))
        else:
            base_schema_uri, frag = SchemaURI, None
        success, data, status, elapsed = callResourceURI(base_schema_uri)
        if success:
            soup = BeautifulSoup(data, "xml")
            # if frag, look inside xml for real target as a reference
            if frag is not None:
                # prefer type over frag, truncated down
                # using frag, check references
                frag = getNamespace(SchemaType)
                frag = frag.split('.', 1)[0]
                refType, refLink = getReferenceDetails(
                    soup, name=base_schema_uri).get(frag, (None, None))
                if refLink is not None:
                    success, linksoup, newlink = getSchemaDetails(refType, refLink)
                    if success:
                        return True, linksoup, newlink
                    else:
                        rst.traverseLogger.error(
                            "SchemaURI couldn't call reference link {} inside {}".format(frag, base_schema_uri))
                else:
                    rst.traverseLogger.error(
                        "SchemaURI missing reference link {} inside {}".format(frag, base_schema_uri))
                    # error reported; assume likely schema uri to allow continued validation
                    uri = 'http://redfish.dmtf.org/schemas/v1/{}_v1.xml'.format(frag)
                    rst.traverseLogger.info("Continue assuming schema URI for {} is {}".format(SchemaType, uri))
                    return getSchemaDetails(SchemaType, uri)
            else:
                return True, soup, base_schema_uri
        if isNonService(base_schema_uri) and ServiceOnly:
            rst.traverseLogger.info("Nonservice URI skipped: {}".format(base_schema_uri))
        else:
            rst.traverseLogger.debug("SchemaURI called unsuccessfully: {}".format(base_schema_uri))
    if LocalOnly:
        rst.traverseLogger.debug("This program is currently LOCAL ONLY")
    if ServiceOnly:
        rst.traverseLogger.debug("This program is currently SERVICE ONLY")
    if not LocalOnly and not ServiceOnly and isNonService(SchemaURI):
        rst.traverseLogger.warn("SchemaURI {} was unable to be called, defaulting to local storage in {}".format(SchemaURI, SchemaLocation))
    return getSchemaDetailsLocal(SchemaType, SchemaURI)


def getSchemaDetailsLocal(SchemaType, SchemaURI):
    # Use local if no URI or LocalOnly
    # What are we looking for?  Parse from URI
    # if we're not able to use URI to get suffix, work with option fallback
    Alias = getNamespace(SchemaType).split('.')[0]
    config = currentService.config
    SchemaLocation, SchemaSuffix = config['metadatafilepath'], config['schemasuffix']
    if SchemaURI is not None:
        uriparse = SchemaURI.split('/')[-1].split('#')
        xml = uriparse[0]
    else:
        rst.traverseLogger.warn("SchemaURI was empty, must generate xml name from type {}".format(SchemaType)),
        return getSchemaDetailsLocal(SchemaType, Alias + SchemaSuffix)
    rst.traverseLogger.debug((SchemaType, SchemaURI, SchemaLocation + '/' + xml))
    pout = Alias + SchemaSuffix if xml is None else xml
    try:
        # get file
        filehandle = open(SchemaLocation + '/' + xml, "r")
        data = filehandle.read()
        filehandle.close()
        # get tags
        soup = BeautifulSoup(data, "xml")
        edmxTag = soup.find('edmx:Edmx', recursive=False)
        parentTag = edmxTag.find('edmx:DataServices', recursive=False)
        child = parentTag.find('Schema', recursive=False)
        SchemaNamespace = child['Namespace']
        FoundAlias = SchemaNamespace.split(".")[0]
        rst.traverseLogger.debug(FoundAlias)
        if '/redfish/v1/$metadata' in SchemaURI:
            if len(uriparse) > 1:
                frag = getNamespace(SchemaType)
                frag = frag.split('.', 1)[0]
                refType, refLink = getReferenceDetails(
                    soup, name=SchemaLocation+'/'+pout).get(frag, (None, None))
                if refLink is not None:
                    rst.traverseLogger.debug('Entering {} inside {}, pulled from $metadata'.format(refType, refLink))
                    return getSchemaDetails(refType, refLink)
                else:
                    rst.traverseLogger.error('Could not find item in $metadata {}'.format(frag))
                    return False, None, None
            else:
                return True, soup, "local" + SchemaLocation + '/' + pout
        if FoundAlias in Alias:
            return True, soup, "local" + SchemaLocation + '/' + pout
    except FileNotFoundError as ex:
        # if we're looking for $metadata locally... ditch looking for it, go straight to file
        if '/redfish/v1/$metadata' in SchemaURI and Alias != '$metadata':
            rst.traverseLogger.warn("Unable to find a harddrive stored $metadata at {}, defaulting to {}".format(SchemaLocation, Alias + SchemaSuffix))
            return getSchemaDetailsLocal(SchemaType, Alias + SchemaSuffix)
        else:
            rst.traverseLogger.warn
            (
                "Schema file {} not found in {}".format(pout, SchemaLocation))
            if Alias == '$metadata':
                rst.traverseLogger.warn(
                    "If $metadata cannot be found, Annotations may be unverifiable")
    except Exception as ex:
        rst.traverseLogger.error("A problem when getting a local schema has occurred {}".format(SchemaURI))
        rst.traverseLogger.warn("output: ", exc_info=True)
    return False, None, None


def check_redfish_extensions_alias(name, item):
    """
    Check that edmx:Include for Namespace RedfishExtensions has the expected 'Redfish' Alias attribute
    :param name: the name of the resource
    :param item: the edmx:Include item for RedfishExtensions
    :return:
    """
    alias = item.get('Alias')
    if alias is None or alias != 'Redfish':
        msg = ("In the resource {}, the {} namespace must have an alias of 'Redfish'. The alias is {}. " +
               "This may cause properties of the form [PropertyName]@Redfish.TermName to be unrecognized.")
        rst.traverseLogger.error(msg.format(name, item.get('Namespace'),
                             'missing' if alias is None else "'" + str(alias) + "'"))


def getReferenceDetails(soup, metadata_dict=None, name='xml'):
    """
    Create a reference dictionary from a soup file

    param arg1: soup
    param metadata_dict: dictionary of service metadata, compare with
    return: dictionary
    """
    refDict = {}

    maintag = soup.find("edmx:Edmx", recursive=False)
    refs = maintag.find_all('edmx:Reference', recursive=False)
    for ref in refs:
        includes = ref.find_all('edmx:Include', recursive=False)
        for item in includes:
            if item.get('Namespace') is None or ref.get('Uri') is None:
                rst.traverseLogger.error("Reference incorrect for: {}".format(item))
                continue
            if item.get('Alias') is not None:
                refDict[item['Alias']] = (item['Namespace'], ref['Uri'])
            else:
                refDict[item['Namespace']] = (item['Namespace'], ref['Uri'])
            # Check for proper Alias for RedfishExtensions
            if name == '$metadata' and item.get('Namespace').startswith('RedfishExtensions.'):
                check_redfish_extensions_alias(name, item)

    cntref = len(refDict)
    if metadata_dict is not None:
        refDict.update(metadata_dict)
    rst.traverseLogger.debug("References generated from {}: {} out of {}".format(name, cntref, len(refDict)))
    return refDict


class rfSchema:
    def __init__(self, soup, context, origin, metadata=None, name='xml'):
        self.soup = soup
        self.refs = getReferenceDetails(soup, metadata, name)
        self.context = context 
        self.origin = origin
        self.name = name

    def getSchemaFromReference(self, namespace):
        tup = self.refs.get(namespace)
        tupVersionless = self.refs.get(getNamespace(namespace))
        if tup is None:
            if tupVersionless is None:
                rst.traverseLogger.warn('No such reference {} in {}'.format(namespace, self.origin))
                return None
            else:
                tup = tupVersionless
                rst.traverseLogger.warn('No such reference {} in {}, using unversioned'.format(namespace, self.origin))
        typ, uri = tup
        newSchemaObj = getSchemaObject(typ, uri)
        return newSchemaObj

    def getTypeTagInSchema(self, currentType, tagType):
        pnamespace, ptype = getNamespace(currentType), getType(currentType)
        soup = self.soup

        currentSchema = soup.find(  # BS4 line
            'Schema', attrs={'Namespace': pnamespace})

        if currentSchema is None:
            return None 

        currentEntity = currentSchema.find(tagType, attrs={'Name': ptype}, recursive=False)  # BS4 line

        return currentEntity

    def getParentType(self, currentType, tagType=['EntityType', 'ComplexType']):
        currentType = currentType.replace('#', '')
        typetag = self.getTypeTagInSchema(currentType, tagType)
        if typetag is not None: 
            currentType = typetag.get('BaseType')
            if currentType is None:
                return False, None, None
            typetag = self.getTypeTagInSchema(currentType, tagType)
            if typetag is not None: 
                return True, self, currentType
            else:
                namespace = getNamespace(currentType)
                schemaObj = self.getSchemaFromReference(namespace)
                if schemaObj is None: 
                    return False, None, None
                propSchema = schemaObj.soup.find(  
                    'Schema', attrs={'Namespace': namespace})
                if propSchema is None:
                    return False, None, None
                return True, schemaObj, currentType 
        else:
            return False, None, None

    def getHighestType(self, acquiredtype):
        typesoup = self.soup
        typelist = list()
        for schema in typesoup.find_all('Schema'):
            newNamespace = schema.get('Namespace')
            typelist.append((newNamespace, schema))
        for ns, schema in reversed(sorted(typelist)):
            rst.traverseLogger.debug(
                "{}   {}".format(ns, getType(acquiredtype)))
            if schema.find(['EntityType', 'ComplexType'], attrs={'Name': getType(acquiredtype)}, recursive=False):
                acquiredtype = ns + '.' + getType(acquiredtype)
                break
        return acquiredtype


def getSchemaObject(typename, uri, metadata=None):

    result = getSchemaDetails(typename, uri)
    success, soup = result[0], result[1]
    origin = result[2]


    if success is False:
        return None
    return rfSchema(soup, uri, origin, metadata=metadata, name=typename) 

