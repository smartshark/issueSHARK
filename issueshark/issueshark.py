import logging
import timeit

import sys

from datetime import datetime
from mongoengine import connect, DoesNotExist
from issueshark.backends.basebackend import BaseBackend
from pycoshark.mongomodels import Project, IssueSystem
from pycoshark.utils import create_mongodb_uri_string

logger = logging.getLogger("main")


class IssueSHARK(object):
    """
    Main application

    1. Connects to MongoDB

    2. Searches for the project in it

    3. Creates an issue system document, if not already in the database. If it is in database, it updates the \
    last_updated field

    4. Finds fitting backend via :func:`~issueshark.backends.basebackend.BaseBackend.find_fitting_backend`

    5. Calls :func:`~issueshark.backends.basebackend.BaseBackend.process` on the found backend
    """
    def __init__(self):
        pass

    def start(self, cfg):
        """
        Starts the collection process

        :param cfg: holds all configuration parameters. Object of class :class:`~issueshark.config.Config`
        """
        logger.setLevel(cfg.get_debug_level())
        start_time = timeit.default_timer()

        # Connect to mongodb
        uri = create_mongodb_uri_string(cfg.user, cfg.password, cfg.host, cfg.port, cfg.authentication_db,
                                        cfg.ssl_enabled)
        connect(cfg.database, host=uri)

        # Get the project for which issue data is collected
        try:
            project_id = Project.objects(name=cfg.project_name).get().id
        except DoesNotExist:
            logger.error('Project %s not found!' % cfg.project_name)
            sys.exit(1)

        # Create issue system if not already there
        last_system = IssueSystem.objects.filter(project_id=project_id).order_by('-collection_date').first()
        self.last_system_id = last_system.id if last_system else None

        issue_system = IssueSystem(project_id=project_id, url=cfg.tracking_url, collection_date=datetime.now())
        issue_system.save()

        # Find correct backend
        backend = BaseBackend.find_fitting_backend(cfg, issue_system.id, project_id, self.last_system_id)
        logger.debug("Using backend: %s" % backend.identifier)

        # Process the issues for the corresponding project_id
        backend.process()

        elapsed = timeit.default_timer() - start_time
        logger.info("Execution time: %0.5f s" % elapsed)

