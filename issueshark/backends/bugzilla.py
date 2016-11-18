from issueshark.backends.basebackend import BaseBackend


class BugzillaBackend(BaseBackend):
    @property
    def identifier(self):
        return 'bugzilla'

    def __init__(self, cfg, project_id):
        super().__init__(cfg, project_id)

    def process(self):
        pass
