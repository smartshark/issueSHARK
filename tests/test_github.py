import configparser
import unittest
import os
import json
import datetime

import logging
import mock
from bson import ObjectId
from mongoengine import connect
import mongomock
import mongoengine
from issueshark.backends.github import GithubBackend
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

class GithubBackendTest(unittest.TestCase):

    def setUp(self):
        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/github/people.json", 'r', encoding='utf-8') as people_file:
            self.person = json.load(people_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/github/issue_6131.json", 'r', encoding='utf-8') as issues_file:
            self.issue_6131 = json.load(issues_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/github/issue_6131_events.json", 'r', encoding='utf-8') as event_file:
            self.events_issue_6131 = json.load(event_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/github/issue_6131_comments.json", 'r', encoding='utf-8') as cmt_file:
            self.comments_issue_6131 = json.load(cmt_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/github/issue_6050.json", 'r', encoding='utf-8') as issues_file:
            self.issue_6050 = json.load(issues_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/github/issue_6050_events.json", 'r', encoding='utf-8') as event_file:
            self.events_issue_6050 = json.load(event_file)

        with open(os.path.dirname(os.path.realpath(__file__)) + "/data/github/issue_6050_comments.json", 'r', encoding='utf-8') as cmt_file:
            self.comments_issue_6050 = json.load(cmt_file)

        # Create testconfig
        config = configparser.ConfigParser()
        config.read(os.path.dirname(os.path.realpath(__file__)) + "/data/used_test_config.cfg")
        mongoengine.connection.disconnect()
        mongoengine.connect('mongoenginetest', host='mongodb://localhost', mongo_client_class=mongomock.MongoClient)

        Project.drop_collection()
        IssueSystem.drop_collection()
        Issue.drop_collection()
        IssueComment.drop_collection()
        Event.drop_collection()

        self.project_id = Project(name='Composer').save().id
        self.issues_system_id = IssueSystem(project_id=self.project_id, url="http://blub.de",
                                            last_updated=datetime.datetime.now()).save().id

        self.conf = ConfigMock(None, None, None, None, None, None, 'Ant', 'http://blub.de', 'github', None, None, None,
                               None, None, None, 'DEBUG', '123')


    @mock.patch('issueshark.backends.github.GithubBackend._send_request')
    def test_get_people(self, mock_request):
        mock_request.return_value = self.person

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend._get_people('mocked_URL')

        mongo_person = People.objects(username='TomasVotruba').get()
        self.assertEqual('info@tomasvotruba.cz', mongo_person.email)
        self.assertEqual('Tomáš Votruba', mongo_person.name)

    @mock.patch('issueshark.backends.github.GithubBackend._get_people')
    def test_store_issue_two_times(self, mock_people):
        mock_people.return_value = ObjectId('5899f79cfc263613115e5ccb')

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend.store_issue(self.issue_6131)
        gh_backend.store_issue(self.issue_6131)

        mongo_issue = Issue.objects(external_id='6131').all()
        self.assertEqual(1, len(mongo_issue))

    @mock.patch('issueshark.backends.github.GithubBackend._get_people')
    def test_store_issue(self, mock_people):
        mock_people.return_value = ObjectId('5899f79cfc263613115e5ccb')

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend.store_issue(self.issue_6131)

        mongo_issue = Issue.objects(external_id='6131').get()
        self.assertEqual(self.issues_system_id, mongo_issue.issue_system_id)
        self.assertEqual('Inexplainable dependency conflict', mongo_issue.title)
        self.assertEqual('Steps to reproduce:\r\n\r\nhttps://github.com/Berdir/strict-dependency-bug\r\n\r\nOutput:'
                         '\r\n\r\n```\r\nYour requirements could not be resolved to an installable set of packages.'
                         '\r\n\r\n  Problem 1\r\n    - berdir/strict-dependency-bug 1.0.0 requires '
                         'webflo/drupal-core-strict 8.2.6 -> satisfiable by webflo/drupal-core-strict[8.2.6].\r\n    -'
                         ' berdir/strict-dependency-bug 1.0.1 requires webflo/drupal-core-strict 8.2.6 -> satisfiable'
                         ' by webflo/drupal-core-strict[8.2.6].\r\n    - Conclusion: don\'t install '
                         'webflo/drupal-core-strict 8.2.6\r\n    - Installation request for '
                         'berdir/strict-dependency-bug ^1.0 -> satisfiable by berdir/strict-dependency-bug[1.0.0, 1.0.1]'
                         '.\r\n\r\n\r\nInstallation failed, reverting ./composer.json to its original content.'
                         '\r\n```\r\n\r\nThe problem is related to having more than one valid version in '
                         'strict-dependency-bug, if you do \"composer require berdir/strict-dependency-bug:1.0.1\" '
                         'instead, it installs fine.\r\n\r\nThe error doesn\'t really make sense, how can there be a '
                         'conflict because of two identical versions?\r\n\r\ndrupal-core-strict is a package that aims '
                         'to enforce the same dependencies as defined in Drupal\'s composer.lock. We\'ve noticed that '
                         'sometimes there are unexpected changes in untested dependencies versions, this is an idea to'
                         ' prevent that.\r\n\r\n(That might or might not really be a good idea. I mostly sharing this '
                         'in case there\'s a deeper depencency resolving problem here)\r\n\r\nAny idea what\'s going on? ',
        mongo_issue.desc)
        self.assertEqual(datetime.datetime(2017,2,4,14,33,47), mongo_issue.created_at)
        self.assertEqual(datetime.datetime(2017,2,5,13,24,9), mongo_issue.updated_at)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), mongo_issue.reporter_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), mongo_issue.creator_id)
        self.assertEqual('open', mongo_issue.status)
        self.assertListEqual(['Solver', 'Support'], mongo_issue.labels)

    @mock.patch('issueshark.backends.github.GithubBackend._get_people')
    def test_store_issue_2(self, mock_people):
        mock_people.return_value = ObjectId('5899f79cfc263613115e5ccb')

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend.store_issue(self.issue_6050)

        mongo_issue = Issue.objects(external_id='6050').get()
        self.assertEqual(self.issues_system_id, mongo_issue.issue_system_id)
        self.assertEqual("Local path package does not autoload classes", mongo_issue.title)
        self.assertEqual("I'm about to write post about local packages, but there is one thing that blocks me.\r\n\r\nI "
                         "use [path local package](https://getcomposer.org/doc/05-repositories.md#path).\r\n\r\nI need "
                         "to autoload-dev and require-dev dependencies so I could run tests on those local packages."
                         "\r\nWithout that, I have to put this into main `composer.json`, which kinda kills the "
                         "decoupling to path package.\r\n\r\nIs there a way to do that?\r\n\r\n---\r\n\r\nOutput of "
                         "`composer diagnose`:\r\n\r\n```json\r\nChecking composer.json: OK\r\nChecking platform "
                         "settings: OK\r\nChecking git settings: OK\r\nChecking http connectivity to packagist: "
                         "OK\r\nChecking https connectivity to packagist: OK\r\nChecking github.com oauth access: "
                         "OK\r\nChecking disk free space: OK\r\nChecking pubkeys: \r\nTags Public Key Fingerprint: "
                         "57815BA2 7E54DC31 7ECC7CC5 573090D0  87719BA6 8F3BB723 4E5D42D0 84A14642\r\nDev Public "
                         "Key Fingerprint: 4AC45767 E5EC2265 2F0C1167 CBBB8A2B  0C708369 153E328C AD90147D "
                         "AFE50952\r\nOK\r\nChecking composer version: OK\r\n```", mongo_issue.desc)
        self.assertEqual(datetime.datetime(2017, 1, 7, 12, 55, 43), mongo_issue.created_at)
        self.assertEqual(datetime.datetime(2017, 1, 11, 8, 17, 12), mongo_issue.updated_at)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), mongo_issue.reporter_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), mongo_issue.creator_id)
        self.assertEqual('open', mongo_issue.status)
        self.assertListEqual(['Support'], mongo_issue.labels)


    @mock.patch('issueshark.backends.github.GithubBackend._send_request')
    @mock.patch('issueshark.backends.github.GithubBackend._get_people')
    def test_store_events_two_times(self, mock_people, mock_request):
        mock_people.return_value = ObjectId('5899f79cfc263613115e5ccb')
        mock_request.return_value = self.events_issue_6131

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend.store_issue(self.issue_6131)
        gh_backend._process_events('6131', Issue.objects(external_id='6131').get())
        gh_backend._process_events('6131', Issue.objects(external_id='6131').get())

        mongo_events = Event.objects.order_by('+created_at', '+external_id')
        self.assertEqual(6, len(mongo_events))

    @mock.patch('issueshark.backends.github.GithubBackend._send_request')
    @mock.patch('issueshark.backends.github.GithubBackend._get_people')
    def test_store_events(self, mock_people, mock_request):
        mock_people.return_value = ObjectId('5899f79cfc263613115e5ccb')
        mock_request.return_value = self.events_issue_6131

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend.store_issue(self.issue_6131)
        gh_backend._process_events('6131', Issue.objects(external_id='6131').get())

        mongo_issue = Issue.objects(external_id='6131').get()

        mongo_events = Event.objects.order_by('+created_at', '+external_id')
        self.assertEqual(6, len(mongo_events))

        event = mongo_events[0]
        self.assertEqual(datetime.datetime(2017, 2, 4, 14, 35, 53), event.created_at)
        self.assertEqual(949130826, event.external_id)
        self.assertEqual(mongo_issue.id, event.issue_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), event.author_id)
        self.assertEqual('renamed', event.status)
        self.assertEqual('Inexplainable', event.old_value)
        self.assertEqual('Inexplainable dependency conflict', event.new_value)

        event = mongo_events[1]
        self.assertEqual(datetime.datetime(2017, 2, 5, 11, 25, 57), event.created_at)
        self.assertEqual(949403950, event.external_id)
        self.assertEqual(mongo_issue.id, event.issue_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), event.author_id)
        self.assertEqual('labeled', event.status)
        self.assertEqual(None, event.old_value)
        self.assertEqual('Solver', event.new_value)

        event = mongo_events[2]
        self.assertEqual(datetime.datetime(2017, 2, 5, 11, 25, 57), event.created_at)
        self.assertEqual(949403951, event.external_id)
        self.assertEqual(mongo_issue.id, event.issue_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), event.author_id)
        self.assertEqual('labeled', event.status)
        self.assertEqual(None, event.old_value)
        self.assertEqual('Support', event.new_value)

        event = mongo_events[3]
        self.assertEqual(datetime.datetime(2017, 2, 5, 11, 27, 17), event.created_at)
        self.assertEqual(949404323, event.external_id)
        self.assertEqual(mongo_issue.id, event.issue_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), event.author_id)
        self.assertEqual('mentioned', event.status)

        event = mongo_events[4]
        self.assertEqual(datetime.datetime(2017, 2, 5, 11, 27, 17), event.created_at)
        self.assertEqual(949404324, event.external_id)
        self.assertEqual(mongo_issue.id, event.issue_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), event.author_id)
        self.assertEqual('subscribed', event.status)

        event = mongo_events[5]
        self.assertEqual(datetime.datetime(2017,2,6,23,19,52), event.created_at)
        self.assertEqual(951210829, event.external_id)
        self.assertEqual(mongo_issue.id, event.issue_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), event.author_id)
        self.assertEqual('referenced', event.status)

    @mock.patch('issueshark.backends.github.GithubBackend._send_request')
    @mock.patch('issueshark.backends.github.GithubBackend._get_people')
    def test_store_events_2(self, mock_people, mock_request):
        mock_people.return_value = ObjectId('5899f79cfc263613115e5ccb')
        mock_request.return_value = self.events_issue_6050

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend.store_issue(self.issue_6050)
        gh_backend._process_events('6050', Issue.objects(external_id='6050').get())

        mongo_issue = Issue.objects(external_id='6050').get()

        mongo_events = Event.objects.order_by('+created_at', '+external_id')
        self.assertEqual(3, len(mongo_events))

        event = mongo_events[0]
        self.assertEqual(datetime.datetime(2017, 1, 7, 13, 2, 14), event.created_at)
        self.assertEqual(914944953, event.external_id)
        self.assertEqual(mongo_issue.id, event.issue_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), event.author_id)
        self.assertEqual('closed', event.status)

        event = mongo_events[1]
        self.assertEqual(datetime.datetime(2017, 1, 10, 11, 3, 36), event.created_at)
        self.assertEqual(917330267, event.external_id)
        self.assertEqual(mongo_issue.id, event.issue_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), event.author_id)
        self.assertEqual('reopened', event.status)

        event = mongo_events[2]
        self.assertEqual(datetime.datetime(2017, 1, 11, 7, 41, 25), event.created_at)
        self.assertEqual(918698316, event.external_id)
        self.assertEqual(mongo_issue.id, event.issue_id)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), event.author_id)
        self.assertEqual('labeled', event.status)
        self.assertEqual(None, event.old_value)
        self.assertEqual('Support', event.new_value)

    @mock.patch('issueshark.backends.github.GithubBackend._send_request')
    @mock.patch('issueshark.backends.github.GithubBackend._get_people')
    def test_store_comments_two_times(self, mock_people, mock_request):
        mock_people.return_value = ObjectId('5899f79cfc263613115e5ccb')
        mock_request.return_value = self.comments_issue_6131

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend.store_issue(self.issue_6131)

        mongo_issue = Issue.objects(external_id='6131').get()
        gh_backend._process_comments('6131', mongo_issue)
        gh_backend._process_comments('6131', mongo_issue)

        mongo_comments = IssueComment.objects.order_by('+created_at', '+external_id')
        self.assertEqual(3, len(mongo_comments))

    @mock.patch('issueshark.backends.github.GithubBackend._send_request')
    @mock.patch('issueshark.backends.github.GithubBackend._get_people')
    def test_store_comments(self, mock_people, mock_request):
        mock_people.return_value = ObjectId('5899f79cfc263613115e5ccb')
        mock_request.return_value = self.comments_issue_6131

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend.store_issue(self.issue_6131)

        mongo_issue = Issue.objects(external_id='6131').get()
        gh_backend._process_comments('6131', mongo_issue)

        mongo_comments = IssueComment.objects.order_by('+created_at', '+external_id')
        self.assertEqual(3, len(mongo_comments))

        comment = mongo_comments[0]
        self.assertEqual(277513605, comment.external_id)
        self.assertEqual(mongo_issue.id, comment.issue_id)
        self.assertEqual(datetime.datetime(2017, 2, 5, 11, 27, 17), comment.created_at)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), comment.author_id)
        self.assertEqual("Might be interesting for @naderman  to look at as it seems to happen with a minimal "
                         "subset of packages, but can you please share the smallest possible composer.json you "
                         "use to reproduce this?", comment.comment)

        comment = mongo_comments[1]
        self.assertEqual(277519109, comment.external_id)
        self.assertEqual(mongo_issue.id, comment.issue_id)
        self.assertEqual(datetime.datetime(2017, 2, 5, 13, 15, 54), comment.created_at)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), comment.author_id)
        self.assertEqual("Thanks for checking.\r\n\r\nI can try, but I suspect it only happens in combination with "
                         "starting off with a drupal-project. I just tried the last two commands (adding the repo and"
                         " requiring it) after initializing a new and empty composer.json and then it works "
                         "fine.\r\n\r\nI guess it is the combination of depending on drupal/core which has the same "
                         "dependencies as drupal-core-strict, just not as strict. But testing that alone also doesn't "
                         "really give the same. Whe I just run composer require drupal/core and then try to add mine "
                         "then I do get conflicts, but they go away after a rm -rf composer.lock vendor/.\r\n\r\nSo as"
                         " far as I see, it only happens when you actually start of with drupal-project.\r\n\r\n",
                         comment.comment)

        comment = mongo_comments[2]
        self.assertEqual(277519551, comment.external_id)
        self.assertEqual(mongo_issue.id, comment.issue_id)
        self.assertEqual(datetime.datetime(2017, 2, 5, 13, 23, 43), comment.created_at)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), comment.author_id)
        self.assertEqual("Thanks for helping. I did some testing a while ago over in"
                         " https://gist.github.com/webflo/5d8a2310734a9089eb67ab5ec85ce1cd\r\n\r\nIt looks like that "
                         "is works if i add it to the composer.json and run ``composer update`` on the whole set. "
                         "``composer update --with-dependencies`` or ``composer require  --update-with-dependencies``"
                         " does not work.", comment.comment)

    @mock.patch('issueshark.backends.github.GithubBackend._send_request')
    @mock.patch('issueshark.backends.github.GithubBackend._get_people')
    def test_store_comments_2(self, mock_people, mock_request):
        mock_people.return_value = ObjectId('5899f79cfc263613115e5ccb')
        mock_request.return_value = self.comments_issue_6050

        gh_backend = GithubBackend(self.conf, self.issues_system_id, self.project_id)
        gh_backend.store_issue(self.issue_6050)

        mongo_issue = Issue.objects(external_id='6050').get()
        gh_backend._process_comments('6131', mongo_issue)

        mongo_comments = IssueComment.objects.order_by('+created_at', '+external_id')
        self.assertEqual(2, len(mongo_comments))

        comment = mongo_comments[0]
        self.assertEqual(271799582, comment.external_id)
        self.assertEqual(mongo_issue.id, comment.issue_id)
        self.assertEqual(datetime.datetime(2017, 1, 11, 7, 41, 1), comment.created_at)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), comment.author_id)
        self.assertEqual("No, the `autoload-dev` and `require-dev` are root only attributes, meaning that they only "
                         "are read from your root composer.json, not your dependencies.", comment.comment)

        comment = mongo_comments[1]
        self.assertEqual(271805655, comment.external_id)
        self.assertEqual(mongo_issue.id, comment.issue_id)
        self.assertEqual(datetime.datetime(2017, 1, 11, 8, 17, 12), comment.created_at)
        self.assertEqual(ObjectId('5899f79cfc263613115e5ccb'), comment.author_id)
        self.assertEqual("That's what I thought :(\r\n\r\nHow do you use your approach local packages tests then?",
                         comment.comment)








