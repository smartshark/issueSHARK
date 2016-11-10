import time

import sys
import timeit
import datetime

from mongoengine import NotUniqueError, DoesNotExist
from pymongo.errors import DuplicateKeyError

from issueshark.backends.basebackend import BaseBackend
import logging
import requests
import dateutil.parser

from issueshark.storage.models import Issue, People, Project, Comment, Commit, Event

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

        self.people = {}

    def process(self):
        logger.info("Starting the collection process...")

        try:
            project_id = Project.objects(url=self.config.project_url).get().id
        except DoesNotExist:
            logger.error('Project not found. Use vcsSHARK beforehand!')
            sys.exit(1)

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

        # Otherwise, go through all issues
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

        mongo_issue_id = issue.save().id

        # Process comments
        self._process_comments(str(issue.system_id), mongo_issue_id)

        # Process events
        self._process_events(str(issue.system_id), mongo_issue_id, project_id)

    def _process_events(self, system_id, mongo_issue_id, project_id):
        target_url = '%s/%s/events' % (self.config.tracking_url, system_id)
        events = self._send_request(target_url)

        events_to_store = []
        for raw_event in events:
            created_at = dateutil.parser.parse(raw_event['created_at'])

            # If the event is already saved, we can just continue, because nothing will change on the event
            try:
                Event.objects(system_id=raw_event['id']).get()
                continue
            except DoesNotExist:
                event = Event(system_id=raw_event['id'],
                              issue_id=mongo_issue_id, created_at=created_at, status=raw_event['event'])

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

            if 'assignee' in raw_event and raw_event['assignee'] is not None:
                event.assignee_id = self._get_people(raw_event['assignee']['url'])

            if 'assigner' in raw_event and raw_event['assigner'] is not None:
                event.assigner_id = self._get_people(raw_event['assigner']['url'])

            if 'milestone' in raw_event:
                event.milestone = raw_event['milestone']['title']

            if 'label' in raw_event:
                event.label = raw_event['label']['name']

            events_to_store.append(event)

        # Bulk insert to database
        if events_to_store:
            Event.objects.insert(events_to_store, load_bulk=False)

    def _process_comments(self, system_id, mongo_issue_id):
        target_url = '%s/%s/comments' % (self.config.tracking_url, system_id)
        comments = self._send_request(target_url)

        comments_to_insert = []
        for raw_comment in comments:
            created_at = dateutil.parser.parse(raw_comment['created_at'])
            try:
                Comment.objects(system_id=raw_comment['id']).get()
                continue
            except DoesNotExist:
                comment = Comment(
                    system_id=raw_comment['id'],
                    issue_id=mongo_issue_id,
                    created_at=created_at,
                    author_id=self._get_people(raw_comment['user']['url']),
                    comment=raw_comment['body'],
                )
                comments_to_insert.append(comment)

        # If comments need to be inserted -> bulk insert
        if comments_to_insert:
            Comment.objects.insert(comments_to_insert, load_bulk=False)

    def get_issues(self, search_state='all', start_date=None, sorting='asc', pagecount=1):
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

        people_id = People.objects(name=name, email=email).upsert_one(name=name, email=email).id
        self.people[user_url] = people_id
        return people_id

    def _send_request(self, url):
        logger.debug("Sending request to url: %s" % url)
        headers = {'Authorization': 'token %s' % self.config.token}

        if self.config.use_proxy:
            proxies = {
              'http': self.config.get_proxy_string(),
              'https': self.config.get_proxy_string(),
            }
            resp = requests.get(url, headers=headers, proxies=proxies)
        else:
            resp = requests.get(url, headers=headers)

        if resp.status_code != 200:
            logger.error("Problem with getting data from github via url %s. Error: %s" % (url, resp.json()['message']))

        # It can happen that we exceed the github api limit. If we have only 1 request left we will wait
        if int(resp.headers['X-RateLimit-Remaining'] == 1):

            # We get the reset time (UTC Epoch seconds)
            time_when_reset = datetime.datetime.fromtimestamp(float(resp.headers['X-RateLimit-Reset']))
            now = datetime.datetime.now()

            # Then we substract and add 10 seconds to it (so that we do not request directly at the threshold
            waiting_time = ((time_when_reset-now).total_seconds())+10

            logger.info("Only got one request left on Github API. Waiting for %0.5f seconds...")
            resp = requests.get(url)

        logger.debug('Got response: %s' % resp.json())

        return resp.json()

