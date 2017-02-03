==========
issueSHARK
==========

.. image:: https://travis-ci.org/smartshark/pycoSHARK.svg?branch=master
    :target: https://travis-ci.org/smartshark/pycoSHARK

============
Introduction
============

This introduction will show the requirements of **issueSHARK** , how it is installed, tested, and executed. Furthermore,
a small tutorial in the end will show step by step, how to use this tool.

In contrast to, e.g., `Bicho <https://github.com/MetricsGrimoire/Bicho>`_ from MetricsGrimoire, we divide the collected
data strictly into static and dynamic data. Static data is not changing anymore, regardless of how often issueSHARK
is executed (e.g., creation time of the issue). Dynamic data can change over time, e.g., the title of an issue can
change and new events or comments can be made on the issue. Therefore, we store the data in three steps:

1. gather issues, together with their change events and comments
2. rewind the issue by applying the opposite of the change events to get the original issue
3. store the original issue, all change events and comments.


We use a vanilla Ubuntu 16.04 operating system as basis for the steps that we describe. If necessary, we give hints
on how to perform this step with a different operating system.


.. WARNING:: This software is still in development.



Model Documentation
===================
The documentation for the used database models can be found here: https://smartshark.github.io/pycoSHARK/api.html


.. _installation:

Installation
============
The installation process is straight forward. For a vanilla Ubuntu 16.04, we need to install the following packages:

.. code-block:: bash

	$ sudo apt-get install git python3-pip python3-cffi


Furthermore, you need a running MongoDB. The process of setting up a MongoDB is
explained here: https://docs.mongodb.com/manual/installation/


After these requirements are met, first clone the **issueSHARK**
`repository <https://github.com/smartshark/issueSHARK/>`_ repository to a folder you want. In the following, we assume
that you have cloned the repository to **~/issueSHARK**. Afterwards,
the installation of **issueSHARK** can be done in two different ways:

via Pip
-------
.. code-block:: bash

	$ sudo pip3 install https://github.com/smartshark/issueSHARK/zipball/master --process-dependency-links

via setup.py
------------
.. code-block:: bash

	$ sudo python3.5 ~/issueSHARK/setup.py install



.. NOTE::
	It is advisable to change the location, where the logs are written to.
	They can be changed in the **loggerConfiguration.json**. There are different file handlers defined.
	Just change the "filename"-attribute to a location of your wish.


Tests
=====
The tests of **issueSHARK** can be executed by calling

	.. code-block:: bash

		$ python3.5 ~/vcsSHARK/setup.py test

The tests can be found in the folder "tests".

.. WARNING:: The generated tests are not fully complete. They just test the basic functionality.


Execution
==========
In this chapter, we explain how you can execute **issueSHARK**. Furthermore, the different execution parameters are
explained in detail.

1) Checkout the repository from which you want to collect the data.

2) Make sure that your MongoDB is running!

	.. code-block:: bash

		$ sudo systemctl status mongodb

3) Make sure that the project from which you collect data is already in the project collection of the MongoDB. If not,
you can add them by:

	.. code-block:: bash

		$ db.project.insert({"name": <PROJECT_NAME>})


4) Execute **issueSHARK** by calling

	.. code-block:: bash

		$ python3.5 ~/issueSHARK/main.py


**issueSHARK** supports different commandline arguments:

--help, -h: shows the help page for this command

--version, -v: shows the version

--db-user <USER>, -U <USER>: mongodb user name; Default: None

--db-password <PASSWORD>, -P <PASSWORD>: mongodb password; Default: None

--db-database <DATABASENAME>, -DB <DATABASENAME>: database name; Default: smartshark

--db-hostname <HOSTNAME>, -H <HOSTNAME>: hostname, where the mongodb runs on; Default: localhost

--db-port <PORT>, -p <PORT>: port, where the mongodb runs on; Default: 27017

--db-authentication <DB_AUTHENTICATION> -a <DB_AUTHENTICATION>: name of the authentication database; Default: None

--debug <DEBUG_LEVEL>, -d <DEBUG_LEVEL>: Debug level (INFO, DEBUG, WARNING, ERROR); Default: DEBUG

--project-name <PROJECT_NAME>: Name of the project, from which the data is collected; Required

--issueurl <URL>, -i <URL>: URL to the bugtracking system; Required

	.. WARNING::
		See in the Section IssueURLs, how they need to be defined!

--token <TOKEN>, -t <TOKEN>: Token to use for accessing the ITS (e.g., `github token <https://github.com/blog/1509-personal-api-tokens>`_); Default: None

--backend  <BACKENDNAME>, -b <BACKENDNAME>: Backend to use for the issue parsing; Required

--issue-user <ISSUEUSER>, -iU <ISSUEUSER>: Username to use the issue tracking system; Default: None

--issue-password <ISSUEPASSWORD>, -iP <ISSUEPASSWORD>: Password to use the issue tracking system; Default: None

--proxy-host <PROXYHOST>, -PH <PROXYHOST>: Proxy hostname or IP address; Default: None

--proxy-port <PROXYPORT>, -PP <PROXYPORT>: Port of the proxy to use; Default: None

--proxy-password <PROXYPASSWORD>, -Pp <PROXYPASSWORD>: Password to use the proxy (HTTP Basic Auth); Default: None

--proxy-user <PROXYUSER>, -PU <PROXYUSER>: Username to use the proxy (HTTP Basic Auth); Default: None


.. _IssueURLs:

Issue URLs
----------
The issue urls must be given to issueSHARK in a specific form.

For **github**: Directly pointing to the github issues api of the project. For example:
https://api.github.com/repos/composer/composer/issues

For **jira**: Directly pointing to the rest api and putting the project name into the jql search string. For example:
https://issues.apache.org/jira/rest/api/2/search?jql=project=ZOOKEEPER

For **bugzilla**: Directly pointing to the rest api (bug endpoint) and putting the product as get parameter behind it.
For example: https://bz.apache.org/bugzilla/rest.cgi/bug?product=Ant

Tutorial
========

In this section we show step-by-step how you can collect issue tracking system data from the project
`Zookeeper <https://zookeeper.apache.org/>`_ and store the data in a mongodb.

1.	First, if you need to have a mongodb running (version 3.2+).
How this can be achieved is explained here: https://docs.mongodb.org/manual/.

.. WARNING::
	Make sure, that you activated the authentication of mongodb
	(**issueSHARK** also works without authentication, but with authentication it is much safer!).
	Hints how this can be achieved are given `here <https://docs.mongodb.org/manual/core/authentication/>`_.

2. Add Zookeeper to the projects table in MongoDB.

	.. code-block:: bash

		$ mongo
		$ use smartshark
		$ db.project.insert({"name": "Zookeeper"})

3. Install **issueSHARK**. An explanation is given above.

3. Enter the **issueSHARK** directory via

	.. code-block:: bash

		$ cd issueSHARK

4. Test if everything works as expected

	.. code-block:: bash

		$ python3.5 main.py --help

	.. NOTE:: If you receive an error here, it is most likely, that the installation process failed.

5. Execute **issueSHARK**:

	.. code-block:: bash

		$ cd ~/issueSHARK
		$ python3.5 main.py --backend jira --project-name Zookeeper --issueurl https://issues.apache.org/jira/rest/api/2/search?jql=project=ZOOKEEPER --issue-user <user> --issue-password <password>

	.. NOTE:: If you do not have an JIRA account for the Apache project, you can create it here: https://issues.apache.org/jira/secure/Signup!default.jspa

Thats it. The results are explained in the database documentation
of `SmartSHARK <http://smartshark2.informatik.uni-goettingen.de/documentation/>`_.

