Change log for dserver-dependency-graph-plugin
==============================================

Unreleased
----------

* Graphs are explored level by level with indexed queries on the dataset
  collection, instead of MongoDB views over the whole collection. Requests
  no longer recompute all dependencies, no longer fail for large collections
  (16 MB document limit), and no longer create views; the ``dep:...`` views
  and the ``dep_views`` collection can be dropped.
* Only datasets the user may search are traversed: a hidden dataset no
  longer connects visible ones, and ``derived_from`` lists only datasets in
  the response.
* ``derived_from`` lists each parent once, also when a dependency is
  recorded under several keys.
* ``DSERVER_DYNAMIC_DEPENDENCY_KEYS`` is off by default; invalid keys are
  rejected (400).
* New ``DSERVER_DEPENDENCY_GRAPH_MAX_SIZE`` (default 1000).
* Removed ``DSERVER_FORCE_REBUILD_DEPENDENCY_VIEW`` and
  ``DSERVER_MONGO_DEPENDENCY_VIEW_PREFIX``, ``..._BOOKKEEPING``,
  ``..._CACHE_SIZE``.

0.4.2 (13Oct25)
---------------

* Switched from stndard flask JWT authentication to customized dserver authntication

0.4.1 (9Jul24)
---------------

* Automated github release creation

0.4.0 (13Jun24)
---------------

* Exchanged ``dtool-lookup-server`` dependency for ``dservercore``

0.3.0 (07Jun24)
---------------

* Added ``CHANGELOG.rst``.
* Rebranded from ``dtool-lookup-server-`` prefix to ``dserver-`` prefix.
* Adapted to match remodeled dserver REST API.
