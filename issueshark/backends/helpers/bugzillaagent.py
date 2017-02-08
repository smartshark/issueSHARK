import urllib.parse

import requests
import time

from collections import OrderedDict


class BugzillaApiException(Exception):
    """
    Exception that is thrown, if there was a problem with the bugzilla API
    """
    pass


class BugzillaAgent(object):
    """
    Class that is used to connect to the bugzilla API
    """
    def __init__(self, logger, config):
        """
        Initialization

        :param logger: logger that can be used (see: :mod:`logging`)
        :param config: config of class :class:`~issueshark.config.Config`
        """
        parsed_url = urllib.parse.urlparse(config.tracking_url)

        # Get project name
        self.logger = logger
        self.project_name = urllib.parse.parse_qs(parsed_url.query)['product'][0]

        # Get base url
        path = parsed_url.path.split('/')
        path_without_endpoint = '/'.join(path[0:len(path)-1])
        self.base_url = parsed_url.scheme+"://"+parsed_url.netloc+path_without_endpoint

        self.username = config.issue_user
        self.password = config.issue_password
        self.api_key = config.token
        self.proxy = config.get_proxy_dictionary()

        if self.username is not None and self.password is None:
            raise BugzillaApiException('If a username is given, a password needs to be given too!')

    def get_bug_list(self, last_change_time=None, offset=0, limit=50):
        """
        Gets a list of bugs from the bugzilla API

        :param last_change_time: time since the bug was last changed
        :param offset: offset of the list that is returned (e.g., if 100 bugs were found and offset is 10 Bug 11-100 is returned)
        :param limit: limits the number of bugs that are returned
        """
        options = {
            'product': self.project_name,
            'offset': offset,
            'limit': limit,
            'order': 'creation_time%20ASC'
        }

        if last_change_time is not None:
            options['last_change_time'] = last_change_time

        return self._send_request('bug', options)['bugs']

    def get_user(self, id, options=None):
        """
        Gets the user via the id

        :param id: id of the user
        :param options: options for the request
        """
        try:
            return self._send_request('user/'+str(id), options)['users'][0]
        except KeyError:
            return None

    def get_issue_history(self, external_issue_id, new_since=None):
        """
        Gets the issue history for a specific issue

        :param external_issue_id: id of the issue how it is called in the ITS
        :param new_since: gets only these history, that is new since this date
        """
        options = {}

        if new_since is not None:
            options['new_since'] = new_since

        return self._send_request(('bug/%s/history' % external_issue_id), new_since)['bugs'][0]['history']

    def get_comments(self, external_issue_id, new_since=None):
        """
        Get comments for a specific issue

        :param external_issue_id: id of the issue how it is called in the ITS
        :param new_since: gets only these comments, that are new since this date
        """
        options = {}

        if new_since is not None:
            options['new_since'] = new_since

        return self._send_request(('bug/%s/comment' % external_issue_id), new_since)['bugs'][str(external_issue_id)]['comments']

    def _build_query(self, endpoint, options):
        if options is not None:
            sorted_options = OrderedDict(sorted(options.items()))
        else:
            sorted_options = None
        query = '%s' % endpoint

        # The api accepts two things: first arrays, where we need to set the name all the time before the value
        # meaning: product: ['Firefox', 'Ant'] will be transformed to &product=Firefox&product=Ant
        # Second, they accept normal strings
        if sorted_options is not None:
            for key, value in sorted_options.items():
                if isinstance(value, list):
                    for item in value:
                        query += '&%s=%s' % (key, item)
                else:
                    if 'last_change_time' in key:
                        query += '&%s=%s' % (key, urllib.parse.quote_plus(str(value)))
                    else:
                        query += '&%s=%s' % (key, value)

        if self.api_key is not None:
            query += '&api_key=%s' % self.api_key

        if self.api_key is None and self.username is not None and self.password is not None:
            query += '&login=%s&password=%s' % (urllib.parse.quote_plus(self.username),
                                                urllib.parse.quote_plus(self.password))

        # We replace the first '&' with an '?'
        query = query.replace('&', '?', 1)
        return '%s/%s' % (self.base_url, query)

    def _send_request(self, endpoint, options):
        """
        Sends a request to a specific endpoint of the bugzilla API using specific options

        :param endpoint: endpoint to which the request should be sent (e.g., user/)
        :param options: options for the request
        """
        request = self._build_query(endpoint, options)

        self.logger.info('Sending request %s...' % request)
        got_no_response = True
        timeout_start = time.time()
        timeout = 300  # 5 minutes

        # Retrieve the issue via the client and retry as long as the timeout is not running out
        while got_no_response and time.time() < timeout_start + timeout:
            try:
                resp = requests.get(request, proxies=self.proxy)
                if resp.status_code != 200:
                    self.logger.error("Problem with getting data via url %s. Error: %s" %
                                      (request, resp.json()['message']))
                else:
                    got_no_response = False

                self.logger.debug('Got response: %s' % resp.json())
                return resp.json()
            except Exception:
                time.sleep(10)
        self.logger.error('Something went wrong with getting data via url %s!' % request)