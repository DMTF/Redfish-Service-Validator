#!/usr/bin/env python3
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link:
# https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import sys
import logging
from redfish_service_validator.RedfishServiceValidator import main

my_logger = logging.getLogger('rsv')
my_logger.setLevel(logging.DEBUG)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        my_logger.exception("Program finished prematurely: %s", e)
        raise
