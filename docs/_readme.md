**Doc-zero** streamlines the process of writing documentation for your project. It is
an opinionated and explicitly non-configurable tool that extracts information
from your Python codebase and generates nice documentation with minimal effort.

The main influence is the `elm` language tooling: no config, nice defaults and
it creates a very decent documentation out of the box. Rust has a similar
experience with RustDoc. In comparison, both Sphinx and MkDocs are very powerful
but somewhat clunky to use and configure.

## How does it work?

`doc-zero` introspect your codebase and creates a Sphinx project under the hood. In
practice, if you have a relatively modern Python project (i.e., it assumes the
existence of pyproject.toml) just type

```bash
$ doc-zero build # or the doc0 alias
```

in the project root and it will create and build the documentation under
`<project-root>/docs`. In `doc-zero`, all your documentation resides either in the
README.md file in your repository or inside the source code.

You can also type

```bash
$ doc-zero serve
```

and

```bash
doc-zero test
```

to run either the live server or to test the doctests inside the documentation.


## Adding the documentation to your project

Doc-zero assumes your project is already documented using docstrings and that 
you have a README.md file in the project root. It will use those assets to
generate the documentation and the necessary configurations to make it buildable
with Sphinx and ready to be hosted to readthedocs.io. 

The first step is to install `doc-zero` as a development dependency in your project. 
You can do this by running

```bash
$ pip install doc-zero
```

or the equivalent command for the package manager of choice.


Then, the following command generates the documentation:

```bash
$ doc-zero build
```

`doc-zero` always creates a module documentation for your toplevel module. It will
also scan all sub-modules and generate a documentation page if they satisfy the
following conditions:

* The module is not private (i.e., it does not start with an underscore).
* The module has a docstring.
* The module defines a `__all__` variable that lists its public API.

`doc-zero` only includes the public API in the generated documentation. 
