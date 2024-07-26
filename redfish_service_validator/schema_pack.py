# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import argparse
import os
import logging
from io import BytesIO
import zipfile
import requests

# live_zip_uri = 'http://redfish.dmtf.org/schemas/DSP8010_2021.1.zip'
live_zip_uri = 'https://www.dmtf.org/sites/default/files/standards/documents/DSP8010.zip' 

my_logger = logging.getLogger()

def setup_schema_pack(uri, local_dir, http_proxy='', https_proxy=''):
    proxies, timeout = None, 20
    if http_proxy != '' or https_proxy != '':
        proxies = {}
        if http_proxy != '': proxies['http'] = http_proxy
        if https_proxy != '': proxies['https'] = https_proxy
    if uri == 'latest':
        uri = live_zip_uri
    my_logger.info('Unpacking schema pack... {}'.format(uri))
    try:
        if not os.path.isdir(local_dir):
            os.makedirs(local_dir)
        response = requests.get(uri, timeout=timeout, proxies=proxies)
        expCode = [200]
        elapsed = response.elapsed.total_seconds()
        statusCode = response.status_code
        my_logger.debug('{}, {}, {},\nTIME ELAPSED: {}'.format(statusCode,
                                                                        expCode, response.headers, elapsed))
        if statusCode in expCode:
            if not zipfile.is_zipfile(BytesIO(response.content)):
                my_logger.error('This URL did not return a valid zipfile')
                pass
            else:
                zf = zipfile.ZipFile(BytesIO(response.content))
                zf.testzip()
                for name in zf.namelist():
                    if '.xml' in name:
                        cpath = '{}/{}'.format(local_dir, name.split('/')[-1])
                        my_logger.debug((name, cpath))
                        item = zf.open(name)
                        with open(cpath, 'wb') as f:
                            f.write(item.read())
                        item.close()
                zf.close()
    except Exception as ex:
        my_logger.error("A problem when getting resource has occurred {}".format(uri))
        my_logger.warning("output: ", exc_info=True)
    return True


if __name__ == '__main__':
    argget = argparse.ArgumentParser(description='Acquire schema_pack from DMTF website')

    # config
    argget.add_argument('--source', type=str, default=live_zip_uri, help='URL of the given schemapack, if unspecified, always grab latest')
    argget.add_argument('--schema_directory', type=str, default='./SchemaFiles/metadata', help='directory for local schema files')

    args = argget.parse_args()

    setup_schema_pack(args.source, args.schema_directory)
