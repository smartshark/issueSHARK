import logging
import timeit
import time

import datetime
import requests

from mongoengine import connect
from issueshark.backends.basebackend import BaseBackend

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

        backend.process()

        elapsed = timeit.default_timer() - start_time
        logger.info("Execution time: %0.5f s" % elapsed)

