# -*- coding: utf-8 -*-
from subprocess import check_output
from RGBMatrixEmulator import graphics
from .drawstuff import clockstr_tt, drawppm_bottomleft, drawppm_topcentered, drawppm_centered, drawsecpixels, drawverticaltime
from .lines import textpx


def rightbar_wide(canvas, x, y, rightbarwidth, font, color, i, step, currenttime, ppmlist):
    timestr = clockstr_tt(currenttime)
    graphics.DrawText(canvas, font, canvas.width-rightbarwidth+(rightbarwidth-textpx(font, timestr))//2, font.baseline, color, timestr)
    # Temperatur
    # pitemp = int(Decimal(int(check_output(['cat', '/sys/class/thermal/thermal_zone0/temp']).decode('utf-8').strip())/1000).quantize(0, ROUND_HALF_UP))
    pitemp = "--"
    tempstr = str(pitemp)
    degstr = "°"
    _temppos = canvas.width-rightbarwidth+(rightbarwidth-textpx(font, tempstr))//2
    _temppos += graphics.DrawText(canvas, font, _temppos, canvas.height-1, color, tempstr)
    graphics.DrawText(canvas, font, _temppos, canvas.height-1, color, degstr)
    # Bilder
    drawppm_centered(canvas, ppmlist[int(((i % step)/step)*len(ppmlist))], canvas.width-1-rightbarwidth//2, canvas.height//2)


def rightbar_tmp(canvas, x, y, rightbarwidth, font, color, i, step, currenttime, logoppm, seccolor=None):  #, r_scroller=None):
    timestr = clockstr_tt(currenttime)
    y += font.baseline + 1
    tw = graphics.DrawText(canvas, font, canvas.width-rightbarwidth+(rightbarwidth-textpx(font, timestr))//2, y, color, timestr) - 1
    drawsecpixels(canvas, tuple((x+_,y) for _ in range(tw)), currenttime.tm_sec, seccolor or color)
    y += 2
    drawppm_topcentered(canvas, logoppm, canvas.width-1-rightbarwidth//2, y)
    # if r_scroller:
    #     r_scroller.render(canvas, canvas.height)


def rightbar_verticalclock(canvas, x, y, rightbarwidth, font, color, i, step, currenttime, showsecs):
    drawverticaltime(canvas, font, x+1, y+font.height, color, currenttime.tm_hour, currenttime.tm_min, currenttime.tm_sec if showsecs else None)


def startscreen(canvas, font, color, ifopt, ppm):
    textpos = drawppm_bottomleft(canvas, ppm, 0, 7)
    graphics.DrawText(canvas, font, textpos + 1, 6, color, "DFI")
    graphics.DrawText(canvas, font, 0, 14, color, ifopt[3:])
    ip = check_output(['hostname', '-I']).decode('utf-8').split(" ")[0].split(".")
    graphics.DrawText(canvas, font, 0, 22, color, ".".join(ip[0:2])+".")
    graphics.DrawText(canvas, font, 0, 30, color, ".".join(ip[2:4]))
