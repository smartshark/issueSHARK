import abc
import os
import sys


class BaseBackend(metaclass=abc.ABCMeta):

    @abc.abstractproperty
    def identifier(self):
        return

    def __init__(self, cfg):
        self.config = cfg

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
    def find_fitting_backend(cfg):
        BaseBackend._import_backends()

        for sc in BaseBackend.__subclasses__():
            backend = sc(cfg)
            if backend.identifier == cfg.identifier:
                return backend

        return None

    @staticmethod
    def get_all_possible_backend_options():
        BaseBackend._import_backends()

        choices = []
        for sc in BaseBackend.__subclasses__():
            backend = sc(None)
            choices.append(backend.identifier)
        return choices
