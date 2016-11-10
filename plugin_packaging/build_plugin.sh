#!/bin/bash

current=`pwd`
mkdir -p /tmp/issueSHARK/
cp -R ../issueshark /tmp/issueSHARK/
cp ../setup.py /tmp/issueSHARK/
cp ../main.py /tmp/issueSHARK
cp ../loggerConfiguration.json /tmp/issueSHARK
cp * /tmp/issueSHARK/
cd /tmp/issueSHARK/

tar -cvf "$current/issueSHARK_plugin.tar" --exclude=*.tar --exclude=build_plugin.sh --exclude=*/tests --exclude=*/__pycache__ --exclude=*.pyc *
