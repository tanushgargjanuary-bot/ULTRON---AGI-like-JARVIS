"""Optional-dependency adapters; importing this module needs only Python."""

from __future__ import annotations

import ctypes
import importlib.util
import os
from html.parser import HTMLParser
from types import SimpleNamespace


def _available(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


HAS_PSUTIL = _available("psutil")
HAS_BS4 = _available("bs4")
HAS_CTK = _available("customtkinter")
HAS_HYPOTHESIS = _available("hypothesis")
HAS_RUFF = _available("ruff")


class ProcessCompat:
    class Error(Exception):
        pass

    def __init__(self, pid=None):
        self.pid = pid or os.getpid()
        self._process = None
        if HAS_PSUTIL:
            try:
                import psutil

                self._process = psutil.Process(self.pid)
            except ImportError:
                pass

    def memory_info(self):
        if self._process is not None:
            return self._process.memory_info()
        try:
            if os.name == "nt":
                from ctypes import wintypes

                class Counters(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                    ] + [
                        (name, ctypes.c_size_t)
                        for name in (
                            "PeakWorkingSetSize",
                            "WorkingSetSize",
                            "QuotaPeakPagedPoolUsage",
                            "QuotaPagedPoolUsage",
                            "QuotaPeakNonPagedPoolUsage",
                            "QuotaNonPagedPoolUsage",
                            "PagefileUsage",
                            "PeakPagefileUsage",
                        )
                    ]

                counters = Counters()
                counters.cb = ctypes.sizeof(counters)
                kernel = ctypes.windll.kernel32
                kernel.GetCurrentProcess.restype = wintypes.HANDLE
                query = ctypes.windll.psapi.GetProcessMemoryInfo
                query.argtypes = [
                    wintypes.HANDLE,
                    ctypes.POINTER(Counters),
                    wintypes.DWORD,
                ]
                query.restype = wintypes.BOOL
                if not query(
                    kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
                ):
                    raise OSError("GetProcessMemoryInfo failed")
                rss = counters.WorkingSetSize
            elif os.path.exists("/proc/self/statm"):
                with open("/proc/self/statm", encoding="ascii") as stream:
                    rss = int(stream.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
            else:
                import resource
                import sys

                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                if sys.platform != "darwin":
                    rss *= 1024
            return SimpleNamespace(rss=rss)
        except (OSError, ValueError, IndexError) as exc:
            raise self.Error(str(exc)) from exc

    def name(self):
        return self._process.name() if self._process else "unknown"


psutil_shim = SimpleNamespace(Process=ProcessCompat, Error=ProcessCompat.Error)


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg", "aside"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.in_title = False
        self.title = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        if tag == "title":
            self.in_title = True

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.depth = max(0, self.depth - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if not self.depth and data.strip():
            self.text.append(data.strip())
            if self.in_title:
                self.title.append(data.strip())


def extract_webpage_text(html: str) -> tuple[str, str]:
    if HAS_BS4:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(list(_TextParser.SKIP)):
                tag.decompose()
            title = soup.title.get_text(strip=True) if soup.title else ""
            return title, soup.get_text(separator="\n", strip=True)
        except ImportError:
            pass
    parser = _TextParser()
    parser.feed(html)
    return " ".join(parser.title), "\n".join(parser.text)


class _MissingWidget:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "Native UI requires customtkinter; install requirements.txt or use offline --no-gui verification"
        )


class _CtkShim:
    def __getattr__(self, name):
        if name.startswith("set_"):
            return lambda *args, **kwargs: None
        return _MissingWidget


ctk_shim = _CtkShim()
