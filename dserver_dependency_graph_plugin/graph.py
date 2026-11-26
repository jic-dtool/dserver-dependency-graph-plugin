"""Traversal of dataset dependency graphs.

Datasets record the datasets they were derived from under the dependency
keys, e.g. ``readme_parsed.derived_from.uuid`` (README ``derived_from``
entries) or ``annotations.source_dataset_uuid``. Starting from one dataset,
the graph is explored level by level in both directions:

- parents: the UUIDs the datasets of the current level name, and
- children: the datasets naming a dataset of the current level.

Every query is restricted to the base URIs the user may search, so the
traversal never passes through, and the result never mentions, datasets the
user cannot see. Queries use indexes on ``uuid`` and the dependency keys;
nothing is precomputed over the whole collection.
"""

import logging
import re

import dtoolcore.utils

logger = logging.getLogger(__name__)

UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$")

# Fields of a dataset in the response, as in dservercore's DatasetSchema,
# plus derived_from.
DATASET_FIELDS = (
    "base_uri",
    "created_at",
    "creator_username",
    "frozen_at",
    "name",
    "uri",
    "uuid",
    "number_of_items",
    "size_in_bytes",
    "uploaded_by",
    "uploaded_at",
)

TIMESTAMP_FIELDS = ("created_at", "frozen_at", "uploaded_at")


def values_at(document, path):
    """Return all values at a dotted path, descending into lists."""
    current = [document]
    for part in path.split("."):
        found = []
        for value in current:
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, dict) and part in item:
                    found.append(item[part])
        current = found
    values = []
    for value in current:
        values.extend(value if isinstance(value, list) else [value])
    return values


def parents_of(document, dependency_keys):
    """Return the UUIDs a dataset document names as its parents."""
    parents = set()
    for key in dependency_keys:
        for value in values_at(document, key):
            if isinstance(value, str) and UUID_REGEX.match(value):
                parents.add(value)
    parents.discard(document.get("uuid"))
    return parents


def _response_entry(document, derived_from):
    entry = {key: document[key] for key in DATASET_FIELDS if key in document}
    for key in TIMESTAMP_FIELDS:
        if entry.get(key) is not None and not isinstance(
                entry[key], (int, float)):
            entry[key] = dtoolcore.utils.timestamp(entry[key])
    entry["derived_from"] = sorted(derived_from)
    return entry


def dependency_graph(collection, uuid, base_uris, dependency_keys,
                     max_size=1000):
    """Return the datasets in the same dependency graph as uuid.

    :param collection: pymongo collection of dataset documents
    :param uuid: UUID of the dataset to start from
    :param base_uris: base URIs the user may search
    :param dependency_keys: dotted paths of parent UUIDs in the documents
    :param max_size: stop exploring once the graph has this many datasets
    :returns: list of dataset entries (sorted by UUID), each with
        ``derived_from``: the UUIDs of its parents within the result
    """
    visible = {"base_uri": {"$in": list(base_uris)}}
    if not base_uris or collection.count_documents(
            {"uuid": uuid, **visible}, limit=1) == 0:
        return []

    key_projection = {key: True for key in dependency_keys}
    key_projection.update({"uuid": True, "_id": False})

    seen = {uuid}
    frontier = {uuid} if dependency_keys else set()
    while frontier and len(seen) < max_size:
        neighbours = set()
        # Parents named by the datasets of this level.
        for doc in collection.find(
                {"uuid": {"$in": sorted(frontier)}, **visible},
                key_projection):
            neighbours |= parents_of(doc, dependency_keys)
        # Datasets naming a dataset of this level.
        children_query = {
            "$or": [{key: {"$in": sorted(frontier)}}
                    for key in dependency_keys],
            **visible,
        }
        for doc in collection.find(children_query, {"uuid": True}):
            neighbours.add(doc["uuid"])

        candidates = neighbours - seen
        if not candidates:
            break
        # Only datasets the user can see are part of the graph.
        found = set(collection.distinct(
            "uuid", {"uuid": {"$in": sorted(candidates)}, **visible}))
        room = max_size - len(seen)
        if len(found) > room:
            logger.warning(
                "Dependency graph of %s exceeds %d datasets; truncated.",
                uuid, max_size)
            found = set(sorted(found)[:room])
        seen |= found
        frontier = found

    # One entry per UUID (a dataset may be registered in several base URIs:
    # the first base URI in alphabetical order).
    entries = {}
    projection = {"_id": False, "manifest": False, "readme": False}
    for doc in collection.find(
            {"uuid": {"$in": sorted(seen)}, **visible}, projection,
            sort=[("uuid", 1), ("base_uri", 1)]):
        if doc["uuid"] in entries:
            continue
        derived_from = parents_of(doc, dependency_keys) & seen
        entries[doc["uuid"]] = _response_entry(doc, derived_from)

    return [entries[key] for key in sorted(entries)]
