#!/usr/bin/env python3
# -*- coding: utf-8 -*-

repeat = 10
spacing = 6
bgcolor_t = (8,8,8)

with open("out-orig.ppm", "rb") as f:
    b = f.read()

_firstn = b.index(b"\n")
orig_width, orig_height = map(int, b[_firstn+1:b.index(b"\n", _firstn+1)].split(b" "))
width = orig_width*repeat+orig_width*spacing
height = orig_height*repeat+orig_height*spacing

_s = b"255\n"
_p = b.index(_s) + len(_s)

tmp = bytearray()
for _i in range(orig_width*orig_height):
    start = _p + _i*3
    end = start + 3
    _bytes = b[start:end]
    tmp.extend(bytearray(bgcolor_t)*spacing)
    tmp.extend(bytearray(_bytes)*repeat)

out = bytearray()
for _w in range(height):
    start = _w*width*3
    end = start + width*3
    _lb = tmp[start:end]
    out.extend(bytearray(bgcolor_t)*(width+spacing)*spacing)
    out.extend((_lb+bytearray(bgcolor_t)*spacing)*repeat)
height += spacing
width += spacing
out.extend(bytearray(bgcolor_t)*width*spacing)

with open("out-mod.ppm", "wb") as f:
    f.write(b"P6\n"+bytes(str(width), encoding='ascii')+b" "+bytes(str(height), encoding='ascii')+b"\n255\n"+out)
