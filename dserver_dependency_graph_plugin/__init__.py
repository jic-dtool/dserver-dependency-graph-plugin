try:
    from importlib.metadata import version, PackageNotFoundError
except ModuleNotFoundError:
    from importlib_metadata import version, PackageNotFoundError

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # package is not installed
    pass

import logging

from flask import (
    abort,
    current_app,
    jsonify,
)
from dservercore.utils_auth import (
    jwt_required,
    get_jwt_identity,
)
from flask_smorest import Blueprint
from flask_smorest.pagination import PaginationParameters
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from dservercore import AuthenticationError, ExtensionABC
from dservercore.sql_models import DatasetSchema
from dservercore.utils import _preprocess_privileges

from .schemas import DependencyKeysSchema
from .graph import dependency_graph
from .config import Config, CONFIG_SECRETS_TO_OBFUSCATE


graph_bp = Blueprint("graph", __name__, url_prefix="/graph")


logger = logging.getLogger(__name__)


def _config(key):
    return current_app.config.get(key, getattr(Config, key))


def dependency_graph_by_user_and_uuid(username, uuid, dependency_keys=None):
    """Return all datasets within the same dependency graph as uuid.

    Only datasets in base URIs the user may search are traversed and
    returned.

    :param username: username
    :param uuid: UUID of dataset to start dependency graph search from
    :param dependency_keys: keys naming parent UUIDs; the configured
        DEPENDENCY_KEYS if None, or if DYNAMIC_DEPENDENCY_KEYS is disabled
    :returns: List of dicts if user is valid and has access to datasets.
              Empty list if user is valid but has not got access to any
              datasets.
    :raises: AuthenticationError if user is invalid.
    """
    if not _config("ENABLE_DEPENDENCY_VIEW"):
        logger.warning(
            "Received dependency graph request from user '{}', but "
            "feature is disabled.".format(username))
        return []

    default_keys = list(_config("DEPENDENCY_KEYS"))
    if dependency_keys is None:
        dependency_keys = default_keys
    elif not _config("DYNAMIC_DEPENDENCY_KEYS") and \
            sorted(dependency_keys) != sorted(default_keys):
        logger.info(
            "Ignoring dependency keys '{}' from user '{}': dynamic dependency "
            "keys are disabled (DSERVER_DYNAMIC_DEPENDENCY_KEYS).".format(
                dependency_keys, username))
        dependency_keys = default_keys
    for key in dependency_keys:
        if not key or "$" in key:
            raise ValueError(f"Invalid dependency key: {key!r}")

    base_uris = _preprocess_privileges(username, {})["base_uris"]
    if not base_uris:
        return []

    return dependency_graph(
        DependencyGraphExtension.db[current_app.config["MONGO_COLLECTION"]],
        uuid, base_uris, dependency_keys,
        max_size=int(_config("DEPENDENCY_GRAPH_MAX_SIZE")))


def _respond(pagination_parameters, username, uuid, dependency_keys=None):
    try:
        datasets = dependency_graph_by_user_and_uuid(
            username, uuid, dependency_keys)
    except AuthenticationError:
        abort(401)
    except ValueError as e:
        abort(400, str(e))
    pagination_parameters.item_count = len(datasets)
    return jsonify(
        datasets[pagination_parameters.first_item:
                 pagination_parameters.last_item + 1]
    )


@graph_bp.route("/uuids/<uuid>", methods=["GET"])
@graph_bp.response(200, DatasetSchema(many=True))
@graph_bp.paginate()
@jwt_required()
def lookup_dependency_graph_by_default_keys(pagination_parameters: PaginationParameters,
                                            uuid):
    """List the datasets within the same dependency graph as <uuid>.

    Each dataset carries ``derived_from``, the UUIDs of its parents within
    the result. Only datasets the user can search are traversed, so the
    graph may be incomplete."""
    return _respond(pagination_parameters, get_jwt_identity(), uuid)


@graph_bp.route("/uuids/<uuid>", methods=["POST"])
@graph_bp.arguments(DependencyKeysSchema(partial=True))
@graph_bp.response(200, DatasetSchema(many=True))
@graph_bp.paginate()
@jwt_required()
def lookup_dependency_graph_by_custom_keys(dependency_keys: DependencyKeysSchema,
                                           pagination_parameters: PaginationParameters,
                                           uuid):
    """List the datasets within the same dependency graph as <uuid>, with
    custom dependency keys (if DYNAMIC_DEPENDENCY_KEYS is enabled)."""
    return _respond(pagination_parameters, get_jwt_identity(), uuid,
                    dependency_keys.get("dependency_keys"))


class DependencyGraphExtension(ExtensionABC):
    """Extensions for building and queryng dependency graphs."""

    # NOTE: Not very neat using class variables here, but the way the plugin
    # system works now, we need to provide the class-external route above some
    # means of accessing the database that's configured within the init_app
    # method here.
    client = None
    collection = None
    db = None

    def init_app(self, app):
        try:
            self._mongo_uri = app.config["MONGO_URI"]
            DependencyGraphExtension.client = MongoClient(self._mongo_uri,
                                      uuidRepresentation='standard')
        except KeyError:
            raise(RuntimeError("Please set the MONGO_URI environment variable"))  # NOQA

        try:
            self._mongo_db = app.config["MONGO_DB"]
            DependencyGraphExtension.db = self.client[self._mongo_db]
        except KeyError:
            raise(RuntimeError("Please set the MONGO_DB environment variable"))  # NOQA

        try:
            self._mongo_collection = app.config["MONGO_COLLECTION"]
            DependencyGraphExtension.collection = self.db[self._mongo_collection]
        except KeyError:
            raise(RuntimeError("Please set the MONGO_COLLECTION environment variable"))  # NOQA

        self._create_indexes(
            app.config.get("DEPENDENCY_KEYS", Config.DEPENDENCY_KEYS))

    def _create_indexes(self, dependency_keys):
        """Index uuid and the dependency keys, which the traversal queries.

        Creating an index that exists is a no-op. Failures (e.g. missing
        privileges, MongoDB not reachable yet) only slow queries down."""
        for key in ["uuid", *dependency_keys]:
            try:
                DependencyGraphExtension.collection.create_index(key)
            except PyMongoError as e:
                logger.warning("Could not create index on '%s': %s", key, e)

    def register_dataset(self, dataset_info):
        """Does nothing: the graph is read from the search plugin's
        collection."""
        pass

    def get_config(self):
        """Return initial Config object, available app-instance independent."""
        return Config

    def get_config_secrets_to_obfuscate(self):
        """Return config secrets never to be exposed clear text."""
        return CONFIG_SECRETS_TO_OBFUSCATE

    def get_blueprint(self):
        return graph_bp
