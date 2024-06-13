import logging
import os
import sys
from abc import abstractmethod, ABCMeta


class BaseBackend(metaclass=ABCMeta):
    """
    BaseBackend from which all backends must inherit
    """

    @property
    @abstractmethod
    def identifier(self):
        """
        Identifier of the backend

        .. WARNING:: Must be unique among all backends
        """
        return

    def __init__(self, cfg, issue_system_id, project_id):
        """
        Initialization of the backend

        :param cfg: holds als configuration. Object of class :class:`~issueshark.config.Config`
        :param issue_system_id: id of the issue system for which data should be collected. :class:`bson.objectid.ObjectId`
        :param project_id: id of the project to which the issue system belongs. :class:`bson.objectid.ObjectId`
        """
        self.config = cfg
        self.issue_system_id = issue_system_id
        self.project_id = project_id
        self.debug_level = logging.DEBUG

        if self.config is not None:
            self.debug_level = self.config.get_debug_level()

    @abstractmethod
    def process(self):
        """
        Method that is called if the collection process should be started
        """
        pass

    @staticmethod
    def _import_backends():
        """
        Imports all backends that are in the backends folder
        """
        backend_files = [x[:-3] for x in os.listdir(os.path.dirname(os.path.realpath(__file__))) if x.endswith(".py")]
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        for backend in backend_files:
            __import__(backend)

    @staticmethod
    def find_fitting_backend(cfg, issue_system_id, project_id):
        """
        Finds a fitting backend by first importing all backends and checking if the identifier of the backend
        matches the identifier given by the user

        :param cfg: holds als configuration. Object of class :class:`~issueshark.config.Config`
        :param issue_system_id: id of the issue system for which data should be collected. :class:`bson.objectid.ObjectId`
        :param project_id: id of the project to which the issue system belongs. :class:`bson.objectid.ObjectId`
        """
        BaseBackend._import_backends()

        for sc in BaseBackend.__subclasses__():
            backend = sc(cfg, issue_system_id, project_id)
            if backend.identifier == cfg.identifier:
                return backend

        return None

    @staticmethod
    def get_all_possible_backend_options():
        """
        Returns all possible backend options by importing the backends and getting their identifier
        """
        BaseBackend._import_backends()

        choices = set()
        for sc in BaseBackend.__subclasses__():
            backend = sc(None, None, None)
            choices.add(backend.identifier)

        return choices
