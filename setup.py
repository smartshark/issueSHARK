#!/usr/bin/env python

import sys

from setuptools import setup, find_packages

if not sys.version_info[0] == 3:
    print('only python3 supported!')
    sys.exit(1)

setup(
    name='issueSHARK',
    version='2.0.6',
    author='Fabian Trautsch',
    author_email='trautsch@cs.uni-goettingen.de',
    description='Collect data from issue tracking systems',
    install_requires=['mongoengine', 'pymongo', 'requests>=2.10.0', 
                      'cryptography>=1.3.4', 'python-dateutil', 'validate_email',
                      'jira==2.0.0', 'pycoshark>=1.2.6', 'mock'],
    url='https://github.com/smartshark/issueSHARK',
    download_url='https://github.com/smartshark/issueSHARK/zipball/master',
    packages=find_packages(),
    test_suite ='tests',
    zip_safe=False,
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache2.0 License",
        "Operating System :: POSIX :: Linux",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
