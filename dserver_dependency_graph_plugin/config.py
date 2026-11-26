import json
import os

AFFIRMATIVE_EXPRESSIONS = ['true', '1', 'y', 'yes', 'on']


CONFIG_SECRETS_TO_OBFUSCATE = [
    "MONGO_URI",
    "MONGO_DB",
    "MONGO_COLLECTION",
]


class Config(object):
    # MongoDB connection settings
    # These are required for the dependency graph plugin to connect to MongoDB
    MONGO_URI = os.environ.get("MONGO_URI")
    MONGO_DB = os.environ.get("MONGO_DB")
    MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION")
    # Enables the dependency graph routes (/graph/...).
    ENABLE_DEPENDENCY_VIEW = os.environ.get('DSERVER_ENABLE_DEPENDENCY_VIEW',
                                            'True').lower() in AFFIRMATIVE_EXPRESSIONS

    # Stop exploring a dependency graph once it has this many datasets.
    DEPENDENCY_GRAPH_MAX_SIZE = int(os.environ.get(
        'DSERVER_DEPENDENCY_GRAPH_MAX_SIZE', '1000'))

    # Specify a key or multiple possible keys that hold unidirectional
    # dependency information in form of parents' UUIDs. The syntax must be
    # a single key or a JSON-formatted list of keys.
    # Nested fields are separated by a dot (.)
    DEPENDENCY_KEYS = [
        'readme_parsed.derived_from.uuid',
        'annotations.source_dataset_uuid'
    ]

    dep_key = os.environ.get('DSERVER_DEPENDENCY_KEYS', '')
    if len(dep_key) > 0:
        try:
            DEPENDENCY_KEYS = json.loads(dep_key)
        except json.JSONDecodeError:  # assume only one key, plain string
            DEPENDENCY_KEYS = [dep_key]

    # Allow clients to submit their own dependency keys (POST
    # /graph/uuids/<uuid>). Off by default: queries on keys without an index
    # scan the whole collection.
    DYNAMIC_DEPENDENCY_KEYS = os.environ.get('DSERVER_DYNAMIC_DEPENDENCY_KEYS',
                                             'False').lower() in AFFIRMATIVE_EXPRESSIONS