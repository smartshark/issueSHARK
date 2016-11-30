import os
import sys

from setuptools import setup, find_packages

setup(
    name='issueSHARK',
    version='0.1',
    description='Collect data from issue tracking systems',
    install_requires=['requests', 'mongoengine', 'pymongo', 'python-dateutil', 'validate_email'],
    author='Fabian Trautsch',
    author_email='ftrautsch@googlemail.com',
    url='https://github.com/smartshark/issueSHARK',
    test_suite='tests',
    packages=find_packages(),
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

