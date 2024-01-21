import copy

import dateutil
import sys

import time
from mongoengine import DoesNotExist

from issueshark.backends.basebackend import BaseBackend
from urllib.parse import urlparse, quote_plus
from jira import JIRA, JIRAError

import logging

from pycoshark.mongomodels import *


logger = logging.getLogger('backend')


class JiraException(Exception):
    """
    Exception that is thrown if there was a problem with the JIRA API
    """
    pass


class JiraBackend(BaseBackend):
    """
    Backend that collects data via the JIRA API
    """
    @property
    def identifier(self):
        """
        Identifier of the backend (jira)
        """
        return 'jira'

    def __init__(self, cfg, issue_system_id, project_id, last_system_id):
        """
        Initialization
        Initializes the people dictionary see: :func:`~issueshark.backends.jirabackend.JiraBackend._get_people`
        Initializes the attribute mapping: Maps attributes from the JIRA API to our database design


        :param cfg: holds als configuration. Object of class :class:`~issueshark.config.Config`
        :param issue_system_id: id of the issue system for which data should be collected. :class:`bson.objectid.ObjectId`
        :param project_id: id of the project to which the issue system belongs. :class:`bson.objectid.ObjectId`
        """
        super().__init__(cfg, issue_system_id, project_id, last_system_id)

        logger.setLevel(self.debug_level)
        self.people = {}
        self.jira_client = None

        self.jira_mongo_terminology_mapping = {
            'summary': 'title',
            'description': 'desc',
            'created': 'created_at',
            'updated': 'updated_at',
            'creator': 'creator_id',
            'reporter': 'reporter_id',
            'issuetype': 'issue_type',
            'priority': 'priority',
            'status': 'status',
            'versions': 'affects_versions',
            'components': 'components',
            'labels': 'labels',
            'resolution': 'resolution',
            'fixVersions': 'fix_versions',
            'assignee': 'assignee_id',
            'issuelinks': 'issue_links',
            'parent': 'parent_issue_id',
            'timeoriginalestimate': 'original_time_estimate',
            'environment': 'environment'
        }

    def process(self):
        """
        Processes the issues:

        1) Get all issues that are updated since the last time we executed this

        2) Go through all issues step by step, see: :func:`~issueshark.backends.jirabackend.JiraBackend._process_issue`

        """
        logger.info("Starting the collection process...")
        if self.config.use_token():
            raise JiraException('Jira does not support tokens! Use issue_user and issue_password instead')

        url_to_jira = self._create_url_to_jira_rest_interface()

        # Connect to jira
        if self.config.issue_user and self.config.issue_password:
            self.jira_client = JIRA(
                {'server': url_to_jira},
                basic_auth=(self.config.issue_user, self.config.issue_password),
                proxies=self.config.get_proxy_dictionary()
            )
        else:
            self.jira_client = JIRA(
                {'server': url_to_jira},
                proxies=self.config.get_proxy_dictionary()
            )

        # Get last modification date (since then, we will collect bugs)
        query = self._create_issue_query()

        # We search our intital set of issues
        issues = self.jira_client.search_issues(query, startAt=0, maxResults=50, fields='summary')
        logger.debug('Found %d issues via url %s' % (
            len(issues),
            self.jira_client._get_url('search?jql=%s&startAt=0&maxResults=50' % quote_plus(query))
        ))

        # If no new bugs found, return
        if len(issues) == 0:
            logger.info('No new issues found. Exiting...')
            sys.exit(0)

        # Otherwise, go through all issues
        processed_results = 50
        while processed_results < 51:
            logger.info("Processing %d issues..." % len(issues))
            for issue in issues:
                self._process_issue(issue.key)
            # Go through the next issues
            issues = self.jira_client.search_issues(query, startAt=processed_results, maxResults=50, fields='summary')
            logger.debug('Found %d issues via url %s' %
                         (len(issues), self.jira_client._get_url('search?jql=%s&startAt=%d&maxResults=50' %
                                                                (quote_plus(query), processed_results))))
            print('wow')
            processed_results += 50
        self.save_issues()
        self.link_issues()

    def link_issues(self):
        """
            Link parsed issues and events from an external issue tracking system to corresponding MongoDB documents.

            This method iterates through the parsed issues and their events, updating the issue and event documents
            in the MongoDB database based on external identifiers. It performs the following tasks:

            1. Iterates through parsed issues, retrieves corresponding MongoDB document, and updates linked issues and parent issue.
            2. Iterates through events of each issue, retrieves corresponding MongoDB document, and updates external issue references.
        """
        for issue_id, issue in self.parsed_issues['issues'].items():
            try:
                issue = Issue.objects.get(issue_system_ids=self.issue_system_id, external_id=issue_id)
            except DoesNotExist:
                continue
            for link_issue in issue.issue_links:
                if isinstance(link_issue['issue_id'], str):
                    link_issue['issue_id'] = self._get_issue_id_by_external_id(link_issue['issue_id'])
                    issue.save()
            if isinstance(issue.parent_issue_id, str):
                issue.parent_issue_id = self._get_issue_id_by_external_id(issue.parent_issue_id)
                issue.save()
            if issue_id not in self.parsed_issues['events']:
                continue
            for item_id, item in self.parsed_issues['events'][issue_id].items():
                try:
                    event = IssueEvent.objects.get(issue_id=issue.id, external_id=item_id)
                except DoesNotExist:
                    continue
                if isinstance(event.new_value, str):
                    external_id = event.new_value
                    event.new_value = self._get_issue_id_by_external_id(external_id)
                if isinstance(event.old_value, str):
                    external_id = event.old_value
                    event.old_value = self._get_issue_id_by_external_id(external_id)
                if isinstance(event.new_value, dict) and isinstance(event.new_value['issue_id'], str):
                    external_id = event.new_value['issue_id']
                    mongo_issue_id = self._get_issue_id_by_external_id(external_id)
                    event.new_value = {'issue_id': mongo_issue_id, 'type': event.new_value['type'], 'effect': event.new_value['effect']}
                if isinstance(event.old_value, dict) and isinstance(event.old_value['issue_id'], str):
                    external_id = event.old_value['issue_id']
                    mongo_issue_id = self._get_issue_id_by_external_id(external_id)
                    event.old_value = {'issue_id': mongo_issue_id, 'type': event.old_value['type'], 'effect': event.old_value['effect']}
                event.save()

    def _create_url_to_jira_rest_interface(self):
        """
        Creates the url to the jira rest interface
        """

        # We need to get the name of the project (how it is called in jira, e.g. 'ZOOKEEPER')
        parsed_url = urlparse(self.config.tracking_url)

        rest_url = parsed_url.scheme+"://"+parsed_url.netloc

        # If the path does not start with /rest, meaning there is something in between (e.g. "/jira"), we need
        # to add that to the server
        if not parsed_url.path.startswith('/rest'):
            rest_url = rest_url + '/' + parsed_url.path.split('/')[1]

        return rest_url

    def _create_issue_query(self):
        """
        Creates the issue query, including sorting
        """
        # Get project name from last part of url
        project_name = self.config.tracking_url.split('=')[-1]

        query = "project=%s ORDER BY updatedDate ASC" % project_name

        return query

    def _get_newest_issue(self, jira_issue_id):
        """
        Gets the issue with the given id from the jira rest api

        :param jira_issue_id: id of the issue that is to be retrieved (e.g. "ZOOKEEPER-1")
        """
        issue_not_retrieved = True
        issue = None

        # Retrieve the issue via the client and retry as long as the timeout is not running out
        timeout_start = time.time()
        timeout = 300  # 5 minutes
        while issue_not_retrieved and time.time() < timeout_start + timeout:
            try:
                logger.debug('Processing issue %s via url %s' % (
                    jira_issue_id,
                    self.jira_client._get_url('issue/%s?expand=changelog' % jira_issue_id))
                )
                issue = self.jira_client.issue(jira_issue_id, expand='changelog')
                logger.debug('Got fields: %s' % vars(issue.fields))
                issue_not_retrieved = False
            except JIRAError:
                time.sleep(30)
                pass

        return issue

    def _process_issue(self, jira_issue_id):
        """
        Processes the issue in three steps:

        1) Get the issue with the given id from the jira rest api. See: :func:`~issueshark.backends.jirabackend.JiraBackend._get_newest_issue`

        2) update the issue in the database (or store it if it was not parsed before). See: :func:`~issueshark.backends.jirabackend.JiraBackend._store_jira_issue`

        3) Stores all events of this issue. See: :func:`~issueshark.backends.jirabackend.JiraBackend._store_events`

        4) Stores all comments of this issue. See: :func:`~issueshark.backends.jirabackend.JiraBackend._store_comments`


        :param jira_issue_id: id of the issue that is to be retrieved (e.g. "ZOOKEEPER-1")
        """
        # Get newest issue version
        jira_issue = self._get_newest_issue(jira_issue_id)

        # Update it in database
        mongo_issue = self._store_jira_issue(jira_issue)

        # Store events
        self._store_events(jira_issue, mongo_issue)

        # Store comments
        self._store_comments(jira_issue, mongo_issue)

    def _store_comments(self, jira_issue, mongo_issue):
        """
        Processes the comments from an jira issue

        :param issue: original jira issue
        :param issue_id:  Object of class :class:`bson.objectid.ObjectId`. Identifier of the document that holds \
        the issue information
        """

        # Go through all comments of the issue
        comments_to_insert = []
        logger.info('Processing %d comments...' % len(jira_issue.fields.comment.comments))
        for comment in jira_issue.fields.comment.comments:
            logger.debug('Processing comment: %s' % comment)
            created_at = dateutil.parser.parse(comment.created).replace(tzinfo=None)
            mongo_comment = None
            if mongo_issue:
                try:
                    mongo_comment = IssueComment.objects(external_id=comment.id, issue_id=mongo_issue.id).get()
                    logger.debug('Comment already in database, id: %s' % mongo_comment.id)
                except DoesNotExist:
                    mongo_comment = None
            new_comment = IssueComment(
                external_id=comment.id,
                created_at=created_at,
                author_id=self._get_people(comment.author.name, self._get_user_email(comment.author),
                                           comment.author.displayName),
                comment=comment.body,
            )
            logger.debug('Resulting comment: %s' % new_comment)

            if self.issue_id not in self.parsed_issues['comments']:
                self.parsed_issues['comments'][self.issue_id] = {}
            self.parsed_issues['comments'][self.issue_id][comment.id] = new_comment
            self.check_diff_comment_event(mongo_comment, new_comment)

    def _store_jira_issue(self, jira_issue):
        """
        Transforms the Jira issue to our issue model

        :param jira_issue: original jira issue, like we got it from the Jira API
        """
        self.issue_id = jira_issue.key
        try:
            # We can not return here, as the issue might be updated. This means, that the title could be updated
            # as well as comments and new events
            mongo_issue = Issue.objects(issue_system_ids=self.last_system_id, external_id=self.issue_id).get()
            self.old_issues['issues'][self.issue_id] = mongo_issue
        except DoesNotExist:
            mongo_issue = None
        new_issue = Issue(issue_system_ids=[self.issue_system_id], external_id=jira_issue.key)

        for at_name_jira, at_name_mongo in self.jira_mongo_terminology_mapping.items():
            # If the attribute is in the rest response set it
            if hasattr(jira_issue.fields, at_name_jira):

                jira_issue_fields = copy.deepcopy(jira_issue.fields)

                # special case issuelinks: PIG-1904 links to itself, we can not allow this or it creates the issue without data and throws an Exist error on mongo_issue.save()
                if at_name_jira == 'issuelinks':
                    new_issue_links = []
                    for issue_link in getattr(jira_issue.fields, at_name_jira):
                        if hasattr(issue_link, 'outwardIssue'):
                            if issue_link.outwardIssue.key != jira_issue.key:
                                new_issue_links.append(issue_link)
                        else:
                            if issue_link.inwardIssue.key != jira_issue.key:
                                new_issue_links.append(issue_link)
                    setattr(jira_issue_fields, 'issuelinks', new_issue_links)

                if isinstance(getattr(new_issue, at_name_mongo), list):
                    # Get the result and the current value and merge it together
                    result = self._parse_jira_field(jira_issue_fields, at_name_jira)
                    current_value = getattr(new_issue, at_name_mongo, list())
                    if not isinstance(result, list):
                        result = [result]

                    # Extend
                    current_value.extend(result)
                    if len(current_value) > 0 and at_name_mongo == 'issue_links':
                        current_value = [dict(t) for t in set([tuple(d.items()) for d in current_value])]
                    else:
                        current_value = list(set(current_value))

                    # Set the attribute
                    setattr(new_issue, at_name_mongo, copy.deepcopy(current_value))
                else:
                    setattr(new_issue, at_name_mongo, self._parse_jira_field(jira_issue_fields, at_name_jira))

        self.parsed_issues['issues'][self.issue_id] = new_issue
        self.check_diff_issue(mongo_issue, new_issue)
        return mongo_issue

    def _parse_jira_field(self, jira_issue_fields, at_name_jira):
        """
        Parses the jira fields from the original issue

        :param jira_issue_fields: fields of the original jira issue
        :param at_name_jira: attribute name that should be returned
        """
        field_mapping = {
            'summary': self._parse_string_field,
            'description': self._parse_string_field,
            'created': self._parse_date_field,
            'updated': self._parse_date_field,
            'creator': self._parse_author_details,
            'reporter': self._parse_author_details,
            'issuetype': self._parse_string_field,
            'priority': self._parse_string_field,
            'status': self._parse_string_field,
            'versions': self._parse_array_field,
            'components': self._parse_array_field,
            'labels': self._parse_array_field,
            'resolution': self._parse_string_field,
            'fixVersions': self._parse_array_field,
            'assignee': self._parse_author_details,
            'issuelinks': self._parse_issue_links,
            'parent': self._parse_parent_issue,
            'timeoriginalestimate': self._parse_string_field,
            'environment': self._parse_string_field
        }

        correct_function = field_mapping.get(at_name_jira)
        return correct_function(jira_issue_fields, at_name_jira)

    def _parse_string_field(self, jira_issue_fields, at_name_jira):
        """
        Parses the string jira fields from the original issue

        :param jira_issue_fields: fields of the original jira issue
        :param at_name_jira: attribute name that should be returned
        """
        attribute = getattr(jira_issue_fields, at_name_jira)
        if hasattr(attribute, 'name'):
            return getattr(attribute, 'name')
        else:
            return attribute

    def _parse_date_field(self, jira_issue_fields, at_name_jira):
        """
        Parses the date jira fields from the original issue

        :param jira_issue_fields: fields of the original jira issue
        :param at_name_jira: attribute name that should be returned
        """
        return dateutil.parser.parse(getattr(jira_issue_fields, at_name_jira)).replace(tzinfo=None)

    def _parse_parent_issue(self, jira_issue_fields, at_name_jira):
        """
        Parses the parent issue field from the original issue

        :param jira_issue_fields: fields of the original jira issue
        :param at_name_jira: attribute name that should be returned
        """
        return jira_issue_fields.parent.key

    def _parse_author_details(self, jira_issue_fields, at_name_jira):
        """
        Parses the author detail fields from the original issue

        :param jira_issue_fields: fields of the original jira issue
        :param at_name_jira: attribute name that should be returned
        """
        people = getattr(jira_issue_fields, at_name_jira)
        if people is not None:
            return self._get_people(people.name, self._get_user_email(people), people.displayName)
        return None

    def _parse_array_field(self, jira_issue_fields, at_name_jira):
        """
        Parses the array fields from the original issue

        :param jira_issue_fields: fields of the original jira issue
        :param at_name_jira: attribute name that should be returned
        """
        array_field = getattr(jira_issue_fields, at_name_jira)
        new_array = []
        for value in array_field:
            if hasattr(value, 'name'):
                new_array.append(getattr(value, 'name'))
            else:
                new_array.append(value)

        return new_array

    def _parse_issue_links(self, jira_issue_fields, at_name_jira):
        """
        Parses the issue links field from the original issue

        :param jira_issue_fields: fields of the original jira issue
        :param at_name_jira: attribute name that should be returned
        """
        links = []
        for issue_link in getattr(jira_issue_fields, at_name_jira):
            if hasattr(issue_link, 'outwardIssue'):
                issue_id = issue_link.outwardIssue.key
                issue_type, issue_effect = self._get_issue_link_type_and_effect(issue_link.type.outward)
            else:
                issue_id = issue_link.inwardIssue.key
                issue_type, issue_effect = self._get_issue_link_type_and_effect(issue_link.type.inward)

            links.append({'issue_id': issue_id, 'type': issue_type, 'effect': issue_effect})
        return links

    @staticmethod
    def _get_issue_link_type_and_effect(msg_string):
        """
        Gets the correct issue link type and effect from a message

        :param msg_string: String from which type and effect should be acquired
        """
        if "Blocked" in msg_string:
            return "Blocked", "Blocked"
        elif "is blocked by" in msg_string:
            return "Blocker", "is blocked by"
        elif "blocks" in msg_string:
            return "Blocker", "blocks"
        elif "is cloned by" in msg_string:
            return "Cloners", "is cloned by"
        elif "is a clone of" in msg_string or "is cloned as" in msg_string:
            return "Cloners", "is cloned by"
        elif "Is contained by" in msg_string or "is contained by" in msg_string:
            return "Container", "is contained by"
        elif "contains" in msg_string:
            return "Container", "contains"
        elif "Dependent" in msg_string:
            return "Dependent", "Dependent"
        elif "is duplicated by" in msg_string:
            return "Duplicate", "is duplicated by"
        elif "duplicates" in msg_string:
            return "Duplicate", "duplicates"
        elif "is part of" in msg_string:
            return "Incorporates", "is part of"
        elif "incorporates" in msg_string:
            return "Incorporates", "incorporates"
        elif "is related to" in msg_string:
            return "Reference", "is related to"
        elif "relates" in msg_string:
            return "Reference", "relates to"
        elif "is broken by" in msg_string:
            return "Regression", "is broken by"
        elif "breaks" in msg_string:
            return "Regression", "breaks"
        elif "is required by" in msg_string:
            return "Required", "is required by"
        elif "requires" in msg_string:
            return "Required", "requires"
        elif "is superceded by" in msg_string:
            return "Supercedes", "is superceded by"
        elif "supercedes" in msg_string:
            return "Supercedes", "supercedes"
        elif "is depended upon by" in msg_string:
            return "Dependent", "is depended upon by"
        elif "depends upon" in msg_string:
            return "Dependent", "depends upon"
        elif "depends on" in msg_string:
            return "Dependent", "depends on"
        else:
            logger.warning("Could not find issue type and effect of string %s" % msg_string)
            return None, None

    def _get_newest_key_for_issue(self, old_key):
        """
        Gets the newes key for an issue. We query the saved issue and access it via our jira connection.
        The jira connection will give us back the NEW value (e.g., if we access via the key ZOOKEEPER-659,
        we will get back BOOKKEEPER-691 which is the new value
        :param old_key: old issue key
        """

        try:
            issue = self.jira_client.issue(old_key, fields='summary')
            if old_key != issue.key:
                logger.debug('Got new issue: %s' % issue)
            return issue.key
        except JIRAError:
            # Can happen as issue may be deleted
            return old_key

    def _store_events(self, jira_issue, mongo_issue):
        # Go through history of jira issue
        # We go thorugh from newest to oldest
        # If we find an issue that is already stored -> return

        for history in reversed(jira_issue.changelog.histories):
            i = 0
            created_at = dateutil.parser.parse(history.created).replace(tzinfo=None)

            # It can happen that an event does not have an author (e.g., ZOOKEEPER-2218)
            author_id = None
            if hasattr(history, 'author'):
                author_id = self._get_people(history.author.name, name=history.author.displayName,
                                             email=self._get_user_email(history.author))

            for jira_event in history.items:
                logger.debug('Processing changelog entry: %s' % vars(jira_event))

                unique_event_id = str(history.id) + "%%" + str(i)
                self._store_event(jira_event, unique_event_id, author_id, created_at, mongo_issue)

                i += 1

    def _store_event(self, jira_event, unique_event_id, author_id, created_at, mongo_issue):
        """
        Stores the given jira event

        :param jira_event: jira event
        :param unique_event_id: unique identifier of this event
        :param author_id: author that authored this event
        :param created_at: creation date
        :param mongo_issue: issue to which this event is connected
        """
        terminology_mapping = {
            'Component': 'components',
            'Link': 'issuelinks',
            'Fix Version': 'fixVersions',
            'Version': 'versions',
            'Labels': 'labels',
            'Parent': 'parent',
        }

        # If the try block succeeds, the event already exist in the database
        mongo_event = None
        if mongo_issue:
            try:
               mongo_event = IssueEvent.objects(external_id=unique_event_id, issue_id=mongo_issue.id).get()
            except DoesNotExist:
                mongo_event = None

        new_event = IssueEvent(
            external_id=unique_event_id,
            created_at=created_at,
            author_id=author_id,
        )

        # We need to map the terminology from the histories in jira to the terminology that
        # is used when querying an issue
        # E.g., in the changelog "labels" is called "Labels"
        try:
            jira_at_name = terminology_mapping[getattr(jira_event, 'field')]
        except KeyError:
            jira_at_name = getattr(jira_event, 'field')

        # Map jira terminology to our terminology
        try:
            new_event.status = self.jira_mongo_terminology_mapping[jira_at_name]
        except KeyError:
            logger.warning('Mapping for attribute %s not found.' % jira_at_name)
            new_event.status = jira_at_name

        if new_event.status == 'assignee_id':
            if getattr(jira_event, 'from') is not None:
                people_id = self._get_people(getattr(jira_event, 'from'))
                new_event.old_value = people_id
            if jira_event.to is not None:
                people_id = self._get_people(jira_event.to)
                new_event.new_value = people_id
        elif new_event.status == 'parent_issue_id':
            if getattr(jira_event, 'from') is not None:
                issue_id = jira_event.fromString
                new_event.old_value = issue_id
            if jira_event.to is not None:
                issue_id = jira_event.toString
                new_event.new_value = issue_id
        elif new_event.status == 'issue_links':

            if getattr(jira_event, 'from') is not None:
                issue_type, issue_effect = self._get_issue_link_type_and_effect(jira_event.fromString)
                issue_id = getattr(jira_event, 'from')
                new_event.old_value = {'issue_id': issue_id, 'type': issue_type, 'effect': issue_effect}
            if jira_event.to is not None:
                issue_type, issue_effect = self._get_issue_link_type_and_effect(jira_event.toString)
                issue_id = jira_event.to
                new_event.new_value = {'issue_id': issue_id, 'type': issue_type, 'effect': issue_effect}
        elif new_event.status == 'original_time_estimate':
            if getattr(jira_event, 'from') is not None:
                new_event.old_value = int(jira_event.fromString)

            if jira_event.to is not None:
                new_event.new_value = int(jira_event.toString)

        else:
            new_event.new_value = getattr(jira_event, 'toString')
            new_event.old_value = getattr(jira_event, 'fromString')

        if self.issue_id not in self.parsed_issues['events']:
            self.parsed_issues['events'][self.issue_id] = {}
        self.parsed_issues['events'][self.issue_id][unique_event_id] = new_event
        self.check_diff_comment_event(mongo_event, new_event)

    def _get_people(self, username, email=None, name=None):
        """
        Gets the document from the people collection. First checks the people dictionary to save API requests

        :param username: username of the person
        :param email: email of the person
        :param name: name of the person
        """
        # Check if user was accessed before. This reduces the amount of API requests
        if username in self.people:
            return self.people[username]

        # If email and name are not set, make a request to get the user
        if email is None and name is None:
            user = self._get_user(username)

            # It can happen that a user is no longer available
            if user is None:
                email = username
                name = username
            else:
                email = self._get_user_email(user)
                name = user.displayName

        # Replace the email address "anonymization"
        email = email.replace(' at ', '@').replace(' dot ', '.')
        people_id = People.objects(name=name, email=email).upsert_one(name=name, email=email, username=username).id
        self.people[username] = people_id
        return people_id

    def _get_user(self, username):
        """
        Gets the user via the jira client

        :param username: username of the jira user
        """
        # Get user via the jira client
        if username is None:
            return None

        # It can happen that a user is no longer available
        try:
            return self.jira_client.find('user?username={0}', username)
        except JIRAError:
            return None

    def _get_user_email(self, user):
        """
        Return user email address.

        Check for existence of emailAddress attribute, it can be hidden in Jira.
        If it exists return it if not return 'null' (because that is the current convention in the MongoDB).

        :param user: jira user object
        :returns: str -- users email or 'null'
        """
        email = 'null'
        if hasattr(user, 'emailAddress'):
            email = user.emailAddress
        return email

    def _get_issue_id_by_external_id(self, external_id):
        """
        Gets the issue by their id that was assigned by the bugzilla ITS
        :param external_id: id of the issue in the bugzilla ITS
        """
        issue_id = None
        try:
            issue_id = Issue.objects(issue_system_ids=self.issue_system_id, external_id=str(external_id)).only(
                'id').get().id
        except DoesNotExist:
            pass
        if not issue_id:
            try:
                issue = Issue.objects(issue_system_ids=self.last_system_id, external_id=str(external_id)).get()
                issue.issue_system_ids.append(self.issue_system_id)
                issue.save()
                issue_id = issue.id
            except DoesNotExist:
                issue_id = Issue(issue_system_ids=[self.issue_system_id], external_id=str(external_id)).save().id

        return issue_id
