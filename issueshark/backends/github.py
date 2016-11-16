import time

import sys
import datetime

from mongoengine import DoesNotExist
from requests.auth import HTTPBasicAuth

from issueshark.backends.basebackend import BaseBackend
import logging
import requests
import dateutil.parser

from issueshark.storage.models import Issue, People, Project, IssueComment, Commit, Event

logger = logging.getLogger('backend')
STATE_ALL = 'all'
STATE_CLOSED = 'closed'
STATE_OPEN = 'open'


class GitHubAPIError(Exception):
    pass


class GithubBackend(BaseBackend):
    @property
    def identifier(self):
        return 'github'

    def __init__(self, cfg):
        super().__init__(cfg)

        logger.setLevel(self.debug_level)
        self.people = {}

    def process(self, project_id):
        logger.info("Starting the collection process...")

        # Get last modification date (since then, we will collect bugs)
        last_issue = Issue.objects(project_id=project_id).order_by('-updated_at').only('updated_at').first()
        starting_date = None
        if last_issue is not None:
            starting_date = last_issue.updated_at

        # Get all issues
        issues = self.get_issues(start_date=starting_date)

        # If no new bugs found, return
        if len(issues) == 0:
            logger.info('No new issues found. Exiting...')
            sys.exit(0)

        # Otherwise, go through all issues (and all pages)
        page_number = 1
        while len(issues) > 0:
            for issue in issues:
                self.store_issue(issue, project_id)
            page_number += 1
            issues = self.get_issues(pagecount=page_number, start_date=starting_date)

    def store_issue(self, raw_issue, project_id):
        logger.debug('Processing issue %s' % raw_issue)
        updated_at = dateutil.parser.parse(raw_issue['updated_at'])
        created_at = dateutil.parser.parse(raw_issue['created_at'])

        try:
            # We can not return here, as the issue might be updated. This means, that the title could be updated
            # as well as comments and new events
            issue = Issue.objects(project_id=project_id, system_id=raw_issue['number']).get()
        except DoesNotExist:
            issue = Issue(project_id=project_id, system_id=raw_issue['number'])

        issue.title = raw_issue['title']
        issue.desc = raw_issue['body']
        issue.updated_at = updated_at
        issue.created_at = created_at

        mongo_issue = issue.save()

        # Process comments
        self._process_comments(str(issue.system_id), mongo_issue)

        # Process events
        self._process_events(str(issue.system_id), mongo_issue, project_id)

    def _process_events(self, system_id, mongo_issue, project_id):
        # Get all events to the corresponding issue
        target_url = '%s/%s/events' % (self.config.tracking_url, system_id)
        events = self._send_request(target_url)

        # Go through all events and create mongo objects from it
        events_to_store = []
        for raw_event in events:
            created_at = dateutil.parser.parse(raw_event['created_at'])

            # If the event is already saved, we can just continue, because nothing will change on the event
            try:
                Event.objects(system_id=raw_event['id']).get()
                continue
            except DoesNotExist:
                event = Event(system_id=raw_event['id'],
                              issue_id=mongo_issue.id, created_at=created_at, status=raw_event['event'])

            if raw_event['commit_id'] is not None:
                # It can happen that a commit from another repository references this issue. Therefore, we can not
                # find the commit, as it is not part of THIS repository
                try:
                    event.commit_id = Commit.objects(projectId=project_id, revisionHash=raw_event['commit_id'])\
                        .only('id').get().id
                except DoesNotExist:
                    pass

            if 'actor' in raw_event and raw_event['actor'] is not None:
                event.author_id = self._get_people(raw_event['actor']['url'])

            self._set_old_and_new_value_for_event(event, raw_event)

            # if event is renamed, then the title was renamed and we need to overwrite the value of the mongo issue
            # and save it again
            if raw_event['event'] == 'renamed' and 'rename' in raw_event:
                mongo_issue.title = raw_event['rename']['from']
                mongo_issue.save()

            events_to_store.append(event)

        # Bulk insert to database
        if events_to_store:
            Event.objects.insert(events_to_store, load_bulk=False)

    def _set_old_and_new_value_for_event(self, event, raw_event):
        # Sets the old and new value for an event (what was changed)

        if raw_event['event'] == 'assigned':
            if 'assignee' in raw_event and raw_event['assignee'] is not None:
                event.new_value = self._get_people(raw_event['assignee']['url'])

            #if 'assigner' in raw_event and raw_event['assigner'] is not None:
            #    event.assigner_id = self._get_people(raw_event['assigner']['url'])

        if raw_event['event'] == 'unassigned':
            if 'assignee' in raw_event and raw_event['assignee'] is not None:
                event.old_value = self._get_people(raw_event['assignee']['url'])

            #if 'assigner' in raw_event and raw_event['assigner'] is not None:
            #    event.assigner_id = self._get_people(raw_event['assigner']['url'])

        if raw_event['event'] == 'labeled' and 'label' in raw_event:
            event.new_value = raw_event['label']['name']

        if raw_event['event'] == 'unlabeled' and 'label' in raw_event:
            event.old_value = raw_event['label']['name']

        if raw_event['event'] == 'milestoned' and 'milestone' in raw_event:
            event.new_value = raw_event['milestone']['title']

        if raw_event['event'] == 'demilestoned' and 'milestone' in raw_event:
            event.old_value = raw_event['milestone']['title']

        if raw_event['event'] == 'renamed' and 'rename' in raw_event:
            event.old_value = raw_event['rename']['from']
            event.new_value = raw_event['rename']['to']

    def _process_comments(self, system_id, mongo_issue):
        # Get all the comments for the corresponding issue
        target_url = '%s/%s/comments' % (self.config.tracking_url, system_id)
        comments = self._send_request(target_url)

        # Go through all comments
        comments_to_insert = []
        for raw_comment in comments:
            created_at = dateutil.parser.parse(raw_comment['created_at'])
            try:
                IssueComment.objects(system_id=raw_comment['id']).get()
                continue
            except DoesNotExist:
                comment = IssueComment(
                    system_id=raw_comment['id'],
                    issue_id=mongo_issue.id,
                    created_at=created_at,
                    author_id=self._get_people(raw_comment['user']['url']),
                    comment=raw_comment['body'],
                )
                comments_to_insert.append(comment)

        # If comments need to be inserted -> bulk insert
        if comments_to_insert:
            IssueComment.objects.insert(comments_to_insert, load_bulk=False)

    def get_issues(self, search_state='all', start_date=None, sorting='asc', pagecount=1):
        # Creates the target url for getting the issues
        target_url = self.config.tracking_url + "?state=" + search_state + "&page=" + str(pagecount) \
            + "&per_page=100&sort=updated&direction=" + sorting

        if start_date:
            target_url = target_url + "&since=" + str(start_date)

        issues = self._send_request(target_url)
        return issues

    def _get_people(self, user_url):
        # Check if user was accessed before. This reduces the amount of API requests to github
        if user_url in self.people:
            return self.people[user_url]

        raw_user = self._send_request(user_url)
        name = raw_user['name']

        if name is None:
            name = raw_user['login']

        email = raw_user['email']
        if email is None:
            email = 'null'

        people_id = People.objects(
            name=name,
            email=email
        ).upsert_one(name=name, email=email, username=raw_user['login']).id
        self.people[user_url] = people_id
        return people_id

    def _send_request(self, url):
        logger.debug("Sending request to url: %s" % url)

        auth = None
        headers = None

        # If tokens are used, set the header, if not use basic authentication
        if self.config.use_token():
            headers = {'Authorization': 'token %s' % self.config.token}
        else:
            auth = HTTPBasicAuth(self.config.issue_user, self.config.issue_password)

        # Make the request
        resp = requests.get(url, headers=headers, proxies=self.config.get_proxy_dictionary(), auth=auth)

        if resp.status_code != 200:
            logger.error("Problem with getting data from github via url %s. Error: %s" % (url, resp.json()['message']))

        # It can happen that we exceed the github api limit. If we have only 1 request left we will wait
        if int(resp.headers['X-RateLimit-Remaining']) <= 1:

            # We get the reset time (UTC Epoch seconds)
            time_when_reset = datetime.datetime.fromtimestamp(float(resp.headers['X-RateLimit-Reset']))
            now = datetime.datetime.now()

            # Then we substract and add 10 seconds to it (so that we do not request directly at the threshold
            waiting_time = ((time_when_reset-now).total_seconds())+10

            logger.info("Github API limit exceeded. Waiting for %0.5f seconds..." % waiting_time)
            time.sleep(waiting_time)

            resp = requests.get(url)

        logger.debug('Got response: %s' % resp.json())

        return resp.json()

