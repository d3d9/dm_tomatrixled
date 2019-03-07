# -*- coding: utf-8 -*-
import random
from rgbmatrix import graphics


def clockstr_tt(tt):
    return f"{tt.tm_hour:02}:{tt.tm_min:02}"


def colorppm(ppm, color, fromcolor=(255, 255, 255)):
    newppm = ppm.copy()
    data = newppm.load()
    for x in range(newppm.size[0]):
        for y in range(newppm.size[1]):
            if data[x, y] == fromcolor:
                data[x, y] = (color.red, color.green, color.blue)
    return newppm


def drawppm_topcentered(canvas, ppm, cx, ty, unsafe=True, transp=False):
    halfwidth = ppm.size[0]//2
    canvas.SetImage(ppm, cx-halfwidth, ty, unsafe, transp)
    return cx+halfwidth


def drawppm_centered(canvas, ppm, cx, cy, unsafe=True, transp=False):
    halfwidth = ppm.size[0]//2
    canvas.SetImage(ppm, cx-halfwidth, cy-ppm.size[1]//2, unsafe, transp)
    return cx+halfwidth


def drawppm_bottomleft(canvas, ppm, lx, by, unsafe=True, transp=False):
    canvas.SetImage(ppm, lx, by-ppm.size[1], unsafe, transp)
    return lx+ppm.size[0]


def drawppm_bottomright(canvas, ppm, rx, by, unsafe=True, transp=False):
    canvas.SetImage(ppm, rx+1-ppm.size[0], by-ppm.size[1], unsafe, transp)
    return rx+1


def drawsecpixels(canvas, coords, sec, maincolor, addcolor=None, offcolor=graphics.Color()):
    if addcolor is None:
        addcolor = maincolor
    groups = len(coords)
    groupsecs = 60 / groups
    for _i, (x, y) in enumerate(coords):
        spos = sec // groupsecs
        if _i == spos:
            vm = (sec % groupsecs)/groupsecs
            _r, _g, _b = int(vm*addcolor.red), int(vm*addcolor.green), int(vm*addcolor.blue)
        else:
            _c = maincolor if _i < spos else offcolor
            _r, _g, _b = _c.red, _c.green, _c.blue
        canvas.SetPixel(x, y, _r, _g, _b)


def drawverticaltime(canvas, font, x, y, color, hour, minute, sec=None, sec_mainc=None, sec_addc=None, sec_offc=graphics.Color()):
    y = 1 + graphics.VerticalDrawText(canvas, font, x, y, color, f"{hour:02}")
    if sec is not None:
        drawsecpixels(canvas, ((x+2,y), (x+2,y+1), (x+1,y+1), (x+1,y)), sec, maincolor=(sec_mainc or color), addcolor=sec_addc, offcolor=sec_offc)
    y += 1 + font.height + 1
    y += graphics.VerticalDrawText(canvas, font, x, y, color, f"{minute:02}")


def makechristmasfn(maxrgb, randspeed, ptrgb, ptspeed, ptlen, ptscale):
    def drawchristmas(canvas, x_min, x_max, y_min, y_max, i):
        l = x_max+1-x_min
        bbness = 1
        if ptspeed:
            pt = x_min+((i//ptspeed)%(x_max-x_min))
            # canvas.SetPixel(pt, y_max-4, 255, 255, 255)
        if randspeed:
            random.seed(i//randspeed)
        for x in range(x_min, x_max+1):
            if ptspeed and ptscale:
                dist = abs(x-pt)
                bbness = (min(dist/l, (l-dist)/l))*ptscale
                bbness = max(0, min(bbness, 1))
            rv, gv, bv = (maxrgb[_]*bbness*((not randspeed) or random.triangular(0.2, 1, 0.6)) for _ in (0, 1, 2))
            # % usw.. anpassen/?
            canvas.SetPixel(x, y_min+x%2, rv*bool(x%5), gv*(not x%3), bv*(not x%5))
            canvas.SetPixel(x_min+x_max-x, y_max-x%2, rv*bool(x%5), gv*(not x%3), bv*(not x%5))
        if ptspeed:
            tmp = l-(l%2)  # ?
            for x in range(pt-ptlen, pt+ptlen+1):
                canvas.SetPixel(x_min+x%(tmp), y_min, ptrgb[0]*bool(x%2), ptrgb[1]*bool(x%2), ptrgb[2]*bool(x%2))
                canvas.SetPixel(x_min+x%(tmp), y_min+1, ptrgb[0]*(not x%2), ptrgb[1]*(not x%2), ptrgb[2]*(not x%2))
                canvas.SetPixel(x_min+(x_max-x)%(tmp), y_max-1, ptrgb[0]*bool(x%2), ptrgb[1]*bool(x%2), ptrgb[2]*bool(x%2))
                canvas.SetPixel(x_min+(x_max-x)%(tmp), y_max, ptrgb[0]*(not x%2), ptrgb[1]*(not x%2), ptrgb[2]*(not x%2))
    return drawchristmas
