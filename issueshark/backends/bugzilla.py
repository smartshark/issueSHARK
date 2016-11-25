import sys

from issueshark.backends.basebackend import BaseBackend
from issueshark.backends.helpers.bugzillaagent import BugzillaAgent
import urllib.parse
import logging

from issueshark.mongomodels import Issue

logger = logging.getLogger('backend')

class BugzillaBackend(BaseBackend):
    @property
    def identifier(self):
        return 'bugzilla'

    def __init__(self, cfg, issue_system_id, project_id):
        super().__init__(cfg, issue_system_id, project_id)

        logger.setLevel(self.debug_level)
        self.bugzilla_agent = None

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
                self._process_issue(issue)

            # Go through the next issues
            issues = self.bugzilla_agent.get_bug_list(last_change_time=starting_date, limit=50, offset=processed_results)
            processed_results += 50

    def _process_issue(self, issue):
        # Transform issue
        # TODO

        # Go through history
        # 1) Set back issue
        # 2) Store events

        # Store issue

        # Store comments
        print(self.bugzilla_agent.get_comments(issue['id']))

