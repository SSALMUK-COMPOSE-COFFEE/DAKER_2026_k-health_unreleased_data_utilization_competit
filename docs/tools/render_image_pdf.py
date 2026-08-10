import re, zlib, struct, sys, pathlib

PDF = sys.argv[1]
OUT = sys.argv[2]
S = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0

b = pathlib.Path(PDF).read_bytes()

# ---- index objects: num -> (dictbytes, streambytes)
objs = {}
for m in re.finditer(rb'(?<![0-9])(\d+)\s+0\s+obj\b', b):
    num = int(m.group(1))
    start = m.end()
    end = b.find(b'endobj', start)
    body = b[start:end]
    sm = re.search(rb'stream\r?\n', body)
    if sm:
        d = body[:sm.start()]
        e = body.find(b'endstream', sm.end())
        st = body[sm.end():e]
    else:
        d, st = body, None
    objs[num] = (d, st)

def val(d, key, default=None):
    m = re.search(re.escape(key) + rb'\s*(/?[A-Za-z0-9.\-]+)', d)
    return m.group(1) if m else default

def ref(d, key):
    m = re.search(re.escape(key) + rb'\s+(\d+)\s+0\s+R', d)
    return int(m.group(1)) if m else None

def decomp(d, st):
    if st is None: return None
    if b'FlateDecode' in d:
        try: return zlib.decompress(st)
        except Exception:
            try: return zlib.decompressobj().decompress(st)
            except Exception: return None
    return st

def gray_of(num):
    """return (w,h,bytearray of 0..255 luminance) for an image xobject, or None"""
    if num not in objs: return None
    d, st = objs[num]
    w = val(d, b'/Width'); h = val(d, b'/Height')
    if not w or not h: return None
    w, h = int(w), int(h)
    bpc = int(val(d, b'/BitsPerComponent', b'8'))
    data = decomp(d, st)
    if data is None: return None
    if b'/DeviceRGB' in d and bpc == 8:
        need = w*h*3
        if len(data) < need: return None
        out = bytearray(w*h)
        for i in range(w*h):
            j = i*3
            out[i] = (data[j]*299 + data[j+1]*587 + data[j+2]*114)//1000
        return (w, h, out)
    if bpc == 1:
        rb_ = (w + 7)//8
        if len(data) < rb_*h: return None
        out = bytearray(w*h)
        for y in range(h):
            base = y*rb_; o = y*w
            for x in range(w):
                bit = (data[base + (x >> 3)] >> (7 - (x & 7))) & 1
                out[o+x] = 255 if bit else 0
        return (w, h, out)
    if bpc == 8:
        need = w*h
        if len(data) < need: return None
        return (w, h, bytearray(data[:need]))
    return None

# ---- pages
pages = []
for num, (d, st) in objs.items():
    if re.search(rb'/Type\s*/Page[^s]', d):
        pages.append(num)
pages.sort()

def resources_xobj(d):
    """map name -> objnum from /Resources ... /XObject << ... >>"""
    rnum = ref(d, b'/Resources')
    rd = objs[rnum][0] if rnum is not None else d
    xnum = ref(rd, b'/XObject')
    if xnum is not None:
        xd = objs[xnum][0]
    else:
        m = re.search(rb'/XObject\s*<<(.*?)>>', rd, re.S)
        if not m: return {}
        xd = m.group(1)
    return {n.decode(): int(o) for n, o in re.findall(rb'/([A-Za-z0-9_.\-]+)\s+(\d+)\s+0\s+R', xd)}

PW, PH = 540.0, 780.0
CW, CH = int(PW*S), int(PH*S)

for pi, pnum in enumerate(pages, 1):
    d, _ = objs[pnum]
    xmap = resources_xobj(d)
    cnum = ref(d, b'/Contents')
    content = b''
    if cnum is not None and cnum in objs:
        content = decomp(*objs[cnum]) or b''
    canvas = bytearray(b'\xff' * (CW*CH))

    ctm = [1, 0, 0, 1, 0, 0]
    stack = []
    tok = re.compile(rb'(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+cm|/([A-Za-z0-9_.\-]+)\s+Do|(\bq\b)|(\bQ\b)')
    placed = 0
    for m in tok.finditer(content):
        if m.group(8):
            stack.append(list(ctm)); continue
        if m.group(9):
            if stack: ctm = stack.pop()
            continue
        if m.group(1):
            ctm = [float(m.group(i)) for i in range(1, 7)]
            continue
        name = m.group(7).decode()
        if name not in xmap: continue
        onum = xmap[name]
        od = objs.get(onum, (b'', None))[0]
        if b'/Image' not in od: continue
        sm = ref(od, b'/SMask')
        src = gray_of(sm) if sm is not None else gray_of(onum)
        if src is None: continue
        iw, ih, pix = src
        use_alpha = sm is not None
        a, bb, c, dd, e, f = ctm
        x0 = e*S; y0 = (PH - (f + dd))*S
        w_px = a*S; h_px = dd*S
        if w_px <= 0 or h_px <= 0: continue
        placed += 1
        X0 = max(0, int(x0)); X1 = min(CW, int(x0 + w_px + 0.999))
        Y0 = max(0, int(y0)); Y1 = min(CH, int(y0 + h_px + 0.999))
        for Y in range(Y0, Y1):
            sy = int((Y - y0) / h_px * ih)
            if sy < 0 or sy >= ih: continue
            srow = sy*iw; crow = Y*CW
            for X in range(X0, X1):
                sx = int((X - x0) / w_px * iw)
                if sx < 0 or sx >= iw: continue
                v = pix[srow + sx]
                ink = v if use_alpha else (255 - v)   # alpha: high=ink ; 1bit: 0=ink
                if ink > 40:
                    nv = 255 - ink
                    if nv < canvas[crow + X]: canvas[crow + X] = nv

    # write PNG (grayscale 8-bit)
    raw = bytearray()
    for y in range(CH):
        raw.append(0)
        raw += canvas[y*CW:(y+1)*CW]
    def chunk(t, data):
        return struct.pack('>I', len(data)) + t + data + struct.pack('>I', zlib.crc32(t + data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', CW, CH, 8, 0, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 6))
    png += chunk(b'IEND', b'')
    fn = f'{OUT}_{pi:02d}.png'
    pathlib.Path(fn).write_bytes(png)
    print(fn, 'images placed:', placed)
