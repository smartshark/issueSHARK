from mongoengine import Document, StringField, ListField, DateTimeField, IntField, ObjectIdField, DictField


class Issue(Document):
    meta = {
        'indexes': [
            'system_id',
            'project_id',
        ]
    }

    system_id = StringField(unique_with=['project_id'])
    project_id = ObjectIdField(unique_with=['system_id'])
    title = StringField()
    desc = StringField()
    created_at = DateTimeField()
    updated_at = DateTimeField()

    issue_type = StringField()
    priority = StringField()
    status = StringField()
    affects_versions = ListField(StringField())
    components = ListField(StringField())
    labels = ListField(StringField())
    resolution = StringField()
    fix_versions = ListField(StringField())
    assignee = ObjectIdField()
    issue_links = ListField(DictField())
    original_time_estimate=IntField()
    environment=StringField()

    def __str__(self):
        return "System_id: %s, project_id: %s, title: %s, desc: %s, created_at: %s, updated_at: %s, issue_type: %s," \
               " priority: %s, affects_versions: %s, components: %s, labels: %s, resolution: %s, fix_versions: %s," \
               "assignee: %s, issue_links: %s, status: %s, time_estimate: %s, environment %s" % (
            self.system_id, self.project_id, self.title, self.desc, self.created_at, self.updated_at, self.issue_type,
            self.priority, ','.join(self.affects_versions), ','.join(self.components), ','.join(self.labels),
            self.resolution, ','.join(self.fix_versions), self.assignee, str(self.issue_links), self.status,
            str(self.original_time_estimate), self.environment
        )


class Event(Document):
    STATI = (
        ('created', 'The issue was created by the actor.'),
        ('closed','The issue was closed by the actor. When the commit_id is present, it identifies the commit '
                  'that closed the issue using "closes / fixes #NN" syntax.'),
        ('reopened', 'The issue was reopened by the actor.'),
        ('subscribed', 'The actor subscribed to receive notifications for an issue.'),
        ('merged','The issue was merged by the actor. The `commit_id` attribute is the SHA1 of the HEAD '
                  'commit that was merged.'),
        ('referenced', 'The issue was referenced from a commit message. The `commit_id` attribute is the '
                       'commit SHA1 of where that happened.'),
        ('mentioned', 'The actor was @mentioned in an issue body.'),
        ('assigned', 'The issue was assigned to the actor.'),
        ('unassigned', 'The actor was unassigned from the issue.'),
        ('labeled', 'A label was added to the issue.'),
        ('unlabeled', 'A label was removed from the issue.'),
        ('milestoned', 'The issue was added to a milestone.'),
        ('demilestoned', 'The issue was removed from a milestone.'),
        ('renamed', 'The issue title was changed.'),
        ('locked', 'The issue was locked by the actor.'),
        ('unlocked','The issue was unlocked by the actor.'),
        ('head_ref_deleted', 'The pull requests branch was deleted.'),
        ('head_ref_restored', 'The pull requests branch was restored.'),
    )

    meta = {
        'indexes': [
            'issue_id',
            'created_at',
            ('issue_id', '-created_at')
        ]
    }

    system_id = StringField(unique=True)
    issue_id = ObjectIdField()
    created_at = DateTimeField()
    status = StringField(max_length=50, choices=STATI)
    author_id = ObjectIdField()

    old_value = StringField()
    new_value = StringField()

    '''
    label = StringField()
    commit_id = ObjectIdField()
    assignee_id = ObjectIdField()
    assigner_id = ObjectIdField()
    milestone = StringField()
    '''
'''
class Milestone(Document):
    title = StringField()
    desc = StringField()
    creator = ObjectIdField()
    created_at = DateTimeField()
    due_on = DateTimeField()
'''


class IssueComment(Document):
    meta = {
        'indexes': [
            'issue_id',
            'created_at',
        ]
    }

    system_id = IntField(unique=True)
    issue_id = ObjectIdField()
    created_at = DateTimeField()
    author_id = ObjectIdField()
    comment = StringField()


class People(Document):
    """ Document that inherits from :class:`mongoengine.Document`. Holds information for the people collection.

    :property name: name of the person (type: :class:`mongoengine.fields.StringField`)
    :property email: email of the person (type: :class:`mongoengine.fields.StringField`)

    .. NOTE:: Unique (or primary key) are the fields: name and email.
    """

     #PK: email, name
    email = StringField(max_length=150, required=True, unique_with=['name'])
    name = StringField(max_length=150, required=True, unique_with=['email'])
    username = StringField(max_length=300)

    def __hash__(self):
        return hash(self.name+self.email)


class Project(Document):
    """ Document that inherits from :class:`mongoengine.Document`. Holds information for the project collection.

    :property url: url to the project repository (type: :class:`mongoengine.fields.StringField`)
    :property name: name of the project (type: :class:`mongoengine.fields.StringField`)
    :property repositoryType: type of the repository (type: :class:`mongoengine.fields.StringField`)

    .. NOTE:: Unique (or primary key) is the field url.
    """
    # PK uri
    url = StringField(max_length=400, required=True, unique=True)
    name = StringField(max_length=100, required=True)
    repositoryType = StringField(max_length=15)
    issue_urls = ListField(StringField())


class Commit(Document):
    """ Document that inherits from :class:`mongoengine.Document`. Holds information for the commit collection.

    :property projectId: id of the project, which belongs to the file action (type: :class:`mongoengine.fields.ObjectIdField`)
    :property revisionHash: revision hash of the commit (type: :class:`mongoengine.fields.StringField`)
    :property branches: list of branches to which the commit belongs to (type: :class:`mongoengine.fields.ListField(:class:`mongoengine.fields.StringField`)`)
    :property tagIds: list of tag ids, which belong to the commit (type: :class:`mongoengine.fields.ListField(:class:`mongoengine.fields.ObjectIdField`)`)
    :property parents: list of parents of the commit (type: :class:`mongoengine.fields.ListField(:class:`mongoengine.fields.StringField`)`)
    :property authorId: id of the author of the commit (type: :class:`mongoengine.fields.ObjectIdField`)
    :property authorDate: date when the commit was created (type: :class:`mongoengine.fields.DateTimeField`)
    :property authorOffset: offset of the authorDate (type: :class:`mongoengine.fields.IntField`)
    :property committerId: id of the committer of the commit (type: :class:`mongoengine.fields.ObjectIdField`)
    :property committerDate: date when the commit was committed (type: :class:`mongoengine.fields.DateTimeField`)
    :property committerOffset: offset of the committerDate (type: :class:`mongoengine.fields.IntField`)
    :property message: commit message (type: :class:`mongoengine.fields.StringField`)
    :property fileActionIds: list of file action ids, which belong to the commit (type: :class:`mongoengine.fields.ListField(:class:`mongoengine.fields.ObjectIdField`)`)

    .. NOTE:: Unique (or primary key) are the fields projectId and revisionHash.
    """

    #PK: projectId and revisionhash
    projectId = ObjectIdField(required=True,unique_with=['revisionHash'] )
    revisionHash = StringField(max_length=50, required=True, unique_with=['projectId'])
    branches = ListField(StringField(max_length=500))
    tagIds = ListField(ObjectIdField())
    parents = ListField(StringField(max_length=50))
    authorId = ObjectIdField()
    authorDate = DateTimeField()
    authorOffset = IntField()
    committerId = ObjectIdField()
    committerDate = DateTimeField()
    committerOffset = IntField()
    message = StringField()
    fileActionIds = ListField(ObjectIdField())


    def __str__(self):
        return ""

