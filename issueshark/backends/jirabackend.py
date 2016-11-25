import dateutil
import sys

import time
from mongoengine import DoesNotExist

from issueshark.backends.basebackend import BaseBackend
from urllib.parse import urlparse, quote_plus
from jira import JIRA, JIRAError

import logging

from issueshark.mongomodels import *


logger = logging.getLogger('backend')


class JiraException(Exception):
    pass


class JiraBackend(BaseBackend):
    @property
    def identifier(self):
        return 'jira'

    def __init__(self, cfg, issue_system_id, project_id):
        super().__init__(cfg, issue_system_id, project_id)

        logger.setLevel(self.debug_level)
        self.people = {}
        self.jira_client = None

    def process(self):
        logger.info("Starting the collection process...")
        if self.config.use_token():
            raise JiraException('Jira does not support tokens! Use issue_user and issue_password instead')

        # We need to get the name of the project (how it is called in jira, e.g. 'ZOOKEEPER')
        project_name = self.config.tracking_url.split('=')[-1]
        parsed_url = urlparse(self.config.tracking_url)

        # We need to add the original server (e.g. https://issues.apache.org)
        options = {
            'server': parsed_url.scheme+"://"+parsed_url.netloc,
        }

        # If the path does not start with /rest, meaning there is something in between (e.g. "/jira"), we need
        # to add that to the server
        # TODO only works for one path part
        if not parsed_url.path.startswith('/rest'):
            options['server'] = options['server']+'/'+parsed_url.path.split('/')[1]

        # Connect to jira
        self.jira_client = JIRA(options, basic_auth=(self.config.issue_user, self.config.issue_password),
                    proxies=self.config.get_proxy_dictionary())

        # Get last modification date (since then, we will collect bugs)
        last_issue = Issue.objects(issue_system_id=self.issue_system_id).order_by('-updated_at').only('updated_at').first()
        if last_issue is not None:
            starting_date = last_issue.updated_at
            query = "project=%s and updatedDate > '%s' ORDER BY createdDate ASC" % (
                project_name,
                starting_date.strftime('%Y/%m/%d %H:%M')
            )
        else:
            query = "project=%s ORDER BY createdDate ASC" % project_name

        # We search our intital set of issues
        issues = self.jira_client.search_issues(query, startAt=0, maxResults=50, fields='summary')
        logger.debug('Found %d issues via url %s' % (len(issues),
                                                     self.jira_client._get_url('search?jql=%s&startAt=0&maxResults=50' %
                                                                                quote_plus(query))))

        # If no new bugs found, return
        if len(issues) == 0:
            logger.info('No new issues found. Exiting...')
            sys.exit(0)

        # Otherwise, go through all issues
        processed_results = 50
        while len(issues) > 0:
            logger.info("Processing %d issues..." % len(issues))
            for issue in issues:
                self._process_issue(issue.key)

            # Go through the next issues
            issues = self.jira_client.search_issues(query, startAt=processed_results, maxResults=50, fields='summary')
            logger.debug('Found %d issues via url %s' %
                         (len(issues), self.jira_client._get_url('search?jql=%s&startAt=%d&maxResults=50' %
                                                                (quote_plus(query), processed_results))))
            processed_results += 50

    def _transform_jira_issue(self, jira_issue):
        updated_at = dateutil.parser.parse(jira_issue.fields.updated)
        created_at = dateutil.parser.parse(jira_issue.fields.created)
        try:
            # We can not return here, as the issue might be updated. This means, that the title could be updated
            # as well as comments and new events
            new_issue = Issue.objects(issue_system_id=self.issue_system_id, external_id=jira_issue.key).get()
        except DoesNotExist:
            new_issue = Issue(
                issue_system_id=self.issue_system_id,
                external_id=jira_issue.key,
            )

        # if the issue is a sub type we need to set the parent
        if hasattr(jira_issue.fields, 'parent'):
            issue_id = self._get_issue_id_by_system_id(jira_issue.fields.parent.key)
            new_issue.parent_issue_id = issue_id

        new_issue.title = jira_issue.fields.summary
        new_issue.desc = jira_issue.fields.description
        new_issue.created_at = created_at
        new_issue.updated_at = updated_at
        new_issue.issue_type = jira_issue.fields.issuetype.name
        new_issue.creator_id = self._get_people(jira_issue.fields.creator.name,
                                             jira_issue.fields.creator.emailAddress,
                                             jira_issue.fields.creator.displayName)
        new_issue.reporter_id = self._get_people(jira_issue.fields.reporter.name,
                                              jira_issue.fields.reporter.emailAddress,
                                              jira_issue.fields.reporter.displayName)
        new_issue.priority = jira_issue.fields.priority.name
        new_issue.status = jira_issue.fields.status.name
        new_issue.affects_versions = [version.name for version in jira_issue.fields.versions]
        new_issue.components = [component.name for component in jira_issue.fields.components]

        splitted_labels = []
        for label in jira_issue.fields.labels:
            splitted_labels.extend(label.split(" "))
        new_issue.labels = splitted_labels

        if jira_issue.fields.resolution is not None:
            new_issue.resolution = jira_issue.fields.resolution.name

        new_issue.environment=jira_issue.fields.environment
        new_issue.original_time_estimate=jira_issue.fields.timeoriginalestimate

        new_issue.fix_versions = [version.name for version in jira_issue.fields.fixVersions]

        if jira_issue.fields.assignee is not None:
            new_issue.assignee_id = self._get_people(jira_issue.fields.assignee.name,
                                                     name=jira_issue.fields.assignee.displayName,
                                                     email=jira_issue.fields.assignee.emailAddress)

        if jira_issue.fields.issuelinks:
            links = []
            for issue_link in jira_issue.fields.issuelinks:
                if hasattr(issue_link, 'outwardIssue'):
                    issue_id = self._get_issue_id_by_system_id(issue_link.outwardIssue.key)
                else:
                    issue_id = self._get_issue_id_by_system_id(issue_link.inwardIssue.key)

                links.append({'issue_id': issue_id, 'type': issue_link.type.name, 'effect': issue_link.type.outward})
            new_issue.issue_links = links

        return new_issue

    def _process_issue(self, issue_key):
        """
        There are the following steps executed:
        1) Transformation of the jira issue into a mongo db issue (can directly be saved)
        2) Go through the whole history of the jira issue, create events and set back the values
        3) This way, we get the ORIGINAL issue that was posted in jira, which is then saved in the issue collection
        --> Some things can not be turned back, e.g. issue links, as there is information missing in the changelog
        4) Comments of the issue are processed (and stored)

        :param jira_client: connection to the jira instance
        :param issue_key: key of the issue (e.g. ZOOKEEPER-2124)
        :return:
        """
        issue_not_retrieved = True
        timeout_start = time.time()
        timeout = 300  # 5 minutes

        # Retrieve the issue via the client and retry as long as the timeout is not running out
        while issue_not_retrieved and time.time() < timeout_start + timeout:
            try:
                issue = self.jira_client.issue(issue_key, expand='changelog')
                issue_not_retrieved = False
            except JIRAError:
                time.sleep(30)
                pass

        if time.time() >= timeout_start + timeout:
            logger.error('Could not get issue: %s' % issue)
            return

        logger.debug('Processing issue %s via url %s' % (issue,
                                                         self.jira_client._get_url('issue/%s?expand=changelog' % issue)))
        logger.debug('Got fields: %s' % vars(issue.fields))

        # Transform jira issue to mongo issue
        new_issue = self._transform_jira_issue(issue)
        logger.debug('Transformed issue: %s' % new_issue)

        # Go through all events and set back issue items till we get the original one
        events = []
        for history in reversed(issue.changelog.histories):
            i = 0
            for item in reversed(history.items):
                logger.debug('Processing changelog entry: %s' % vars(item))
                # Create event list
                (event, newly_created) = self._process_event(history, item, i, new_issue)
                logger.debug('Newly created?: %s, Resulting event: %s' % (newly_created, event))

                # Append to list if event is not stored in db
                if newly_created:
                    events.append(event)

                # Set back issue
                self._set_back_issue(new_issue, event)

                i += 1
        logger.debug('Original issue to store: %s' % new_issue)

        # Store issue
        if new_issue.id is None:
            # We need to set the status to open here, as this is the first status for every issue
            new_issue.status = 'Open'

        issue_id = new_issue.save().id
        # Set issue_id for event list and bulk write
        if events:
            for event in events:
                event.issue_id = issue_id
            Event.objects.insert(events, load_bulk=False)

        # Store comments of issue
        self._process_comments(issue, issue_id)

    def _process_comments(self, issue, issue_id):

        # Go through all comments of the issue
        comments_to_insert = []
        logger.info('Processing %d comments...' % len(issue.fields.comment.comments))
        for comment in issue.fields.comment.comments:
            logger.debug('Processing comment: %s' % comment)
            created_at = dateutil.parser.parse(comment.created)
            try:
                IssueComment.objects(external_id=comment.id, issue_id=issue_id).get()
                continue
            except DoesNotExist:
                mongo_comment = IssueComment(
                    external_id=comment.id,
                    issue_id=issue_id,
                    created_at=created_at,
                    author_id=self._get_people(comment.author.name, comment.author.emailAddress,
                                               comment.author.displayName),
                    comment=comment.body,
                )
                logger.debug('Resulting comment: %s' % mongo_comment)
                comments_to_insert.append(mongo_comment)

        # If comments need to be inserted -> bulk insert
        if comments_to_insert:
            IssueComment.objects.insert(comments_to_insert, load_bulk=False)

    def _get_issue_id_by_system_id(self, system_id, refresh_key=False):
        if refresh_key:
            system_id = self._get_newest_key_for_issue(system_id)

        try:
            issue_id = Issue.objects(issue_system_id=self.issue_system_id, external_id=system_id).only('id').get().id
        except DoesNotExist:
            issue_id = Issue(issue_system_id=self.issue_system_id, external_id=system_id).save().id

        return issue_id

    def _process_event(self, history, item, i, issue):
        created_at = dateutil.parser.parse(history.created)

        # Maybe this should be  changed when it becomes important
        system_id = str(history.id)+"%%"+str(i)

        # The event can only exist, if the issue is existent
        if issue.id is not None:
            # Try to get the event. If it is already existent, then return directly
            try:
                event = Event.objects(external_id=system_id, issue_id=issue.id).get()
                return event, False
            except DoesNotExist:
                event = Event(
                    external_id=system_id,
                    issue_id=issue.id,
                    created_at=created_at,
                    status=self._replace_item_field_for_storage(item.field).lower(),
                )
        else:
            event = Event(
                external_id=system_id,
                created_at=created_at,
                status=self._replace_item_field_for_storage(item.field).lower(),
            )

        # It can happen that an event does not have an author (e.g., ZOOKEEPER-2218)
        if hasattr(history, 'author'):
            event.author_id = self._get_people(history.author.name, name=history.author.displayName,
                                               email=history.author.emailAddress)

        # Some fields need to be taken care of (e.g., getting the objectid of the assignee)
        if item.field == 'assignee':
            if getattr(item, 'from') is not None:
                event.old_value = self._get_people(getattr(item, 'from'))
            if item.to is not None:
                event.new_value = self._get_people(item.to)
        elif item.field == 'Parent':
            if getattr(item, 'from') is not None:
                event.old_value = self._get_issue_id_by_system_id(getattr(item, 'from'), refresh_key=True)
            if item.to is not None:
                event.new_value = self._get_issue_id_by_system_id(item.to, refresh_key=True)
        elif item.field == 'Link':
            if getattr(item, 'from') is not None:
                event.old_value = self._get_issue_id_by_system_id(getattr(item, 'from'), refresh_key=True)
            if item.to is not None:
                event.new_value = self._get_issue_id_by_system_id(item.to, refresh_key=True)
        else:
            event.old_value = item.fromString
            event.new_value = item.toString

        return event, True

    def _replace_item_field_for_storage(self, status):
        stati_replacements = {
            'assignee': 'assigned',
            'summary': 'renamed'
        }

        # Replace the status message so that it is the same as with github
        if status in stati_replacements:
            return stati_replacements[status]
        else:
            return status

    def _set_back_issue(self, issue, event):
        if event.status == 'description':
            issue.desc = event.old_value
        elif event.status == 'priority':
            issue.priority = event.old_value
        elif event.status == 'status':
            issue.status = event.old_value
        elif event.status == 'resolution':
            issue.resolution = event.old_value
        elif event.status == 'renamed':
            issue.title = event.old_value
        elif event.status == 'issuetype':
            issue.issue_type = event.old_value
        elif event.status == 'environment':
            issue.environment = event.old_value
        elif event.status == 'timeoriginalestimate':
            issue.original_time_estimate = event.old_value
        elif event.status == 'assigned':
            if event.old_value is not None:
                issue.assignee_id = event.old_value
            else:
                issue.assignee_id = None
        elif event.status == 'parent':
            if event.old_value is not None:
                issue.parent_issue_id = event.old_value
            else:
                issue.parent_issue_id = None
        elif event.status == 'version':
            # If a version was removed, we need to add it to get the older state
            if not event.new_value and event.old_value:
                issue.affects_versions.append(event.old_value)

            if not event.old_value and event.new_value:
                issue.affects_versions.remove(event.new_value)

            if event.old_value and event.new_value:
                issue.affects_versions.add(event.old_value)
                issue.affects_versions.remove(event.new_value)
        elif event.status == 'component':
            # If a component was removed, we need to add it to get the older state
            if not event.new_value and event.old_value:
                issue.components.append(event.old_value)

            if not event.old_value and event.new_value:
                issue.components.remove(event.new_value)

            if event.old_value and event.new_value:
                issue.components.add(event.old_value)
                issue.components.remove(event.new_value)

        elif event.status == 'labels':
            # If a label was removed, we need to add it to get the older state
            if not event.new_value and event.old_value:
                for old_label in event.old_value.split(" "):
                    issue.labels.append(old_label)

            if not event.old_value and event.new_value:
                for new_label in event.new_value.split(" "):
                    issue.labels.remove(new_label)

            if event.old_value and event.new_value:
                for old_label in event.old_value.split(" "):
                    issue.labels.append(old_label)

                # It can happen, that one label gets renamed into two separate labels (e.g. ZOOKEEPER-2512)
                for new_label in event.new_value.split(" "):
                    issue.labels.remove(new_label)
        elif event.status == 'fix version':
            # If a fixed version was removed, we need to add it to get the older state
            if not event.new_value and event.old_value:
                issue.fix_versions.append(event.old_value)

            if not event.old_value and event.new_value:
                issue.fix_versions.remove(event.new_value)

            if event.old_value and event.new_value:
                issue.fix_versions.append(event.old_value)
                issue.fix_versions.remove(event.new_value)
        elif event.status == 'link':
            # If a link was removed, we need to add it to get the older state
            if event.new_value is None:
                # Here information is lost! We can not know the type and effect of this issuelink, as it is not in the
                # data!
                issue.issue_links.append({
                    'issue_id': event.old_value, 'type': None, 'effect': None
                })
            else:
                index_of_found_entry = 0
                for issue_link in issue.issue_links:
                    if issue_link['issue_id'] == event.new_value:
                        break
                    index_of_found_entry += 1
                try:
                    del issue.issue_links[index_of_found_entry]
                except IndexError:
                    logger.warning('Could not delete issue link of issue %s with event %s' % (issue, event))
        elif event.status == 'attachment' or event.status == 'release note' or event.status == 'remoteissuelink' or \
             event.status == 'comment' or event.status == 'hadoop flags' or event.status == 'timeestimate' or \
             event.status == 'tags' or event.status == 'duedate' or event.status == 'timespent' or \
             event.status == 'worklogid' or event.status == 'flags' or event.status == 'reproduced in' or \
             event.status == 'infra-members' or event.status == 'workflow' or event.status == 'key' or \
             event.status == 'project':
            # Ignore these fields
            return
        else:
            logger.warning('Item field "%s" not handled' % event.status)

    def _get_newest_key_for_issue(self, old_key):
        # We query the saved issue and access it via our jira connection. The jira connection will give us back
        # the NEW value (e.g., if we access via the key ZOOKEEPER-659, we will get back BOOKKEEPER-691 which is the
        # new value
        try:
            issue = self.jira_client.issue(old_key, fields='summary')
            if old_key != issue.key:
                logger.debug('Got new issue: %s' % issue)
            return issue.key
        except JIRAError:
            # Can happen as issue may be deleted
            return old_key

    def _get_people(self, username, email=None, name=None):
        # Check if user was accessed before. This reduces the amount of API requests
        if username in self.people:
            return self.people[username]

        # If email and name are not set, make a request to get the user
        if email is None and name is None:
            user = self._get_user(username)
            email = user.emailAddress
            name = user.displayName

        # Replace the email address "anonymization"
        email = email.replace(' at ', '@').replace(' dot ', '.')
        people_id = People.objects(name=name, email=email).upsert_one(name=name, email=email, username=username).id
        self.people[username] = people_id
        return people_id

    def _get_user(self, username):
        # Get user via the jira client
        if username is None:
            return None

        return self.jira_client.find('user?username={0}', username)