import abc
import os
import sys
import logging


class BaseBackend(metaclass=abc.ABCMeta):

    @abc.abstractproperty
    def identifier(self):
        return

    def __init__(self, cfg, issue_system_id, project_id):
        self.config = cfg
        self.issue_system_id = issue_system_id
        self.project_id = project_id
        self.debug_level = logging.DEBUG

        if self.config is not None:
            self.debug_level = self.config.get_debug_level()

    @abc.abstractmethod
    def process(self):
        pass

    @staticmethod
    def _import_backends():
        backend_files = [x[:-3] for x in os.listdir(os.path.dirname(os.path.realpath(__file__))) if x.endswith(".py")]
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        for backend in backend_files:
            __import__(backend)

    @staticmethod
    def find_fitting_backend(cfg, issue_system_id, project_id):
        BaseBackend._import_backends()

        for sc in BaseBackend.__subclasses__():
            backend = sc(cfg, issue_system_id, project_id)
            if backend.identifier == cfg.identifier:
                return backend

        return None

    @staticmethod
    def get_all_possible_backend_options():
        BaseBackend._import_backends()

        choices = []
        for sc in BaseBackend.__subclasses__():
            backend = sc(None, None, None)
            choices.append(backend.identifier)
        return choices
