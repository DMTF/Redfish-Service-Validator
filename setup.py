# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link:
# https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

from setuptools import setup
from codecs import open

with open("README.md", "r", "utf-8") as f:
    long_description = f.read()

setup(
    name="redfish_service_validator",
    version="2.4.9",
    description="Redfish Service Validator",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="DMTF, https://www.dmtf.org/standards/feedback",
    license="BSD 3-clause \"New\" or \"Revised License\"",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Topic :: Communications"
    ],
    keywords="Redfish",
    url="https://github.com/DMTF/Redfish-Protocol-Validator",
    packages=["redfish_service_validator"],
    entry_points={
        'console_scripts': [
            'rf_service_validator=redfish_service_validator.RedfishServiceValidator:main',
            'rf_service_validator_gui=redfish_service_validator.RedfishServiceValidatorGui:main'
        ]
    },
    install_requires=[
      "redfish>=3.1.5",
      "requests",
      "beautifulsoup4>=4.6.0",
      "lxml"
    ]
)
