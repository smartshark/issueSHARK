import logging
import timeit

import sys

import datetime
from mongoengine import connect, DoesNotExist
from issueshark.backends.basebackend import BaseBackend
from pycoshark.mongomodels import Project, IssueSystem

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
        connect(cfg.database, username=cfg.user, password=cfg.password, host=cfg.host, port=cfg.port,
                authentication_source=cfg.authentication_db)

        # Get the project for which issue data is collected
        try:
            project_id = Project.objects(name=cfg.project_name).get().id
        except DoesNotExist:
            logger.error('Project %s not found!' % cfg.project_name)
            sys.exit(1)

        # Create issue system if not already there
        try:
            issue_system = IssueSystem.objects(url=cfg.tracking_url).get()
        except DoesNotExist:
            issue_system = IssueSystem(project_id=project_id, url=cfg.tracking_url).save()
        issue_system.last_updated = datetime.datetime.now()
        issue_system.save()

        # Find correct backend
        backend = BaseBackend.find_fitting_backend(cfg, issue_system.id, project_id)
        logger.debug("Using backend: %s" % backend.identifier)

        # Process the issues for the corresponding project_id
        backend.process()

        elapsed = timeit.default_timer() - start_time
        logger.info("Execution time: %0.5f s" % elapsed)

