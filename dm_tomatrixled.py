#!/usr/bin/env python3.7
# -*- coding: utf-8 -*-
from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
# from subprocess import check_output
from sys import stderr
from time import localtime, sleep  # , monotonic
from typing import List, Tuple, Dict, Callable, Any, Iterable

from loguru import logger
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

from dm_drawstuff import clockstr_tt, colorppm, drawppm_centered, drawppm_bottomleft, drawppm_bottomright, drawverticaltime, makechristmasfn
from dm_areas import rightbar_wide, rightbar_tmp, rightbar_verticalclock, startscreen
from dm_lines import MultisymbolScrollline, SimpleScrollline, propscroll, textpx, fittext
from dm_depdata import Departure, Meldung, MOT, linenumpattern, GetdepsEndAll, type_depfnlist, type_depfns, getdeps, getefadeps, getdbrestdeps, getd3d9msgdata


### Logging

datafilelog = False
logger.remove(0)
logger.add(sink=stderr, level="TRACE", backtrace=False, enqueue=True)
logger.add(sink="./log/log.txt", level="DEBUG", backtrace=False, enqueue=True)
if datafilelog:
    logger.add(sink="./log/data.txt", level="TRACE", backtrace=False, enqueue=True, compression="gz", rotation="50 MB", filter=lambda r: r["level"] == "TRACE")

### Arguments

parser = ArgumentParser()
parser.add_argument("-s", "--stop-ifopt", action="store", help="IFOPT reference of stop or area or platform. Default: de:05914:2114:0:1", default="de:05914:2114:0:1", type=str)
parser.add_argument("--ibnr", action="store", help="IBNR. With this set, there will be train data only from DB and others only from EFA. (temporary parameter)", default="", type=str)
parser.add_argument("--test-d3d9", action="store", help="Try to get data from d3d9.xyz like messages, brightness (test)", default="", type=str)
parser.add_argument("-e", "--enable-efamessages", action="store_true", help="Enable line messages. (still overwritten by -m option)")
parser.add_argument("-m", "--message", action="store", help="Message to scroll at the bottom. Default: none", default="", type=str)
parser.add_argument("-r", "--rightbar", action="store", help="Enable sidebar on the right side with additional info. Disables header clock. Value: type of rightbar (1: vertical clock (default if just -r); 2: clock with icon, wide; 3: clock with progress, VRR icon, allows scrolling through it", nargs="?", const=1, default=0, type=int)
parser.add_argument("-t", "--enable-top", action="store_true", help="Enable header with stop name and current time")
parser.add_argument("-p", "--proportional", action="store_true", help="Use proportional font")
parser.add_argument("-n", "--show-zero", action="store_false", help="Show a zero instead of a bus when countdown is 0")
parser.add_argument("-d", "--daemon", action="store_true", help="Run as daemon")
parser.add_argument("-l", "--line-height", action="store", help="Departure line height. Default: 8", default=8, type=int)
parser.add_argument("-f", "--firstrow-y", action="store", help="(text_startr) Where to start with the rows vertically (bottom pixel). Default: 6", default=6, type=int)
parser.add_argument("-w", "--linenum-width", action="store", help="pixels for line number. Default: 20", default=20, type=int)
parser.add_argument("--platform-width", action="store", help="pixels for platform, 0 to disable. Default: 0", default=0, type=int)
parser.add_argument("--place-string", action="append", help="Strings that are usually at the beginning of stop names, to be filtered out (for example (default:) \"Hagen \", \"HA-\")", default=[], type=str, dest="place_strings")
parser.add_argument("--ignore-infotype", action="append", help="EFA: ignore this 'infoType' (can be used multiple times)", default=[], type=str)
parser.add_argument("--ignore-infoid", action="append", help="EFA: ignore this 'infoID' (can be used multiple times)", default=[], type=str)
parser.add_argument("--no-rt-msg", action="store", help="Show warning if no realtime departures are returned, value of this parameter is the maximum countdown up to which one would usually expect a RT departure. Default: 20", default=20, type=int)
parser.add_argument("--show-start", action="store_true", help="Show startscreen with IFOPT and IP")
parser.add_argument("--disable-mintext", action="store_false", help="Don't show \"min\" after the countdown & a larger bus")
parser.add_argument("--min-delay", action="store", help="Minimum minutes of delay for the time to be shown in red color. 1-99. Default: 4", default=4, choices=range(1, 100), type=int)
parser.add_argument("--min-slightdelay", action="store", help="Minimum minutes of delay for the time to be shown in yellow color (set to same as --min-delay to ignore). 1-99. Default: 2", default=2, choices=range(1, 100), type=int)
parser.add_argument("--max-minutes", action="store", help="Maximum countdown minutes to show time in minutes instead of absolute time. -1-99. Default: 59", default=59, choices=range(-1, 100), type=int)
parser.add_argument("--disable-blink", action="store_false", help="Disable blinking of bus/zero when countdown is 0")
parser.add_argument("--stop-name", action="store", help="Override header (-t) stop name returned by the API. Default: none", default="", type=str)
parser.add_argument("--christmas", action="store_true", help="green/red lights at top and bottom (height 2), test")
parser.add_argument("--show-progress", action="store_true", help="Show progress bar at the bottom")
parser.add_argument("--disable-topscroll", action="store_false", help="Disable scrolling of stop name in the header (-t)")
parser.add_argument("--small", action="store_true", help="enable --small-text, --small-countdown, --small-linenum.")
# small_text doch aufteilen? small_auto hinzufuegen?
parser.add_argument("--small-text", action="store_true", help="Show destination, stop name, message with smaller letters")
parser.add_argument("--small-countdown", action="store_true", help="Show countdown with smaller numbers")
parser.add_argument("--small-linenum", action="store_true", help="Show line number with smaller characters")
parser.add_argument("--update-steps", action="store", help="Loop steps until reload of data. Default: 600", default=600, type=int)
parser.add_argument("--sleep-interval", action="store", help="Sleep interval (inside the main loop). Default: 0.03", default=0.03, type=float)
parser.add_argument("--limit-multiplier", action="store", help="How many extra departures (value * actual limit) to load (useful for stops with a lot of departures where a few delays might \"hide\" earlier departures. Default: 3", default=3, type=int)
# matrix settings
parser.add_argument("-c", "--led-chain", action="store", help="Daisy-chained boards. Default: 2.", default=2, type=int)
parser.add_argument("-b", "--led-brightness", action="store", help="Sets brightness level. Default: 30. Range: 1..100", default=30, type=int)
parser.add_argument("--write-ppm", action="store", help="Write binary ppm to given file name every loop", default="", type=str)
parser.add_argument("--led-rows", action="store", help="Display rows. 16 for 16x32, 32 for 32x32. Default: 32", default=32, type=int)
parser.add_argument("--led-cols", action="store", help="Panel columns. Typically 32 or 64. (Default: 64)", default=64, type=int)
parser.add_argument("--led-parallel", action="store", help="For Plus-models or RPi2: parallel chains. 1..3. Default: 1", default=1, type=int)
parser.add_argument("--led-pwm-bits", action="store", help="Bits used for PWM. Something between 1..11. Default: 11", default=11, type=int)
parser.add_argument("--led-gpio-mapping", help="Hardware Mapping: regular, adafruit-hat, adafruit-hat-pwm", choices=['regular', 'adafruit-hat', 'adafruit-hat-pwm'], type=str)
parser.add_argument("--led-scan-mode", action="store", help="Progressive or interlaced scan. 0 Progressive, 1 Interlaced (default)", default=1, choices=range(2), type=int)
parser.add_argument("--led-pwm-lsb-nanoseconds", action="store", help="Base time-unit for the on-time in the lowest significant bit in nanoseconds. Default: 130", default=130, type=int)
parser.add_argument("--led-show-refresh", action="store_true", help="Shows the current refresh rate of the LED panel")
parser.add_argument("--led-slowdown-gpio", action="store", help="Slow down writing to GPIO. Range: 1..100. Default: 1", choices=range(3), type=int)
parser.add_argument("--led-no-hardware-pulse", action="store", help="Don't use hardware pin-pulse generation")
parser.add_argument("--led-rgb-sequence", action="store", help="Switch if your matrix has led colors swapped. Default: RGB", default="RGB", type=str)
parser.add_argument("--led-pixel-mapper", action="store", help="Apply pixel mappers. e.g \"Rotate:90\"", default="", type=str)
parser.add_argument("--led-row-addr-type", action="store", help="0 = default; 1=AB-addressed panels;2=row direct", default=0, type=int, choices=[0, 1, 2])
parser.add_argument("--led-multiplexing", action="store", help="Multiplexing type: 0=direct; 1=strip; 2=checker; 3=spiral; 4=ZStripe; 5=ZnMirrorZStripe; 6=coreman; 7=Kaler2Scan; 8=ZStripeUneven (Default: 0)", default=0, type=int)

args = parser.parse_args()

options = RGBMatrixOptions()
if args.led_gpio_mapping is not None:
    options.hardware_mapping = args.led_gpio_mapping
options.rows = args.led_rows
options.cols = args.led_cols
options.chain_length = args.led_chain
options.parallel = args.led_parallel
options.row_address_type = args.led_row_addr_type
options.multiplexing = args.led_multiplexing
options.pwm_bits = args.led_pwm_bits
options.brightness = args.led_brightness
options.pwm_lsb_nanoseconds = args.led_pwm_lsb_nanoseconds
options.led_rgb_sequence = args.led_rgb_sequence
options.pixel_mapper_config = args.led_pixel_mapper
if args.led_show_refresh:
    options.show_refresh_rate = 1
if args.led_slowdown_gpio is not None:
    options.gpio_slowdown = args.led_slowdown_gpio
if args.led_no_hardware_pulse:
    options.disable_hardware_pulsing = True
options.daemon = args.daemon
options.drop_privileges = 0

writeppm = bool(args.write_ppm)
ppmfile = args.write_ppm
options.pixelsvector = writeppm

gpiotest = False
gpiotest_minb = 10
gpiotest_maxb = 65

if gpiotest:
    available_inputs = matrix.GPIORequestInputs(0xffffffff)

### Fonts

fontdir = "./bdf/"
fontmin = graphics.Font()
fontmin.LoadFont(fontdir+"tom-thumb.bdf")
fontnum = graphics.Font()
fontnum.LoadFont(fontdir+"4x6.bdf")
fontlargernum = graphics.Font()
fontlargernum.LoadFont(fontdir+"5x7-mod.bdf")
propfont = graphics.Font()
propfont.LoadFont(fontdir+"uwe_prop_mod.bdf")
proptest = args.proportional

if args.small or args.small_text:
    fonttext = fontnum
else:
    if proptest:
        fonttext = propfont
    else:
        fonttext = fontlargernum

if args.small or args.small_countdown:
    fontcountdown = fontnum
else:
    if proptest:
        fontcountdown = propfont
    else:
        fontcountdown = fontlargernum

if args.small or args.small_linenum:
    fontlinenum = fontnum
else:
    if proptest:
        fontlinenum = propfont
    else:
        fontlinenum = fontlargernum

### Colors

# matrixbgColor_t = (0, 16, 19)
matrixbgColor_t = None
textColor = graphics.Color(255, 65, 0)
texthighlightColor = graphics.Color(255, 20, 0)
rtnoColor = graphics.Color(190, 190, 190)
rtColor = graphics.Color(0, 255, 0)
rtslightColor = graphics.Color(255, 255, 0)
rtlateColor = graphics.Color(255, 0, 0)
rtnegativeColor = graphics.Color(0, 255, 255)
lighttextColor = graphics.Color(100, 100, 100)
barColor = graphics.Color(8, 8, 8)
if options.brightness < 15:
    linebgColor = graphics.Color(0, 12, 12)
    barColor = graphics.Color(12, 12, 12)
else:
    linebgColor = graphics.Color(0, 8, 9)
linefgColor = textColor

### linenum

linenum_width = args.linenum_width
linenumheight = fontlinenum.height - 1
linenum_normalsmalloffset = 1  # in zukunft einfach nur vertikal zentrieren?
linenum_drawbg = True
linenum_retext_1 = lambda _s: _s.group(1)+_s.group(2)
linenum_retext_2 = lambda _s: _s.group(1)

### PPM

ppmdir = "./ppm/"
ppm_info = Image.open(ppmdir+"icon-info.ppm")
ppm_warn = Image.open(ppmdir+"icon-warn.ppm")
ppm_stop = Image.open(ppmdir+"icon-stop.ppm")
ppm_smile = Image.open(ppmdir+"icon-smile.ppm")
ppm_ad = Image.open(ppmdir+"icon-ad.ppm")
ppm_delay = Image.open(ppmdir+"icon-delay.ppm")
ppm_earlyterm = Image.open(ppmdir+"icon-earlyterm.ppm")
ppm_no_rt = Image.open(ppmdir+"icon-no-rt.ppm")
ppm_no_deps = Image.open(ppmdir+"icon-no-deps.ppm")

meldungicons = {"info": ppm_info,
                "warn": ppm_warn,
                "stop": ppm_stop,
                "smile": ppm_smile,
                "ad": ppm_ad,
                "delay": ppm_delay,
                "earlyterm": ppm_earlyterm,
                "nort": ppm_no_rt,
                "nodeps": ppm_no_deps,
                }

symtextoffset = fonttext.height-fonttext.baseline

'''
# erstmal nicht mehr weiter verfolgt.
nolinenumicons = False

supportedlnlhs = (6, 7)
defaultppmlnlh = 6
ppmlinenumh = linenumheight if linenumheight in supportedlnlhs else defaultppmlnlh
linenumicons = (not nolinenumicons) and linenumheight in supportedlnlhs

ppm_whiteice = Image.open(f"{ppmdir}icon-ice{ppmlinenumh}.ppm")
ppm_whiteic = Image.open(f"{ppmdir}icon-ic{ppmlinenumh}.ppm")
ppm_whitene = Image.open(f"{ppmdir}icon-ne{ppmlinenumh}.ppm")
ppm_whitenethin = Image.open(f"{ppmdir}icon-ne-thin{ppmlinenumh}.ppm")
ppm_ice = colorppm(ppm_whiteice, linefgColor)
ppm_ic = colorppm(ppm_whiteic, linefgColor)
ppm_ne = colorppm(ppm_whitene, linefgColor)
ppm_nethin = colorppm(ppm_whitenethin, linefgColor)
'''

longausfall = True
ppm_ausfall = Image.open(ppmdir+"red-ausfall"+("-long" if longausfall else "")+".ppm")

ppm_whitesofort = Image.open(ppmdir+"white-sofort.ppm")
sofort = False

minoffset = 1
ppm_whitemin = Image.open(ppmdir+"white-min.ppm")
ppmmincolordict = {}
for _color in (rtnoColor, rtColor, rtslightColor, rtlateColor, rtnegativeColor):
    ppmmincolordict[_color] = colorppm(ppm_whitemin, _color)

supportedcdlhs = (6, 7)
defaultppmcdlh = 6
ppmcdh = fontcountdown.height - 1
ppmcdh = ppmcdh if ppmcdh in supportedcdlhs else defaultppmcdlh
ppm_whitebus = Image.open(f"{ppmdir}white-bus{ppmcdh}.ppm")
ppm_whitetrain = Image.open(f"{ppmdir}white-train{ppmcdh}.ppm")
ppm_whitehispeed = Image.open(f"{ppmdir}white-hispeed{ppmcdh}.ppm")
ppm_whitetram = Image.open(f"{ppmdir}white-tram{ppmcdh}.ppm")
ppm_whitehanging = Image.open(f"{ppmdir}white-hanging{ppmcdh}.ppm")

if sofort:
    ppmmotdict = dict.fromkeys((MOT.BUS, MOT.TRAIN, MOT.HISPEED, MOT.TRAM, MOT.HANGING), ppm_whitesofort)
else:
    ppmmotdict = {MOT.BUS: ppm_whitebus,
                  MOT.TRAIN: ppm_whitetrain,
                  MOT.HISPEED: ppm_whitehispeed,
                  MOT.TRAM: ppm_whitetram,
                  MOT.HANGING: ppm_whitehanging,
                  }

ppmmotcolordict = dict.fromkeys(ppmmotdict.keys())

for mot, ppm in ppmmotdict.items():
    ppmmotcolordict[mot] = dict()
    for _color in (rtnoColor, rtColor, rtslightColor, rtlateColor, rtnegativeColor):
        ppmmotcolordict[mot][_color] = colorppm(ppm, _color)

ppm_vrr = Image.open("./ppm/matrix13x13vrr-engebuchstaben-2.ppm").convert('RGB')
ppm_db11 = Image.open("./ppm/dbkeks.ppm").convert('RGB')
ppm_sonne11 = Image.open("./ppm/sonne.ppm").convert('RGB')
ppm_wolke11 = Image.open("./ppm/wolke.ppm").convert('RGB')
ppm_wolkesonne11 = Image.open("./ppm/wolke mit sonne.ppm").convert('RGB')
ppm_wolkeregen11 = Image.open("./ppm/wolke mit regen.ppm").convert('RGB')

### Display configuration

lineheight = args.line_height
text_startr = args.firstrow_y

placelist = args.place_strings
if not placelist:
    placelist = ["Hagen ", "HA-"]
ifopt = args.stop_ifopt
step = args.update_steps
interval = args.sleep_interval
efamenabled = args.enable_efamessages
header = args.enable_top
headername = args.stop_name
headerscroll = args.disable_topscroll
mindelay = args.min_delay
minslightdelay = args.min_slightdelay
maxmin = args.max_minutes
mintext = args.disable_mintext
christmas = args.christmas
progress = args.show_progress
blink = args.disable_blink
zerobus = args.show_zero
# zur config (und alles andere eigentlich auch):
stopsymbol = True
melsymbol = True

platformwidth = args.platform_width

rightbar = bool(args.rightbar)
rightbarcolor = rtnoColor
scrollmsg_through_rightbar = False
rightbarargs: Iterable

if args.rightbar == 1:
    rightbarfn, rightbarwidth, rightbarargs, rightbarfont = rightbar_verticalclock, 6, (True,), fontlargernum
elif args.rightbar in {2, 3}:
    currenttime = localtime()
    rightbarfont = fonttext
    rightbarwidth = textpx(rightbarfont, clockstr_tt(currenttime))  # muss eigentlich laufend angepasst werden
    if args.rightbar == 2:
        rightbarfn = rightbar_wide
        rightbarargs = ((ppm_vrr, ppm_vrr, ppm_vrr, ppm_sonne11, ppm_wolkesonne11, ppm_wolke11, ppm_wolkeregen11, ppm_db11),)
    elif args.rightbar == 3:
        rightbarfn = rightbar_tmp
        _width = args.led_cols*args.led_chain
        # r_scroller = SimpleScrollline(_width-rightbarwidth, _width-1, symtextoffset, fonttext, lighttextColor)
        # r_scroller.update(None, "Fahrplanauskünfte werden durch den Lizenzgeber zur Verfügung gestellt. Alle Angaben ohne Gewähr.")
        rightbarargs = (ppm_vrr, graphics.Color(50, 50, 50))  # , r_scroller)
        scrollmsg_through_rightbar = True

# Abstand Ziel - Zeit
spacedt = 1
# Abstand Liniennummer - Ziel
spaceld = 2
# Abstand Zeit - Steig (falls platformwidth > 0)
spacetp = 1
# Abstand Abfahrtsinfo (bis Zeit bzw. Steig usw.) zum rechten Bereich (Uhr, Logo, Wetter usw.)
spacetr = 1

header_spacest = 1

countdownlowerlimit = -9

min_timeout = 10
servertimeout = max(min_timeout, (interval*step)/2)
tz = datetime.utcnow().astimezone().tzinfo
maxkwaretries = 3

efaserver = 'https://openservice.vrr.de/vrr/XML_DM_REQUEST'
efaserver_backup = 'http://www.efa-bw.de/nvbw/XML_DM_REQUEST'

d3d9id = args.test_d3d9  # tmp
d3d9server = 'https://d3d9.xyz/dfi'

# z. B. Aufzugsmeldungen
# ignore_infoTypes = {"stopInfo"}
ignore_infoTypes = set(args.ignore_infotype) if args.ignore_infotype else None

# z. B. Umleitung Wetter; Ausfall Eckeseyer Br.; Sonderburgstr.:
# ignore_infoIDs = {"41354_HST", "28748_HST", "45828_HST"}
ignore_infoIDs = set(args.ignore_infoid) if args.ignore_infoid else None

content_for_short_titles = True

trainTMOTefa = {0, 1, 13, 14, 15, 16, 18}
trainMOT = {MOT.TRAIN, MOT.HISPEED}

dbrestserver = 'http://d3d9.xyz:3000'
dbrestserver_backup = 'https://2.db.transport.rest'
dbrestibnr = args.ibnr

delaymsg_enable = True
delaymsg_mindelay = 2
etermmsg_enable = True
etermmsg_only_visible = True
nortmsg_limit = args.no_rt_msg

### christmas fn

randspeed = 8
maxrgb = (130, 150, 35)
# maxrgb = (150, 150, 0)
ptspeed = 4
ptlen = 3
ptscale = 0.8
ptrgb = (77, 65, 0)
# ptrgb = (153, 130, 0)
drawchristmas = makechristmasfn(maxrgb, randspeed, ptrgb, ptspeed, ptlen, ptscale)

### End of configuration


def loop(matrix, pe):
    i = 0
    # canvas und loop setup
    canvas = matrix.CreateFrameCanvas(writeppm)
    x_min = 0
    y_min = 0
    x_max = canvas.width - 1 - (rightbar and (rightbarwidth + spacetr))
    y_max = canvas.height - 1

    linenum_min = x_min
    linenum_max = linenum_min + linenum_width - 1
    limit = (y_max - y_min + 1 - text_startr - fonttext.height + fonttext.baseline + lineheight) // lineheight
    x_pixels = x_max - x_min + 1

    currenttime = localtime()
    # xmax hier muss man eigentlich immer neu berechnen
    scrollx_stop_xmax = x_max-((not rightbar) and header_spacest+textpx(fonttext, clockstr_tt(currenttime)))
    stop_scroller = SimpleScrollline(x_min, scrollx_stop_xmax, symtextoffset, fonttext, lighttextColor, noscroll=not headerscroll)

    # tmp
    deptime_x_max = x_max

    if platformwidth:
        deptime_x_max -= (spacetp + platformwidth)

    platform_min = deptime_x_max + spacetp + 1
    platform_max = platform_min + platformwidth - 1

    deps: List[Departure] = []
    meldungs: List[Meldung] = []

    scrollx_msg_xmax = (canvas.width - 1) if scrollmsg_through_rightbar else x_max
    meldung_scroller = MultisymbolScrollline(x_min, scrollx_msg_xmax, symtextoffset, fonttext, lighttextColor, meldungicons, bgcolor_t=matrixbgColor_t, initial_pretext=2, initial_posttext=10)

    # tmp
    if args.message:
        meldungs.append(Meldung(symbol="ad", text=args.message))

    pe_f = None
    joined = True

    # "volles" Beispiel in dm_depdata.py
    depfun_efa: type_depfns = {
        ("efa-main", True): [(getefadeps, [{'serverurl': efaserver,
                                            'timeout': servertimeout,
                                            'ifopt': ifopt,
                                            'limit': limit*args.limit_multiplier,
                                            'tz': tz,
                                            'ignore_infoTypes': ignore_infoTypes,
                                            'ignore_infoIDs': ignore_infoIDs,
                                            'content_for_short_titles': content_for_short_titles,
                                           },
                                           {'serverurl': efaserver_backup,
                                            'timeout': servertimeout,
                                            'ifopt': ifopt,
                                            'limit': limit*args.limit_multiplier,
                                            'tz': tz,
                                            'ignore_infoTypes': ignore_infoTypes,
                                            'ignore_infoIDs': ignore_infoIDs,
                                            'content_for_short_titles': content_for_short_titles,
                                           },
                                          ])
                            ],
        }

    depfun_efadb: type_depfns = {
        ("efa-notr", True): [(getefadeps, [{'serverurl': efaserver,
                                            'timeout': servertimeout,
                                            'ifopt': ifopt,
                                            'limit': limit*args.limit_multiplier,
                                            'tz': tz,
                                            'exclMOT': trainTMOTefa,
                                            'ignore_infoTypes': ignore_infoTypes,
                                            'ignore_infoIDs': ignore_infoIDs,
                                            'content_for_short_titles': content_for_short_titles,
                                           },
                                           {'serverurl': efaserver_backup,
                                            'timeout': servertimeout,
                                            'ifopt': ifopt,
                                            'limit': limit*args.limit_multiplier,
                                            'tz': tz,
                                            'exclMOT': trainTMOTefa,
                                            'ignore_infoTypes': ignore_infoTypes,
                                            'ignore_infoIDs': ignore_infoIDs,
                                            'content_for_short_titles': content_for_short_titles,
                                           },
                                          ])
                            ],
        ("dbre-tr", True): [(getdbrestdeps, [{'serverurl': dbrestserver,
                                               'timeout': servertimeout,
                                               'ibnr': dbrestibnr,
                                               'limit': limit*args.limit_multiplier,
                                               'inclMOT': trainMOT,
                                             },
                                             {'serverurl': dbrestserver_backup,
                                               'timeout': servertimeout,
                                               'ibnr': dbrestibnr,
                                               'limit': limit*args.limit_multiplier,
                                               'inclMOT': trainMOT,
                                             }
                                            ]),
                            (getefadeps, [{'serverurl': efaserver,
                                           'timeout': servertimeout,
                                           'ifopt': ifopt,
                                           'limit': limit*args.limit_multiplier,
                                           'tz': tz,
                                           'inclMOT': trainTMOTefa,
                                           'ignore_infoTypes': ignore_infoTypes,
                                           'ignore_infoIDs': ignore_infoIDs,
                                           'content_for_short_titles': content_for_short_titles,
                                          },
                                          {'serverurl': efaserver_backup,
                                           'timeout': servertimeout,
                                           'ifopt': ifopt,
                                           'limit': limit*args.limit_multiplier,
                                           'tz': tz,
                                           'inclMOT': trainTMOTefa,
                                           'ignore_infoTypes': ignore_infoTypes,
                                           'ignore_infoIDs': ignore_infoIDs,
                                           'content_for_short_titles': content_for_short_titles,
                                          }
                                         ])
                           ],
        }

    depfunctions = depfun_efadb if dbrestibnr else depfun_efa
    if d3d9id:
        depfnlist_d3d9: type_depfnlist = [(getd3d9msgdata, [{'serverurl': d3d9server, 'timeout': servertimeout, 'dfi_id': d3d9id}])]
        depfunctions.update({('d3d9-m+d', False): depfnlist_d3d9})

    logger.info(f"started loop with depfunctions {', '.join(x[0] for x in depfunctions.keys())}")
    while True:
        # time_measure = monotonic()
        canvas.Fill(*matrixbgColor_t) if matrixbgColor_t else canvas.Clear()
        if joined and not i % step:
            joined = False
            pe_f = pe.submit(getdeps,
                             depfunctions=depfunctions,
                             getdeps_timezone=tz,
                             getdeps_lines=limit-header,
                             getdeps_placelist=placelist,
                             getdeps_mincountdown=countdownlowerlimit,
                             getdeps_max_retries=maxkwaretries,
                             extramsg_messageexists=bool(args.message),  # ob es *bereits* eine Meldung geben wird - aktuell nur durch args.message so.
                             delaymsg_enable=delaymsg_enable,
                             delaymsg_mindelay=delaymsg_mindelay,
                             etermmsg_enable=etermmsg_enable,
                             etermmsg_only_visible=etermmsg_only_visible,
                             nodepmsg_enable=True,
                             nortmsg_limit=nortmsg_limit)

        if pe_f.done() and not joined:
            try:
                deps, meldungs, _add_data = pe_f.result()
            except Exception as e:
                if e.__class__ != GetdepsEndAll:
                    logger.exception("exception from getdeps")
                deps = []
                meldungs = [Meldung(symbol="warn", text="Fehler bei Datenabruf. Bitte Aushangfahrpläne beachten.")]
            else:
                if args.message:
                    meldungs.append(Meldung(symbol="ad", text=args.message))
                for di, dep in enumerate(deps):
                    for _mel in dep.messages:
                        if _mel not in meldungs and ((not _mel.efa) or (efamenabled and di < limit-header-1)):
                            meldungs.append(_mel)
                _brightness = _add_data.get("brightness")
                if _brightness is not None and _brightness != matrix.brightness:
                    matrix.brightness = _brightness
            finally:
                joined = True
                meldung_scroller.update(meldungs)

        blinkstep = i % 40 < 20
        blinkon = blinkstep or not blink
        if rightbar or header:
            currenttime = localtime()
        r = y_min + text_startr

        if rightbar:
            # x_min, y_min usw. fehlen
            rightbarfn(canvas, x_max+1+spacetr, 0, rightbarwidth, rightbarfont, rightbarcolor, i, step, currenttime, *rightbarargs)

        if header:
            stop_scroller.update(ppm_stop if stopsymbol else None, headername or (deps and deps[0].stopname) or "")
            stop_scroller.render(canvas, r)

            if not rightbar:
                graphics.DrawText(canvas, fonttext, scrollx_stop_xmax+1+header_spacest, r, rtnoColor, clockstr_tt(currenttime))

            r += lineheight

        for dep in deps[:(limit-bool(meldungs)-header)]:
            if linenum_drawbg:
                for y in range(r-linenumheight, r):
                    graphics.DrawLine(canvas, linenum_min, y, linenum_max, y, linebgColor)

            _lnfont, linenumstr, linenumpx, _roff = fittext(
                dep.disp_linenum,
                linenum_width,
                linenum_min,
                linenum_max,
                fontlinenum,
                fontnum,
                smallpxoffset=linenum_normalsmalloffset,
                pattern=linenumpattern,
                alt_retext_1=linenum_retext_1,
                alt_retext_2=linenum_retext_2)
            graphics.DrawText(canvas, _lnfont, linenum_max - linenumpx + (linenumpx == linenum_width), r-_roff, linefgColor, linenumstr)

            color = rtnoColor
            if dep.realtime:
                if dep.delay >= mindelay or dep.cancelled:
                    color = rtlateColor
                elif dep.delay >= minslightdelay:
                    color = rtslightColor
                elif dep.delay < 0:
                    color = rtnegativeColor
                else:
                    color = rtColor

            direction_x = linenum_max + 1 + spaceld
            directionpixel = deptime_x_max - direction_x
            timeoffset = 0

            if dep.cancelled:
                drawppm_bottomright(canvas, ppm_ausfall, deptime_x_max, r, transp=True)
                timeoffset += ppm_ausfall.size[0]
            elif dep.disp_countdown > maxmin:
                timestr = clockstr_tt(dep.deptime.timetuple())
                timestrpx = textpx(fontcountdown, timestr)
                graphics.DrawText(canvas, fontcountdown, deptime_x_max - timestrpx + 1, r, color, timestr)
                timeoffset += timestrpx
            elif blinkon and dep.disp_countdown == 0 and zerobus:
                drawppm_bottomright(canvas, ppmmotcolordict[dep.mot][color], deptime_x_max, r, transp=True)
                timeoffset += ppmmotdict[dep.mot].size[0]
            elif dep.disp_countdown or blinkon:
                timestr = str(dep.disp_countdown)
                timestrpx = textpx(fontcountdown, timestr)
                graphics.DrawText(canvas, fontcountdown, deptime_x_max - timestrpx - ((ppm_whitemin.size[0]-1+minoffset) if mintext else -1), r, color, timestr)
                timeoffset += timestrpx
                if mintext:
                    drawppm_bottomright(canvas, ppmmincolordict[color], deptime_x_max, r, transp=True)
                    timeoffset += ppm_whitemin.size[0] + minoffset

            if platformwidth > 0 and dep.platformno:
                platprefix = dep.platformtype or ("Gl." if dep.mot in trainMOT else "Bstg.")
                _platfont, platstr, platpx, _roff = fittext(
                    platprefix + str(dep.platformno),
                    platformwidth,
                    platform_min,
                    platform_max,
                    fontcountdown,
                    fontnum,
                    smallpxoffset=linenum_normalsmalloffset,
                    alt_text=str(dep.platformno))
                platformchanged = dep.platformno_planned and (dep.platformno_planned != dep.platformno)
                graphics.DrawText(canvas, _platfont, platform_max - platpx + 1, r-_roff, texthighlightColor if platformchanged else textColor, platstr)

            # erweiterbar
            if dep.earlytermination:
                dirtextcolor = texthighlightColor
            else:
                dirtextcolor = textColor

            directionpixel -= (timeoffset + spacedt*bool(timeoffset))
            directionlimit = propscroll(fonttext, dep.disp_direction, direction_x, direction_x+directionpixel)
            graphics.DrawText(canvas, fonttext, direction_x, r, dirtextcolor, dep.disp_direction[:directionlimit])

            r += lineheight

        if meldungs:
            meldung_scroller.render(canvas, r)
            r += lineheight

        if progress:
            x_progress = int(x_pixels-1 - ((i % step)*((x_pixels-1)/step)))
            graphics.DrawLine(canvas, x_min, y_max, x_min+x_progress, y_max, barColor)

        if christmas:
            drawchristmas(canvas, x_min, x_max, y_min, y_max, i)

        if writeppm:
            canvas.ppm(ppmfile)

        canvas = matrix.SwapOnVSync(canvas)

        if gpiotest:
            inputs = matrix.AwaitInputChange(0)
            if inputs & (1 << 21):
                # check_output(["/sbin/shutdown", "now"])
                matrix.brightness = ((matrix.brightness - gpiotest_minb + 1) % (gpiotest_maxb - gpiotest_minb + 1)) + gpiotest_minb

        # _st = interval-monotonic()+time_measure
        # if _st > 0:
        #     sleep(_st)
        if interval > 0:
            sleep(interval)
        i += 1


if __name__ == "__main__":
    logger.info("started")
    matrix = RGBMatrix(options=options)
    if args.show_start:
        startcanvas = matrix.CreateFrameCanvas(writeppm)
        startscreen(startcanvas, fontnum, lighttextColor, ifopt, ppm_smile)
        matrix.SwapOnVSync(startcanvas)
        sleep(5)
    while True:
        try:
            with ProcessPoolExecutor(max_workers=1) as ppe:
                loop(matrix, ppe)
        except KeyboardInterrupt:
            break
        except Exception:
            logger.opt(exception=True).critical("exception in loop or module")
    logger.info("exiting")
