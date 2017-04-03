import unittest
import RedfishServiceValidator as rsv
from bs4 import BeautifulSoup


class TestDMTF(unittest.TestCase):
    
    # TODO: a myriad of tests, for example:
        # callResourceURI on fakeHTTP requests
        # getSchemaDetails on fake HTTP requests
        # getEntityTypeDetails on dmtf server
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
