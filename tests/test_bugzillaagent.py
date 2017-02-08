import unittest
import logging
import datetime

from issueshark.backends.helpers.bugzillaagent import BugzillaAgent, BugzillaApiException


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


class BugzillaAgentTest(unittest.TestCase):

    def setUp(self):
        self.conf = ConfigMock(None, None, None, None, None, None, 'Ant',
                               'https://bz.apache.org/bugzilla/rest.cgi/bug?product=Ant', 'github', None, None, None, None, None,
                               None, 'DEBUG', None)
        self.logger = logging.getLogger('root')
    def test_initialization_fails(self):
        conf = ConfigMock(None, None, None, None, None, None, 'Ant',
                          'https://bz.apache.org/bugzilla/rest.cgi/bug?product=Ant', 'github', None, None, None, None,
                          'user', None, 'DEBUG', None)
        with self.assertRaises(BugzillaApiException) as cm:
            ba = BugzillaAgent(self.logger, conf)
            self.assertEqual('If a username is given, a password needs to be given too!', cm.msg)

    def test_initialization_succeeds(self):
        ba = BugzillaAgent(self.logger, self.conf)
        self.assertEqual('https://bz.apache.org/bugzilla/rest.cgi', ba.base_url)
        self.assertEqual('Ant', ba.project_name)

    def test_build_query_bug_list_with_last_change_time(self):
        ba = BugzillaAgent(self.logger, self.conf)
        options = {
            'product': 'Ant',
            'offset': 12,
            'limit': 10,
            'order': 'creation_time%20ASC',
            'last_change_time': datetime.datetime(2012,10,1,10,5,10)
        }

        self.assertEqual(
            'https://bz.apache.org/bugzilla/rest.cgi/bug?last_change_time=2012-10-01+10%3A05%3A10&limit=10'
            '&offset=12&order=creation_time%20ASC&product=Ant',
            ba._build_query('bug', options)
        )

    def test_build_query_bug_list(self):
        ba = BugzillaAgent(self.logger, self.conf)
        options = {
            'product': 'Ant',
            'offset': 12,
            'limit': 10,
            'order': 'creation_time%20ASC'
        }
        self.assertEqual(
            'https://bz.apache.org/bugzilla/rest.cgi/bug?limit=10&offset=12&order=creation_time%20ASC&product=Ant',
            ba._build_query('bug', options)
        )

    def test_build_query_user(self):
        ba = BugzillaAgent(self.logger, self.conf)
        self.assertEqual('https://bz.apache.org/bugzilla/rest.cgi/user/hans', ba._build_query('user/hans', None))

    def test_build_query_issue_history(self):
        ba = BugzillaAgent(self.logger, self.conf)
        self.assertEqual('https://bz.apache.org/bugzilla/rest.cgi/bug/1241/history', ba._build_query('bug/1241/history',
                                                                                                     None))

    def test_build_query_get_comments(self):
        ba = BugzillaAgent(self.logger, self.conf)
        self.assertEqual('https://bz.apache.org/bugzilla/rest.cgi/bug/1241/comment', ba._build_query('bug/1241/comment',
                                                                                                     None))
