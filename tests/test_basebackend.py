import unittest
import logging

from issueshark.backends.basebackend import BaseBackend


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

class BaseBackendTest(unittest.TestCase):

    def setUp(self):
        pass

    def test_get_all_possible_backend_options(self):
        all_options = BaseBackend.get_all_possible_backend_options()
        self.assertIn('github', all_options)
        self.assertIn('jira', all_options)
        self.assertIn('bugzilla', all_options)
        self.assertEqual(3, len(all_options))

    def test_find_fitting_backend_github(self):
        config = ConfigMock(None, None, None, None, None, None, None, None, 'github', None, None, None, None, None,
                            None, None, None)
        self.assertEqual('GithubBackend', type(BaseBackend.find_fitting_backend(config, None, None)).__name__)

    def test_find_fitting_backend_jira(self):
        config = ConfigMock(None, None, None, None, None, None, None, None, 'jira', None, None, None, None, None,
                            None, None, None)
        self.assertEqual('JiraBackend', type(BaseBackend.find_fitting_backend(config, None, None)).__name__)

    def test_find_fitting_backend_bugzilla(self):
        config = ConfigMock(None, None, None, None, None, None, None, None, 'bugzilla', None, None, None, None, None,
                            None, None, None)
        self.assertEqual('BugzillaBackend', type(BaseBackend.find_fitting_backend(config, None, None)).__name__)