try:
    from js import window, XMLHttpRequest
except ImportError:
    window = None

import hashlib
import importlib
import io
import json
from pathlib import Path
import zipfile

from distlib import markers, util, version


# Provide implementations of HTTP fetching for in-browser and out-of-browser to
# make testing easier
if window is not None:
    # Inside the browser
    import pyodide

    def get_url(url):
        return pyodide.open_url(url)

    def get_url_async(url, cb):
        req = XMLHttpRequest.new()
        req.open('GET', url, True)
        req.responseType = 'arraybuffer'

        def callback(e):
            if req.readyState == 4:
                cb(io.BytesIO(req.response))

        req.onreadystatechange = callback
        req.send(None)

    WHEEL_BASE = Path(__file__).parent
else:
    # Outside the browser
    from urllib.request import urlopen

    def get_url(url):
        with urlopen(url) as fd:
            content = fd.read()
        return io.BytesIO(content)

    def get_url_async(url, cb):
        with urlopen(url) as fd:
            content = fd.read()
        cb(io.BytesIO(content))

    WHEEL_BASE = Path('.') / 'wheels'


def get_pypi_json(pkgname):
    url = f'https://pypi.org/pypi/{pkgname}/json'
    fd = get_url(url)
    return json.load(fd)


class WheelInstaller:
    def extract_wheel(self, fd):
        with zipfile.ZipFile(fd) as zf:
            zf.extractall(WHEEL_BASE)

    def validate_wheel(self, data, fileinfo):
        sha256 = fileinfo['digests']['sha256']
        m = hashlib.sha256()
        m.update(data.getvalue())
        if m.hexdigest() != sha256:
            raise ValueError("Contents don't match hash")

    def __call__(self, name, fileinfo):
        url = self.fetch_wheel(name, fileinfo)

        def callback(wheel):
            self.validate_wheel(wheel, fileinfo)
            self.extract_wheel(wheel)

        get_url_async(url, callback)


class RawWheelInstaller(WheelInstaller):
    def fetch_wheel(self, name, fileinfo):
        return 'https://cors-anywhere.herokuapp.com/' + fileinfo['url']


class DevPiWheelInstaller(WheelInstaller):
    def __init__(self, base_url=None):
        if base_url is None:
            base_url = 'http://localhost:3141'
        self._base_url = base_url

    def fetch_wheel(self, name, fileinfo):
        api_url = f"{self._base_url}/root/pypi/+simple/{name}/"
        # This triggers devpi to fetch the information about the source files.
        # We don't actually need the response
        get_url(api_url)

        sha256 = fileinfo['digests']['sha256']
        wheel_url = (
            f"{self._base_url}/root/pypi/+f/"
            f"{sha256[:3]}/{sha256[3:16]}/"
            f"{fileinfo['filename']}#sha256={sha256}"
        )
        return wheel_url


class PackageManager:
    version_scheme = version.get_scheme('normalized')

    def __init__(self):
        self.installed_packages = {}

    def install(self, requirements, ctx=None, wheel_installer=None):
        if ctx is None:
            ctx = {'extra': None}

        if wheel_installer is None:
            wheel_installer = RawWheelInstaller()

        complete_ctx = dict(markers.DEFAULT_CONTEXT)
        complete_ctx.update(ctx)

        if isinstance(requirements, str):
            requirements = [requirements]

        transaction = {
            'wheels': [],
            'locked': dict(self.installed_packages)
        }
        for requirement in requirements:
            self.add_requirement(requirement, ctx, transaction)

        for name, wheel, ver in transaction['wheels']:
            wheel_installer(name, wheel)
            self.installed_packages[name] = ver

    def add_requirement(self, requirement, ctx, transaction):
        req = util.parse_requirement(requirement)

        if req.marker:
            if not markers.evaluator.evaluate(
                    req.marker, ctx):
                return

        matcher = self.version_scheme.matcher(req.requirement)

        # If we already have something that will work, don't
        # fetch again
        for name, ver in transaction['locked'].items():
            if name == req.name:
                if matcher.match(ver):
                    break
                else:
                    raise ValueError(
                        f"Requested '{requirement}', "
                        f"but {name}=={ver} is already installed"
                    )
        else:
            metadata = get_pypi_json(req.name)
            wheel, ver = self.find_wheel(metadata, req)
            transaction['locked'][req.name] = ver

            reqs = metadata.get('info', {}).get('requires_dist') or []
            for req in reqs:
                self.add_requirement(req, ctx, transaction)

            transaction['wheels'].append((req.name, wheel, ver))

    def find_wheel(self, metadata, req):
        releases = []
        for ver, files in metadata.get('releases', {}).items():
            ver = self.version_scheme.suggest(ver)
            if ver is not None:
                releases.append((ver, files))
        releases = sorted(releases, reverse=True)
        matcher = self.version_scheme.matcher(req.requirement)
        for ver, meta in releases:
            if matcher.match(ver):
                for fileinfo in meta:
                    if fileinfo['filename'].endswith('py3-none-any.whl'):
                        return fileinfo, ver

        raise ValueError(
            f"Couldn't find a pure Python 3 wheel for '{req.requirement}'"
        )


PACKAGE_MANAGER = PackageManager()
del PackageManager


def install(requirements, ctx=None, wheel_installer=None):
    PACKAGE_MANAGER.install(
        requirements, ctx=ctx, wheel_installer=wheel_installer
    )
    importlib.invalidate_caches()


__all__ = ['install']


if __name__ == '__main__':
    install('snowballstemmer')
