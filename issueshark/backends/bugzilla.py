import sys

import dateutil.parser
from mongoengine import DoesNotExist
import copy

from issueshark.backends.basebackend import BaseBackend
from issueshark.backends.helpers.bugzillaagent import BugzillaAgent
from validate_email import validate_email
import urllib.parse
import logging

from issueshark.mongomodels import Issue, People, Event, IssueComment

logger = logging.getLogger('backend')


class BugzillaBackend(BaseBackend):
    @property
    def identifier(self):
        return 'bugzilla'

    def __init__(self, cfg, issue_system_id, project_id):
        super().__init__(cfg, issue_system_id, project_id)

        logger.setLevel(self.debug_level)
        self.bugzilla_agent = None
        self.people = {}

        self.at_mapping = {
            'assigned_to_detail': 'assignee_id',
            'blocks': 'issue_links',
            'component': 'components',
            'creation_time': 'created_at',
            'creator_detail': 'creator_id',
            'depends_on': 'issue_links',
            'dupe_of': 'issue_links',
            'keywords': 'labels',
            'last_change_time': 'updated_at',
            'op_sys': 'environment',
            'platform': 'platform',
            'resolution': 'resolution',
            'severity': 'priority',
            'status': 'status',
            'summary': 'title',
            'target_milestone': 'fix_versions',
            'version': 'affects_versions'
        }

    def process(self):
        self.bugzilla_agent = BugzillaAgent(logger, self.config)
        # Get last modification date (since then, we will collect bugs)
        last_issue = Issue.objects(issue_system_id=self.issue_system_id).order_by('-updated_at')\
            .only('updated_at').first()
        starting_date = None
        if last_issue is not None:
            starting_date = last_issue.updated_at

        # Get all issues
        issues = self.bugzilla_agent.get_bug_list(last_change_time=starting_date, limit=50)

        # If no new bugs found, return
        if len(issues) == 0:
            logger.info('No new issues found. Exiting...')
            sys.exit(0)

        # Otherwise, go through all issues
        processed_results = 50
        while len(issues) > 0:
            logger.info("Processing %d issues..." % len(issues))
            for issue in issues:
                logger.info("Processing issue %s" % issue['id'])
                self._process_issue(issue)

            # Go through the next issues
            issues = self.bugzilla_agent.get_bug_list(last_change_time=starting_date, limit=50, offset=processed_results)
            processed_results += 50

    def _process_issue(self, issue):
        # Transform issue
        comments = self.bugzilla_agent.get_comments(issue['id'])
        histories = self.bugzilla_agent.get_issue_history(issue['id'])
        mongo_issue = self._transform_issue(issue, comments)

        logger.debug('Transformed issue: %s', mongo_issue)

        # Go through history
        # 1) Set back issue
        # 2) Store events
        j = 0
        events_to_insert = []
        for history in reversed(histories):
            i = 0
            change_date = dateutil.parser.parse(history['when'])
            author_id = self._get_people(history['who'])
            for bz_event in history['changes']:
                logger.debug("Processing event: %s" % bz_event)
                unique_event_id = str(issue['id'])+"%%"+str(i)+"%%"+str(j)
                mongo_event, is_new_event = self._process_event(unique_event_id, bz_event, mongo_issue, change_date,
                                                                author_id)
                logger.debug('Newly created?: %s, Resulting event: %s' % (is_new_event, mongo_event))

                # Append to list if event is not stored in db
                if is_new_event:
                    events_to_insert.append(mongo_event)

                i += 1
            j += 1

        # Update issue to the original version
        mongo_issue.save()

        # Store events
        if events_to_insert:
            Event.objects.insert(events_to_insert, load_bulk=False)

        # Store comments
        self._process_comments(mongo_issue.id, comments)

    def _process_comments(self, mongo_issue_id, comments):
        # Go through all comments of the issue
        comments_to_insert = []
        logger.info('Processing %d comments...' % (len(comments)-1))
        i = -1
        for comment in comments:
            # Comment with count 0 is the description of the bug
            if comment['count'] == 0:
                continue

            i += 1
            logger.debug('Processing comment: %s' % comment)
            unique_comment_id = "%s%%%s" % (mongo_issue_id, i)
            try:
                IssueComment.objects(external_id=unique_comment_id, issue_id=mongo_issue_id).get()
                continue
            except DoesNotExist:
                mongo_comment = IssueComment(
                    external_id=unique_comment_id,
                    issue_id=mongo_issue_id,
                    created_at=dateutil.parser.parse(comment['creation_time']),
                    author_id=self._get_people(comment['creator']),
                    comment=comment['text'],
                )
                logger.debug('Resulting comment: %s' % mongo_comment)
                comments_to_insert.append(mongo_comment)


        # If comments need to be inserted -> bulk insert
        if comments_to_insert:
            IssueComment.objects.insert(comments_to_insert, load_bulk=False)

    def _process_event(self, unique_event_id, bz_event, mongo_issue, change_date, author_id):
        is_new_event = True
        try:
            mongo_event = Event.objects(external_id=unique_event_id, issue_id=mongo_issue.id).get()
            is_new_event = False
        except DoesNotExist:
            mongo_event = Event(
                external_id=unique_event_id,
                issue_id=mongo_issue.id,
                created_at=change_date,
                author_id=author_id
            )

        # We need to map back the status from the bz terminology to ours. Special: The assigned_to must be mapped to
        # assigned_to_detail beforehand, as we are using this for the issue parsing
        if bz_event['field_name'] == 'assigned_to':
            bz_at_name = 'assigned_to_detail'
        else:
            bz_at_name = bz_event['field_name']

        try:
            mongo_event.status = self.at_mapping[bz_at_name]
        except KeyError:
            logger.warning('Mapping for attribute %s not found.' % bz_at_name)
            mongo_event.status = bz_at_name

        # Check if the mongo_issue has the attribute.
        # If yes: We can use the mongo_issue to set the old and new value of the event
        # If no: We use the added / removed fields
        if hasattr(mongo_issue, mongo_event.status):
            mongo_event.new_value = copy.deepcopy(getattr(mongo_issue, mongo_event.status))
            self._set_back_mongo_issue(mongo_issue, mongo_event.status, bz_event)
            mongo_event.old_value = copy.deepcopy(getattr(mongo_issue, mongo_event.status))
        else:
            mongo_event.new_value = bz_event['added']
            mongo_event.old_value = bz_event['removed']

        return mongo_event, is_new_event

    def _set_back_mongo_issue(self, mongo_issue, mongo_at_name, bz_event):
        function_mapping = {
            'title': self._set_back_string_field,
            'priority': self._set_back_priority,
            'status': self._set_back_string_field,
            'affects_versions': self._set_back_array_field,
            'components': self._set_back_array_field,
            'labels': self._set_back_array_field,
            'resolution': self._set_back_string_field,
            'fix_versions': self._set_back_array_field,
            'assignee_id': self._set_back_assignee,
            'issue_links': self._set_back_issue_links,
            'environment': self._set_back_string_field,
            'platform': self._set_back_string_field
        }

        correct_function = function_mapping[mongo_at_name]
        correct_function(mongo_issue, mongo_at_name, bz_event)

    def _set_back_priority(self, mongo_issue, mongo_at_name, bz_event):
        if bz_event['removed'] == 'enhancement':
            mongo_issue.issue_type = 'Enhancement'
        else:
            mongo_issue.issue_type = 'Bug'

        mongo_issue.priority = bz_event['removed']

    def _set_back_issue_links(self, mongo_issue, mongo_at_name, bz_event):
        type_mapping = {
            'blocks': 'Blocker',
            'dupe_of': 'Duplicate',
            'depends_on': 'Dependent',
        }

        item_list = getattr(mongo_issue, mongo_at_name)

        # Everything that is in "removed" must be added
        if bz_event['removed']:
            issue_id = self._get_issue_id_by_system_id(bz_event['removed'])
            if issue_id not in [entry['issue_id'] for entry in item_list]:
                item_list.append({'issue_id': issue_id, 'type': type_mapping[bz_event['field_name']],
                                  'effect': bz_event['field_name']})

        # Everything that is in "added" must be removed
        if bz_event['added']:
            issue_id = self._get_issue_id_by_system_id(bz_event['added'])
            found_index = 0
            for stored_issue in item_list:
                if stored_issue['issue_id'] == issue_id:
                    break
                found_index += 1
            try:
                del item_list[found_index]
            except IndexError:
                logger.warning('Could not process event %s completely. Did not found issue to delete Issue %s' %
                               (bz_event, mongo_issue))

        setattr(mongo_issue, mongo_at_name, item_list)

    def _set_back_assignee(self, mongo_issue, mongo_at_name, bz_event):
        if bz_event['removed']:
            setattr(mongo_issue, mongo_at_name, self._get_people(bz_event['removed']))
        else:
            setattr(mongo_issue, mongo_at_name, None)

    def _set_back_string_field(self, mongo_issue, mongo_at_name, bz_event):
        setattr(mongo_issue, mongo_at_name, bz_event['removed'])

    def _set_back_array_field(self, mongo_issue, mongo_at_name, bz_event):
        item_list = getattr(mongo_issue, mongo_at_name)
        # Everything that is in "added" must be removed
        if bz_event['added']:
            # We try to remove the item. If it is not in there, we remove the whole list. Observations showed,
            # that this is most likely the correct decision
            try:
                item_list.remove(bz_event['added'])
            except ValueError:
                item_list.clear()

        # Everything that is in "removed" must be added
        if bz_event['removed'] and bz_event['removed'] not in item_list:
            item_list.append(bz_event['removed'])

        setattr(mongo_issue, mongo_at_name, item_list)

    def _parse_bz_field(self, bz_issue, at_name_bz):
        field_mapping = {
            'assigned_to_detail': self._parse_author_details,
            'blocks': self._parse_issue_links,
            'component': self._parse_string_field,
            'creation_time': self._parse_date_field,
            'creator_detail': self._parse_author_details,
            'depends_on': self._parse_issue_links,
            'dupe_of': self._parse_issue_links,
            'keywords': self._parse_array_field,
            'last_change_time': self._parse_date_field,
            'op_sys': self._parse_string_field,
            'platform': self._parse_string_field,
            'resolution': self._parse_string_field,
            'severity': self._parse_string_field,
            'status': self._parse_string_field,
            'summary': self._parse_string_field,
            'target_milestone': self._parse_string_field,
            'version': self._parse_string_field,
        }

        correct_function = field_mapping.get(at_name_bz)
        return correct_function(bz_issue, at_name_bz)

    def _parse_author_details(self, bz_issue, at_name_bz):
        if 'email' in bz_issue[at_name_bz]:
            return self._get_people(bz_issue[at_name_bz]['name'], bz_issue[at_name_bz]['email'],
                                    bz_issue[at_name_bz]['real_name'])
        else:
            return self._get_people(bz_issue[at_name_bz]['name'])

    def _parse_string_field(self, bz_issue, at_name_bz):
        return bz_issue[at_name_bz]

    def _parse_array_field(self, bz_issue, at_name_bz):
        return bz_issue[at_name_bz]

    def _parse_issue_links(self, bz_issue, at_name_bz):
        type_mapping = {
            'blocks': 'Blocker',
            'dupe_of': 'Duplicate',
            'depends_on': 'Dependent',
        }

        issue_links = []
        if isinstance(bz_issue[at_name_bz], list):
            for link in bz_issue[at_name_bz]:
                issue_links.append({
                    'issue_id': self._get_issue_id_by_system_id(link),
                    'type': type_mapping[at_name_bz],
                    'effect': at_name_bz
                })
        else:
            if bz_issue[at_name_bz] is not None:
                issue_links.append({
                    'issue_id': self._get_issue_id_by_system_id(bz_issue[at_name_bz]),
                    'type': type_mapping[at_name_bz],
                    'effect': at_name_bz
                })

        return issue_links

    def _parse_date_field(self, bz_issue, at_name_bz):
        return dateutil.parser.parse(bz_issue[at_name_bz])

    def _transform_issue(self, bz_issue, bz_comments):
        try:
            mongo_issue = Issue.objects(issue_system_id=self.issue_system_id, external_id=str(bz_issue['id'])).get()
        except DoesNotExist:
            mongo_issue = Issue(
                issue_system_id=self.issue_system_id,
                external_id=str(bz_issue['id'])
            )

        # Set fields that can be directly mapped
        for at_name_bz, at_name_mongo in self.at_mapping.items():
            if isinstance(getattr(mongo_issue, at_name_mongo), list):
                # Get the result and the current value and merge it together
                result = self._parse_bz_field(bz_issue, at_name_bz)
                current_value = getattr(mongo_issue, at_name_mongo, list())
                if not isinstance(result, list):
                    result = [result]

                # Extend
                current_value.extend(result)
                if len(current_value) > 0 and at_name_mongo == 'issue_links':
                    current_value = list({v['issue_id']: v for v in current_value}.values())
                else:
                    current_value = list(set(current_value))

                # Set the attribute
                setattr(mongo_issue, at_name_mongo, copy.deepcopy(current_value))
            else:
                setattr(mongo_issue, at_name_mongo, self._parse_bz_field(bz_issue, at_name_bz))

        # The first comment is the description! Bugzilla does not have a separate description field. The comment
        # with the count == 0 is the description
        for comment in bz_comments:
            if comment['count'] == 0:
                mongo_issue.desc = comment['text']
                break

        # Bugzilla does not have a separate field for the type. Therefore, we distinguish between bug an enhancement
        # based on the severity information
        if bz_issue['severity'] == 'enhancement':
            mongo_issue.issue_type = 'Enhancement'
        else:
            mongo_issue.issue_type = 'Bug'

        return mongo_issue.save()

    def _get_mongo_attribute(self, field_name):
        return self.at_mapping[field_name]

    def _get_people(self, username, email=None, name=None):
        # Check if user was accessed before. This reduces the amount of API requests
        if username in self.people:
            return self.people[username]

        # If email and name are not set, make a request to get the user
        if email is None and name is None:
            user = self.bugzilla_agent.get_user(username)

            # If the user is not found, we must use the username name
            if user is None:
                email = None
                name = username
            else:
                email = user['email']
                name = user['real_name']

            # Check if email is none, this can happen as an email address may be excluded from the return value
            if email is None:
                # Check if the username is a valid email address, if yes use this
                if validate_email(username):
                    email = username
                else:
                    email = "nobody@nobody.com"

        # Replace the email address "anonymization"
        email = email.replace(' at ', '@').replace(' dot ', '.')
        people_id = People.objects(name=name, email=email).upsert_one(name=name, email=email, username=username).id
        self.people[username] = people_id
        return people_id

    def _get_issue_id_by_system_id(self, system_id):
        try:
            issue_id = Issue.objects(issue_system_id=self.issue_system_id, external_id=str(system_id)).only('id').get().id
        except DoesNotExist:
            issue_id = Issue(issue_system_id=self.issue_system_id, external_id=str(system_id)).save().id

        return issue_id
