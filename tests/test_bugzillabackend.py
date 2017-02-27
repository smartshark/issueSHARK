import configparser
import unittest
import os
import datetime

import logging
import json
import jira
import mock
from mongoengine import connect

from issueshark.backends.bugzilla import BugzillaBackend
from pycoshark.mongomodels import IssueSystem, Project, Issue, Event, IssueComment, People

from issueshark.backends.helpers.bugzillaagent import BugzillaAgent


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


class BugzillaBackendTest(unittest.TestCase):

    def setUp(self):
        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/bugzilla/issue1.json", 'r', encoding='utf-8') as \
                issue_1_file:
            self.issue_1 = json.load(issue_1_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/bugzilla/issue95.json", 'r', encoding='utf-8') as \
                issue_95_file:
            self.issue_95 = json.load(issue_95_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/bugzilla/issue95_comments.json", 'r', encoding='utf-8') as \
                issue_95_comments_file:
            self.issue_95_comments = json.load(issue_95_comments_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/bugzilla/issue95_history.json", 'r', encoding='utf-8') as \
                issue_95_history_file:
            self.issue_95_history = json.load(issue_95_history_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/bugzilla/conor_apache_org_user.json", 'r', encoding='utf-8') as \
                conor_user_file:
            self.conor_user = json.load(conor_user_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/bugzilla/dev_tomcat_apache_org_user.json", 'r', encoding='utf-8') as \
                dev_tomcat_file:
            self.dev_tomcat_file = json.load(dev_tomcat_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/bugzilla/craig_mcclanahan_user.json", 'r', encoding='utf-8') as \
                craig_user_file:
            self.craig_user = json.load(craig_user_file)

        # Create testconfig
        config = configparser.ConfigParser()
        config.read(os.path.dirname(os.path.realpath(__file__)) + "/data/used_test_config.cfg")

        # Setting up database with data that is normally put into it via vcs program
        connect(config['Database']['db_database'], username=config['Database']['db_user'],
                password=config['Database']['db_password'], host=config['Database']['db_hostname'],
                port=int(config['Database']['db_port']),
                authentication_source=config['Database']['db_authentication'],
                connect=False)

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
                               'Nonsense?product=Blub', 'bugzilla', None, None, None,
                               None, None, None, 'DEBUG', '123')

    def test_transform_issue(self):
        bugzilla_backend = BugzillaBackend(self.conf, self.issues_system_id, self.project_id)
        bugzilla_backend._transform_issue(self.issue_95, self.issue_95_comments)

        stored_issue = Issue.objects(external_id="95").get()
        blocks_issue_1 = Issue.objects(external_id="31389").get()
        blocks_issue_2 = Issue.objects(external_id="23453").get()

        depends_on_issue_1 = Issue.objects(external_id="22269").get()
        depends_on_issue_2 = Issue.objects(external_id="34532").get()

        duplicates_issue = Issue.objects(external_id="30576").get()


        creator = People.objects(email="anand@avnisoft.com").get()
        assignee = People.objects(email="notifications@ant.apache.org").get()

        self.assertEqual(stored_issue.issue_system_id, self.issues_system_id)
        self.assertEqual(stored_issue.title, "The \"java\" task doesn't work. BugRat Report#85")
        self.assertEqual(stored_issue.desc, "Description text")
        self.assertEqual(stored_issue.created_at, datetime.datetime(2000, 9, 7, 20, 20, 32))
        self.assertEqual(stored_issue.updated_at, datetime.datetime(2008, 2, 22, 12, 18, 59))
        self.assertEqual(stored_issue.creator_id, creator.id)
        self.assertEqual(stored_issue.reporter_id, creator.id)
        self.assertEqual(stored_issue.issue_type, "Bug")
        self.assertEqual(stored_issue.priority, "normal")
        self.assertEqual(stored_issue.status, "CLOSED")
        self.assertEqual(stored_issue.affects_versions, ["1.2"])
        self.assertEqual(stored_issue.components, ["Core tasks"])
        self.assertEqual(len(stored_issue.labels), 2)
        self.assertIn("PatchAvailable", stored_issue.labels)
        self.assertIn("Keyword2", stored_issue.labels)
        self.assertEqual(stored_issue.resolution, "WORKSFORME")
        self.assertEqual(stored_issue.fix_versions, ["---"])
        self.assertEqual(stored_issue.assignee_id, assignee.id)
        self.assertEqual(len(stored_issue.issue_links), 5)
        self.assertIn({'issue_id': blocks_issue_1.id, 'type': 'Blocker', 'effect': 'blocks'}, stored_issue.issue_links)
        self.assertIn({'issue_id': blocks_issue_2.id, 'type': 'Blocker', 'effect': 'blocks'}, stored_issue.issue_links)
        self.assertIn({'issue_id': depends_on_issue_1.id, 'type': 'Dependent', 'effect': 'depends on'}, stored_issue.issue_links)
        self.assertIn({'issue_id': depends_on_issue_2.id, 'type': 'Dependent', 'effect': 'depends on'}, stored_issue.issue_links)
        self.assertIn({'issue_id': duplicates_issue.id, 'type': 'Duplicate', 'effect': 'duplicates'}, stored_issue.issue_links)
        self.assertEqual(stored_issue.environment, "All")
        self.assertEqual(stored_issue.platform, "All")

    def test_store_issue_two_times(self):
        bugzilla_backend = BugzillaBackend(self.conf, self.issues_system_id, self.project_id)
        bugzilla_backend._transform_issue(self.issue_1, self.issue_95_comments)
        bugzilla_backend._transform_issue(self.issue_1, self.issue_95_comments)

        stored_issues = Issue.objects.all()
        self.assertEqual(len(stored_issues), 1)

    @mock.patch('issueshark.backends.helpers.bugzillaagent.BugzillaAgent.get_user')
    def test_process_comments(self, get_user_mock):
        bugzilla_backend = BugzillaBackend(self.conf, self.issues_system_id, self.project_id)
        bugzilla_backend.bugzilla_agent = BugzillaAgent(None, self.conf)
        issue = Issue(external_id="TEST", issue_system_id=self.issues_system_id).save()

        get_user_mock.side_effect = [self.dev_tomcat_file, self.conor_user]

        bugzilla_backend._process_comments(issue.id, self.issue_95_comments)

        all_comments = IssueComment.objects(issue_id=issue.id).all()
        self.assertEqual(2, len(all_comments))

        # comment 1
        commenter = People.objects(email="dev@tomcat.apache.org").get()
        comment = all_comments[0]
        self.assertEqual(comment.created_at, datetime.datetime(2001, 2, 4, 6, 20, 32))
        self.assertEqual(comment.author_id, commenter.id)
        self.assertEqual(comment.comment, "I have tested this on NT (JDK 1.1, 1.2.2, 1.3) and Linux "
                                          "(Redhat 6.2, JDK \n1.1.2) and could not reproduce this problem. ")

        # comment 2
        commenter = People.objects(email="conor@apache.org").get()
        comment = all_comments[1]
        self.assertEqual(comment.created_at, datetime.datetime(2001, 2, 6, 19, 35, 1))
        self.assertEqual(comment.author_id, commenter.id)
        self.assertEqual(comment.comment, "For query purposes, mark as fixed for Tomcat 3.3:\nFixed in Tomcat 3.3\n")

    @mock.patch('issueshark.backends.helpers.bugzillaagent.BugzillaAgent.get_user')
    def test_process_comments_two_times(self, get_user_mock):
        bugzilla_backend = BugzillaBackend(self.conf, self.issues_system_id, self.project_id)
        bugzilla_backend.bugzilla_agent = BugzillaAgent(None, self.conf)
        issue = Issue(external_id="TEST", issue_system_id=self.issues_system_id).save()

        get_user_mock.side_effect = [self.dev_tomcat_file, self.conor_user]

        bugzilla_backend._process_comments(issue.id, self.issue_95_comments)
        bugzilla_backend._process_comments(issue.id, self.issue_95_comments)

        self.assertEqual(2, len(IssueComment.objects.all()))

    @mock.patch('issueshark.backends.helpers.bugzillaagent.BugzillaAgent.get_user')
    def test_store_events(self, get_user_mock):
        bugzilla_backend = BugzillaBackend(self.conf, self.issues_system_id, self.project_id)
        bugzilla_backend.bugzilla_agent = BugzillaAgent(None, self.conf)
        issue = Issue(external_id="TEST", issue_system_id=self.issues_system_id).save()

        get_user_mock.side_effect = [self.craig_user, self.conor_user, self.craig_user, self.conor_user, self.conor_user]
        bugzilla_backend._store_events(self.issue_95_history, self.issue_95, issue)

        craig_user = People.objects(email="craig.mcclanahan@sun.com").get()
        conor_user = People.objects(email="conor@apache.org").get()

        all_events = Event.objects.all()

        self.assertEqual(16, len(all_events))

        # assignee_id
        event = all_events[0]
        self.assertEqual(event.status, "assignee_id")
        self.assertEqual(event.old_value, craig_user.id)
        self.assertEqual(event.new_value, conor_user.id)
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # status
        event = all_events[1]
        self.assertEqual(event.status, "status")
        self.assertEqual(event.old_value, "NEW")
        self.assertEqual(event.new_value, "UNCONFIRMED")
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # component
        event = all_events[2]
        self.assertEqual(event.status, "components")
        self.assertEqual(event.old_value, "Other")
        self.assertEqual(event.new_value, "Core tasks")
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # labels
        event = all_events[3]
        self.assertEqual(event.status, "labels")
        self.assertEqual(event.old_value, "85")
        self.assertEqual(event.new_value, None)
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # labels
        event = all_events[4]
        self.assertEqual(event.status, "labels")
        self.assertEqual(event.old_value, None)
        self.assertEqual(event.new_value, "PatchAvailable")
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # environment
        event = all_events[5]
        self.assertEqual(event.status, "environment")
        self.assertEqual(event.old_value, "Windows")
        self.assertEqual(event.new_value, "All")
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # platform
        event = all_events[6]
        self.assertEqual(event.status, "platform")
        self.assertEqual(event.old_value, "OSX")
        self.assertEqual(event.new_value, "All")
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # affects versions
        event = all_events[7]
        self.assertEqual(event.status, "affects_versions")
        self.assertEqual(event.old_value, "3.1")
        self.assertEqual(event.new_value, "1.2")
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # resolution
        event = all_events[8]
        self.assertEqual(event.status, "resolution")
        self.assertEqual(event.old_value, "NOTHING")
        self.assertEqual(event.new_value, "WORKSFORME")
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # depends_on / issue_links
        related_issue_41817 = Issue.objects(external_id="41817").get()

        event = all_events[9]
        self.assertEqual(event.status, "issue_links")
        self.assertEqual(event.old_value, None)
        self.assertEqual(event.new_value, {'issue_id': related_issue_41817.id, 'type': 'Dependent', 'effect': 'depends on'})
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # depends_on / issue_links
        related_issue_41818 = Issue.objects(external_id="41818").get()

        event = all_events[10]
        self.assertEqual(event.status, "issue_links")
        self.assertEqual(event.old_value, {'issue_id': related_issue_41818.id, 'type': 'Dependent', 'effect': 'depends on'})
        self.assertEqual(event.new_value, None)
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        # blocks / issue_links
        event = all_events[11]
        self.assertEqual(event.status, "issue_links")
        self.assertEqual(event.old_value, None)
        self.assertEqual(event.new_value, {'issue_id': related_issue_41817.id, 'type': 'Blocker', 'effect': 'blocks'})
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 3, 17, 48, 45))
        self.assertEqual(event.author_id, craig_user.id)

        ############
        # blocks / issue_links
        event = all_events[12]
        self.assertEqual(event.status, "issue_links")
        self.assertEqual(event.old_value, {'issue_id': related_issue_41818.id, 'type': 'Blocker', 'effect': 'blocks'})
        self.assertEqual(event.new_value, None)
        self.assertEqual(event.created_at, datetime.datetime(2001, 2, 4, 6, 20, 32))
        self.assertEqual(event.author_id, conor_user.id)

        #############
        # title
        event = all_events[13]
        self.assertEqual(event.status, "title")
        self.assertEqual(event.old_value, "cvschangelog task: CVS log date output format changed on CVS 1.12.9 ")
        self.assertEqual(event.new_value, "cvschangelog task: CVS log date output format changed on CVS 1.12.9")
        self.assertEqual(event.created_at, datetime.datetime(2001, 3, 2, 5, 0, 52))
        self.assertEqual(event.author_id, conor_user.id)

        # fix_versions
        event = all_events[14]
        self.assertEqual(event.status, "fix_versions")
        self.assertEqual(event.old_value, "---")
        self.assertEqual(event.new_value, "1.7")
        self.assertEqual(event.created_at, datetime.datetime(2001, 3, 2, 5, 0, 52))
        self.assertEqual(event.author_id, conor_user.id)

        # priority
        event = all_events[15]
        self.assertEqual(event.status, "priority")
        self.assertEqual(event.old_value, "major")
        self.assertEqual(event.new_value, "enhancement")
        self.assertEqual(event.created_at, datetime.datetime(2001, 3, 2, 5, 0, 52))
        self.assertEqual(event.author_id, conor_user.id)

    @mock.patch('issueshark.backends.helpers.bugzillaagent.BugzillaAgent.get_user')
    def test_store_events_two_times(self, get_user_mock):
        bugzilla_backend = BugzillaBackend(self.conf, self.issues_system_id, self.project_id)
        bugzilla_backend.bugzilla_agent = BugzillaAgent(None, self.conf)
        issue = Issue(external_id="TEST", issue_system_id=self.issues_system_id).save()

        get_user_mock.side_effect = [self.craig_user, self.conor_user, self.craig_user, self.conor_user,
                                     self.conor_user]
        bugzilla_backend._store_events(self.issue_95_history, self.issue_95, issue)
        bugzilla_backend._store_events(self.issue_95_history, self.issue_95, issue)

        all_events = Event.objects.all()

        self.assertEqual(16, len(all_events))
