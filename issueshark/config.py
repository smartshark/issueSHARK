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

        if args.proxy_host.startswith('http://'):
            self.proxy_host = args.proxy_host[7:]
        else:
            self.proxy_host = args.proxy_host

        self.proxy_port = args.proxy_port
        self.proxy_username = args.proxy_user
        self.proxy_password = args.proxy_password

    def get_proxy_string(self):
        if self.proxy_password is None or self.proxy_username is None:
            return 'http://'+self.proxy_host+':'+self.proxy_port
        else:
            return 'http://'+self.proxy_username+':'+self.proxy_password+'@'+self.proxy_host+':'+self.proxy_port

    def use_proxy(self):
        if self.proxy_host is None:
            return False

        return True

    def __str__(self):
        return "Config: identifier: %s, token: %s, tracking_url: %s, project_url: %s, host: %s, port: %s, user: %s, " \
               "password: %s, database: %s, authentication_db: %s, proxy_host: %s, proxy_port: %s, proxy_username: %s" \
               "proxy_password: %s" % \
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
                   self.authentication_db,
                   self.proxy_host,
                   self.proxy_port,
                   self.proxy_username,
                   self.proxy_password
               )



