import configparser
import unittest
import os
import datetime

import logging
import json
import jira
import mock
from mongoengine import connect
import mongomock
import mongoengine

from issueshark.backends.jirabackend import JiraBackend
from pycoshark.mongomodels import IssueSystem, Project, Issue, Event, IssueComment, People


class ConfigMock(object):
    def __init__(self, db_user, db_password, db_database, db_hostname, db_port, db_authentication, project_name,
                 issue_url, backend, proxy_host, proxy_port, proxy_user, proxy_password, issue_user, issue_password,
                 debug, token):
        self.db_user = db_user
        self.db_password = db_password
        self.db_database = db_database
        self.db_hostname = db_hostname
        self.db_port = db_port
        self.db_authentication = db_authentication
        self.project_name = project_name
        self.tracking_url = issue_url
        self.identifier = backend
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_user = proxy_user
        self.proxy_password = proxy_password
        self.issue_user = issue_user
        self.issue_password = issue_password
        self.debug = debug
        self.token = token

    def get_debug_level(self):
        return logging.DEBUG

    def get_proxy_dictionary(self):
        return None

    def use_token(self):
        return True


class JiraBackendTest(unittest.TestCase):

    def setUp(self):
        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/jira/drill_1_issue.json", 'r', encoding='utf-8') as drill_1:
            self.issue_drill_1 = json.load(drill_1)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/jira/drill_138_issue.json", 'r', encoding='utf-8') as drill_138:
            self.issue_drill_138 = json.load(drill_138)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/jira/drill_38_issue.json", 'r', encoding='utf-8') as drill_38:
            self.issue_drill_38 = json.load(drill_38)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/jira/get_user1.json", 'r', encoding='utf-8') as user1_file:
            self.user1 = json.load(user1_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/jira/get_user2.json", 'r', encoding='utf-8') as user2_file:
            self.user2 = json.load(user2_file)

        # Create testconfig
        config = configparser.ConfigParser()
        config.read(os.path.dirname(os.path.realpath(__file__)) + "/data/used_test_config.cfg")
        mongoengine.connection.disconnect()
        mongoengine.connect('testdb', host='mongodb://localhost', mongo_client_class=mongomock.MongoClient)

        Project.drop_collection()
        IssueSystem.drop_collection()
        Issue.drop_collection()
        IssueComment.drop_collection()
        Event.drop_collection()

        self.project_id = Project(name='Bla').save().id
        self.issues_system_id = IssueSystem(project_id=self.project_id,
                                            url="https://issues.apache.org/search?jql=project=BLA",
                                            last_updated=datetime.datetime.now()).save().id

        self.conf = ConfigMock(None, None, None, None, None, None, 'Bla',
                               'https://issues.apache.org/search?jql=project=BLA', 'jira', None, None, None,
                               None, None, None, 'DEBUG', '123')

    def test_create_url_to_rest_interface_apache(self):
        self.conf.tracking_url = 'https://issues.apache.org/jira/rest/api/2/search?jql=project=DRILL'
        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)

        self.assertEqual('https://issues.apache.org/jira', new_jira_backend._create_url_to_jira_rest_interface())

    def test_create_url_to_rest_interface_non_apache(self):
        self.conf.tracking_url = 'https://issues.sonatype.org/rest/api/2/search?jql=project=NEXUS'
        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)

        self.assertEqual('https://issues.sonatype.org',new_jira_backend._create_url_to_jira_rest_interface())

    def test_query_without_issue_available(self):
        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)

        self.assertEqual('project=BLA ORDER BY updatedDate ASC', new_jira_backend._create_issue_query())

    def test_query_with_issue_available(self):
        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)

        current_date = datetime.datetime.now()
        Issue(issue_system_id=self.issues_system_id, updated_at=current_date).save()

        self.assertEqual(
            'project=BLA and updatedDate > \'%s\' ORDER BY updatedDate ASC' % current_date.strftime('%Y/%m/%d %H:%M'),
            new_jira_backend._create_issue_query()
        )

    @mock.patch('issueshark.backends.jirabackend.JiraBackend._get_user')
    def test_store_events(self, get_user_mock):
        user1_obj = jira.resources.User(options=None, session=None, raw=self.user1)
        user2_obj = jira.resources.User(options=None, session=None, raw=self.user2)
        get_user_mock.side_effect = [user1_obj, user2_obj]

        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)

        issue = jira.resources.Issue(options=None, session=None, raw=self.issue_drill_138)
        mongo_issue = Issue(external_id="TEST", issue_system_id=self.issues_system_id).save()

        new_jira_backend._store_events(issue, mongo_issue.id)

        stored_events = Event.objects(issue_id=mongo_issue.id).all()
        self.assertEqual(24, len(stored_events))

        jacques_user = People.objects(email="jacques@apache.org", username="jnadeau").get()
        timothy_user = People.objects(email="tnachen@gmail.com", username="tnachen").get()
        cmerrick_user = People.objects(email="christopherrmerrick@gmail.com", username="cmerrick").get()

        # Check each event
        # Custom event
        event = stored_events[0]
        self.assertEqual(event.status, "Target Version/s")
        self.assertEqual(event.old_value, None)
        self.assertEqual(event.new_value, "0.1")
        self.assertEqual(event.created_at, datetime.datetime(2016, 8, 13, 17, 29, 13, 718000))
        self.assertEqual(event.author_id, jacques_user.id)

        # Status
        event = stored_events[1]
        self.assertEqual(event.status, "status")
        self.assertEqual(event.old_value, "Reopened")
        self.assertEqual(event.new_value, "Resolved")
        self.assertEqual(event.created_at, datetime.datetime(2016, 8, 13, 17, 29, 13, 718000))
        self.assertEqual(event.author_id, jacques_user.id)

        # Resolution
        event = stored_events[2]
        self.assertEqual(event.status, "resolution")
        self.assertEqual(event.old_value, "Test")
        self.assertEqual(event.new_value, "Fixed")
        self.assertEqual(event.created_at, datetime.datetime(2016, 8, 13, 17, 29, 13, 718000))
        self.assertEqual(event.author_id, jacques_user.id)

        # Attachment
        event = stored_events[3]
        self.assertEqual(event.status, "Attachment")
        self.assertEqual(event.old_value, None)
        self.assertEqual(event.new_value, "testfails_ZOOKEEPER-136.patch")
        self.assertEqual(event.created_at, datetime.datetime(2016, 8, 13, 17, 29, 13, 718000))
        self.assertEqual(event.author_id, jacques_user.id)

        event = stored_events[4]
        self.assertEqual(event.status, "Attachment")
        self.assertEqual(event.old_value, "testfails_ZOOKEEPER-137.patch")
        self.assertEqual(event.new_value, None)
        self.assertEqual(event.created_at, datetime.datetime(2016, 8, 13, 17, 29, 13, 718000))
        self.assertEqual(event.author_id, jacques_user.id)

        # Link
        related_issue_1 = Issue.objects(external_id="ZOOKEEPER-232").get()
        related_issue_2 = Issue.objects(external_id="ZOOKEEPER-231").get()

        event = stored_events[5]
        self.assertEqual(event.status, "issue_links")
        self.assertEqual(event.old_value, None)
        self.assertEqual(event.new_value, {'effect': 'relates to', 'issue_id': related_issue_1.id, 'type': 'Reference'})
        self.assertEqual(event.created_at, datetime.datetime(2016, 8, 13, 17, 29, 13, 718000))
        self.assertEqual(event.author_id, jacques_user.id)


        event = stored_events[6]
        self.assertEqual(event.status, "issue_links")
        self.assertEqual(event.old_value,  {'effect': 'relates to', 'issue_id': related_issue_2.id, 'type': 'Reference'})
        self.assertEqual(event.new_value, None)
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        # assignee
        assignee_old = People.objects(username="breed").get()
        assignee_new = People.objects(username="phunt").get()

        event = stored_events[7]
        self.assertEqual(event.status, "assignee_id")
        self.assertEqual(event.old_value, assignee_old.id)
        self.assertEqual(event.new_value, assignee_new.id)
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        # fix version
        event = stored_events[8]
        self.assertEqual(event.status, "fix_versions")
        self.assertEqual(event.old_value, None)
        self.assertEqual(event.new_value, "3.6.0")
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        event = stored_events[9]
        self.assertEqual(event.status, "fix_versions")
        self.assertEqual(event.old_value, "3.5.0")
        self.assertEqual(event.new_value, None)
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        # priority
        event = stored_events[10]
        self.assertEqual(event.status, "priority")
        self.assertEqual(event.old_value, "Major")
        self.assertEqual(event.new_value, "Blocker")
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        # issue type
        event = stored_events[11]
        self.assertEqual(event.status, "issue_type")
        self.assertEqual(event.old_value, "New Feature")
        self.assertEqual(event.new_value, "Improvement")
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        # affects version
        event = stored_events[12]
        self.assertEqual(event.status, "affects_versions")
        self.assertEqual(event.old_value, None)
        self.assertEqual(event.new_value, "3.0.0")
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        event = stored_events[13]
        self.assertEqual(event.status, "affects_versions")
        self.assertEqual(event.old_value, "3.0.1")
        self.assertEqual(event.new_value, None)
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        # title
        event = stored_events[14]
        self.assertEqual(event.status, "title")
        self.assertEqual(event.old_value, "Dump of ZooKeeper SVN repository")
        self.assertEqual(event.new_value, "Initial ZooKeeper code contribution from Yahoo!")
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        # desc
        event = stored_events[15]
        self.assertEqual(event.status, "desc")
        self.assertEqual(event.old_value, "There are a couple of cases of member variables that need to be marked "
                                          "volatile or surrounded in a synchronization block. A couple of examples "
                                          "are:\n\n* QuorumPeer state should be synchronous\n* currentVote in "
                                          "QuorumPeer is marked volatile, but when it's members are often accessed "
                                          "individually as if they were in an atomic unit. Such code should be changed"
                                          " to get a reference to the currentVote and they access members through that"
                                          " reference.\n")
        self.assertEqual(event.new_value, "There are a couple of cases of member variables that need to be marked "
                                          "volatile or surrounded in a synchronization block. A couple of examples "
                                          "are:\n\n* QuorumPeer state should be synchronous\n* currentVote in "
                                          "QuorumPeer is marked volatile, but when it's members are often accessed "
                                          "individually as if they were in an atomic unit. Such code should be "
                                          "changed to get a reference to the currentVote and they access members "
                                          "through that reference.\n* It looks like logicalClock in FastLeaderElection"
                                          " should be volatile. It should either be fixed or commented to explain why "
                                          "it doesn't need to be.")
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        # labels
        event = stored_events[16]
        self.assertEqual(event.status, "labels")
        self.assertEqual(event.old_value, "newbie")
        self.assertEqual(event.new_value, "docuentation newbie")
        self.assertEqual(event.created_at, datetime.datetime(2015, 2, 24, 17, 0, 58, 268000))
        self.assertEqual(event.author_id, timothy_user.id)

        # parent issue id
        event = stored_events[17]
        self.assertEqual(event.status, "parent_issue_id")
        self.assertEqual(event.old_value, related_issue_1.id)
        self.assertEqual(event.new_value, related_issue_2.id)
        self.assertEqual(event.created_at, datetime.datetime(2014, 2, 24, 17, 43, 46, 87000))
        self.assertEqual(event.author_id, cmerrick_user.id)

        # environment
        event = stored_events[18]
        self.assertEqual(event.status, "environment")
        self.assertEqual(event.old_value, "Sparc Solaris 10\r\nJava 6u17 64 bits\r\n5 nodes ensemble")
        self.assertEqual(event.new_value, "Sparc Solaris 10 and 11\r\nJava 6u17 64 bits\r\n5 nodes ensemble")
        self.assertEqual(event.created_at, datetime.datetime(2014, 2, 24, 17, 43, 46, 87000))
        self.assertEqual(event.author_id, cmerrick_user.id)

        # Custom labels
        event = stored_events[19]
        self.assertEqual(event.status, "labels")
        self.assertEqual(event.old_value, "")
        self.assertEqual(event.new_value, "zookeeper")
        self.assertEqual(event.created_at, datetime.datetime(2014, 2, 24, 17, 43, 46, 87000))
        self.assertEqual(event.author_id, cmerrick_user.id)

        event = stored_events[20]
        self.assertEqual(event.status, "labels")
        self.assertEqual(event.old_value, "zookeeper1")
        self.assertEqual(event.new_value, "")
        self.assertEqual(event.created_at, datetime.datetime(2014, 2, 24, 17, 43, 46, 87000))
        self.assertEqual(event.author_id, cmerrick_user.id)

        # original_time_estimate
        event = stored_events[21]
        self.assertEqual(event.status, "original_time_estimate")
        self.assertEqual(event.old_value, 480)
        self.assertEqual(event.new_value, 28800)
        self.assertEqual(event.created_at, datetime.datetime(2014, 2, 24, 17, 43, 46, 87000))
        self.assertEqual(event.author_id, cmerrick_user.id)

        # component
        event = stored_events[22]
        self.assertEqual(event.status, "components")
        self.assertEqual(event.old_value, None)
        self.assertEqual(event.new_value, "c client")
        self.assertEqual(event.created_at, datetime.datetime(2014, 2, 24, 17, 43, 46, 87000))
        self.assertEqual(event.author_id, cmerrick_user.id)

        event = stored_events[23]
        self.assertEqual(event.status, "components")
        self.assertEqual(event.old_value, "python client")
        self.assertEqual(event.new_value, None)
        self.assertEqual(event.created_at, datetime.datetime(2014, 2, 24, 17, 43, 46, 87000))
        self.assertEqual(event.author_id, cmerrick_user.id)

    def test_store_events_two_times(self):
        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)

        issue = jira.resources.Issue(options=None, session=None, raw=self.issue_drill_1)
        mongo_issue = Issue(external_id="TEST", issue_system_id=self.issues_system_id).save()

        new_jira_backend._store_events(issue, mongo_issue.id)
        new_jira_backend._store_events(issue, mongo_issue.id)

        stored_events = Event.objects(issue_id=mongo_issue.id).all()
        self.assertEqual(7, len(stored_events))

    def test_store_jira_issue(self):
        issue = jira.resources.Issue(options=None, session=None, raw=self.issue_drill_1)
        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)
        new_jira_backend._store_jira_issue(issue)

        stored_issue = Issue.objects(external_id='DRILL-1').get()
        creator = People.objects(email="michael.hausenblas@gmail.com").get()
        related_issue = Issue.objects(external_id='DRILL-48').get()

        self.assertEqual(stored_issue.issue_system_id, self.issues_system_id)
        self.assertEqual(stored_issue.title, 'Thrift-based wire protocol')
        self.assertEqual(stored_issue.desc, 'Support a Thrift-based [1] wire protocol. Contributor: Michael Hausenblas.\r\n\r\nSee [2] for the discussion.\r\n\r\n\r\n[1] http://thrift.apache.org/\r\n[2] http://mail-archives.apache.org/mod_mbox/incubator-drill-dev/201209.mbox/%3C4C785CAB-FD0E-4C5A-8D83-7AD0B7752139%40gmail.com%3E')
        self.assertEqual(stored_issue.created_at, datetime.datetime(2012,9,5,16,34,55, 991000))
        self.assertEqual(stored_issue.updated_at, datetime.datetime(2014,7,31,6,32,54, 672000))
        self.assertEqual(stored_issue.creator_id, creator.id)
        self.assertEqual(stored_issue.reporter_id, creator.id)
        self.assertEqual(stored_issue.issue_type, 'Improvement')
        self.assertEqual(stored_issue.priority, 'Minor')
        self.assertEqual(stored_issue.status, 'Resolved')
        self.assertListEqual(stored_issue.affects_versions, [])
        self.assertListEqual(stored_issue.components, [])
        self.assertListEqual(stored_issue.labels, [])
        self.assertEqual(stored_issue.resolution, 'Won\'t Fix')
        self.assertListEqual(stored_issue.fix_versions, ['0.4.0'])
        self.assertEqual(stored_issue.assignee_id, None)
        self.assertListEqual(stored_issue.issue_links, [{'effect': 'is related to', 'issue_id': related_issue.id, 'type': 'Reference'}])
        self.assertEqual(stored_issue.parent_issue_id, None)
        self.assertEqual(stored_issue.original_time_estimate, 3600)
        self.assertEqual(stored_issue.environment, "Windows")
        self.assertEqual(stored_issue.platform, None)

        issue = jira.resources.Issue(options=None, session=None, raw=self.issue_drill_138)
        new_jira_backend._store_jira_issue(issue)

        stored_issue = Issue.objects(external_id='DRILL-138').get()
        creator = People.objects(email="altekrusejason@gmail.com").get()
        related_issue = Issue.objects(external_id='DRILL-49').get()

        self.assertEqual(stored_issue.issue_system_id, self.issues_system_id)
        self.assertEqual(stored_issue.title, 'Fill basic optimizer with new Physical Operators')
        self.assertEqual(stored_issue.desc, 'As new Physical Operators are completed they must be added to the basic optimizer for logical to physical plan conversion.')
        self.assertEqual(stored_issue.created_at, datetime.datetime(2013, 7, 3, 0, 16, 13, 737000))
        self.assertEqual(stored_issue.updated_at, datetime.datetime(2013, 10, 9, 18, 9, 28, 672000))
        self.assertEqual(stored_issue.creator_id, creator.id)
        self.assertEqual(stored_issue.reporter_id, creator.id)
        self.assertEqual(stored_issue.issue_type, 'New Feature')
        self.assertEqual(stored_issue.priority, 'Major')
        self.assertEqual(stored_issue.status, 'Closed')
        self.assertListEqual(stored_issue.affects_versions, ["3.0.0"])
        self.assertIn("server", stored_issue.components)
        self.assertIn("java client", stored_issue.components)
        self.assertIn("tests", stored_issue.components)
        self.assertIn("operator", stored_issue.labels)
        self.assertIn("optimizer", stored_issue.labels)
        self.assertIn("physical", stored_issue.labels)
        self.assertEqual(stored_issue.resolution, 'Duplicate')
        self.assertListEqual(stored_issue.fix_versions, ['0.1.0-m1'])
        self.assertEqual(stored_issue.assignee_id, creator.id)
        self.assertListEqual(stored_issue.issue_links,
                             [{'effect': 'duplicates', 'issue_id': related_issue.id, 'type': 'Duplicate'}])
        self.assertEqual(stored_issue.parent_issue_id, None)
        self.assertEqual(stored_issue.original_time_estimate, 3600)
        self.assertEqual(stored_issue.environment, None)
        self.assertEqual(stored_issue.platform, None)

        issue = jira.resources.Issue(options=None, session=None, raw=self.issue_drill_38)
        new_jira_backend._store_jira_issue(issue)

        stored_issue = Issue.objects(external_id='DRILL-38').get()
        creator = People.objects(email="christopherrmerrick@gmail.com", username="chrismerrick").get()
        assignee = People.objects(email="christopherrmerrick@gmail.com", username="cmerrick").get()
        parent_issue = Issue.objects(external_id='DRILL-37').get()

        self.assertEqual(stored_issue.issue_system_id, self.issues_system_id)
        self.assertEqual(stored_issue.title, 'Limit ROP Unit Tests')
        self.assertEqual(stored_issue.desc, None)
        self.assertEqual(stored_issue.created_at, datetime.datetime(2013, 2, 24, 2, 4, 42, 952000))
        self.assertEqual(stored_issue.updated_at, datetime.datetime(2013, 10, 9, 18, 9, 34, 2000))
        self.assertEqual(stored_issue.creator_id, creator.id)
        self.assertEqual(stored_issue.reporter_id, creator.id)
        self.assertEqual(stored_issue.issue_type, 'Sub-task')
        self.assertEqual(stored_issue.priority, 'Major')
        self.assertEqual(stored_issue.status, 'Closed')
        self.assertListEqual(stored_issue.affects_versions, [])
        self.assertListEqual(stored_issue.components, [])
        self.assertEqual(stored_issue.resolution, 'Fixed')
        self.assertListEqual(stored_issue.fix_versions, ['0.1.0-m1'])
        self.assertEqual(stored_issue.assignee_id, assignee.id)
        self.assertListEqual(stored_issue.issue_links, [])
        self.assertEqual(stored_issue.parent_issue_id, parent_issue.id)
        self.assertEqual(stored_issue.original_time_estimate, None)
        self.assertEqual(stored_issue.environment, None)
        self.assertEqual(stored_issue.platform, None)

    def test_store_jira_issue_after_change(self):
        issue = jira.resources.Issue(options=None, session=None, raw=self.issue_drill_38)

        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)
        new_jira_backend._store_jira_issue(issue)

        stored_issue = Issue.objects(external_id='DRILL-38').get()
        creator = People.objects(email="christopherrmerrick@gmail.com", username="chrismerrick").get()
        assignee = People.objects(email="christopherrmerrick@gmail.com", username="cmerrick").get()
        parent_issue = Issue.objects(external_id='DRILL-37').get()

        self.assertEqual(stored_issue.issue_system_id, self.issues_system_id)
        self.assertEqual(stored_issue.title, 'Limit ROP Unit Tests')
        self.assertEqual(stored_issue.desc, None)
        self.assertEqual(stored_issue.created_at, datetime.datetime(2013, 2, 24, 2, 4, 42, 952000))
        self.assertEqual(stored_issue.updated_at, datetime.datetime(2013, 10, 9, 18, 9, 34, 2000))
        self.assertEqual(stored_issue.creator_id, creator.id)
        self.assertEqual(stored_issue.reporter_id, creator.id)
        self.assertEqual(stored_issue.issue_type, 'Sub-task')
        self.assertEqual(stored_issue.priority, 'Major')
        self.assertEqual(stored_issue.status, 'Closed')
        self.assertListEqual(stored_issue.affects_versions, [])
        self.assertListEqual(stored_issue.components, [])
        self.assertEqual(stored_issue.resolution, 'Fixed')
        self.assertListEqual(stored_issue.fix_versions, ['0.1.0-m1'])
        self.assertEqual(stored_issue.assignee_id, assignee.id)
        self.assertListEqual(stored_issue.issue_links, [])
        self.assertEqual(stored_issue.parent_issue_id, parent_issue.id)
        self.assertEqual(stored_issue.original_time_estimate, None)
        self.assertEqual(stored_issue.environment, None)
        self.assertEqual(stored_issue.platform, None)

        issue.fields.priority = 'Minor'
        new_jira_backend._store_jira_issue(issue)
        stored_issue = Issue.objects(external_id='DRILL-38').get()

        self.assertEqual(stored_issue.issue_system_id, self.issues_system_id)
        self.assertEqual(stored_issue.title, 'Limit ROP Unit Tests')
        self.assertEqual(stored_issue.desc, None)
        self.assertEqual(stored_issue.created_at, datetime.datetime(2013, 2, 24, 2, 4, 42, 952000))
        self.assertEqual(stored_issue.updated_at, datetime.datetime(2013, 10, 9, 18, 9, 34, 2000))
        self.assertEqual(stored_issue.creator_id, creator.id)
        self.assertEqual(stored_issue.reporter_id, creator.id)
        self.assertEqual(stored_issue.issue_type, 'Sub-task')
        self.assertEqual(stored_issue.priority, 'Minor')
        self.assertEqual(stored_issue.status, 'Closed')
        self.assertListEqual(stored_issue.affects_versions, [])
        self.assertListEqual(stored_issue.components, [])
        self.assertEqual(stored_issue.resolution, 'Fixed')
        self.assertListEqual(stored_issue.fix_versions, ['0.1.0-m1'])
        self.assertEqual(stored_issue.assignee_id, assignee.id)
        self.assertListEqual(stored_issue.issue_links, [])
        self.assertEqual(stored_issue.parent_issue_id, parent_issue.id)
        self.assertEqual(stored_issue.original_time_estimate, None)
        self.assertEqual(stored_issue.environment, None)
        self.assertEqual(stored_issue.platform, None)

    def test_store_comments(self):
        issue = jira.resources.Issue(options=None, session=None, raw=self.issue_drill_38)
        mongo_issue = Issue(external_id="TEST", issue_system_id=self.issues_system_id).save()

        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)
        new_jira_backend._store_comments(issue, mongo_issue.id)

        all_comments = IssueComment.objects(issue_id=mongo_issue.id).all()

        self.assertEqual(len(all_comments), 4)

        chris_merrick = People.objects(email="christopherrmerrick@gmail.com", username="chrismerrick").get()
        chris_merrick2 = People.objects(email="christopherrmerrick@gmail.com", username="cmerrick").get()
        timothy_chen = People.objects(email="tnachen@gmail.com").get()
        jacques_nadeau = People.objects(email="jacques@apache.org").get()

        # comment 1
        comment = all_comments[0]
        self.assertEqual(comment.created_at, datetime.datetime(2013, 2, 24, 2, 13, 0, 18000))
        self.assertEqual(comment.author_id, chris_merrick.id)
        self.assertEqual(comment.comment, "I can't figure out how to assign this to myself "
                                          "(not seeing a button anywhere).  Can someone either give me permission to do"
                                          " that or teach me how to use JIRA?  Thanks.")

        # comment 2
        comment = all_comments[1]
        self.assertEqual(comment.created_at, datetime.datetime(2013, 2, 24, 17, 1, 36, 848000))
        self.assertEqual(comment.author_id, timothy_chen.id)
        self.assertEqual(comment.comment, "You most likely don't have permissions. I don't have permissions to assign "
                                          "permissions, so probably either Ted or Jacques can do this. "
                                          "I've assigned this task to you.")

        # comment 3
        comment = all_comments[2]
        self.assertEqual(comment.created_at, datetime.datetime(2013, 2, 24, 17, 43, 36, 857000))
        self.assertEqual(comment.author_id, chris_merrick2.id)
        self.assertEqual(comment.comment, "Submitted pull request: https://github.com/apache/incubator-drill/pull/9")

        # comment 4
        comment = all_comments[3]
        self.assertEqual(comment.created_at, datetime.datetime(2013, 2, 25, 4, 2, 43, 710000))
        self.assertEqual(comment.author_id, jacques_nadeau.id)
        self.assertEqual(comment.comment, "merged")

    def test_store_comments_two_times(self):
        issue = jira.resources.Issue(options=None, session=None, raw=self.issue_drill_38)
        mongo_issue = Issue(external_id="TEST", issue_system_id=self.issues_system_id).save()

        new_jira_backend = JiraBackend(self.conf, self.issues_system_id, self.project_id)
        new_jira_backend._store_comments(issue, mongo_issue.id)
        new_jira_backend._store_comments(issue, mongo_issue.id)

        all_comments = IssueComment.objects(issue_id=mongo_issue.id).all()

        self.assertEqual(len(all_comments), 4)

