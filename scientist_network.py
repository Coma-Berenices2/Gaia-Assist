"""Bounded TAP transport and persistent raw-response cache for Scientist only."""
from contextlib import contextmanager, closing
from contextvars import ContextVar
from dataclasses import asdict, dataclass
import atexit
import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path
import queue
import sqlite3
import threading
import time
from urllib.parse import urljoin, urlparse

import requests

LOGGER = logging.getLogger("gaia_assist_temperature")
BASE = "https://gea.esac.esa.int/tap-server/tap"
CONFIG = Path(__file__).with_name("scientist_network_settings.json")
CACHE_FILE = Path(__file__).with_name("scientist_cache.sqlite3")
SCHEMA = "scientist-raw-3"
_slots = threading.BoundedSemaphore(3)
_locks = [threading.Lock() for _ in range(64)]
_state_lock = threading.Lock()
_contexts = {}
_children = set()


def cancel_all():
    with _state_lock:
        for context in _contexts.values():
            context.cancel.set()


def active_queries():
    with _state_lock:
        return len(_contexts)


def _exit_cleanup():
    cancel_all()
    with _state_lock:
        children = list(_children)
    for child in children:
        if child.is_alive():
            child.terminate()
        child.join(timeout=.2)


atexit.register(_exit_cleanup)


class NetworkFailure(RuntimeError):
    pass


class QueryTimeout(NetworkFailure):
    pass


class QueryCancelled(NetworkFailure):
    pass


@dataclass(frozen=True)
class NetworkOptions:
    request_timeout: float = 15.
    overall_timeout: float = 60.
    optional_timeout: float = 20.
    cache_ttl: float = 86400.
    batch_size: int = 20
    sync_limit: int = 20
    attempts: int = 2
    poll_interval: float = .75

    def __post_init__(self):
        for key in ("request_timeout", "overall_timeout", "optional_timeout", "cache_ttl", "poll_interval"):
            value = getattr(self, key)
            if not isinstance(value, (int, float)) or not 0 < value < 1e9:
                raise ValueError(f"{key} must be finite and positive")
        for key, maximum in (("batch_size", 200), ("sync_limit", 200), ("attempts", 3)):
            value = getattr(self, key)
            if not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{key} must be an integer from 1 to {maximum}")


def settings():
    try:
        return NetworkOptions(**json.loads(CONFIG.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return NetworkOptions()


def save_settings(options):
    CONFIG.write_text(json.dumps(asdict(options), indent=2), encoding="utf-8")


@dataclass
class QueryContext:
    options: NetworkOptions
    cancel: threading.Event
    progress: object = None
    force_refresh: bool = False
    deadline: float = 0.

    def check(self):
        if self.cancel.is_set():
            raise QueryCancelled("Query cancelled")
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise QueryTimeout("Overall query time limit reached")
        return left

    def report(self, message):
        self.check()
        if self.progress:
            self.progress(message)


CURRENT = ContextVar("scientist_query", default=None)


@contextmanager
def query_context(*, options=None, cancel=None, progress=None, force_refresh=False):
    options = options or settings()
    context = QueryContext(options, cancel or threading.Event(), progress, force_refresh,
                           time.monotonic() + options.overall_timeout)
    token = CURRENT.set(context)
    with _state_lock:
        _contexts[id(context)] = context
    try:
        yield context
    finally:
        with _state_lock:
            _contexts.pop(id(context), None)
        CURRENT.reset(token)


@contextmanager
def timed(stage):
    start = time.monotonic()
    try:
        yield
    finally:
        LOGGER.info("Timing %s: %.3f s", stage, time.monotonic()-start)


def cache_key(kind, inputs):
    return json.dumps([SCHEMA, kind, inputs], sort_keys=True, separators=(",", ":"))


def cache_get(key, *, force=False, options=None):
    start = time.monotonic()
    value, hit = None, False
    options = options or settings()
    if not force and CACHE_FILE.exists():
        with closing(sqlite3.connect(CACHE_FILE, timeout=2)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, created REAL, payload TEXT)")
            row = db.execute("SELECT created,payload FROM records WHERE key=?", (key,)).fetchone()
            if row and 0 <= time.time()-row[0] < options.cache_ttl:
                value, hit = json.loads(row[1]), True
    LOGGER.info("Timing cache lookup: %.3f s; %s", time.monotonic()-start, "hit" if hit else "miss/refresh")
    return hit, value


def cache_put(key, value):
    with closing(sqlite3.connect(CACHE_FILE, timeout=2)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, created REAL, payload TEXT)")
        db.execute("INSERT OR REPLACE INTO records VALUES (?,?,?)", (key, time.time(), json.dumps(value, allow_nan=False)))
        db.commit()


def cached(kind, inputs, operation, *, cache_none=True):
    context = CURRENT.get()
    if context:
        context.check()
    options = context.options if context else settings()
    force = bool(context and context.force_refresh)
    key = cache_key(kind, inputs)
    hit, result = cache_get(key, force=force, options=options)
    if hit:
        return result
    lock = _locks[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(_locks)]
    while not lock.acquire(timeout=.1):
        if context:
            context.check()
    try:
        hit, result = cache_get(key, force=force, options=options)
        if hit:
            return result
        result = operation()
        if result is not None or cache_none:
            cache_put(key, result)
        return result
    finally:
        lock.release()


def transient(error):
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(error, requests.HTTPError):
        return error.response is not None and error.response.status_code in (408, 429, 500, 502, 503, 504)
    return False


def request(session, method, url, options, deadline, emit, **kwargs):
    """Retry idempotent requests only; never resubmit an ambiguous job POST."""
    attempts = options.attempts if method == "GET" else 1
    for attempt in range(attempts):
        left = deadline-time.monotonic()
        if left <= 0:
            raise QueryTimeout("Request deadline reached")
        try:
            start = time.monotonic()
            response = session.request(method, url, timeout=min(options.request_timeout, left), stream=True, **kwargs)
            emit(("timing", "HTTP " + method + " " + url.rsplit("/", 1)[-1] + " submission / headers", time.monotonic()-start))
            response.raise_for_status()
            start = time.monotonic()
            data = bytearray()
            for chunk in response.iter_content(65536):
                if time.monotonic() >= deadline:
                    raise QueryTimeout("Result download time limit reached")
                data.extend(chunk)
            response._content = bytes(data)
            response._content_consumed = True
            emit(("timing", "result download", time.monotonic()-start))
            response.close()
            return response
        except requests.RequestException as error:
            if not transient(error) or attempt+1 == attempts:
                raise
            delay = min(.5 * 2**attempt, max(0, deadline-time.monotonic()))
            emit(("progress", "Temporary service error; retrying affected request"))
            time.sleep(delay)


def parse_rows(response):
    payload = response.json()  # Python preserves arbitrary-precision JSON integers.
    if not isinstance(payload, dict) or "metadata" not in payload or "data" not in payload:
        raise NetworkFailure("Gaia returned an invalid result document")
    names = [column["name"].lower() for column in payload["metadata"]]
    rows = [dict(zip(names, values)) for values in payload["data"]]
    for row in rows:
        for key in ("source_id", "ap_source_id", "dr3_source_id"):
            if row.get(key) is not None:
                if isinstance(row[key], (float, bool)):
                    raise NetworkFailure("Gaia source identifier was not an exact integer/string")
                row[key] = str(row[key])
    return rows


def tap_core(query, mode, options, deadline, emit):
    job_url = None
    with requests.Session() as session:
        try:
            params = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": query}
            if mode == "sync":
                emit(("progress", "Waiting for Gaia data and parameters"))
                response = request(session, "GET", BASE+"/sync", options, deadline, emit, params=params)
            else:
                response = request(session, "POST", BASE+"/async", options, deadline, emit,
                                   data=params, allow_redirects=False)
                location = response.headers.get("Location")
                if not location:
                    raise NetworkFailure("Gaia did not return an async job address")
                job_url = urljoin(BASE+"/async/", location)
                if urlparse(job_url).netloc != urlparse(BASE).netloc:
                    raise NetworkFailure("Unexpected Gaia job host")
                emit(("job", job_url))
                request(session, "POST", job_url+"/phase", options, deadline, emit, data={"PHASE": "RUN"}, allow_redirects=False)
                last_phase, phase_start = None, time.monotonic()
                while True:
                    phase = request(session, "GET", job_url+"/phase", options, deadline, emit).text.strip().upper()
                    if phase != last_phase:
                        now = time.monotonic()
                        if last_phase:
                            emit(("timing", "async "+last_phase, now-phase_start))
                        phase_start, last_phase = now, phase
                        emit(("progress", "Waiting for Gaia: "+phase.lower()))
                    if phase == "COMPLETED":
                        break
                    if phase in ("ERROR", "ABORTED"):
                        raise NetworkFailure("Gaia async job "+phase.lower())
                    if time.monotonic()+options.poll_interval >= deadline:
                        raise QueryTimeout("Gaia async polling time limit reached")
                    time.sleep(options.poll_interval)
                response = request(session, "GET", job_url+"/results/result", options, deadline, emit)
            start = time.monotonic()
            rows = parse_rows(response)
            emit(("timing", "result parsing", time.monotonic()-start))
            return rows
        except BaseException:
            if job_url:
                try:
                    session.post(job_url+"/phase", data={"PHASE": "ABORT"}, timeout=1)
                except requests.RequestException:
                    pass
            raise


def _worker(output, task, payload, options, limit):
    try:
        if task == "tap":
            result = tap_core(payload[0], payload[1], options, time.monotonic()+limit, output.put)
        elif task == "abort":
            requests.post(payload+"/phase", data={"PHASE": "ABORT"}, timeout=1)
            result = None
        else:
            # Dust/name functions are module-level, allowing Windows spawn.
            import importlib
            fn = getattr(importlib.import_module(payload[0]), payload[1])
            result = fn(*payload[2], network_options=options, emit=output.put)
        output.put(("result", result))
    except BaseException as error:
        kind = "timeout" if isinstance(error, (QueryTimeout, requests.Timeout)) else "failure"
        output.put(("error", kind, str(error)))


class NetworkProcess:
    """Launch only this module, never re-import the desktop launcher/astroquery.

    A pipe-reader thread belongs to this child and is joined after termination;
    no unbounded request runs in that thread.
    """
    def __init__(self, output, task, payload, options, limit):
        self.output = output
        self.input = json.dumps([task, payload, asdict(options), limit])
        self.process = None
        self.reader = None

    @property
    def pid(self):
        return self.process.pid if self.process else None

    def start(self):
        self.process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), "--worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with _state_lock:
            _children.add(self)
        self.process.stdin.write(self.input)
        self.process.stdin.close()
        def read():
            for line in self.process.stdout:
                try:
                    self.output.put(json.loads(line))
                except ValueError:
                    self.output.put(("error", "failure", "Invalid network-worker response"))
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def is_alive(self):
        return self.process is not None and self.process.poll() is None

    def terminate(self):
        try:
            self.process.terminate()
        except ProcessLookupError:
            pass

    def join(self, timeout=1):
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=1)

    def close(self):
        if self.reader:
            self.reader.join(timeout=1)
        if self.process and self.process.stdout:
            self.process.stdout.close()
        with _state_lock:
            _children.discard(self)


def bounded(task, payload, *, limit=None, options=None):
    """A killable worker bounds DNS, sockets, parsing AND repeated polling.

    No timed-out network thread is left running. The shared semaphore bounds
    simultaneous children, including simultaneous desktop/web requests.
    """
    context = CURRENT.get()
    options = options or (context.options if context else settings())
    limit = min(limit or options.overall_timeout, context.check() if context else options.overall_timeout)
    hard_deadline = time.monotonic()+limit
    reserve = min(2., limit/3) if task == "tap" and payload[1] == "async" else 0.
    deadline = hard_deadline-reserve
    while not _slots.acquire(timeout=.1):
        if context:
            context.check()
        if time.monotonic() >= deadline:
            raise QueryTimeout("Network concurrency wait reached time limit")
    output = queue.Queue()
    process = NetworkProcess(output, task, payload, options, max(.001, deadline-time.monotonic()))
    job = None
    failed = True
    last_progress = "Waiting for remote service"
    heartbeat = time.monotonic()
    try:
        process.start()
        while True:
            if context:
                context.check()
            if time.monotonic() >= deadline:
                raise QueryTimeout("Network operation reached overall time limit")
            try:
                event = output.get(timeout=min(.1, max(.001, deadline-time.monotonic())))
            except queue.Empty:
                if context and time.monotonic()-heartbeat >= 1:
                    context.report(last_progress)
                    heartbeat = time.monotonic()
                if not process.is_alive():
                    raise NetworkFailure("Network worker ended without a result")
                continue
            if event[0] == "result":
                failed = False
                return event[1]
            if event[0] == "error":
                raise (QueryTimeout if event[1] == "timeout" else NetworkFailure)(event[2])
            if event[0] == "job":
                job = event[1]
                LOGGER.info("Gaia async job: %s", job)
            elif event[0] == "timing":
                LOGGER.info("Timing %s: %.3f s", event[1], event[2])
            elif event[0] == "progress" and context:
                last_progress = event[1]
                context.report(event[1])
    finally:
        if process.pid:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            process.close()
        _slots.release()
        if failed and job:
            # Async calls reserve time for best-effort remote cancellation.
            try:
                token = CURRENT.set(None)
                try:
                    remaining = hard_deadline-time.monotonic()
                    if remaining > 0:
                        bounded("abort", job, limit=min(2, remaining), options=options)
                    else:
                        LOGGER.warning("No remaining time to confirm Gaia remote abort")
                finally:
                    CURRENT.reset(token)
            except NetworkFailure:
                LOGGER.warning("Gaia remote abort could not be confirmed")


def tap_query(query, count=1, *, mode=None, limit=None):
    context = CURRENT.get()
    options = context.options if context else settings()
    mode = mode or ("sync" if count <= options.sync_limit else "async")
    with timed("Gaia "+mode+" total"):
        return bounded("tap", (query, mode), options=options, limit=limit)


if __name__ == "__main__" and "--worker" in sys.argv:
    class Output:
        def put(self, event):
            print(json.dumps(event, ensure_ascii=False, allow_nan=False), flush=True)
    task, payload, options, limit = json.loads(sys.stdin.read())
    # Aux modules import scientist_network by name; use that same class identity.
    import scientist_network as worker_module
    worker_module._worker(Output(), task, payload, worker_module.NetworkOptions(**options), limit)
