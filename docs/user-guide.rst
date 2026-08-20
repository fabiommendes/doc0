User Guide
==========

.. contents:: On this page
   :local:
   :depth: 2

This guide covers everything you need to use the ``doc-zero`` command-line
tool day to day: installing it, organizing a project so it can find your
code, the commands themselves, and a few advanced patterns.

Installation
------------

doc-zero is distributed on PyPI under the name **doc-zero** (the ``doc-zero``
name was already taken). Install it as a development dependency of the
project you want to document:

.. code-block:: bash

   pip install doc-zero
   # or: uv add --dev doc-zero

It requires Python 3.13 or newer -- not just to run doc-zero itself, but
because doc-zero executes your project's code in-process to read docstrings
and ``__all__``, so your project needs to import cleanly under the same
interpreter.

Once installed, it provides the ``doc-zero`` command (and its alias ``doc0``)
into your virtual environment.

Quick start
-----------

In the simplest case -- a project with a ``pyproject.toml`` and a single
top-level package whose directory name matches ``project.name`` -- there
is nothing to configure. From the project root:

.. code-block:: bash

   doc-zero build

This generates a Sphinx project under ``docs/`` and builds it to HTML
under ``dist/docs/``. Run it again any time your code or README changes;
every generated file is overwritten from scratch on each run (more on
that under `What gets regenerated on every build`_).


Concepts
--------

doc-zero is deliberately non-configurable: instead of a config file, it
looks at conventional signals in your project -- ``pyproject.toml``,
your package's directory layout, docstrings, ``__all__``, and a handful
of well-known filenames -- and turns them into a Sphinx project. This
section explains those signals.

How doc-zero finds your code
~~~~~~~~~~~~~~~~~~~~~~~~~~~~ 

doc-zero needs to know which module(s) are the root of your public API. It
tries a few heuristics:

1. **build-backend configuration.** If ``pyproject.toml`` declares a 
   ``build-system.build-backend``, doc-zero tries to use the build-backend 
   configuration to discover the available modules/packages. For now, doc-zero
   only supports the ``uv_build`` build backend.
   
2. **src layout.** If there's a ``src/`` directory, doc-zero documents every
   public package and its sub-packages and sub-modules.

3. **Toplevel package layout.** Otherwise, doc-zero looks for a directory
   at the project root whose name is equivalent ``project.name`` from
   ``pyproject.toml``, containing an ``__init__.py``.


What gets regenerated on every build
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every ``doc-zero build`` / ``doc-zero serve`` unconditionally overwrites:

- ``docs/conf.py``
- ``docs/index.rst``
- ``docs/api/`` (the whole directory is deleted and rewritten)
- ``docs/_readme.md``

.. warning::

   Don't hand-edit any of the files above -- your changes will be lost
   on the next build. If you need content Sphinx can't derive from your
   README and docstrings, put it in one of the guide directories
   described in `Adding narrative documentation`_ instead; those are
   never touched by doc-zero.

Two files, by contrast, are written **once** and then left alone:

- ``.readthedocs.yml`` at the project root
- ``docs/requirements.txt``

Those files automatically prepare a doc-zero project for publishing on Read the 
Docs. You can edit them if you need to further tweak the build environment.

All other files under ``docs/`` are left untouched. Doc-zero may use some
of those files for specific purposes (e.g., logos, how-to guides, tutorials, 
etc.).

The README
~~~~~~~~~~

Your project's front page comes from ``README.md`` (mind the .md extension!). 
Since the README often have some reduntant content for the docs (e.g., the main
title, badges, GitHub-specific pitch), doc-zero supports two modes of operation:

- **Default.** doc-zero strips a leading Markdown title and uses the rest 
  verbatim.
- **With a marker.** If ``README.md`` contains an HTML comment
  ``<!-- doc-zero-start -->``, everything *before* the marker is dropped
  (badges, a GitHub-only pitch, install one-liners aimed at scanners
  of a repo listing) and everything *after* it is used verbatim. This
  is the better option once your README has accumulated GitHub-specific
  furniture you don't want in the generated docs.

License, copyright, authors, and other metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Doc-zero scans ``pyproject.toml`` for the following relevant information about 
your project:

- ``project.name`` -- the project name
- ``project.authors`` -- a list of authors, each with ``name`` and optional ``email`` fields
- ``project.license`` -- the license identifier (e.g., ``MIT``)
- ``project.urls`` 
   - ``"Homepage"`` -- the project homepage
   - ``"Repository"`` -- the project repository URL
   - ``"Documentation"`` -- the project documentation URL

If it recognizes that it is a Github repository, it may add a button link 
to the repository. This may not work on every theme.

If a ``LICENSE`` file exists at the project root, doc-zero parses a
copyright line out of it (e.g., ``Copyright (c) 2024 Jane Doe``) to fill in 
the ``copyright`` field of your docs configuration.


Sub-module discovery
~~~~~~~~~~~~~~~~~~~~

Beyond your root module(s), doc-zero walks their submodules and documents
each one that:

- isn't private (its filename doesn't start with ``_`` -- so
  ``_internal.py`` and any package under a ``_``-prefixed directory are
  skipped), and
- has a module docstring.

A submodule that passes both checks but has no ``__all__``, or an empty
one, is still documented (Sphinx's autodoc will show whatever it deems
public), but doc-zero logs a warning during the build so you notice:

.. code-block:: text

   WARNING - Module mypkg.legacy has no __all__ attribute
   WARNING - Module mypkg.empty do not export any symbols

You should declare ``__all__`` in every public submodule to keep the generated 
API reference clean and predictable.

By default, Sphinx's autodoc lists a module's members in whatever order
it discovers them -- not necessarily the order that makes sense to a
reader. doc-zero improves on this: when a module's ``__all__`` is written as
a plain list (or tuple) of string literals, doc-zero documents members in
*exactly that order*, and lets you group them into titled sections using
``#:`` comments:

.. code-block:: python

   __all__ = [
       #: Types
       "Foo",
       "Bar",
       #: Utility functions
       #
       # These build ``Foo``/``Bar`` instances from primitive values --
       # prefer them over calling the constructors directly.
       "make_foo",
       "make_bar",
   ]

This renders as two headed sections, "Types" and "Utility functions", in
that order, with the ``Foo``/``Bar``/``make_foo``/``make_bar`` reference
entries listed underneath in declaration order. A few rules to know:

- A section is opened by a standalone comment line (nothing else on the
  line) starting with ``#:``. That line's text is the section title.
- Every comment line directly following it is treated as body text for
  that section, rendered as a paragraph beneath the heading -- a blank
  comment starts a new paragraph.
- Any other stray ``#`` comment inside the list (one that doesn't start
  a section) is just ignored.

If ``__all__`` isn't a plain literal doc-zero can parse this way -- it's
built dynamically, concatenated from another list, mutated after the
fact, or anything else that isn't statically obvious -- doc-zero quietly
falls back to a plain, unordered listing. Nothing breaks; you just lose
ordering and sections for that module.

Notice static analysis tools like Mypy or Pylanc also expect ``__all__`` to be 
a literal list/tuple of string constants, so they can check your module's public 
API without executing it. 

Adding narrative documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Docstrings and your README cover reference material and an overview,
but longer-form guides often don't fit either. doc-zero follows the
`Diátaxis <https://diataxis.fr>`_ framework for building documentation.

It is very simple: drop a directory (or a single file, for something short) 
directly under ``docs/`` using one of these conventional names, and doc-zero 
links it into the generated table of contents automatically:

**Tutorials**
   Tutorials are instructional, step-by-step guides that teach the basic usage
   of a tool or library. They are usually aimed at beginners.
   - ``docs/tutorials/*.(rst|md)`` 
   - ``docs/tutorial.(rst|md)`` 
   
**How-to guides**
   How-to guides explain how to accomplish specific tasks with a tool or library.
   They are usually aimed at users who are already familiar with the basics, but
   want to learn how to use the tool/library to solve a particular problem.
   - ``docs/how-to-guides/*.(rst|md)``
   - ``docs/how-to-guide.(rst|md)``
   
**User guides**
   User guides are comprehensive references that explain how to use a tool 
   or library in depth. User guide is usually a comprehensive manual that
   cover all or most aspects of your project. They are not instructional
   like a tutorial neither task-oriented like a how-to guide.

   This very page you are reading is an example of a user guide ``;)``.

   - ``docs/user-guides/*.(rst|md)``
   - ``docs/user-guide.(rst|md)``
   
**Explanations/concepts**
   Explanations/concepts (doc-zero treats them as equivalent) are reference 
   material that explains the underlying concepts and principles of a tool 
   or library. It can be a glossary of terms, a description of the 
   architecture, or a discussion of the design decisions.

   - ``docs/explanations/*.(rst|md)``
   - ``docs/explanation.(rst|md)``
   - ``docs/concepts/*.(rst|md)``
   - ``docs/concept.(rst|md)``


Theming
~~~~~~~

doc-zero picks a Sphinx HTML theme using the first of these that's set:

1. ``--theme`` on the command line.
2. ``[tool.doc-zero] theme`` in ``pyproject.toml``:

   .. code-block:: toml

      [tool.doc-zero]
      theme = "rtd"

It accepts any theme Sphinx can find, including third-party themes you install
into your virtual environment. This is the only configuration option doc-zero 
exposes.

CLI reference
-------------

``doc-zero build``
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   doc-zero build [--theme THEME]

Regenerates the Sphinx project under ``docs/`` (see `What gets
regenerated on every build`_) and builds it to static HTML under
``dist/docs/``. This is the command you run before publishing, and the
one most CI pipelines should call.

``doc-zero serve``
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   doc-zero serve [--theme THEME]

Same generation step as ``build``, then starts `sphinx-autobuild
<https://github.com/sphinx-doc/sphinx-autobuild>`_: a local web server
that watches ``docs/`` and rebuilds automatically as you edit your
README, docstrings, or narrative pages. Check the terminal output for
the URL to open (sphinx-autobuild's own default is
``http://127.0.0.1:8000``). Use this while you're actively writing.

``doc-zero test``
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   doc-zero test

Reserved for running the doctests embedded in your docstrings and
narrative pages. As of this writing it's a no-op placeholder -- it
doesn't yet execute anything. Don't rely on it as part of a CI gate;
treat any doctests you write as documentation for now, not as tests
that are actually checked.

``--theme``
~~~~~~~~~~~

Available on both ``build`` and ``serve``. Overrides the theme for that
one invocation, taking priority over ``[tool.doc-zero] theme`` in
``pyproject.toml``. See `Theming`_ for the full precedence order and the
built-in aliases.


Organizing your project
------------------------

A project doc-zero is comfortable with typically looks like this:

.. code-block:: text

   myproject/
   ├── pyproject.toml
   ├── README.md
   ├── LICENSE
   ├── mypkg/
   │   ├── __init__.py         # docstring + __all__
   │   ├── core.py             # docstring + __all__
   │   └── _internal.py        # private: skipped
   └── docs/
       ├── user-guide.rst      # optional narrative pages
       └── how-to-guides/


Advanced usage patterns
------------------------

Documenting multiple packages from one project
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If your project ships more than one top-level package (a monorepo-style
layout, or a package split into a core and a set of plugins living
side by side), either use the ``src/`` layout or list them all under the uv 
build-backend heuristic:

.. code-block:: toml

   [tool.uv.build-backend]
   module-name = "mypkg_core, mypkg_plugins"
   module-root = ""

doc-zero documents each one as its own root module, and include all public 
submodules it can find under them.

Grouping a large module's API
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``#:`` section syntax (see `Sub-module discovery`_) is most valuable on 
modules with a wide, mixed API -- public classes next to helper functions next 
\to constants. Group related names under one heading rather than splitting them 
across several small modules just to get separate documentation pages:

.. code-block:: python

   __all__ = [
       #: Core
       "Client",
       "Response",
       #: Exceptions
       "ClientError",
       "TimeoutError",
       #: Configuration
       #
       # Most users only need DEFAULT_CONFIG; the rest are for
       # advanced tuning.
       "DEFAULT_CONFIG",
       "Config",
   ]

Keep ``__all__`` a plain list/tuple literal -- built dynamically or with
string concatenation, it silently loses ordering and falls back to an
unordered listing (see `Sub-module discovery`_).

Publishing on Read the Docs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The first ``doc-zero build`` writes a ``.readthedocs.yml`` at the project
root pointing at ``docs/conf.py``, plus a ``docs/requirements.txt`` --
both left untouched on later builds so you can adjust them.

Read the Docs runs plain ``sphinx-build`` against whatever is already
committed under ``docs/`` -- it does not invoke ``doc-zero`` itself. That
means your generated ``docs/`` directory needs to be up to date in the
commit you publish: either commit it after running ``doc-zero build``
locally, or add a build step to your CI that runs ``doc-zero build`` before
Read the Docs' own build picks it up.

.. warning::

   Sphinx's autodoc extension needs your project's own package
   importable at build time to read its docstrings -- so
   ``docs/requirements.txt`` needs *your* package listed, not just
   doc-zero. Check its contents after the first build and add your own
   project to it if it's missing; doc-zero only writes this file once and
   won't correct it for you on a later run.


Troubleshooting
----------------

A submodule doesn't show up in the API reference
   Check that it has a docstring and isn't private (no leading ``_`` in
   its filename or an ancestor directory's name) -- see `Sub-module
   discovery`_.

Members appear in the wrong order, or sections aren't showing up
   ``__all__`` must be a literal list/tuple of string constants for
   doc-zero to parse it statically. If it's built with a loop, concatenated
   from another list, or mutated after the fact, doc-zero falls back to an
   unordered listing rather than guessing. See `Sub-module discovery`_.
