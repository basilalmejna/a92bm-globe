#!/usr/bin/env python3
"""Render the solar-terrestrial / HF propagation panel (spaceweather.svg).

Laid out like N0NBH's hamqsl.com solar banners, in the A92BM page style:
the Sun in 304 A (SDO/NASA), the main indices, N0NBH's calculated HF band
conditions (day/night) and VHF conditions. N0NBH's XML feed (hourly; credit
required) is the main source; NOAA SWPC fills in any index it cannot give.

  spaceweather.py OUT.svg
"""
import datetime as dt
import html
import json
import re
import sys
import time
import os
import urllib.request
import base64
import io
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from weather import PANEL_W, PANEL_H  # noqa: E402

B = 'https://services.swpc.noaa.gov'
UA = 'A92BM-space-weather-panel (https://basilalmejna.github.io/a92bm-globe/)'
TZ = dt.timezone(dt.timedelta(hours=3), 'AST')
UTC = dt.timezone.utc


def get(path, as_json=True, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(B + path, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read().decode('utf-8', 'replace')
            return json.loads(data) if as_json else data
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))


def ts(s):
    s = s.replace('Z', '')
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


def safe(fn):
    try:
        return fn()
    except Exception as e:  # one failed feed must not blank the whole panel
        print(fn.__name__, 'unavailable:', e)
        return None


# ------------------------------------------------------------------ readers
def sfi():
    r = get('/products/summary/10cm-flux.json')[0]
    return {'value': int(round(float(r['flux']))), 'time': ts(r['time_tag'])}


def ssn():
    rows = [l.split() for l in get('/text/daily-solar-indices.txt', False).splitlines()
            if re.match(r'^\d{4} \d\d \d\d', l)]
    y, m, d, _flux, n = rows[-1][:5]
    return {'value': int(n), 'time': dt.datetime(int(y), int(m), int(d), tzinfo=UTC)}


def kp():
    r = get('/products/noaa-planetary-k-index.json')[-1]
    return {'value': float(r['Kp']), 'time': ts(r['time_tag'])}


def ap():
    for line in reversed(get('/text/daily-geomagnetic-indices.txt', False).splitlines()):
        if not re.match(r'^\d{4} \d\d \d\d', line):
            continue
        tok = line.split()
        if tok[-1] == '-1.00':
            continue  # today's day is not complete yet
        y, m, d = map(int, line[:10].split())
        return {'value': int(tok[-9]), 'time': dt.datetime(y, m, d, tzinfo=UTC)}


def flare():
    r = get('/json/goes/primary/xray-flares-latest.json')[0]
    return {'value': r['max_class'], 'time': ts(r['max_time']), 'now': r.get('current_class')}


def scales():
    r = get('/products/noaa-scales.json')['0']
    return {'R': r['R'], 'S': r['S'], 'G': r['G'], 'time': ts(f"{r['DateStamp']}T{r['TimeStamp']}")}


def solar_wind():
    rows = [r for r in get('/json/rtsw/rtsw_wind_1m.json') if r.get('active') and r.get('proton_speed') is not None]
    r = max(rows, key=lambda r: r['time_tag'])
    return {'value': round(r['proton_speed']), 'time': ts(r['time_tag'])}


def bz():
    rows = [r for r in get('/json/rtsw/rtsw_mag_1m.json') if r.get('active') and r.get('bz_gsm') is not None]
    r = max(rows, key=lambda r: r['time_tag'])
    return {'value': r['bz_gsm'], 'time': ts(r['time_tag'])}


# ------------------------------------------------------------------ N0NBH + SDO
N0NBH = 'https://www.hamqsl.com/solarxml.php'
SDO_304 = 'https://sdo.gsfc.nasa.gov/assets/img/latest/latest_512_0304.jpg'


def fetch(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))


N0NBH_RELAY = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'n0nbh.xml')


def n0nbh():
    try:
        raw = fetch(N0NBH, tries=1)
    except Exception as e:  # hamqsl.com refuses GitHub's servers; Basil's PC relays the XML hourly
        print('N0NBH direct fetch failed, using the relayed copy:', e)
        raw = open(N0NBH_RELAY, 'rb').read()
    root = ET.fromstring(raw).find('solardata')
    t = lambda tag: (root.findtext(tag) or '').strip()
    d = {k: t(k) for k in ('solarflux', 'aindex', 'kindex', 'xray', 'sunspots', 'heliumline', 'protonflux',
                           'electonflux', 'aurora', 'latdegree', 'solarwind', 'magneticfield', 'geomagfield',
                           'signalnoise', 'muf')}
    d['time'] = dt.datetime.strptime(t('updated'), '%d %b %Y %H%M GMT').replace(tzinfo=UTC)
    d['hf'] = {(b.get('name'), b.get('time')): b.text.strip() for b in root.iter('band')}
    d['vhf'] = {(p.get('name'), p.get('location')): p.text.strip() for p in root.iter('phenomenon')}
    return d


def sun_image():
    from PIL import Image
    im = Image.open(io.BytesIO(fetch(SDO_304))).convert('RGB')
    w, h = im.size
    c = int(min(w, h) * 0.86)  # the disc plus its limb; leaves out the caption text in the corners
    im = im.crop(((w - c) // 2, (h - c) // 2, (w + c) // 2, (h + c) // 2)).resize((360, 360), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=82)
    return base64.b64encode(buf.getvalue()).decode()


# ------------------------------------------------------------------ render
GOOD, WARN, SERIOUS, CRIT = '#2bd67b', '#f5c518', '#ff8a3d', '#ff4d6d'
MUTED = '#7f82b0'


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def text(x, y, s, size=13, fill='#e9eaf5', anchor='middle', weight='normal', extra=''):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}"{extra}>{html.escape(str(s))}</text>')


def pill(cx, cy, w, word, color, size=11.5):
    return (f'<rect x="{cx - w / 2:.1f}" y="{cy - 11}" width="{w}" height="22" rx="11" fill="{color}" fill-opacity="0.16" '
            f'stroke="{color}" stroke-opacity="0.75"/>' + text(cx, cy + 4, word, size, color, weight='bold'))


def status_sfi(v):
    return (WARN, 'Low') if v < 90 else (GOOD, 'Good') if v < 150 else (GOOD, 'Excellent')


def status_k(v):
    return (GOOD, 'Quiet') if v < 3 else (WARN, 'Unsettled') if v < 4 else (SERIOUS, 'Active') if v < 5 else (CRIT, f'Storm G{min(5, int(v) - 4)}')


def status_a(v):
    return (GOOD, 'Quiet') if v < 8 else (GOOD, 'Unsettled') if v < 16 else (WARN, 'Active') if v < 30 else (SERIOUS, 'Storm')


def status_xray(s):
    c = (s or '?')[0].upper()
    return {'A': (GOOD, 'Quiet'), 'B': (GOOD, 'Quiet'), 'C': (WARN, 'Minor'), 'M': (SERIOUS, 'Fade risk'),
            'X': (CRIT, 'Blackout risk')}.get(c, (MUTED, '—'))


def status_wind(v):
    return (GOOD, 'Normal') if v < 500 else (WARN, 'Elevated') if v < 700 else (SERIOUS, 'High')


def status_bz(v):
    return (GOOD, 'North') if v >= 0 else (WARN, 'South') if v > -10 else (SERIOUS, 'Strong south')


def cond_color(word):
    w = word.lower()
    return GOOD if w.startswith('good') else WARN if w.startswith('fair') else CRIT if w.startswith('poor') else MUTED


def render(d, now):
    W, H = PANEL_W, PANEL_H
    n, sw = d['n0nbh'] or {}, d['swpc']
    out = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="#000030" stroke="#31336e"/>',
           text(24, 32, 'SOLAR-TERRESTRIAL DATA · HF PROPAGATION', 11, '#17f9da', 'start', extra=' letter-spacing="3.5"')]
    if n:
        stale = (now - n['time']).total_seconds() > 3 * 3600
        out.append(text(W - 24, 32, ('STALE · ' if stale else '') + f"N0NBH {n['time']:%H:%M} UTC", 10,
                        CRIT if stale else MUTED, 'end'))

    # --- the Sun, 304 A
    cx, cy, r = 112, 142, 84
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r + 9}" fill="url(#glow)"/>')
    if d['sun']:
        out.append(f'<clipPath id="disc"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>'
                   f'<image x="{cx - r}" y="{cy - r}" width="{2 * r}" height="{2 * r}" clip-path="url(#disc)" '
                   f'href="data:image/jpeg;base64,{d["sun"]}"/>')
    else:
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#sunfill)"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#17f9da" stroke-opacity="0.55" stroke-width="1.5"/>')
    out.append(text(cx, 244, 'THE SUN NOW · SDO 304 Å', 9, MUTED, extra=' letter-spacing="1.2"'))

    # --- index tiles, 4 x 2
    def val(key, swkey=None, cast=num):
        v = cast(n.get(key)) if n.get(key) not in (None, '', 'NoRpt', 'No Report') else None
        if v is None and swkey and sw.get(swkey):
            v = sw[swkey]['value']
        return v

    sfi, ssn, a, k = val('solarflux', 'sfi'), val('sunspots', 'ssn'), val('aindex', 'ap'), val('kindex', 'kp')
    xr = n.get('xray') or (sw.get('flare') or {}).get('now')
    wind, bz = val('solarwind', 'wind'), val('magneticfield', 'bz')
    sc = sw.get('scales')
    tiles = [('SOLAR FLUX', sfi, lambda v: f'{v:.0f}', status_sfi),
             ('SUNSPOTS', ssn, lambda v: f'{v:.0f}', lambda v: (GOOD, 'Active sun') if v >= 50 else (WARN, 'Quiet sun')),
             ('A-INDEX', a, lambda v: f'{v:.0f}', status_a),
             ('K-INDEX', k, lambda v: f'{v:.0f}' if v == int(v) else f'{v:.1f}', status_k),
             ('X-RAY', xr, lambda v: v, status_xray),
             ('SOLAR WIND', wind, lambda v: f'{v:.0f}', status_wind),
             ('IMF Bz', bz, lambda v: f'{v:+.1f}', status_bz),
             ('NOAA R · S · G', sc, lambda v: f"{v['R']['Scale']} · {v['S']['Scale']} · {v['G']['Scale']}",
              lambda v: (GOOD, 'No alerts') if all(v[x]['Scale'] in ('0', None) for x in 'RSG') else (SERIOUS, 'Alert'))]
    units = {'SOLAR WIND': 'km/s', 'IMF Bz': 'nT'}
    x0, tw, th = 214, 102.5, 94
    for i, (label, v, fmt, st) in enumerate(tiles):
        tx, ty = x0 + (i % 4) * (tw + 4), 48 + (i // 4) * (th + 6)
        mx = tx + tw / 2
        out.append(f'<rect x="{tx:.1f}" y="{ty}" width="{tw}" height="{th}" rx="10" fill="#151541" stroke="#31336e"/>')
        out.append(text(mx, ty + 20, label, 9, '#a9abd0', extra=' letter-spacing="1.2"'))
        if v is None:
            out.append(text(mx, ty + 54, '—', 22, MUTED, weight='bold'))
            out.append(text(mx, ty + 78, 'Unavailable', 10, MUTED))
            continue
        out.append(text(mx, ty + 53, fmt(v), 24, '#17f9da', weight='800'))
        if label in units:
            out.append(text(mx, ty + 66, units[label], 8.5, MUTED))
        color, word = st(v)
        wy = ty + 82
        out.append(f'<circle cx="{mx - 5 - len(word) * 2.9:.1f}" cy="{wy - 3.5}" r="3.5" fill="{color}"/>')
        out.append(text(mx + 5, wy, word, 10, '#e9eaf5', weight='bold'))

    # --- HF band conditions
    out.append(f'<rect x="16" y="256" width="318" height="204" rx="12" fill="#151541" stroke="#31336e"/>')
    out.append(text(32, 279, 'HF BAND CONDITIONS', 10, '#17f9da', 'start', extra=' letter-spacing="2.5"'))
    out.append(text(216, 279, 'DAY', 9.5, '#a9abd0', extra=' letter-spacing="2"'))
    out.append(text(290, 279, 'NIGHT', 9.5, '#a9abd0', extra=' letter-spacing="2"'))
    hf = n.get('hf') or {}
    for i, band in enumerate(('80m-40m', '30m-20m', '17m-15m', '12m-10m')):
        y = 312 + i * 38
        if i:
            out.append(f'<line x1="30" y1="{y - 19}" x2="320" y2="{y - 19}" stroke="#31336e"/>')
        out.append(text(32, y + 5, band.replace('-', ' – '), 15, '#ffffff', 'start', 'bold'))
        for colx, tod in ((216, 'day'), (290, 'night')):
            word = hf.get((band, tod), '—')
            out.append(pill(colx, y, 64, word, cond_color(word)))

    # --- VHF + geomagnetic
    out.append(f'<rect x="342" y="256" width="282" height="204" rx="12" fill="#151541" stroke="#31336e"/>')
    out.append(text(358, 279, 'VHF · GEOMAGNETIC', 10, '#17f9da', 'start', extra=' letter-spacing="2.5"'))
    vhf = n.get('vhf') or {}
    def vword(key):
        w = vhf.get(key)
        if not w:
            return '—', MUTED
        return ('Closed', MUTED) if 'closed' in w.lower() else (w.replace('MHz ES', ' MHz Es').replace('High LAT AUR', 'Aurora open'), GOOD)
    geo = (n.get('geomagfield') or '—').title()
    geo_c = GOOD if geo in ('Quiet', 'Vr Quiet', 'Very Quiet') else WARN if geo in ('Unsettled', 'Active') else MUTED if geo == '—' else SERIOUS
    rows = [('Aurora', *vword(('vhf-aurora', 'northern_hemi'))),
            ('6 m Es · Europe', *vword(('E-Skip', 'europe_6m'))),
            ('4 m Es · Europe', *vword(('E-Skip', 'europe_4m'))),
            ('2 m Es · Europe', *vword(('E-Skip', 'europe'))),
            ('2 m Es · N. America', *vword(('E-Skip', 'north_america'))),
            ('Geomagnetic field', geo, geo_c),
            ('Signal noise', n.get('signalnoise') or '—', '#e9eaf5')]
    for i, (label, word, color) in enumerate(rows):
        y = 306 + i * 23.5
        out.append(text(358, y, label, 11.5, '#e9eaf5', 'start'))
        out.append(f'<circle cx="{604 - len(word) * 6.6 - 8:.1f}" cy="{y - 4}" r="3.5" fill="{color}"/>' if color != '#e9eaf5' else '')
        out.append(text(608, y, word, 11.5, color if color != MUTED else '#a9abd0', 'end', 'bold'))

    # --- more indices, time, credits
    extra = []
    for label, key, unit in (('304 Å', 'heliumline', ''), ('Proton flux', 'protonflux', ''), ('Electron flux', 'electonflux', ''),
                             ('Aurora', 'aurora', ''), ('Aurora lat', 'latdegree', '°'), ('MUF', 'muf', ' MHz')):
        v = n.get(key)
        if v and v not in ('NoRpt', 'No Report'):
            extra.append(f'{label} {v}{unit}')
    if extra:
        out.append(text(W / 2, 484, '  ·  '.join(extra), 10.5, '#a9abd0'))
    local = now.astimezone(TZ)
    out.append(text(W / 2, H - 30, f'As of {now:%H:%M} UTC  ·  {local:%H:%M} Bahrain (UTC+3), {local:%a %d %b %Y}  ·  refreshed every 15 min',
                    10.5, '#a9abd0'))
    out.append(text(W / 2, H - 13, 'Solar data & band conditions: N0NBH, hamqsl.com · NOAA SWPC · Sun image: SDO/NASA',
                    9.5, MUTED))
    defs = ('<radialGradient id="glow"><stop offset="0.82" stop-color="#ff7a2f" stop-opacity="0.45"/>'
            '<stop offset="1" stop-color="#ff7a2f" stop-opacity="0"/></radialGradient>'
            '<radialGradient id="sunfill"><stop offset="0" stop-color="#ffb347"/><stop offset="1" stop-color="#c0391b"/></radialGradient>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            'font-family="Segoe UI, Arial, Helvetica, sans-serif">' + f'<defs>{defs}</defs>' + '\n'.join(out) + '</svg>\n')


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'spaceweather.svg'
    d = {'n0nbh': safe(n0nbh), 'sun': safe(sun_image),
         'swpc': {k: safe(f) for k, f in (('sfi', sfi), ('ssn', ssn), ('kp', kp), ('ap', ap), ('flare', flare),
                                          ('scales', scales), ('wind', solar_wind), ('bz', bz))}}
    open(out, 'w').write(render(d, dt.datetime.now(UTC)))
    print('wrote', out, 'N0NBH' if d['n0nbh'] else 'no N0NBH', 'sun' if d['sun'] else 'no sun image')


if __name__ == '__main__':
    main()
