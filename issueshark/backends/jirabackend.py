import dateutil
import sys
from mongoengine import DoesNotExist

from issueshark.backends.basebackend import BaseBackend
from urllib.parse import urlparse, quote_plus
from jira import JIRA

import logging

from issueshark.storage.models import Event, People, Issue, IssueComment

logger = logging.getLogger('backend')

class JiraException(Exception):
    pass

class JiraBackend(BaseBackend):
    @property
    def identifier(self):
        return 'jira'

    def __init__(self, cfg):
        super().__init__(cfg)

        logger.setLevel(self.debug_level)
        self.people = {}

    def process(self, project_id):
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
        jira = JIRA(options, basic_auth=(self.config.issue_user, self.config.issue_password),
                    proxies=self.config.get_proxy_dictionary())

        # Get last modification date (since then, we will collect bugs)
        last_issue = Issue.objects(project_id=project_id).order_by('-updated_at').only('updated_at').first()
        if last_issue is not None:
            starting_date = last_issue.updated_at
            query = "project=%s and updatedDate > '%s' ORDER BY createdDate ASC" % (
                project_name,
                starting_date.strftime('%Y/%m/%d %H:%M')
            )
        else:
            query = "project=%s ORDER BY createdDate ASC" % project_name

        # We search our intital set of issues
        issues = jira.search_issues(query, startAt=0, maxResults=50)
        logger.debug('Found %d issues via url %s' % (len(issues), jira._get_url('search?jql=%s' % quote_plus(query))))

        # If no new bugs found, return
        if len(issues) == 0:
            logger.info('No new issues found. Exiting...')
            sys.exit(0)

        # Otherwise, go through all issues
        processed_results = 50
        while len(issues) > 0:
            logger.info("Processing %d issues..." % len(issues))
            for issue in issues:
                self._process_issue(jira, issue.key, project_id)

            # Go through the next issues
            issues = jira.search_issues(query, startAt=processed_results, maxResults=processed_results+50)
            processed_results += 50

    def _transform_jira_issue(self, jira_issue, project_id, jira_client):
        updated_at = dateutil.parser.parse(jira_issue.fields.updated)
        created_at = dateutil.parser.parse(jira_issue.fields.created)
        try:
            # We can not return here, as the issue might be updated. This means, that the title could be updated
            # as well as comments and new events
            new_issue = Issue.objects(project_id=project_id, system_id=jira_issue.key).get()
        except DoesNotExist:
            new_issue = Issue(
                project_id=project_id,
                system_id=jira_issue.key,
                title=jira_issue.fields.summary,
                desc=jira_issue.fields.description,
                created_at=created_at,
                updated_at=updated_at,
                issue_type=jira_issue.fields.issuetype.name,
            )

        new_issue.priority=jira_issue.fields.priority.name
        new_issue.status = jira_issue.fields.status
        new_issue.affects_versions = [version.name for version in jira_issue.fields.versions]
        new_issue.components = [component.name for component in jira_issue.fields.components]
        new_issue.labels = jira_issue.fields.labels

        if jira_issue.fields.resolution is not None:
            new_issue.resolution = jira_issue.fields.resolution.name

        new_issue.environment=jira_issue.fields.environment
        new_issue.original_time_estimate=jira_issue.fields.timeoriginalestimate

        new_issue.fix_versions = [version.name for version in jira_issue.fields.fixVersions]

        if jira_issue.fields.assignee is not None:
            new_issue.assignee = self._get_people(jira_client, jira_issue.fields.assignee.name,
                                                  name=jira_issue.fields.assignee.displayName,
                                                  email=jira_issue.fields.assignee.emailAddress)

        if jira_issue.fields.issuelinks:
            links = []
            for issue_link in jira_issue.fields.issuelinks:
                if hasattr(issue_link, 'outwardIssue'):
                    try:
                        issue_id = Issue.objects(project_id=project_id, system_id=issue_link.outwardIssue.key
                                                 ).only('id').get().id
                    except DoesNotExist:
                        issue_id = Issue(project_id=project_id, system_id=issue_link.outwardIssue.key).save().id
                else:
                    try:
                        issue_id = Issue.objects(project_id=project_id, system_id=issue_link.inwardIssue.key
                                                 ).only('id').get().id
                    except DoesNotExist:
                        issue_id = Issue(project_id=project_id, system_id=issue_link.inwardIssue.key).save().id

                links.append({'issue_id': issue_id, 'type': issue_link.type.name, 'effect': issue_link.type.outward})
            new_issue.issue_links = links

        return new_issue

    def _process_issue(self, jira_client, issue_key, project_id):
        issue = jira_client.issue(issue_key, expand='changelog')

        # Transform jira issue to mongo issue
        new_issue = self._transform_jira_issue(issue, project_id, jira_client)

        # Go through all events and set back issue items till we get the original one
        events = []
        for history in reversed(issue.changelog.histories):
            i = 0
            for item in reversed(history.items):
                # Create event list, but check before if event already exists
                event = self._process_event(history, item, i, jira_client, project_id)
                if event is not None:
                    events.append(event)

                # Set back issue
                self._set_back_issue_field(new_issue, item, jira_client, project_id)

                i += 1

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
        self._process_comments(issue, issue_id, jira_client)

    def _process_comments(self, issue, issue_id, jira_client):
        comments_to_insert = []
        for comment in issue.fields.comment.comments:
            created_at = dateutil.parser.parse(comment.created)
            try:
                IssueComment.objects(system_id=comment.id).get()
                continue
            except DoesNotExist:
                mongo_comment = IssueComment(
                    system_id=comment.id,
                    issue_id=issue_id,
                    created_at=created_at,
                    author_id=self._get_people(jira_client, comment.author.name, comment.author.emailAddress,
                                               comment.author.displayName),
                    comment=comment.body,
                )
                comments_to_insert.append(mongo_comment)

        # If comments need to be inserted -> bulk insert
        if comments_to_insert:
            IssueComment.objects.insert(comments_to_insert, load_bulk=False)

    def _process_event(self, history, item, i, client, project_id):
        created_at = dateutil.parser.parse(history.created)

        author_id = self._get_people(client, history.author.name, name=history.author.displayName,
                                     email=history.author.emailAddress)

        # Maybe this should be  changed when it becomes important
        system_id = str(history.id)+"%%"+str(i)

        try:
            Event.objects(system_id=system_id).get()
            return None
        except DoesNotExist:
            event = Event(
                system_id=system_id,
                created_at=created_at,
                status=self._replace_item_field_for_storage(item.field).lower(),
                author_id=author_id,
            )

        if item.field == 'assignee':
            if getattr(item, 'from') is not None:
                event.old_value = self._get_people(client, getattr(item, 'from'))

            if item.to is not None:
                event.new_value = self._get_people(client, item.to)
        elif item.field == 'Link':
            if getattr(item, 'from') is not None:
                try:
                    issue_id_old = Issue.objects(project_id=project_id, system_id=getattr(item, 'from'))\
                        .only('id').get().id
                except DoesNotExist:
                    issue_id_old = Issue(project_id=project_id, system_id=getattr(item, 'from')).save().id
                event.old_value = issue_id_old
            if item.to is not None:
                try:
                    issue_id_new = Issue.objects(project_id=project_id, system_id=item.to).only('id').get().id
                except DoesNotExist:
                    issue_id_new = Issue(project_id=project_id, system_id=item.to).save().id
                event.new_value = issue_id_new
        else:
            event.old_value = item.fromString
            event.new_value = item.toString

        return event

    def _replace_item_field_for_storage(self, status):
        if status == 'assignee':
            return 'assigned'
        return status

    def _set_back_issue_field(self, issue, item, jira_client, project_id):
        if item.field == 'description':
            issue.desc = item.fromString
        elif item.field == 'priority':
            issue.priority = item.fromString
        elif item.field == 'status':
            issue.status = item.fromString
        elif item.field == 'resolution':
            issue.resolution = item.fromString
        elif item.field == 'summary':
            issue.title = item.fromString
        elif item.field == 'issuetype':
            issue.issue_type = item.fromString
        elif item.field == 'environment':
            issue.environment = item.fromString
        elif item.field == 'timeoriginalestimate':
            issue.original_time_estimate = item.fromString
        elif item.field == 'assignee':
            if getattr(item, 'from') is not None:
                issue.assignee = self._get_people(jira_client, getattr(item, 'from'))
            else:
                issue.assignee = None
        elif item.field == 'Version':
            # If a version was removed, we need to add it to get the older state
            if not item.toString and item.fromString:
                issue.affects_versions.append(item.fromString)

            if not item.fromString and item.toString:
                issue.affects_versions.remove(item.toString)

            if item.fromString and item.toString:
                issue.affects_versions.add(item.fromString)
                issue.affects_versions.remove(item.toString)

        elif item.field == 'Component':
            # If a component was removed, we need to add it to get the older state
            if not item.toString and item.fromString:
                issue.components.append(item.fromString)

            if not item.fromString and item.toString:
                issue.components.remove(item.toString)

            if item.fromString and item.toString:
                issue.components.add(item.fromString)
                issue.components.remove(item.toString)

        elif item.field == 'labels':
            # If a label was removed, we need to add it to get the older state
            if not item.toString and item.fromString:
                issue.labels.append(item.fromString)

            if not item.fromString and item.toString:
                issue.labels.remove(item.toString)

            if item.fromString and item.toString:
                issue.labels.append(item.fromString)
                issue.labels.remove(item.toString)
        elif item.field == 'Fix Version':
            # If a fixed version was removed, we need to add it to get the older state
            if not item.toString and item.fromString:
                issue.fix_versions.append(item.fromString)

            if not item.fromString and item.toString:
                issue.fix_versions.remove(item.toString)

            if item.fromString and item.toString:
                issue.fix_versions.append(item.fromString)
                issue.fix_versions.remove(item.toString)

        elif item.field == 'Link':
            # If a link was removed, we need to add it to get the older state
            if item.to is None:
                # Here information is lost! We can not know the type and effect of this issuelink, as it is not in the
                # data!
                issue_id = Issue.objects(project_id=project_id, system_id=getattr(item, 'from')).only('id').get().id
                issue.issue_links.append({
                    'issue_id': issue_id, 'type': None, 'effect': None
                })
            else:
                index_of_found_entry = 0
                issue_id = Issue.objects(project_id=project_id, system_id=item.to).only('id').get().id
                for issue_link in issue.issue_links:
                    if issue_link['issue_id'] == issue_id:
                        break
                    index_of_found_entry += 1

                del issue.issue_links[index_of_found_entry]
        elif item.field == 'Attachment' or item.field == 'Release Note' or item.field == 'RemoteIssueLink' or \
                        item.field == 'Comment' or item.field == 'Hadoop Flags' or item.field == 'timeestimate':
            # Ignore these fields
            return
        else:
            logger.error('Item field "%s" not handled' % item.field)
            sys.exit(1)

    def _get_people(self, jira_client, username, email=None, name=None):
        # Check if user was accessed before. This reduces the amount of API requests to github
        if username in self.people:
            return self.people[username]

        if email is None and name is None:
            user = self._get_user(jira_client, username)
            email = user.emailAddress
            name = user.displayName

        email = email.replace(' at ', '@').replace(' dot ', '.')
        people_id = People.objects(name=name, email=email).upsert_one(name=name, email=email, username=username).id
        self.people[username] = people_id
        return people_id

    def _get_user(self, jira_client, username):
        if username is None:
            return None

        return jira_client.find('user?username={0}', username)