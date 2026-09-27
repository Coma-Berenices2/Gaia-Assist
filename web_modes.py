"""One browser session with independent Explorer and Scientist workspaces."""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

SHELL = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gaia Assist — Choose a Mode</title>
<style>
body{margin:0;font:16px system-ui,sans-serif;background:#f4f7fb;color:#182536}
#chooser{max-width:760px;margin:10vh auto;padding:24px} .cards{display:flex;gap:20px;flex-wrap:wrap}
.card{flex:1;min-width:220px;background:white;padding:24px;border-radius:12px;border:1px solid #ccd6e2}
button{font:inherit;padding:10px 18px;border:1px solid #2461a3;border-radius:7px;background:#2461a3;color:white;cursor:pointer}
button:focus-visible{outline:3px solid #e9a823;outline-offset:3px}
#toolbar{box-sizing:border-box;height:64px;padding:12px 20px;background:white;border-bottom:1px solid #ccd6e2;display:flex;align-items:center;gap:16px}
#toolbar[hidden],iframe[hidden],#chooser[hidden]{display:none}
iframe{border:0;width:100%;height:calc(100dvh - 64px);display:block;background:white}
</style></head><body>
<section id="chooser"><h1>Welcome to Gaia Assist</h1><p>Choose how you want to explore the data. You can switch modes at any time.</p>
<div class="cards"><div class="card"><h2>Explorer</h2><p>Simple object lookups and approximate stellar properties.</p><button data-mode="explorer">Explorer</button></div>
<div class="card"><h2>Scientist</h2><p>Compare estimates and review scientific sources, assumptions and warnings.</p><button data-mode="scientist">Scientist</button></div></div></section>
<nav id="toolbar" aria-label="Application mode" hidden><strong id="modeLabel"></strong><button id="switchMode"></button></nav>
<script>
let currentMode = null;
const frames = {};
function showMode(mode) {
  if (!['explorer', 'scientist'].includes(mode)) return;
  if (!frames[mode]) {
    const frame = document.createElement('iframe');
    frame.src = '/' + mode + '/';
    frame.title = 'Gaia Assist — ' + mode;
    document.body.appendChild(frame);
    frames[mode] = frame;
  }
  for (const [name, frame] of Object.entries(frames)) frame.hidden = name !== mode;
  currentMode = mode;
  document.getElementById('chooser').hidden = true;
  document.getElementById('toolbar').hidden = false;
  const label = mode === 'explorer' ? 'Explorer' : 'Scientist';
  document.getElementById('modeLabel').textContent = 'Mode: ' + label;
  document.getElementById('switchMode').textContent = 'Switch to ' + (mode === 'explorer' ? 'Scientist' : 'Explorer');
  document.title = 'Gaia Assist — ' + label;
}
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => showMode(button.dataset.mode)));
document.getElementById('switchMode').addEventListener('click', () => showMode(currentMode === 'explorer' ? 'scientist' : 'explorer'));
</script></body></html>'''


def mode_page(backend, mode):
    page = backend.make_page()
    # Scope every browser API request to its calculation backend, including streams.
    for endpoint in ('query', 'save', 'bulk-query', 'bulk-save', 'load', 'query-stream', 'bulk-query-stream'):
        page = page.replace('"/' + endpoint + '"', '"/' + mode + '/' + endpoint + '"')
    return page


def make_handler(explorer, scientist):
    backends = {'explorer': explorer, 'scientist': scientist}

    class CombinedHandler(BaseHTTPRequestHandler):
        def page(self, content):
            body = content.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/', '/index.html'):
                self.page(SHELL)
            elif path.strip('/') in backends:
                mode = path.strip('/')
                self.page(mode_page(backends[mode], mode))
            else:
                self.send_error(404)

        def do_POST(self):
            path = urlsplit(self.path).path
            parts = path.split('/', 2)
            if len(parts) != 3 or parts[1] not in backends or not parts[2]:
                self.send_error(404)
                return
            # Reuse existing request handlers without opening another server or
            # parsing the request twice. Each request has its own delegate.
            handler_type = backends[parts[1]].GaiaAssistWebHandler
            delegate = object.__new__(handler_type)
            delegate.__dict__ = self.__dict__.copy()
            delegate.path = '/' + parts[2]
            try:
                delegate.do_POST()
            finally:
                self.close_connection = delegate.close_connection

    return CombinedHandler
