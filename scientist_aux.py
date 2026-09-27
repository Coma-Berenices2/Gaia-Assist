"""Dust/name requests executed inside bounded network processes."""
import re
import time
import requests
from scientist_network import request

DUST_URL = "https://nadc.china-vo.org/data/dustmaps/calculator"


def dust(l, b, distance, *, network_options, emit):
    deadline = time.monotonic()+network_options.optional_timeout
    with requests.Session() as session:
        page = request(session, "GET", DUST_URL, network_options, deadline, emit)
        match = re.search(r'var\s+csrf_token\s*=\s*"([^"]+)"', page.text)
        if not match:
            raise ValueError("Dust service token missing")
        result = request(session, "POST", DUST_URL, network_options, deadline, emit,
            data={"coord_system": "galactic", "coord1": str(l), "coord2": str(b), "d": str(distance), "csrf_token": match[1]},
            headers={"Referer": DUST_URL, "X-CSRFToken": match[1]})
    match = re.search(r'E\(B-V\).*?<kbd>\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*mag\s*</kbd>', result.text, re.I | re.S)
    if not match:
        raise ValueError("Dust result missing E(B-V)")
    return float(match[1])


def sesame(name, *, network_options, emit):
    deadline = time.monotonic()+network_options.optional_timeout
    url = "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxpI/SNV?"+requests.utils.quote(name.strip(), safe="")
    with requests.Session() as session:
        return request(session, "GET", url, network_options, deadline, emit).text
