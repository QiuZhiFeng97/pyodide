# Installing packages from PyPI

Pyodide has experimental support for installing pure Python wheels from PyPI.

The biggest limitation is that the domain where most PyPI wheels are hosted
(`files.pythonhosted.org`) does not all cross-origin requests, so it is
impossible to load the wheels into the browser directly. As a workaround, you
can run a copy of `devpi-server` on your local machine, (patched to support
CORS) which will transparently download and cache the wheels for you.

## Installing a local devpi-server

Check out the fork of [devpi](https://github.com/mdboom/devpi) from github.

`cd server`

`python setup.py install`

`devpi-server --start --init`

See the `devpi` documentation for making the server run permanently on your
machine.

## Loading PyPI packages

```
import micropip
micropip.install('snowballstemmer')
```

... wait for files to complete downloading ...

```
import snowballstemmer
snowballstemmer.stemmer('english')
stemmer.stemWords('go goes going gone'.split())
```
