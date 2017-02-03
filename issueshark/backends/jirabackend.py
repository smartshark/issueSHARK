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

    def __init__(self, cfg, issue_system_id, project_id):
        """
        Initialization
        Initializes the people dictionary see: :func:`~issueshark.backends.jirabackend.JiraBackend._get_people`
        Initializes the attribute mapping: Maps attributes from the JIRA API to our database design


        :param cfg: holds als configuration. Object of class :class:`~issueshark.config.Config`
        :param issue_system_id: id of the issue system for which data should be collected. :class:`bson.objectid.ObjectId`
        :param project_id: id of the project to which the issue system belongs. :class:`bson.objectid.ObjectId`
        """
        super().__init__(cfg, issue_system_id, project_id)

        logger.setLevel(self.debug_level)
        self.people = {}
        self.jira_client = None

        self.at_mapping = {
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
        Processes the data from the JIRA API.

        1. Connects to JIRA

        2. Gets the last stored issues updated_at field

        3. Collects issues that were changed since this date

        4. Calls :func:`~issueshark.backends.jirabackend.JiraBackend._process_issue` for every found issue
        :return:
        """
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
        """
        Transforms the Jira issue to our issue model

        :param jira_issue: original jira issue, like we got it from the Jira API
        """
        try:
            # We can not return here, as the issue might be updated. This means, that the title could be updated
            # as well as comments and new events
            mongo_issue = Issue.objects(issue_system_id=self.issue_system_id, external_id=jira_issue.key).get()
        except DoesNotExist:
            mongo_issue = Issue(
                issue_system_id=self.issue_system_id,
                external_id=jira_issue.key,
            )

        for at_name_jira, at_name_mongo in self.at_mapping.items():
            # If the attribute is in the rest response set it
            if hasattr(jira_issue.fields, at_name_jira):
                if isinstance(getattr(mongo_issue, at_name_mongo), list):
                    # Get the result and the current value and merge it together
                    result = self._parse_jira_field(jira_issue.fields, at_name_jira)
                    current_value = getattr(mongo_issue, at_name_mongo, list())
                    if not isinstance(result, list):
                        result = [result]

                    # Extend
                    current_value.extend(result)
                    if len(current_value) > 0 and at_name_mongo == 'issue_links':
                        current_value = [dict(t) for t in set([tuple(d.items()) for d in current_value])]
                    else:
                        current_value = list(set(current_value))

                    # Set the attribute
                    setattr(mongo_issue, at_name_mongo, copy.deepcopy(current_value))
                else:
                    setattr(mongo_issue, at_name_mongo, self._parse_jira_field(jira_issue.fields, at_name_jira))

        return mongo_issue.save()

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
        return dateutil.parser.parse(getattr(jira_issue_fields, at_name_jira))

    def _parse_parent_issue(self, jira_issue_fields, at_name_jira):
        """
        Parses the parent issue field from the original issue

        :param jira_issue_fields: fields of the original jira issue
        :param at_name_jira: attribute name that should be returned
        """
        return self._get_issue_id_by_system_id(jira_issue_fields.parent.key)

    def _parse_author_details(self, jira_issue_fields, at_name_jira):
        """
        Parses the author detail fields from the original issue

        :param jira_issue_fields: fields of the original jira issue
        :param at_name_jira: attribute name that should be returned
        """
        people = getattr(jira_issue_fields, at_name_jira)
        if people is not None:
            return self._get_people(people.name, people.emailAddress, people.displayName)
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
                issue_id = self._get_issue_id_by_system_id(issue_link.outwardIssue.key)
                issue_type, issue_effect = self._get_issue_link_type_and_effect(issue_link.type.outward)
            else:
                issue_id = self._get_issue_id_by_system_id(issue_link.inwardIssue.key)
                issue_type, issue_effect = self._get_issue_link_type_and_effect(issue_link.type.inward)

            links.append({'issue_id': issue_id, 'type': issue_type, 'effect': issue_effect})
        return links

    def _process_issue(self, issue_key):
        """
        Processes the issue.

        1. Transformation of the jira issue into a mongo db issue (can directly be saved).\
        See: :func:`~issueshark.backends.jirabackend.JiraBackend._transform_jira_issue`

        2. Go through the whole history of the jira issue, create events and set back the values. \
        See: :func:`~issueshark.backends.jirabackend.JiraBackend._process_event`

        3. This way, we get the ORIGINAL issue that was posted in jira, which is then saved in the issue collection \
        --> Some things can not be turned back, e.g. issue links, as there is information missing in the changelog

        4.  Comments of the issue are processed (and stored). \
        See: :func:`~issueshark.backends.jirabackend.JiraBackend._process_comments`


        :param issue_key: key of the issue (e.g. ZOOKEEPER-2124)
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
            logger.error('Could not get issue: %s' % issue_key)
            return

        logger.debug('Processing issue %s via url %s' % (issue,
                                                         self.jira_client._get_url('issue/%s?expand=changelog' % issue)))
        logger.debug('Got fields: %s' % vars(issue.fields))

        # Transform jira issue to mongo issue
        mongo_issue = self._transform_jira_issue(issue)
        logger.debug('Transformed issue: %s' % mongo_issue)

        # Go through all events and set back issue items till we get the original one
        events = []
        for history in reversed(issue.changelog.histories):
            i = 0

            created_at = dateutil.parser.parse(history.created)

            # It can happen that an event does not have an author (e.g., ZOOKEEPER-2218)
            author_id = None
            if hasattr(history, 'author'):
                author_id = self._get_people(history.author.name, name=history.author.displayName,
                                             email=history.author.emailAddress)

            for jira_event in reversed(history.items):
                unique_event_id = str(history.id)+"%%"+str(i)
                logger.debug('Processing changelog entry: %s' % vars(jira_event))

                # Create event list
                event, newly_created = self._process_event(created_at, author_id, jira_event, unique_event_id,
                                                           mongo_issue)
                logger.debug('Newly created?: %s, Resulting event: %s' % (newly_created, event))

                # Append to list if event is not stored in db
                if newly_created:
                    events.append(event)

                i += 1
        logger.debug('Original issue to store: %s' % mongo_issue)

        # We need to set the status to open here, as this is the first status for every issue
        mongo_issue.status = 'Open'

        # Update issue
        mongo_issue.save()

        # Set issue_id for event list and bulk write
        if events:
            Event.objects.insert(events, load_bulk=False)

        # Store comments of issue
        self._process_comments(issue, mongo_issue.id)

    def _process_comments(self, issue, issue_id):
        """
        Processes the comments from an jira issue

        :param issue: original jira issue
        :param issue_id:  Object of class :class:`bson.objectid.ObjectId`. Identifier of the document that holds \
        the issue information
        """

        # Go through all comments of the issue
        comments_to_insert = []
        logger.info('Processing %d comments...' % len(issue.fields.comment.comments))
        for comment in issue.fields.comment.comments:
            logger.debug('Processing comment: %s' % comment)
            created_at = dateutil.parser.parse(comment.created)
            try:
                mongo_comment = IssueComment.objects(external_id=comment.id, issue_id=issue_id).get()
                logger.debug('Comment already in database, id: %s' % mongo_comment.id)
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
        """
        Gets the issue id like it is stored in the mongodb for a system id (like the id that was assigned by jira to
        the issue)


        :param system_id: id of the issue like it was assigned by jira
        :param refresh_key: if set to true, jira is contacted to get the newest system id for this issue
        :return:
        """
        if refresh_key:
            system_id = self._get_newest_key_for_issue(system_id)

        try:
            issue_id = Issue.objects(issue_system_id=self.issue_system_id, external_id=system_id).only('id').get().id
        except DoesNotExist:
            issue_id = Issue(issue_system_id=self.issue_system_id, external_id=system_id).save().id

        return issue_id

    def _set_back_mongo_issue(self, mongo_issue, mongo_at_name, jira_event):
        """
        Sets back the issue like it stored in the mongodb for this jira event

        :param mongo_issue: issue like it is stored in the mongodb
        :param mongo_at_name: attribute name of the field of the issue that is affected by the event
        :param jira_event: original event that was acquired by the jira api
        """
        function_mapping = {
            'title': self._set_back_string_field,
            'desc': self._set_back_string_field,
            'issue_type': self._set_back_string_field,
            'priority': self._set_back_string_field,
            'status': self._set_back_string_field,
            'affects_versions': self._set_back_array_field,
            'components': self._set_back_array_field,
            'labels': self._set_back_labels,
            'resolution': self._set_back_string_field,
            'fix_versions': self._set_back_array_field,
            'assignee_id': self._set_back_assignee,
            'issue_links': self._set_back_issue_links,
            'parent_issue_id': self._set_back_parent_id,
            'original_time_estimate': self._set_back_string_field,
            'environment': self._set_back_string_field,
        }

        correct_function = function_mapping[mongo_at_name]
        correct_function(mongo_issue, mongo_at_name, jira_event)

    def _set_back_labels(self, mongo_issue, mongo_at_name, jira_event):
        """
        Set back the labels array for the event. Somehow the labels are handled differently than, e.g., components. \
         Different labels are split by a space

        :param mongo_issue: issue like it is stored in the mongodb
        :param mongo_at_name: attribute name of the field of the issue that is affected by the event
        :param jira_event: original event that was acquired by the jira api
        """
        old_value = getattr(jira_event, 'fromString')
        new_value = getattr(jira_event, 'toString')

        item_list = getattr(mongo_issue, mongo_at_name)

        if old_value:
            for item in old_value.split(" "):
                item_list.append(item)

        if new_value:
            for item in new_value.split(" "):
                item_list.remove(item)

        setattr(mongo_issue, mongo_at_name, item_list)

    def _set_back_string_field(self, mongo_issue, mongo_at_name, jira_event):
        """
        Set back the string fields for the event.

        :param mongo_issue: issue like it is stored in the mongodb
        :param mongo_at_name: attribute name of the field of the issue that is affected by the event
        :param jira_event: original event that was acquired by the jira api
        """
        setattr(mongo_issue, mongo_at_name, getattr(jira_event, 'fromString'))

    def _set_back_array_field(self, mongo_issue, mongo_at_name, jira_event):
        """
        Set back the array fields for the event.

        :param mongo_issue: issue like it is stored in the mongodb
        :param mongo_at_name: attribute name of the field of the issue that is affected by the event
        :param jira_event: original event that was acquired by the jira api
        """
        old_value = getattr(jira_event, 'fromString')
        new_value = getattr(jira_event, 'toString')

        item_list = getattr(mongo_issue, mongo_at_name)

        if old_value:
            item_list.append(old_value)

        if new_value:
            item_list.remove(new_value)

        setattr(mongo_issue, mongo_at_name, item_list)

    def _set_back_assignee(self, mongo_issue, mongo_at_name, jira_event):
        """
        Set back the assignee field for the event.

        :param mongo_issue: issue like it is stored in the mongodb
        :param mongo_at_name: attribute name of the field of the issue that is affected by the event
        :param jira_event: original event that was acquired by the jira api
        """
        old_assignee = getattr(jira_event, 'from')

        if old_assignee is not None:
            setattr(mongo_issue, mongo_at_name, self._get_people(old_assignee))
        else:
            setattr(mongo_issue, mongo_at_name, None)

    def _set_back_parent_id(self, mongo_issue, mongo_at_name, jira_event):
        """
        Set back the parent id field for the event.

        :param mongo_issue: issue like it is stored in the mongodb
        :param mongo_at_name: attribute name of the field of the issue that is affected by the event
        :param jira_event: original event that was acquired by the jira api
        """
        old_parent_id = getattr(jira_event, 'from')

        if old_parent_id is not None:
            setattr(mongo_issue, mongo_at_name, self._get_issue_id_by_system_id(old_parent_id, refresh_key=True))
        else:
            setattr(mongo_issue, mongo_at_name, None)

    def _set_back_issue_links(self, mongo_issue, mongo_at_name, jira_event):
        """
        Set back the issue links field for the event.

        :param mongo_issue: issue like it is stored in the mongodb
        :param mongo_at_name: attribute name of the field of the issue that is affected by the event
        :param jira_event: original event that was acquired by the jira api
        """
        item_list = getattr(mongo_issue, mongo_at_name)

        # Everything that is added in this event must be removed
        if getattr(jira_event, 'to'):
            issue_id = self._get_issue_id_by_system_id(getattr(jira_event, 'to'), refresh_key=True)
            link_type, link_effect = self._get_issue_link_type_and_effect(getattr(jira_event, 'toString'))
            found_index = 0
            for stored_issue in item_list:
                if stored_issue['issue_id'] == issue_id and stored_issue['effect'].lower() == link_effect.lower() and \
                                stored_issue['type'].lower() == link_type.lower():
                    break
                found_index += 1

            try:
                del item_list[found_index]
            except IndexError:
                logger.warning('Could not find issue link %s to issue %s to delete in issue %s' % (
                    getattr(jira_event, 'toString'),
                    getattr(jira_event, 'to'),
                    mongo_issue)
                )

        # Everything that was before, must be added
        if getattr(jira_event, 'from'):
            issue_id = self._get_issue_id_by_system_id(getattr(jira_event, 'from'), refresh_key=True)
            link_type, link_effect = self._get_issue_link_type_and_effect(getattr(jira_event, 'fromString'))

            already_in_list = False
            for stored_issue in item_list:
                if stored_issue['issue_id'] == issue_id and stored_issue['effect'].lower() == link_effect.lower() \
                        and stored_issue['type'].lower() == link_type.lower():
                    already_in_list = True

            if not already_in_list:
                item_list.append({'issue_id': issue_id, 'type': link_type, 'effect': link_effect})

        setattr(mongo_issue, mongo_at_name, item_list)

    def _get_issue_link_type_and_effect(self, msg_string):
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

    def _process_event(self, created_at, author_id, jira_event, unique_event_id, mongo_issue):
        """
        Processes the jira event for an issue.

        Goes through the event and sets back the mongo issue accordingly.

        :param created_at: date when the issue was created
        :param author_id: id of the author, who created this issue
        :param jira_event: original jira event, like it was acquired from the REST API
        :param unique_event_id: unique id to identify the event
        :param mongo_issue: issue that conforms to our issue model
        """
        terminology_mapping = {
            'Component': 'components',
            'Link': 'issuelinks',
            'Fix Version': 'fixVersions',
            'Version': 'versions',
            'Labels': 'labels',
            'Parent': 'parent'
        }

        is_new_event = True
        try:
            mongo_event = Event.objects(external_id=unique_event_id, issue_id=mongo_issue.id).get()
            is_new_event = False
        except DoesNotExist:
            mongo_event = Event(
                external_id=unique_event_id,
                issue_id=mongo_issue.id,
                created_at=created_at,
                author_id=author_id
            )

        # We need to map back the jira terminology from getting the issues to the terminology in the histories
        try:
            jira_at_name = terminology_mapping[getattr(jira_event, 'field')]
        except KeyError:
            jira_at_name = getattr(jira_event, 'field')

        # Map jira terminology to our terminology
        try:
            mongo_event.status = self.at_mapping[jira_at_name]
        except KeyError:
            logger.warning('Mapping for attribute %s not found.' % jira_at_name)
            mongo_event.status = jira_at_name

        # Check if the mongo_issue has the attribute.
        # If yes: We can use the mongo_issue to set the old and new value of the event
        # If no: We use the added / removed fields
        if hasattr(mongo_issue, mongo_event.status):
            mongo_event.new_value = copy.deepcopy(getattr(mongo_issue, mongo_event.status))
            self._set_back_mongo_issue(mongo_issue, mongo_event.status, jira_event)
            mongo_event.old_value = copy.deepcopy(getattr(mongo_issue, mongo_event.status))
        else:
            mongo_event.new_value = getattr(jira_event, 'toString')
            mongo_event.old_value = getattr(jira_event, 'fromString')

        return mongo_event, is_new_event

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
            email = user.emailAddress
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

        return self.jira_client.find('user?username={0}', username)