import os
import logging
import logging.config
import json
import sys
import argparse

from issueshark.backends.basebackend import BaseBackend
from issueshark.config import Config
from issueshark.issueshark import IssueSHARK


def setup_logging(default_path=os.path.dirname(os.path.realpath(__file__))+"/loggerConfiguration.json",
                  default_level=logging.INFO):
        """
        Setup logging configuration

        :param default_path: path to the logger configuration
        :param default_level: defines the default logging level if configuration file is not found
        (default:logging.INFO)
        """
        path = default_path
        if os.path.exists(path):
            with open(path, 'rt') as f:
                config = json.load(f)
            logging.config.dictConfig(config)
        else:
            logging.basicConfig(level=default_level)


def start():
    """
    Starts the application. First parses the different command line arguments and then it gives these to the mecoApp
    :return:
    """
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Starting issueSHARK...")

    try:
        backend_choices = BaseBackend.get_all_possible_backend_options()
    except Exception as e:
        logger.error("Failed to instantiate backend. Message: %s" % (e))
        sys.exit(1)

    logger.debug("Found the following backends: %s" % ', '.join(backend_choices))

    parser = argparse.ArgumentParser(description='Collects information from different issue tracking systems.')
    parser.add_argument('-U', '--db-user', help='Database user name', default='root')
    parser.add_argument('-P', '--db-password', help='Database user password', default='root')
    parser.add_argument('-DB', '--db-database', help='Database name', default='smartshark')
    parser.add_argument('-H', '--db-hostname', help='Name of the host, where the database server is running',
                        default='localhost')
    parser.add_argument('-p', '--db-port', help='Port, where the database server is listening', default=27017, type=int)
    parser.add_argument('-a', '--db-authentication', help='Name of the authentication database')
    parser.add_argument('-u', '--url', help='URL of the VCS of the project.', required=True)
    parser.add_argument('-i', '--issueurl', help='URL to the bugtracking system.', required=True)
    parser.add_argument('-b', '--backend', help='Backend to use for the issue parsing', default='github',
                        choices=backend_choices)
    parser.add_argument('-t', '--token', help='Token for accessing.')

    try:
        args = parser.parse_args()
        cfg = Config(args)
    except Exception as e:
        logger.error(e)
        sys.exit(1)

    issueshark = IssueSHARK()
    issueshark.start(cfg)

if __name__ == "__main__":
    start()