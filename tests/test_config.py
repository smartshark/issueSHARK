import unittest

from issueshark.config import Config, ConfigValidationException


class ArgparserMock(object):
    def __init__(self, db_user, db_password, db_database, db_hostname, db_port, db_authentication, project_name,
                 issue_url, backend, proxy_host, proxy_port, proxy_user, proxy_password, issue_user, issue_password,
                 debug, token, ssl):
        self.db_user = db_user
        self.db_password = db_password
        self.db_database = db_database
        self.db_hostname = db_hostname
        self.db_port = db_port
        self.db_authentication = db_authentication
        self.project_name = project_name
        self.issueurl = issue_url
        self.backend = backend
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_user = proxy_user
        self.proxy_password = proxy_password
        self.issue_user = issue_user
        self.issue_password = issue_password
        self.debug = debug
        self.token = token
        self.ssl = ssl

class ConfigTest(unittest.TestCase):

    def setUp(self):
        pass

    def test_initialization_success(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             "80", None, None, None, None, 'DEBUG', '234214151', False)
        conf = Config(args)
        self.assertEqual(conf.tracking_url, 'http://api.foo')
        self.assertEqual(conf.proxy_host, '126.0.0.1')

    def test_initialization_fails_issue_user_without_password(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             "80", None, None, 'user', None, 'DEBUG', None, False)

        with self.assertRaises(ConfigValidationException) as cm:
            conf = Config(args)
            self.assertEqual('Issue user and password must be set if either of them are not None.', cm.msg)

    def test_initialization_fails_issue_password_without_user(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             "80", None, None, None, 'password', 'DEBUG', None, False)

        with self.assertRaises(ConfigValidationException) as cm:
            conf = Config(args)
            self.assertEqual('Issue user and password must be set if either of them are not None.', cm.msg)

    def test_initialization_fails_proxy_user_without_password(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             "80", 'proxy_user', None, None, None, 'DEBUG', 'token', False)

        with self.assertRaises(ConfigValidationException) as cm:
            conf = Config(args)
            self.assertEqual('Proxy user and password must be set if either of them are not None.', cm.msg)

    def test_initialization_fails_proxy_password_without_user(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             "80", None, 'proxy_password', None, None, 'DEBUG', None, False)

        with self.assertRaises(ConfigValidationException) as cm:
            conf = Config(args)
            self.assertEqual('Proxy user and password must be set if either of them are not None.', cm.msg)

    def test_initialization_fails_proxy_host_without_port(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             None, None, None, None, None, 'DEBUG', 'token', False)

        with self.assertRaises(ConfigValidationException) as cm:
            conf = Config(args)
            self.assertEqual('Proxy host and port must be set if either of them are not None.', cm.msg)

    def test_initialization_fails_proxy_port_without_host(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, None,
                             "80", None, None, None, None, 'DEBUG', None, False)

        with self.assertRaises(ConfigValidationException) as cm:
            conf = Config(args)
            self.assertEqual('Proxy host and port must be set if either of them are not None.', cm.msg)

    def test_get_proxy_string_with_username_and_password(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             "80", "proxy_user", "proxy_password", None, None, 'DEBUG', '234214151', False)
        conf = Config(args)
        self.assertEqual(conf._get_proxy_string(), 'http://proxy_user:proxy_password@126.0.0.1:80')

    def test_get_proxy_string_without_username_and_password(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             "80", None, None, None, None, 'DEBUG', '234214151', False)
        conf = Config(args)
        self.assertEqual(conf._get_proxy_string(), 'http://126.0.0.1:80')

    def test_get_proxy_dictionary_with_username_and_password(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             "80", "proxy_user", "proxy_password", None, None, 'DEBUG', '234214151', False)
        conf = Config(args)
        expected_output = {
            'http': 'http://proxy_user:proxy_password@126.0.0.1:80',
            'https': 'http://proxy_user:proxy_password@126.0.0.1:80'
        }
        self.assertDictEqual(expected_output, conf.get_proxy_dictionary())

    def test_get_proxy_dictionary_without_username_and_password(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, "http://126.0.0.1",
                             "80", None, None, None, None, 'DEBUG', '234214151', False)
        conf = Config(args)
        expected_output = {
            'http': 'http://126.0.0.1:80',
            'https': 'http://126.0.0.1:80'
        }
        self.assertDictEqual(expected_output, conf.get_proxy_dictionary())

    def test_get_proxy_dictionary_without_proxy_host(self):
        args = ArgparserMock(None, None, None, None, None, None, None, "http://api.foo/", None, None,
                             None, None, None, None, None, 'DEBUG', '234214151', False)
        conf = Config(args)
        self.assertIsNone(conf.get_proxy_dictionary())
