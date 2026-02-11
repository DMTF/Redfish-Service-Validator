# Copyright Notice:
# Copyright 2016-2025 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

"""
Schema Pack

File : schema_pack.py

Brief : This file contains the definitions and functionalities for managing
        the schema cache.
"""

import os
import json
import requests
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

from redfish_service_validator import logger

dsp8010_zip_uri = "https://www.dmtf.org/sites/default/files/standards/documents/DSP8010.zip"
dsp8010_zip_version = "https://redfish.dmtf.org/schemas/v1/info.json"
metadata_uri = "/redfish/v1/$metadata"


def update_dsp8010_files(schema_dir, proxies):
    """
    Download schema files from the DMTF site

    Args:
        schema_dir: The local schema repository
        proxies: HTTP proxy information for accessing external sites
    """

    logger.log_print("Checking schema cache against dmtf.org...")

    # Get the current bundle version of the schema files
    current_ver = "0000.0"
    try:
        with open(schema_dir + os.path.sep + "info.json") as info_file:
            info_contents = json.load(info_file)
            current_ver = info_contents["version"]
            logger.info("Current schema cache version: {}".format(current_ver))
    except:
        # File not present or parsable; redownload
        logger.info("No local schema cache version found.")
        pass

    # Get the current version posted on the DMTF website
    dmtf_ver = "0000.0"
    try:
        response = requests.get(dsp8010_zip_version, proxies=proxies)
        if response.status_code != 200:
            logger.critical("Could not access info.json on dmtf.org; HTTP status: {}\n".format(response.status_code))
            return
        else:
            info_contents = json.loads(response.content)
            dmtf_ver = info_contents["version"]
            logger.info("DMTF schema version: {}".format(dmtf_ver))
    except Exception as err:
        logger.critical("Could not access or unpack info.json on dmtf.org; {}\n".format(err))
        return

    # Update the schema pack if the DMTF site has a newer version
    if dmtf_ver > current_ver:
        logger.log_print("New DSP8010 bundle ({}) found on dmtf.org; downloading...\n".format(dmtf_ver))
        try:
            response = requests.get(dsp8010_zip_uri, proxies=proxies)
            if response.status_code != 200:
                logger.critical(
                    "Could not access DSP8010.zip on dmtf.org; HTTP status: {}\n".format(response.status_code)
                )
                return
            zf = zipfile.ZipFile(BytesIO(response.content))
            zf.testzip()
            for name in zf.namelist():
                if ".xml" in name or "info.json" in name:
                    item = zf.open(name)
                    with open(schema_dir + os.path.sep + name.split("/")[-1], "wb") as f:
                        f.write(item.read())
                    item.close()
            zf.close()
        except Exception as err:
            logger.critical("Could not access or unpack DSP8010.zip on dmtf.org; {}\n".format(err))
            return
    else:
        logger.log_print("Cached DSP8010 up to date ({})\n".format(current_ver))


def update_service_metadata(schema_dir, redfish_obj, proxies):
    """
    Download schema files from the DMTF site

    Args:
        schema_dir: The local schema repository
        redfish_obj: The Redfish object for accessing the service
        proxies: HTTP proxy information for accessing external sites
    """

    logger.log_print("Checking schema cache against the service...")

    # Get $metadata from the service
    uri = metadata_uri
    root = None
    try:
        response = redfish_obj.get(metadata_uri)
        if response.status != 200:
            logger.critical("Could not access {}; HTTP status: {}\n".format(metadata_uri, response.status))
            return
        else:
            root = ET.fromstring(response.text)
    except Exception as err:
        logger.critical("Could not access or unpack {}; {}\n".format(metadata_uri, err))
        return

    # Go through each reference and download the file, if needed
    for reference in root:
        if not reference.tag.endswith("Reference"):
            continue
        schema_uri = reference.attrib.get("Uri", None)
        if schema_uri is None:
            # Shouldn't happen... Just in case...
            continue
        if "docs.oasis-open.org" in schema_uri:
            # Skip OData schemas
            continue

        filename = schema_uri.split("/")[-1]
        if os.path.isfile(schema_dir + os.path.sep + filename):
            # Skip files that are already cached
            # TODO: May want to consider adding logic to see if the schema cache needs an updated copy
            continue

        # Download and save the file
        logger.log_print("Downloading {}...".format(schema_uri))
        try:
            if schema_uri.startswith("/"):
                # Local file; use the Redfish object with auth to the service
                response = redfish_obj.get(schema_uri)
                status = response.status
            else:
                # Remote file; use requests
                response = requests.get(schema_uri, proxies=proxies, verify=False)
                status = response.status_code
            if status != 200:
                logger.critical("Could not access {}; HTTP status: {}".format(schema_uri, status))
            else:
                with open(schema_dir + os.path.sep + filename, "w") as f:
                    f.write(response.text)
        except Exception as err:
            logger.critical("Could not access or unpack {}; {}".format(schema_uri, err))

    logger.log_print("Done checking schemas from the service\n")
