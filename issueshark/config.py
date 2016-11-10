class Config(object):
    def __init__(self, args):
        self.tracking_url = args.issueurl.rstrip('/')
        self.identifier = args.backend
        self.token = args.token
        self.project_url = args.url.rstrip('/')
        self.host = args.db_hostname
        self.port = args.db_port
        self.user = args.db_user
        self.password = args.db_password
        self.database = args.db_database
        self.authentication_db = args.db_authentication

    def __str__(self):
        return "Config: identifier: %s, token: %s, tracking_url: %s, project_url: %s, host: %s, port: %s, user: %s, " \
               "password: %s, database: %s, authentication_db: %s" % \
               (
                   self.identifier,
                   self.token,
                   self.tracking_url,
                   self.project_url,
                   self.host,
                   self.port,
                   self.user,
                   self.password,
                   self.database,
                   self.authentication_db

               )



