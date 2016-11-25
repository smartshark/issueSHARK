import urllib.parse

import requests


class BugzillaApiException(Exception):
    pass


class BugzillaAgent(object):
    def __init__(self, logger, config):
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

    def get_bug_list(self, last_change_time=None, offset=1):
        options = {
            'product': self.project_name,
            'offset': offset
        }

        if last_change_time is not None:
            options['last_change_time'] = last_change_time

        return self._send_request('bug', options)
        pass

    def get_user(self, id, options=None):
        return self._send_request('user/'+str(id), options)

    def _send_request(self, endpoint, options):
        query = '%s' % endpoint

        # The api accepts two things: first arrays, where we need to set the name all the time before the value
        # meaning: product: ['Firefox', 'Ant'] will be transformed to &product=Firefox&product=Ant
        # Second, they accept normal strings
        if options is not None:
            for key, value in options.items():
                if isinstance(value, list):
                    for item in value:
                        query += '&%s=%s' % (key, item)
                else:
                    query += '&%s=%s' % (key, value)

        if self.api_key is not None:
            query += '&api_key=%s' % self.api_key

        if self.api_key is None and self.username is not None and self.password is not None:
            query += '&login=%s&password=%s' % (urllib.parse.quote_plus(self.username),
                                                urllib.parse.quote_plus(self.password))

        # We replace the first '&' with an '?'
        query = query.replace('&', '?', 1)
        request = '%s/%s' % (self.base_url, query)

        self.logger.info('Sending request %s...' % request)
        resp = requests.get(request, proxies=self.proxy)

        if resp.status_code != 200:
            self.logger.error("Problem with getting data via url %s. Error: %s" % (request, resp.json()['message']))

        self.logger.debug('Got response: %s' % resp.json())

        return resp.json()
