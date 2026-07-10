import abc
import os
import sys
import logging
from deepdiff import DeepDiff

class BaseBackend(metaclass=abc.ABCMeta):
    """
    BaseBackend from which all backends must inherit
    """

    @abc.abstractproperty
    def identifier(self):
        """
        Identifier of the backend

        .. WARNING:: Must be unique among all backends
        """
        return

    def __init__(self, cfg, issue_system_id, project_id, last_system_id):
        """
        Initialization of the backend

        :param cfg: holds als configuration. Object of class :class:`~issueshark.config.Config`
        :param issue_system_id: id of the issue system for which data should be collected. :class:`bson.objectid.ObjectId`
        :param project_id: id of the project to which the issue system belongs. :class:`bson.objectid.ObjectId`
        """
        self.issue_id = None
        self.parsed_issues = {'issues': {}, 'comments': {}, 'events': {}}
        self.old_issues = {'issues': {}}
        self.issues_diff = {}
        self.config = cfg
        self.issue_system_id = issue_system_id
        self.project_id = project_id
        self.last_system_id = last_system_id
        self.debug_level = logging.DEBUG

        if self.config is not None:
            self.debug_level = self.config.get_debug_level()

    @abc.abstractmethod
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
    def find_fitting_backend(cfg, issue_system_id, project_id, last_system_id):
        """
        Finds a fitting backend by first importing all backends and checking if the identifier of the backend
        matches the identifier given by the user

        :param cfg: holds als configuration. Object of class :class:`~issueshark.config.Config`
        :param issue_system_id: id of the issue system for which data should be collected. :class:`bson.objectid.ObjectId`
        :param project_id: id of the project to which the issue system belongs. :class:`bson.objectid.ObjectId`
        """
        BaseBackend._import_backends()

        for sc in BaseBackend.__subclasses__():
            backend = sc(cfg, issue_system_id, project_id, last_system_id)
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
            backend = sc(None, None, None, None)
            choices.add(backend.identifier)

        return choices

    def save_issues(self):
        """
          Saves issues and related data.

          Iterates through parsed issues, checks for differences, and saves updates.
          For each issue with differences, it updates and saves the issue, as well as
          associated comments and events.

          Param:
              None

          Returns:
              None
          """
        for issue_id, issue in self.parsed_issues['issues'].items():
            if issue_id in self.issues_diff and self.issues_diff[issue_id]:
                issue.save()
                for field in ['comments', 'events']:
                    if issue_id not in self.parsed_issues[field]:
                        continue
                    for item_id, item in self.parsed_issues[field][issue_id].items():
                        item.issue_id = issue.id
                        item.save()
            else:
                self.old_issues['issues'][issue_id]['issue_system_ids'].append(self.issue_system_id)
                self.old_issues['issues'][issue_id].save()

    def check_diff_issue(self, old, new):
        """
        Compares two sets of data representing different issue configurations
        and checks for differences in the 'run_id' attribute.

        :param old: dict
            The old job artifacts configuration data.
        :param new: dict
            The new job artifacts configuration data.

        :return: None
        """

        self.check_diff(old, new, ["root['issue_system_ids']", "root['issue_links']", "root['parent_issue_id']"])

    def check_diff_comment_event(self, old, new):
        """
        Compares two sets of data representing different comment event configurations
        and checks for differences in the 'run_id' attribute.

        :param old: dict
            The old job artifacts configuration data.
        :param new: dict
            The new job artifacts configuration data.

        :return: None
        """

        self.check_diff(old, new, ["root['issue_id']", "root['old_value']", "root['new_value']"])

    def check_diff(self, old, new, ex_path):
        """
        Compare and identify differences between old and new objects.

        This function compares two objects, `old` and `new`, typically representing data from different
        states, to identify differences between them. The comparison is performed by utilizing the
        DeepDiff library. Differences are stored in the `actions_diff` dictionary for the pull request
        identified by `self.pr_id`. If differences are found, the corresponding key in `actions_diff`
        is set to `True`.

        :param old: The old object to be compared.
        :param new: The new object to be compared.
        :param ex_path: List of paths to be excluded from the comparison.

        """
        if self.issue_id not in self.issues_diff:
            self.issues_diff[self.issue_id] = False

        if old:
            diff = DeepDiff(t1=old.to_mongo().to_dict(), t2=new.to_mongo().to_dict(), exclude_paths=ex_path + ['_id'], ignore_order=True)
            if diff:
                self.issues_diff[self.issue_id] = True
        else:
            self.issues_diff[self.issue_id] = True


