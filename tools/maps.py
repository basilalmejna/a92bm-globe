#!/usr/bin/env python3
"""Render the Gulf temperature/wind map and the grey-line (day/night) world map.

  maps.py gulf OUT.png       Open-Meteo model temperature and wind on a 1-degree grid
  maps.py greyline OUT.png   solar terminator over NASA day/night Earth images

Base layers in tools/basemap: Natural Earth land and borders (public domain),
NASA Blue Marble / Black Marble textures (public domain). No home marker is
drawn; Bahrain is shown at country level only.
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, 'basemap')
UA = 'A92BM-maps (https://basilalmejna.github.io/a92bm-globe/)'
TZ = dt.timezone(dt.timedelta(hours=3), 'AST')
UTC = dt.timezone.utc
NAVY, PANEL, BORDER, MINT, MUTED, TEXT = (0, 0, 48), (21, 21, 65), (49, 51, 110), (23, 249, 218), (169, 171, 208), (233, 234, 245)


def font(size, bold=False):
    for p in (['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'] if bold else []) + \
             ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def frame(img, title, subtitle, footer, k=1):
    """Wrap a map in the page's card style with a title and a footer line (k = pixel scale)."""
    W = img.width
    out = Image.new('RGB', (W, img.height + 64 * k), NAVY)
    out.paste(img, (0, 44 * k))
    d = ImageDraw.Draw(out)
    d.text((14 * k, 8 * k), title, font=font(13 * k, True), fill=MINT)
    d.text((14 * k, 26 * k), subtitle, font=font(11 * k), fill=MUTED)
    d.text((W // 2, img.height + 54 * k), footer, font=font(10 * k), fill=(127, 130, 176), anchor='mm')
    return out


# ------------------------------------------------------------------ Gulf map
# deep, page-matching ramp: cool blues -> teal -> green -> amber -> orange -> crimson -> wine
TEMP_STOPS = [(10, (28, 36, 104)), (18, (34, 82, 158)), (23, (30, 128, 146)), (27, (52, 138, 96)), (31, (176, 146, 46)),
              (35, (196, 96, 38)), (40, (170, 38, 58)), (46, (100, 18, 66))]
T_MIN, T_MAX = TEMP_STOPS[0][0], TEMP_STOPS[-1][0]


def temp_rgb(t):
    t = np.clip(t, TEMP_STOPS[0][0], TEMP_STOPS[-1][0])
    out = np.zeros(t.shape + (3,))
    for (t0, c0), (t1, c1) in zip(TEMP_STOPS, TEMP_STOPS[1:]):
        m = (t >= t0) & (t <= t1)
        f = ((t - t0) / (t1 - t0))[m][:, None]
        out[m] = np.array(c0) * (1 - f) + np.array(c1) * f
    return out


def gulf(path):
    meta = json.load(open(os.path.join(BASE, 'gulf.json')))
    W0, E0, S0, N0 = meta['bbox']
    W, H, kx, ky = meta['width'], meta['height'], meta['kx'], meta['ky']
    k = round(W / 640)                            # drawing scale (maps are rendered at 2x for wide screens)
    lons = np.arange(math.floor(W0), math.ceil(E0) + 0.01, 1.0)
    lats = np.arange(math.floor(S0), math.ceil(N0) + 0.01, 1.0)
    LA, LO = np.meshgrid(lats, lons, indexing='ij')
    url = ('https://api.open-meteo.com/v1/forecast?latitude=' + ','.join(f'{v:.2f}' for v in LA.ravel()) +
           '&longitude=' + ','.join(f'{v:.2f}' for v in LO.ravel()) +
           '&current=temperature_2m,wind_speed_10m,wind_direction_10m&wind_speed_unit=kmh&timezone=Asia%2FBahrain')
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            data = json.load(urllib.request.urlopen(req, timeout=60))
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))
    data = data if isinstance(data, list) else [data]
    T = np.array([p['current']['temperature_2m'] for p in data], float).reshape(LA.shape)
    SP = np.array([p['current']['wind_speed_10m'] for p in data], float).reshape(LA.shape)
    DIR = np.array([p['current']['wind_direction_10m'] for p in data], float).reshape(LA.shape)
    valid = dt.datetime.fromisoformat(data[0]['current']['time'])

    # bilinear temperature field over every pixel
    px_lon = W0 + (np.arange(W) + 0.5) / kx
    px_lat = N0 - (np.arange(H) + 0.5) / ky
    fi = np.clip((px_lat - lats[0]) / 1.0, 0, len(lats) - 1.001)
    fj = np.clip((px_lon - lons[0]) / 1.0, 0, len(lons) - 1.001)
    i0, j0 = fi.astype(int), fj.astype(int)
    di, dj = (fi - i0)[:, None], (fj - j0)[None, :]
    f = (T[i0][:, j0] * (1 - di) * (1 - dj) + T[i0 + 1][:, j0] * di * (1 - dj) +
         T[i0][:, j0 + 1] * (1 - di) * dj + T[i0 + 1][:, j0 + 1] * di * dj)
    rgb = temp_rgb(f)
    land = np.asarray(Image.open(os.path.join(BASE, 'gulf-land.png')).convert('L'), float)[:H, :W] / 255
    sea = rgb * 0.62                                      # same colours over water, just darker, so land stands out
    img = Image.fromarray(np.uint8(rgb * land[..., None] + sea * (1 - land[..., None])), 'RGB')
    d = ImageDraw.Draw(img, 'RGBA')
    coast = Image.open(os.path.join(BASE, 'gulf-land.png')).convert('L').filter(ImageFilter.FIND_EDGES)
    img.paste((255, 255, 255), (0, 0), coast.point(lambda v: min(255, v * 3)))
    borders = Image.open(os.path.join(BASE, 'gulf-borders.png')).convert('L')
    img.paste((40, 40, 70), (0, 0), borders.point(lambda v: int(v * 0.7)))

    def xy(lon, lat):
        return (lon - W0) * kx, (N0 - lat) * ky
    # wind arrows: point the way the wind blows, length grows with speed
    for a in range(LA.shape[0]):
        for b in range(LA.shape[1]):
            x, y = xy(LO[a, b], LA[a, b])
            if not (8 * k < x < W - 8 * k and 8 * k < y < H - 8 * k):
                continue
            to = math.radians(DIR[a, b] + 180)
            L = (8 + min(SP[a, b], 50) * 0.6) * k
            dx, dy = math.sin(to) * L, -math.cos(to) * L
            x0, y0, x1, y1 = x - dx / 2, y - dy / 2, x + dx / 2, y + dy / 2
            d.line([(x0, y0), (x1, y1)], fill=(0, 0, 40, 230), width=round(4 * k))
            d.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, 255), width=round(2 * k))
            for s in (-1, 1):
                ang = to + math.pi + s * 0.5
                d.line([(x1, y1), (x1 + math.sin(ang) * 6 * k, y1 - math.cos(ang) * 6 * k)], fill=(255, 255, 255, 255), width=round(2 * k))
    def temp_at(x, y):
        return float(f[min(H - 1, max(0, int(y))), min(W - 1, max(0, int(x)))])
    for c in meta['cities']:
        x, y = xy(c['lon'], c['lat'])
        if not (0 <= x < W and 0 <= y < H):
            continue
        t = temp_at(x, y)
        label = f"{c['name']}  {round(t)}\u00b0"
        fnt = font(round(11 * k), True)
        right = c.get('side') == 'left' or x > W - 150 * k
        tw = d.textlength(label, font=fnt)
        bx0 = x - 7 * k - tw - 12 * k if right else x + 7 * k
        d.rounded_rectangle([bx0, y - 11 * k, bx0 + tw + 12 * k, y + 11 * k], 8 * k, fill=(0, 0, 40, 200), outline=(255, 255, 255, 90))
        d.text((bx0 + 6 * k, y), label, font=fnt, fill=(255, 255, 255, 255), anchor='lm')
        d.ellipse([x - 3.5 * k, y - 3.5 * k, x + 3.5 * k, y + 3.5 * k], fill=(255, 255, 255, 255), outline=(0, 0, 40, 255))
    # legend
    lg_w = round(300 * k)
    lx, ly = W - lg_w - 12 * k, H - 30 * k
    d.rounded_rectangle([lx - 8 * k, ly - 18 * k, lx + lg_w + 8 * k, ly + 22 * k], 8 * k, fill=(0, 0, 48, 210))
    ramp = temp_rgb(np.linspace(T_MIN, T_MAX, lg_w))
    for c in range(lg_w):
        d.line([(lx + c, ly), (lx + c, ly + 8 * k)], fill=tuple(int(v) for v in ramp[c]))
    for tv in (10, 20, 30, 40):
        tx = lx + (tv - T_MIN) / (T_MAX - T_MIN) * lg_w
        d.text((tx, ly + 10 * k), f'{tv}°', font=font(round(9 * k)), fill=TEXT, anchor='ma')
    d.text((lx, ly - 15 * k), '°C  ·  arrows: wind direction, longer = stronger', font=font(round(9 * k)), fill=TEXT)
    out = frame(img, 'GULF · TEMPERATURE & WIND',
                f'Model analysis valid {valid:%d %b %H:%M} AST  ·  1° grid, interpolated  ·  refreshed every 15 min',
                'Data: Open-Meteo.com (CC BY 4.0)  ·  Coastlines & borders: Natural Earth (public domain)', k)
    out.save(path, optimize=True)
    print('wrote', path, out.size, f'T {T.min():.0f}-{T.max():.0f} C')


# ------------------------------------------------------------------ grey line
def sun_position(when):
    """Subsolar latitude/longitude (degrees) for a UTC datetime."""
    n = (when - dt.datetime(2000, 1, 1, 12, tzinfo=UTC)).total_seconds() / 86400
    L = math.radians((280.460 + 0.9856474 * n) % 360)
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    dec = math.asin(math.sin(eps) * math.sin(lam))
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    gmst = (280.46061837 + 360.98564736629 * n) % 360
    lon = (math.degrees(ra) - gmst + 540) % 360 - 180
    return math.degrees(dec), lon


def greyline(path, now=None):
    now = now or dt.datetime.now(UTC)
    W, H, k = 1280, 640, 2
    day = np.asarray(Image.open(os.path.join(BASE, 'earth-day-2048.jpg')).convert('RGB').resize((W, H), Image.LANCZOS), float)
    night = np.asarray(Image.open(os.path.join(BASE, 'earth-night-2048.jpg')).convert('RGB').resize((W, H), Image.LANCZOS), float)
    night = np.clip(night * 1.6 + 8, 0, 255)
    dec, slon = sun_position(now)
    lon = np.radians(-180 + (np.arange(W) + 0.5) * 360 / W)[None, :]
    lat = np.radians(90 - (np.arange(H) + 0.5) * 180 / H)[:, None]
    d, sl = math.radians(dec), math.radians(slon)
    alt = np.degrees(np.arcsin(np.sin(lat) * math.sin(d) + np.cos(lat) * math.cos(d) * np.cos(lon - sl)))
    w = np.clip((alt + 6) / 12, 0, 1)[..., None]           # civil twilight blend
    rgb = day * w + night * (1 - w)
    band = np.exp(-(alt / 1.2) ** 2)[..., None]             # the grey line itself
    rgb = rgb * (1 - 0.35 * band) + np.array([255, 196, 90]) * 0.35 * band
    img = Image.fromarray(np.uint8(np.clip(rgb, 0, 255)), 'RGB')
    dr = ImageDraw.Draw(img, 'RGBA')
    for gx in range(-150, 181, 30):
        x = (gx + 180) / 360 * W
        dr.line([(x, 0), (x, H)], fill=(255, 255, 255, 28))
    for gy in range(-60, 61, 30):
        y = (90 - gy) / 180 * H
        dr.line([(0, y), (W, y)], fill=(255, 255, 255, 28))

    def xy(lo, la):
        return (lo + 180) / 360 * W, (90 - la) / 180 * H
    sx, sy = xy(slon, dec)
    dr.ellipse([sx - 7 * k, sy - 7 * k, sx + 7 * k, sy + 7 * k], fill=(255, 210, 60, 255), outline=(255, 255, 255, 255), width=k)
    bx, by = xy(50.6, 26.2)                                   # Bahrain, country level
    dr.ellipse([bx - 4 * k, by - 4 * k, bx + 4 * k, by + 4 * k], fill=(23, 249, 218, 255), outline=(0, 0, 40, 255), width=k)
    dr.text((bx + 7 * k, by - 7 * k), 'Bahrain', font=font(11 * k, True), fill=(255, 255, 255, 255), stroke_width=2 * k, stroke_fill=(0, 0, 40, 255))
    panel_svg(path, img, now, dec, slon)


def sun_alt(when, lat=26.30, lon=50.62):
    dec, slon = sun_position(when)
    d, la = math.radians(dec), math.radians(lat)
    return math.degrees(math.asin(math.sin(la) * math.sin(d) + math.cos(la) * math.cos(d) * math.cos(math.radians(lon - slon))))


def crossings(day_local, level):
    """Local times when the sun crosses `level` degrees (rising, setting) over the Bahrain area."""
    start = dt.datetime(day_local.year, day_local.month, day_local.day, tzinfo=TZ)
    prev, up, down = None, None, None
    for m in range(0, 24 * 60 + 1, 2):
        t = start + dt.timedelta(minutes=m)
        a = sun_alt(t.astimezone(UTC)) - level
        if prev is not None:
            if prev < 0 <= a and up is None:
                up = t
            if prev >= 0 > a and down is None:
                down = t
        prev = a
    return up, down


# ------------------------------------------------------------------ tile pictures
def _vgrad(w, h, stops):
    """Vertical gradient; stops = [(0..1, (r, g, b)), ...]."""
    y = np.linspace(0, 1, h)[:, None]
    out = np.zeros((h, 1, 3))
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        m = (y >= p0) & (y <= p1)
        f = np.clip((y - p0) / max(p1 - p0, 1e-6), 0, 1)
        out = np.where(m[..., None], np.array(c0) + (np.array(c1) - np.array(c0)) * f[..., None], out)
    return np.repeat(out, w, axis=1)


def _stars(rgb, n, seed, top=0.0, bottom=1.0):
    rng = np.random.default_rng(seed)
    h, w, _ = rgb.shape
    for _ in range(n):
        x, y = rng.integers(0, w), rng.integers(int(h * top), int(h * bottom))
        rgb[y, x] = np.maximum(rgb[y, x], rng.integers(150, 255))
    return rgb


def sky_scene(kind, w=304, h=124):
    """A painted horizon over the Gulf: 'sunrise', 'sunset' or 'twilight' (the grey line)."""
    hz = int(h * 0.66)
    sky_stops = {
        'sunrise': [(0, (24, 38, 104)), (0.45, (120, 90, 160)), (0.78, (240, 128, 130)), (1, (255, 205, 120))],
        'sunset': [(0, (36, 20, 72)), (0.42, (130, 40, 90)), (0.75, (226, 82, 50)), (1, (255, 168, 64))],
        'twilight': [(0, (4, 8, 40)), (0.55, (24, 40, 110)), (0.86, (70, 80, 150)), (1, (232, 140, 80))],
    }[kind]
    sea_top = {'sunrise': (70, 70, 120), 'sunset': (70, 30, 50), 'twilight': (20, 26, 70)}[kind]
    sky = _vgrad(w, hz, sky_stops)
    sea = _vgrad(w, h - hz, [(0, sea_top), (1, (6, 10, 34))])
    rgb = np.concatenate([sky, sea], 0)
    yy, xx = np.mgrid[0:h, 0:w]
    if kind == 'twilight':
        rgb = _stars(rgb, 60, 7, 0, 0.5)
    else:
        sx, r = w * (0.5 if kind == 'sunrise' else 0.5), h * 0.13
        sun_col = np.array((255, 236, 170) if kind == 'sunrise' else (255, 196, 110))
        d = np.hypot(xx - sx, yy - hz)
        glow = np.exp(-(d / (h * 0.55)) ** 2)[..., None] * (yy < hz)[..., None]
        rgb = rgb * (1 - 0.55 * glow) + sun_col * 0.55 * glow
        disc = (d < r) & (yy < hz)
        rgb[disc] = sun_col
        # glitter path on the water
        rng = np.random.default_rng(3 if kind == 'sunrise' else 5)
        for y in range(hz + 1, h, 2):
            depth = (y - hz) / (h - hz)
            half = r * (0.6 + 2.4 * depth)
            for _ in range(3):
                c = sx + rng.normal(0, half * 0.5)
                ln = rng.uniform(2, 6 + 10 * depth)
                x0, x1 = int(max(0, c - ln)), int(min(w, c + ln))
                a = 0.75 * (1 - 0.6 * depth)
                rgb[y, x0:x1] = rgb[y, x0:x1] * (1 - a) + sun_col * a
    # gentle wave lines
    for y in range(hz + 3, h, 4):
        rgb[y] = rgb[y] * 0.9
    rgb[hz - 1:hz + 1] = rgb[hz - 1:hz + 1] * 0.85 + 30
    img = Image.fromarray(np.uint8(np.clip(rgb, 0, 255)), 'RGB')
    return img.filter(ImageFilter.GaussianBlur(0.7))


def moon_scene(age_days, w=304, h=124):
    """The real Moon (photo) shaded to today's phase, on a night sky."""
    rgb = _stars(_vgrad(w, h, [(0, (2, 4, 26)), (1, (12, 20, 70))]), 70, 11)
    R = int(h * 0.40)
    tex = np.asarray(Image.open(os.path.join(BASE, 'moon-full.jpg')).convert('RGB').resize((2 * R, 2 * R), Image.LANCZOS), float)
    y, x = np.mgrid[-R:R, -R:R] + 0.5
    x, y = x / R, y / R
    inside = x * x + y * y <= 1
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    th = 2 * math.pi * age_days / 29.530588853           # 0 new, pi full; waxing lit on the right (northern sky)
    lit = x * math.sin(th) - z * math.cos(th)
    shade = np.clip(lit * 6 + 0.5, 0, 1)                  # soft terminator
    shade = 0.035 + 0.965 * shade                         # faint earthshine on the dark side
    moon = tex * shade[..., None]
    cx, cy = w // 2, h // 2
    patch = rgb[cy - R:cy + R, cx - R:cx + R]
    edge = np.clip((1 - np.sqrt(x * x + y * y)) * R, 0, 1)[..., None]  # anti-aliased rim
    patch[:] = patch * (1 - edge) + moon * edge
    return Image.fromarray(np.uint8(np.clip(rgb, 0, 255)), 'RGB')


def jpeg_b64(img, q=86):
    import base64
    import io
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=q, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def moon_phase(when):
    age = ((when - dt.datetime(2000, 1, 6, 18, 14, tzinfo=UTC)).total_seconds() / 86400) % 29.530588853
    illum = round(50 * (1 - math.cos(2 * math.pi * age / 29.530588853)))
    names = [(1.85, 'moon-new', 'New moon'), (5.54, 'moon-waxing-crescent', 'Waxing crescent'),
             (9.23, 'moon-first-quarter', 'First quarter'), (12.92, 'moon-waxing-gibbous', 'Waxing gibbous'),
             (16.61, 'moon-full', 'Full moon'), (20.30, 'moon-waning-gibbous', 'Waning gibbous'),
             (23.99, 'moon-last-quarter', 'Last quarter'), (27.68, 'moon-waning-crescent', 'Waning crescent'),
             (29.6, 'moon-new', 'New moon')]
    icon, name = next((i, n) for lim, i, n in names if age < lim)
    waxing = age < 29.530588853 / 2           # name by how much is lit, so the words match the picture
    name = ('New moon' if illum < 3 else 'Full moon' if illum > 97 else
            ('First quarter' if waxing else 'Last quarter') if 47 <= illum <= 53 else
            ('Waxing ' if waxing else 'Waning ') + ('crescent' if illum < 47 else 'gibbous'))
    return icon, name, illum, age


def panel_svg(path, img, now, dec, slon):
    """Grey-line panel with sun and moon details, same size as the other panels."""
    import base64
    import html
    import io
    sys.path.insert(0, HERE)
    from weather import PANEL_W, PANEL_H
    W, H = PANEL_W, PANEL_H
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=84, optimize=True, progressive=True)
    jpg = base64.b64encode(buf.getvalue()).decode()
    local = now.astimezone(TZ)
    t = lambda x, y, s, size=13, fill='#e9eaf5', anchor='middle', weight='normal', extra='': (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}"{extra}>{html.escape(str(s))}</text>')
    rise, sett = crossings(local, -0.833)
    dawn, _ = crossings(local, -6)
    _, dusk = crossings(local, -6)
    micon, mname, illum, age = moon_phase(now)
    hm = lambda x: f'{x:%H:%M}' if x else '\u2014'
    utc = lambda x: f'{x.astimezone(UTC):%H:%M} UTC' if x else ''
    body = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="#000030" stroke="#31336e"/>',
            t(24, 30, 'GREY LINE \u00b7 DAY & NIGHT', 11, '#17f9da', 'start', extra=' letter-spacing="3.5"'),
            t(24, 46, f'{now:%d %b %Y %H:%M} UTC \u00b7 {local:%H:%M} Bahrain \u00b7 sun overhead {abs(dec):.1f}\u00b0{"N" if dec >= 0 else "S"} {abs(slon):.1f}\u00b0{"E" if slon >= 0 else "W"}',
              10.5, '#a9abd0', 'start'),
            '<clipPath id="mapclip"><rect x="12" y="56" width="616" height="308" rx="10"/></clipPath>',
            f'<image x="12" y="56" width="616" height="308" preserveAspectRatio="none" clip-path="url(#mapclip)" href="data:image/jpeg;base64,{jpg}"/>']
    tiles = [(sky_scene('sunrise'), 'SUNRISE', hm(rise) + ' AST', utc(rise)),
             (sky_scene('sunset'), 'SUNSET', hm(sett) + ' AST', utc(sett)),
             (sky_scene('twilight'), 'GREY LINE AT BAHRAIN', f'{hm(dawn)}\u2013{hm(rise)}  \u00b7  {hm(sett)}\u2013{hm(dusk)}', 'dawn and dusk twilight, AST'),
             (moon_scene(age), 'MOON', mname, f'{illum}% illuminated')]
    tw = (W - 24) / 4
    for k, (pic, name, value, note) in enumerate(tiles):
        x0 = 12 + tw * k
        cx = x0 + tw / 2
        body.append(f'<clipPath id="tile{k}"><rect x="{x0 + 3:.1f}" y="374" width="{tw - 6:.1f}" height="124" rx="10"/></clipPath>')
        body.append(f'<rect x="{x0 + 3:.1f}" y="374" width="{tw - 6:.1f}" height="124" rx="10" fill="#151541"/>')
        body.append(f'<image x="{x0 + 3:.1f}" y="374" width="{tw - 6:.1f}" height="62" preserveAspectRatio="xMidYMid slice" '
                    f'clip-path="url(#tile{k})" href="data:image/jpeg;base64,{jpeg_b64(pic)}"/>')
        body.append(f'<rect x="{x0 + 3:.1f}" y="374" width="{tw - 6:.1f}" height="124" rx="10" fill="none" stroke="#31336e"/>')
        body.append(t(cx, 452, name, 9, '#a9abd0', extra=' letter-spacing="1"'))
        body.append(t(cx, 472, value, 15 if len(value) < 14 else 11.5, '#ffffff', weight='bold'))
        body.append(t(cx, 490, note, 9.5, '#7f82b0'))
    body.append(t(W / 2, H - 22, f'Calculated for the Diyar Al Muharraq area \u00b7 updated {local:%H:%M} AST \u00b7 reload for the latest', 10.5, '#a9abd0'))
    body.append(t(W / 2, H - 8, 'Earth: NASA Blue & Black Marble (public domain) \u00b7 Moon photo: Gregory H. Revera (CC BY-SA 3.0)', 9.5, '#7f82b0'))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Segoe UI, Arial, Helvetica, sans-serif">'
           + '\n'.join(body) + '</svg>\n')
    open(path, 'w').write(svg)
    print('wrote', path, len(svg), 'bytes', mname, illum, hm(rise), hm(sett))


def unavailable(path, title, why):
    img = Image.new('RGB', (1280, 952), PANEL)
    d = ImageDraw.Draw(img)
    d.text((640, 300), 'Unavailable', font=font(44, True), fill=MUTED, anchor='mm')
    d.text((640, 364), why[:90], font=font(22), fill=MUTED, anchor='mm')
    frame(img, title, 'No data this hour', 'The map will return at the next successful update', 2).convert('RGB').save(path)


if __name__ == '__main__':
    kind, out = sys.argv[1], sys.argv[2]
    try:
        gulf(out) if kind == 'gulf' else greyline(out)
    except Exception as e:
        print(kind, 'failed:', e)
        if out.endswith('.svg'):
            sys.exit(1)          # build.sh writes the SVG placeholder
        unavailable(out, 'GULF · TEMPERATURE & WIND', str(e))
