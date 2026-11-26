dserver Dependency Graph Plugin
===============================

.. |dtool| image:: https://github.com/jic-dtool/dserver-dependency-graph-plugin/blob/main/icons/22x22/dtool_logo.png?raw=True
    :height: 20px
    :target: https://github.com/jic-dtool/dserver-dependency-graph-plugin
.. |pypi| image:: https://img.shields.io/pypi/v/dserver-dependency-graph-plugin
    :target: https://pypi.org/project/dserver-dependency-graph-plugin/
.. |tag| image:: https://img.shields.io/github/v/tag/jic-dtool/dserver-dependency-graph-plugin
    :target: https://github.com/jic-dtool/dserver-dependency-graph-plugin/tags
.. |test| image:: https://img.shields.io/github/actions/workflow/status/jic-dtool/dserver-dependency-graph-plugin/test.yml?branch=main&label=tests
    :target: https://github.com/jic-dtool/dserver-dependency-graph-plugin/actions/workflows/test.yml
.. |zenodo| image:: https://zenodo.org/badge/298694291.svg
    :target: https://zenodo.org/doi/10.5281/zenodo.12702000

|dtool| |pypi| |tag| |test| |zenodo|

- GitHub: https://github.com/jic-dtool/dserver-dependency-graph-plugin
- PyPI: https://pypi.python.org/pypi/dserver-dependency-graph-plugin
- Free software: MIT License


Features
--------

- Use a dataset UUID to look up all datasets within the same dependency graph,
  with the dependencies between them
- Dependencies are read from configurable keys, e.g. ``derived_from`` in the
  README or a ``source_dataset_uuid`` annotation


Introduction
------------

`dtool <https://dtool.readthedocs.io>`_ is a command line tool for packaging
data and metadata into a dataset. A dtool dataset manages data and metadata
without the need for a central database.

However, if one has to manage more than a hundred datasets it can be helpful
to have the datasets' metadata stored in a central server to enable one to
quickly find datasets of interest.

The `dservercore <https://github.com/jic-dtool/dservercore>`_
provides a web API for registering datasets' metadata
and provides functionality to lookup, list and search for datasets.

This plugin enables the dserver to directly provide all
datasets within a specific dependency graph.


Installation
------------

Install the dserver dependency graph plugin

.. code-block:: bash

    $ pip install dserver-dependency-graph-plugin

Setup and configuration
-----------------------

Configure plugin behavior
^^^^^^^^^^^^^^^^^^^^^^^^^

Datasets name the datasets they were derived from under the dependency keys.
The JSON-formatted list

.. code-block:: bash

    export DSERVER_DEPENDENCY_KEYS='["readme_parsed.derived_from.uuid", "annotations.source_dataset_uuid"]'

is the default: ``derived_from`` entries in the README (as parsed by the
server, ``readme_parsed``) and the annotation ``source_dataset_uuid``. All
keys are treated equivalently and nested fields are separated by the dot (.).
The actual nesting hierarchy does not matter. This means, for example, both
structures evaluate equivalently in the following

.. code-block:: python

    {'readme_parsed': {'derived_from': {'uuid':
        ['8ecd8e05-558a-48e2-b563-0c9ea273e71e',
         'faa44606-cb86-4877-b9ea-643a3777e021']}}}

    {'readme_parsed': {'derived_from':
        [{'uuid': '8ecd8e05-558a-48e2-b563-0c9ea273e71e'},
         {'uuid': 'faa44606-cb86-4877-b9ea-643a3777e021'}]}}

Values that are not UUIDs are ignored. The plugin creates MongoDB indexes on
``uuid`` and the dependency keys at startup.

Further options:

- ``DSERVER_ENABLE_DEPENDENCY_VIEW`` (default ``True``): enables the graph
  routes.
- ``DSERVER_DEPENDENCY_GRAPH_MAX_SIZE`` (default ``1000``): a graph is
  explored up to this many datasets.
- ``DSERVER_DYNAMIC_DEPENDENCY_KEYS`` (default ``False``): lets clients
  choose other dependency keys (see below). Keys without an index make every
  graph query scan the collection, so this is off by default.

Note that the above exports containing JSON syntax are formatted for usage in
bash. Enclosing single quotes are not to be part of the actual variable value
when environment variables are configured elsewhere.

How graphs are explored
^^^^^^^^^^^^^^^^^^^^^^^

Starting from the requested dataset, the graph is explored level by level in
both directions: the datasets a dataset names as its parents, and the
datasets naming it. Every query is restricted to the base URIs the user may
search, so the graph never passes through, and the response never mentions,
datasets the user cannot see. A user with access to only part of a graph gets
that part.

Previous versions cached MongoDB views (``dep:...``) and a bookkeeping
collection (``dep_views``); they are no longer used and can be dropped.


dserver API
-----------

dserver makes use of the Authorized header to pass through the
JSON web token for authorization. Below we create environment variables for the
token and the header used in the ``curl`` commands

.. code-block:: bash

  $ TOKEN=$(flask user token olssont)
  $ HEADER="Authorization: Bearer $TOKEN"


Standard user usage
^^^^^^^^^^^^^^^^^^^

Looking up dependency graphs based on a dataset's UUID
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A dataset can be derived from one or several source datasets, usually
by machine-generated annotations attached via the Python API at dataset
creation time, or manually by recording the UUIDs of parent datasets in some
arbitrary fields within the README.yml. If configured appropriately,
querying the server directly for all datasets within the same dependency
graph by UUID is possible, i.e.

.. code-block:: bash

    $ UUID=41a2e3e2-0c01-444f-bd7d-f9bb45512373
    $ curl -H "$HEADER" http://localhost:5000/graph/uuids/$UUID

The response lists the datasets in the graph (sorted by UUID), each with
``derived_from``: the UUIDs of its parents within the graph. It is paginated
(``page``, ``page_size`` up to 100, ``X-Pagination`` header). A dataset
registered in several base URIs appears once, from the first of these base
URIs in alphabetical order.


Looking up graphs spanned by other dependency keys
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If ``DSERVER_DYNAMIC_DEPENDENCY_KEYS=True``, then the client may
ask the server to explore a graph spanned by dependency keys differing from
the server-side defaults in ``DSERVER_DEPENDENCY_KEYS``, with a ``POST``
request

.. code-block:: bash

    $ curl -H "$HEADER" -H "Content-Type: application/json" -X POST \
        -d '{"dependency_keys": ["annotations.source_dataset_uuid"]}' \
        http://localhost:5000/graph/uuids/$UUID

Otherwise, the server uses its own keys.
