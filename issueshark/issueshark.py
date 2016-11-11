import logging
import timeit

import sys
from mongoengine import connect, DoesNotExist
from issueshark.backends.basebackend import BaseBackend
from issueshark.storage.models import Project

logger = logging.getLogger("main")


class IssueSHARK(object):
    def __init__(self):
        pass

    def start(self, cfg):
        start_time = timeit.default_timer()

        # Find correct backend
        backend = BaseBackend.find_fitting_backend(cfg)
        logger.debug("Using backend: %s" % backend.identifier)

        # Connect to mongodb
        connect(cfg.database, username=cfg.user, password=cfg.password, host=cfg.host, port=cfg.port,
                authentication_source=cfg.authentication_db)

        try:
            project = Project.objects(url=cfg.project_url).get()
            project.issue_urls.append(cfg.tracking_url)
            project_id = project.save().id
        except DoesNotExist:
            logger.error('Project not found. Use vcsSHARK beforehand!')
            sys.exit(1)

        backend.process(project_id)

        elapsed = timeit.default_timer() - start_time
        logger.info("Execution time: %0.5f s" % elapsed)

