import unittest
import RedfishServiceValidator as rsv
from bs4 import BeautifulSoup


class TestDMTF(unittest.TestCase):
    
    def test_namespace_type(self):
        ex = '#Power.v1_0_0.PowerType'
        resultSpace = rsv.getNamespace(ex)
        resultType = rsv.getType(ex)
        self.assertEqual(resultSpace,'Power.v1_0_0')
        self.assertEqual(resultType,'PowerType')

    def test_entitytypedetails(self):
        xml = '\
            <?xml version="1.0" encoding="UTF-8"?>\
            <edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">\
              <edmx:DataServices>\
                <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="Example">\
                  <EntityType Name="Example" BaseType="Resource.v1_0_0.Resource" Abstract="true"\
                  </EntityType>\
                </Schema>\
                <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="Example.v1_0_0">  \
                  <EntityType Name="Example" BaseType="Example.Example">\
                  </EntityType>\
                </Schema>\
              </edmx:DataServices>\
            </edmx:Edmx>'
        soup = BeautifulSoup(xml, "html.parser")
        listType = rsv.getTypeDetails(soup, {'Resource': ('Resource','http://redfish.dmtf.org/schemas/v1/Resource_v1.xml')}, '#Example.v1_0_0.Example','entitytype')
        self.assertEqual(listType, ['Resource.Item:Oem', 'Resource.v1_0_0.Resource:Id', 'Resource.v1_0_0.Resource:Description', 'Resource.v1_0_0.Resource:Name'])
        

    # TODO: a myriad of tests, for example:
    # callResourceURI on fakeHTTP requests
    # getSchemaDetails on fake HTTP requests
    # getTypeDetails on dmtf server
    # getPropertyDetails on one particular property
    # getEnumTypeDetails on one particular property
    # checkPropertyCompliance on easily testable properti
    # getLinkDetails on fake HTTP requests
    # above tests is just one leve of validateURI
    # ... in order to make this a "unit test",
    # each test must be agnostic to each other
    pass

if __name__ == '__main__':
    unittest.main()
