"""Traversal of the dependency graph: edges, privileges and limits."""

import json

import pytest
import yaml

from dserver_dependency_graph_plugin.graph import parents_of, values_at

from .conftest import BASE_URI, TESTING_FAMILY

HIDDEN_BASE_URI = "s3://hidden"


def uuid_of(role):
    return TESTING_FAMILY[role]["uuid"]


def dataset(name, uuid, base_uri=BASE_URI, derived_from=(), annotations=None):
    return {
        "base_uri": base_uri,
        "type": "dataset",
        "uuid": uuid,
        "uri": f"{base_uri}/{uuid}",
        "name": name,
        "readme": yaml.dump(
            {"derived_from": [{"uuid": u} for u in derived_from]}
            if derived_from else {}),
        "creator_username": "god",
        "frozen_at": 1536238185.881941,
        "manifest": {"dtoolcore_version": "3.7.0",
                     "hash_function": "md5sum_hexdigest", "items": {}},
        "annotations": annotations or {},
        "tags": [],
    }


def graph(client, token, uuid, query="", **kwargs):
    headers = dict(Authorization="Bearer " + token)
    if "dependency_keys" in kwargs:
        r = client.post(f"/graph/uuids/{uuid}{query}", headers=headers,
                        data=json.dumps(kwargs), content_type="application/json")
    else:
        r = client.get(f"/graph/uuids/{uuid}{query}", headers=headers)
    return r


def edges(response):
    return {d["name"]: sorted(d["derived_from"]) for d in response.json}


# --- pure helpers ------------------------------------------------------------

def test_values_at_descends_into_lists():
    doc = {"readme_parsed": {"derived_from": [{"uuid": "a"}, {"uuid": "b"},
                                              {"name": "no uuid"}]},
           "annotations": {"source_dataset_uuid": ["c", "d"]}}
    assert values_at(doc, "readme_parsed.derived_from.uuid") == ["a", "b"]
    assert values_at(doc, "annotations.source_dataset_uuid") == ["c", "d"]
    assert values_at(doc, "missing.key") == []


def test_parents_only_valid_uuids_and_not_itself():
    own = "a2218059-5bd0-4690-b090-062faf08e040"
    other = "a2218059-5bd0-4690-b090-062faf08e041"
    doc = {"uuid": own, "readme_parsed": {"derived_from": [
        {"uuid": other}, {"uuid": own}, {"uuid": "unknown"}, {"uuid": 42}]}}
    assert parents_of(doc, ["readme_parsed.derived_from.uuid"]) == {other}


# --- graph -------------------------------------------------------------------

def test_edges_within_the_graph(tmp_app_with_dependent_data, grumpy_token):
    r = graph(tmp_app_with_dependent_data, grumpy_token, uuid_of("brother"))
    assert r.status_code == 200
    assert edges(r) == {
        "grandfather": [],
        # Its parent is not registered.
        "grandmother": [],
        "mother": sorted([uuid_of("grandfather"), uuid_of("grandmother")]),
        # 'unknown' is no UUID.
        "father": [],
        "brother": sorted([uuid_of("mother"), uuid_of("father")]),
        "sister": sorted([uuid_of("mother"), uuid_of("father")]),
        "stepsister": sorted([uuid_of("mother"), uuid_of("ex-husband")]),
        "ex-husband": [],
    }
    # No README or manifest in the response.
    assert all("readme" not in d and "manifest" not in d for d in r.json)
    assert [d["uuid"] for d in r.json] == sorted(d["uuid"] for d in r.json)


def test_unrelated_dataset_alone(tmp_app_with_dependent_data, grumpy_token):
    r = graph(tmp_app_with_dependent_data, grumpy_token, uuid_of("friend"))
    assert edges(r) == {"friend": []}


def test_unknown_dataset(tmp_app_with_dependent_data, grumpy_token):
    r = graph(tmp_app_with_dependent_data, grumpy_token,
              "a2218059-5bd0-4690-b090-062faf08e999")
    assert r.status_code == 200
    assert r.json == []


def test_dependency_recorded_twice_is_one_edge(tmp_app_with_dependent_data,
                                               grumpy_token):
    """In the README and as annotation: one edge."""
    from dservercore.utils import register_dataset
    niece = "a2218059-5bd0-4690-b090-062faf08e050"
    register_dataset(dataset(
        "niece", niece, derived_from=[uuid_of("sister")],
        annotations={"source_dataset_uuid": uuid_of("sister")}))

    r = graph(tmp_app_with_dependent_data, grumpy_token, niece)
    assert edges(r)["niece"] == [uuid_of("sister")]


def test_no_traversal_through_hidden_datasets(tmp_app_with_dependent_data,
                                              grumpy_token):
    """A dataset the user cannot see neither connects visible datasets nor
    shows up in derived_from."""
    from dservercore.utils import (
        register_base_uri, register_dataset, register_permissions)
    register_base_uri(HIDDEN_BASE_URI)
    register_permissions(HIDDEN_BASE_URI, {
        "base_uri": HIDDEN_BASE_URI,
        "users_with_search_permissions": [],
        "users_with_register_permissions": []})
    hidden = "a2218059-5bd0-4690-b090-062faf08e060"
    cousin = "a2218059-5bd0-4690-b090-062faf08e061"
    register_dataset(dataset("hidden", hidden, base_uri=HIDDEN_BASE_URI,
                             derived_from=[uuid_of("friend")]))
    register_dataset(dataset("cousin", cousin, derived_from=[hidden]))

    assert edges(graph(tmp_app_with_dependent_data, grumpy_token,
                       uuid_of("friend"))) == {"friend": []}
    assert edges(graph(tmp_app_with_dependent_data, grumpy_token,
                       cousin)) == {"cousin": []}
    # Not visible to the user at all.
    assert graph(tmp_app_with_dependent_data, grumpy_token, hidden).json == []


def test_dataset_in_two_base_uris_once(tmp_app_with_dependent_data,
                                       grumpy_token):
    from dservercore.utils import (
        register_base_uri, register_dataset, register_permissions)
    other = "s3://other"
    register_base_uri(other)
    register_permissions(other, {
        "base_uri": other,
        "users_with_search_permissions": ["grumpy"],
        "users_with_register_permissions": []})
    register_dataset(dataset("brother", uuid_of("brother"), base_uri=other,
                             derived_from=[uuid_of("mother")]))

    r = graph(tmp_app_with_dependent_data, grumpy_token, uuid_of("brother"))
    brothers = [d for d in r.json if d["name"] == "brother"]
    assert len(brothers) == 1
    # The copy in the first base URI, alphabetically.
    assert brothers[0]["base_uri"] == "s3://other"
    assert len(r.json) == 8


def test_graph_size_limit(tmp_app_with_dependent_data, grumpy_token):
    from flask import current_app
    current_app.config["DEPENDENCY_GRAPH_MAX_SIZE"] = 3
    r = graph(tmp_app_with_dependent_data, grumpy_token, uuid_of("brother"))
    assert len(r.json) == 3
    assert uuid_of("brother") in [d["uuid"] for d in r.json]


def test_pagination(tmp_app_with_dependent_data, grumpy_token):
    """Large graphs come in pages (100 at most per page); X-Pagination says
    how many."""
    r = graph(tmp_app_with_dependent_data, grumpy_token, uuid_of("brother"),
              query="?page=2&page_size=3")
    assert len(r.json) == 3
    pagination = json.loads(r.headers["X-Pagination"])
    assert pagination["total"] == 8
    assert pagination["last_page"] == 3


def test_custom_keys_ignored_unless_enabled(tmp_app_with_dependent_data,
                                            grumpy_token):
    r = graph(tmp_app_with_dependent_data, grumpy_token, uuid_of("brother"),
              dependency_keys=["some_nonexistant_key"])
    assert r.status_code == 200
    assert len(r.json) == 8


def test_invalid_custom_keys_rejected(tmp_app_with_dynamic_keys, grumpy_token):
    r = graph(tmp_app_with_dynamic_keys, grumpy_token, uuid_of("brother"),
              dependency_keys=["readme_parsed.$where"])
    assert r.status_code == 400


@pytest.mark.parametrize("key", ["uuid", "readme_parsed.derived_from.uuid",
                                 "annotations.source_dataset_uuid"])
def test_indexes_created(tmp_app_with_dependent_data, key):
    from dserver_dependency_graph_plugin import DependencyGraphExtension
    indexed = [list(index["key"])[0] for index in
               DependencyGraphExtension.collection.list_indexes()]
    assert key in indexed
