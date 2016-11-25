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

    def process(self):
        agent = BugzillaAgent(logger, self.config)

        options = {
            'status': 'CLOSED'
        }
        agent.get_bug_list(options)
        agent.get_user(114)

        #print(parsed_url.scheme+"://"+parsed_url.netloc+parsed_url.path.split('/'))

        # Get last modification date (since then, we will collect bugs)
        last_issue = Issue.objects(issue_system_id=self.issue_system_id).order_by('-updated_at').only('updated_at').first()
        starting_date = None
        if last_issue is not None:
            starting_date = last_issue.updated_at

        # Get all issues
        issues = agent.get_bug_list(start_date=starting_date)

        # If no new bugs found, return
        if len(issues) == 0:
            logger.info('No new issues found. Exiting...')
            sys.exit(0)

        # Otherwise, go through all issues (and all pages)
        page_number = 1
        while len(issues) > 0:
            for issue in issues:
                self.store_issue(issue)
            page_number += 1
            issues = self.get_issues(pagecount=page_number, start_date=starting_date)

        '''
        # We can use "None" for both instead to not authenticate
        api_key = 'xxx'

        # Load our agent for BMO
        bmo = BMOAgent(None)

        # Set whatever REST API options we want


        # Get the bugs from the api
        buglist = bmo.get_bug_list(options)

        print("Found %s bugs" % (len(buglist)))

        for bug in buglist:
            print(bug)
        '''

