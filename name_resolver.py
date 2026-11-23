"""Selectable France/Harvard name resolution with a Sesame-compatible result."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import re
from pathlib import Path

LABELS = {'france': 'SIMBAD / Sesame — France', 'harvard': 'SIMBAD — Harvard (USA)'}
HARVARD_URL = 'https://simbad.harvard.edu/simbad/sim-id'
FRANCE_SESAME = 'https://cds.unistra.fr/cgi-bin/nph-sesame/-oxpI/SNV?'
_selected = ContextVar('name_resolver_service', default=None)


def selected_service():
    selected = _selected.get()
    if selected is not None:
        return selected
    path = Path(__file__).with_name('scientist_network_settings.json')
    try:
        return validate(json.loads(path.read_text(encoding='utf-8')).get('resolver_service', 'france'))
    except FileNotFoundError:
        return 'france'


def validate(service):
    if service not in LABELS:
        raise ValueError('Choose France or Harvard for the name resolver')
    return service


@contextmanager
def use_service(service):
    token = _selected.set(validate(service))
    try:
        yield
    finally:
        _selected.reset(token)


def fetch(name, get, service):
    """get(url, **kwargs) must raise HTTP errors and return a response."""
    validate(service)
    if service == 'france':
        import requests
        return get(FRANCE_SESAME + requests.utils.quote(name.strip(), safe='')).text
    # The identifier endpoint normalizes names such as Vega / NAME Vega;
    # an exact TAP ident.id match would miss those valid common-name inputs.
    response = get(HARVARD_URL, params={'Ident': name.strip(), 'output.format': 'ASCII'})
    text = response.text
    aliases = re.findall(r'Gaia\s+(DR[123])\s+(\d+)', text, re.I)
    if aliases:
        return '<Sesame><Resolver>' + ''.join(
            '<alias>Gaia ' + release.upper() + ' ' + identifier + '</alias>'
            for release, identifier in aliases) + '</Resolver></Sesame>'
    coordinate = re.search(
        r'Coordinates\s*\(ICRS[^\n]*?\)\s*:\s*'
        r'(\d+)\s+(\d+)\s+([\d.]+)\s+([+-])(\d+)\s+(\d+)\s+([\d.]+)', text, re.I)
    if coordinate:
        hour, minute, second, sign, degree, arcminute, arcsecond = coordinate.groups()
        h, m, sec, d, am, asec = map(float, (hour, minute, second, degree, arcminute, arcsecond))
        if not (0 <= h < 24 and 0 <= m < 60 and 0 <= sec < 60 and
                0 <= d <= 90 and 0 <= am < 60 and 0 <= asec < 60 and
                (d < 90 or am == asec == 0)):
            raise ValueError('Harvard SIMBAD returned invalid ICRS coordinates')
        ra = 15 * (h + m / 60 + sec / 3600)
        dec = (d + am / 60 + asec / 3600) * (-1 if sign == '-' else 1)
        return f'<Sesame><Resolver><jradeg>{ra:.12f}</jradeg><jdedeg>{dec:.12f}</jdedeg></Resolver></Sesame>'
    if re.search(r'(?:identifier|object|name).*?(?:not found|not recognized)|no (?:astronomical )?object found', text, re.I):
        return '<Sesame/>'
    raise ValueError('Harvard SIMBAD returned no usable Gaia identifier or ICRS coordinates')


def add_selector(parent, app):
    from dataclasses import replace
    from tkinter import ttk, StringVar, messagebox
    import scientist_network as network
    frame = ttk.Frame(parent)
    ttk.Label(frame, text='Name resolver').pack(side='left', padx=(0, 8))
    app.resolver_choice = StringVar(master=app.root, value=LABELS[selected_service()])
    combo = ttk.Combobox(frame, textvariable=app.resolver_choice, values=tuple(LABELS.values()), state='readonly', width=29)
    combo.pack(side='left')
    def select(_event):
        previous = network.settings()
        service = next(key for key, label in LABELS.items() if label == app.resolver_choice.get())
        try:
            network.save_settings(replace(previous, resolver_service=service))
        except OSError as error:
            app.resolver_choice.set(LABELS[previous.resolver_service])
            messagebox.showerror('Name resolver preference could not be saved', str(error), parent=app.root)
            return
        app.status.set('Name resolver: ' + LABELS[service] + '. Applies to subsequent name searches, including bulk queries.')
    combo.bind('<<ComboboxSelected>>', select)
    return frame
