#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from argparse import ArgumentParser
import atexit
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from requests import get, post
from itertools import cycle
from json import dumps
from json import load as json_load
from subprocess import check_output
from sys import stderr, stdout
from tempfile import NamedTemporaryFile
from time import localtime, sleep  # , monotonic
from typing import List, Iterable, Tuple, Optional, NoReturn, Union, Callable, Sequence

from ansi2html import Ansi2HTMLConverter
from loguru import logger
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from rgbmatrix.core import FrameCanvas

import dm
from dm.actions import check_action
from dm.drawstuff import clockstr_tt, colorppm
from dm.areas import rightbar_wide, rightbar_tmp, rightbar_verticalclock, startscreen
from dm.lines import MultisymbolScrollline, SimpleScrollline, LinenumOptions, CountdownOptions, PlatformOptions, RealtimeColors, StandardDepartureLine, textpx
from dm.depdata import CallableWithKwargs, DataSource, Departure, Meldung, MOT, trainTMOTefa, trainMOT, linenumpattern, GetdepsEndAll, getdeps, getefadeps, getfptfrestdeps, getextmsgdata, getlocalmsg, getlocaldeps, getrssfeed, getnina, getkvbmonitor


### Arguments

parser = ArgumentParser()
parser.add_argument("-s", "--stop-ifopt", action="store", help="IFOPT reference of stop or area or platform, will be used with EFA.", default="", type=str)
parser.add_argument("--ibnr", action="store", help="IBNR. If ifopt is also set, there will be train data only from DB and others only from EFA. (temporary parameter)", default="", type=str)
parser.add_argument("--bvg-id", action="store", help="BVG station id (temporary parameter; no combination with ibnr/ifopt.)", default="", type=str)
parser.add_argument("--bvg-direction", action="store", help="BVG departures in direction (temporary parameter)", default="", type=str)
parser.add_argument("--hst-colors", action="store_true", help="Use HST (Hagen) Netz 2020 colors (temporary parameter)")

parser.add_argument("--config-system-url", action="store", help="URL of optional configuration system see dfi.d3d9.xyz", default="", type=str)
parser.add_argument("--config-system-id", action="store", help="ID of Anzeigesystem object", default=0, type=int)
parser.add_argument("--config-system-key", action="store", help="API key of Anzeigesystem object", default="", type=str)
parser.add_argument("--ext-data-url", action="store", help="URL to dfi_data endpoint of optional configuration system see dfi.d3d9.xyz", default="", type=str)
parser.add_argument("--save-msg-path", action="store", help="file path to store/load texts from ext-data as a backup option", default="./log/saved_msg.json", type=str)
parser.add_argument("--local-deps", action="store", help="file path to local csv with departures, cmdline option only applied if EFA (not DB/BVG/..) is used", default="", type=str)

parser.add_argument("-e", "--enable-efamessages", action="store_true", help="Enable line messages. (still overwritten by -m option)")
parser.add_argument("-m", "--message", action="store", help="Message to scroll at the bottom. Default: none", default="", type=str)
parser.add_argument("-r", "--rightbar", action="store", help="Enable sidebar on the right side with additional info. Disables header clock. Value: type of rightbar (1: vertical clock (default if just -r); 2: clock with icon, wide; 3: clock with progress, VRR icon, allows scrolling through it", nargs="?", const=1, default=0, type=int)
parser.add_argument("-t", "--enable-top", action="store_true", help="Enable header with stop name and current time")
parser.add_argument("--no-prop", action="store_true", help="Do not use proportional font")
parser.add_argument("-n", "--show-zero", action="store_false", help="Show a zero instead of a bus when countdown is 0")
parser.add_argument("-d", "--daemon", action="store_true", help="Run as daemon")
parser.add_argument("-l", "--line-height", action="store", help="Departure line height. Default: 8", default=8, type=int)
parser.add_argument("-f", "--firstrow-y", action="store", help="(text_startr) Where to start with the rows vertically (bottom pixel). Default: 8", default=8, type=int)
parser.add_argument("-w", "--linenum-width", action="store", help="pixels for line number. Default: 20", default=20, type=int)
parser.add_argument("--lines", action="store", help="Force specific number of lines (for example if different chain lengths are used)", type=int)
parser.add_argument("--columns", action="store", help="Departure columns per line. Default: 1", default=1, type=int)
parser.add_argument("--column-spacing", action="store", help="Space in pixels between columns. Default: 0", default=0, type=int)
parser.add_argument("--column-zigzag", action="store_true", help="Show departures in columns ordered from left->right, left->right etc. instead of top->bottom, top->bottom")
parser.add_argument("--platform-width", action="store", help="pixels for platform, 0 to disable. Default: 0", default=0, type=int)
parser.add_argument("--place-string", action="append", help="Strings that are usually at the beginning of destination names, to be filtered out (for example \"Hagen \" or \"HA-\"). Can be used multiple times.", default=[], type=str, dest="place_strings")
parser.add_argument("--keep-place-string-for", action="append", help="Do not remove --place-string texts for destinations with this text (for example \"Hagen Hauptbahnhof\"). Can be used multiple times.", default=[], type=str, dest="keep_place_strings")
parser.add_argument("--dest-replacement", action="append", help="Strings to be replaced in the destination texts, can be used for abbreviations. Use %% as separator. Format example: \"Hauptbahnhof%%Hbf.\". Can be used multiple times.", default=[], type=str, dest="dest_replacements")
parser.add_argument("--ignore-infotype", action="append", help="EFA: ignore this 'infoType' (can be used multiple times)", default=[], type=str)
parser.add_argument("--ignore-infoid", action="append", help="EFA: ignore this 'infoID' (can be used multiple times)", default=[], type=str)
parser.add_argument("--itdNoTrain-remove-dep", action="append", help="EFA: ignore departures with specific text as substring of itdNoTrain content (can be used multiple times)", default=[], type=str)
parser.add_argument("--itdNoTrain-remove-msg", action="append", help="EFA: do not output itdNoTrain content as message if specific text is substring of itdNoTrain content (can be used multiple times)", default=[], type=str)
parser.add_argument("--no-rt-msg", action="store", help="Show warning if no realtime departures are returned, value of this parameter is the maximum countdown up to which one would usually expect a RT departure. Default: 20", default=20, type=int)
parser.add_argument("--show-start", action="store_true", help="Show startscreen with IFOPT and IP")
parser.add_argument("--disable-mintext", action="store_false", help="Don't show \"min\" after the countdown & a larger bus")
parser.add_argument("--min-delay", action="store", help="Minimum minutes of delay for the time to be shown in red color. >= 1. Default: 9999", default=9999, type=int)
parser.add_argument("--min-slightdelay", action="store", help="Minimum minutes of delay for the time to be shown in yellow color (set to same as --min-delay to ignore). >= 1. Default: 2", default=2, type=int)
parser.add_argument("--min-negativedelay", action="store", help="Minimum minutes of negative delay for the time to be shown in a special color. <= -1. Default: -1", default=-1, type=int)
parser.add_argument("--max-minutes", action="store", help="Maximum countdown minutes to show time in minutes instead of absolute time. >= -1. Default: 59", default=59, type=int)
parser.add_argument("--disable-blink", action="store_false", help="Disable blinking of bus/zero when countdown is 0")
parser.add_argument("--stop-name", action="store", help="Override header (-t) stop name returned by the API. Default: none", default="", type=str)
parser.add_argument("--show-progress", action="store_true", help="Show progress bar at the bottom")
parser.add_argument("--disable-topscroll", action="store_false", help="Disable scrolling of stop name in the header (-t)")
parser.add_argument("--small", action="store_true", help="enable --small-text, --small-countdown, --small-linenum.")
# small_text doch aufteilen? small_auto hinzufuegen?
parser.add_argument("--small-linenum", action="store_true", help="Show line number with smaller characters")
parser.add_argument("--small-text", action="store_true", help="Show destination, stop name, message with smaller letters")
parser.add_argument("--small-countdown", action="store_true", help="Show countdown with smaller numbers")
parser.add_argument("--small-platform", action="store_true", help="Show platform with smaller numbers/letters")
parser.add_argument("--update-steps", action="store", help="Loop steps until reload of data. Default: 600", default=600, type=int)
parser.add_argument("--sleep-interval", action="store", help="Sleep interval (inside the main loop). Default: 0.03", default=0.03, type=float)
parser.add_argument("--limit-multiplier", action="store", help="How many extra departures (value * actual limit) to load (useful for stops with a lot of departures where a few delays might \"hide\" earlier departures. Default: 3", default=3, type=int)

parser.add_argument("--nina-url", action="store", help="NINA API dashboard base URL", default="", type=str)
parser.add_argument("--nina-ags", action="append", help="NINA API amtlicher Gemeindeschlüssel AGS (can be used multiple times)", default=[], type=str)
parser.add_argument("--nina-ignore-msgType", action="append", help="NINA API ignore this msgType (can be used multiple times)", default=[], type=str)
parser.add_argument("--nina-ignore-severity", action="append", help="NINA API ignore this severity (can be used multiple times)", default=[], type=str)
parser.add_argument("--nina-ignore-id", action="append", help="NINA API ignore this ID (can be used multiple times)", default=[], type=str)

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
parser.add_argument("--led-limit-refresh", action="store", help="Limit refresh rate to this frequency in Hz. Useful to keep a constant refresh rate on loaded system. 0=no limit. Default: 0", default=0, type=int)
parser.add_argument("--led-slowdown-gpio", action="store", help="Slow down writing to GPIO. Range: 0..4. Default: 1", default=1, type=int)
parser.add_argument("--led-no-hardware-pulse", action="store", help="Don't use hardware pin-pulse generation")
parser.add_argument("--led-rgb-sequence", action="store", help="Switch if your matrix has led colors swapped. Default: RGB", default="RGB", type=str)
parser.add_argument("--led-pixel-mapper", action="store", help="Apply pixel mappers. e.g \"Rotate:90\"", default="", type=str)
parser.add_argument("--led-row-addr-type", action="store", help="0 = default; 1=AB-addressed panels;2=row direct", default=0, type=int, choices=[0, 1, 2])
parser.add_argument("--led-multiplexing", action="store", help="Multiplexing type: 0=direct; 1=strip; 2=checker; 3=spiral; 4=ZStripe; 5=ZnMirrorZStripe; 6=coreman; 7=Kaler2Scan; 8=ZStripeUneven (Default: 0)", default=0, type=int)

args = parser.parse_args()
if args.min_delay < 1:
    parser.error("--min-delay must be >= 1")
if args.min_slightdelay < 1:
    parser.error("--min-slightdelay must be >= 1")
if args.min_negativedelay > -1:
    parser.error("--min-negativedelay must be <= -1")
if args.max_minutes < -1:
    parser.error("--max-minutes must be >= -1")

min_timeout = 10
servertimeout = max(min_timeout, (args.sleep_interval*args.update_steps)/2)

CONFIG_SYSTEM = False
SYSTEM_URL = args.config_system_url
SYSTEM_ID = args.config_system_id
SYSTEM_KEY = args.config_system_key
_required_system_args = (SYSTEM_URL, SYSTEM_ID, SYSTEM_KEY)
if any(_required_system_args) and not all(_required_system_args):
    parser.error("--config-system-url, --config-system-id, --config-system-key are all required to connect a system")
else:
    CONFIG_SYSTEM = all(_required_system_args)

_ansi_html = Ansi2HTMLConverter(inline=True)

def heartbeat_request(url, dfi_id, key, log=[], get_system_data=tuple(), loaded_data={}, going_offline=False):
    # global config_version
    payload = {"action": "dfi_heartbeat", "id": dfi_id, "key": key} #  , "config_version": dm.config.version}
    if log:
        payload["log"] = log if log == "unchanged" else  _ansi_html.convert("".join(log), full=False)
    if get_system_data:
        system_data = {}
        command = lambda input: check_output(input + " 2>/dev/null", shell=True).decode(stdout.encoding).strip()
        for key in get_system_data:
            value = None
            if key == "temperature_cpu":
                value = command("vcgencmd measure_temp | sed -e 's/temp=//'")
            elif key == "uptime":
                value = command("uptime -p | sed -e 's/up //'")
            if value is not None:
                system_data[key] = str(value)
        payload["system_data"] = dumps(system_data)
    if loaded_data:
        payload["loaded_data"] = dumps(loaded_data)
    if going_offline:
        payload["going_offline"] = 1
    r = post(url, timeout=servertimeout, data=payload)
    try:
        r.raise_for_status()
        response = r.json()
        return response
    except Exception as e:
        raise e


### Logging

datafilelog = False
logger.remove(0)
logger.add(sink=stderr, level="TRACE", backtrace=False, enqueue=True)
logger.add(sink="./log/log.txt", level="DEBUG", backtrace=False, enqueue=True)
if datafilelog:
    logger.add(sink="./log/data.txt", level="TRACE", backtrace=False, enqueue=True, compression="gz", rotation="50 MB", filter=lambda r: r["level"] == "TRACE")

limited_log_limit = 20
limited_log_level = "INFO"
limited_log = []
def add_limited_log(msg):
    global limited_log, limited_log_limit
    limited_log.append(msg)
    #limited_log = limited_log[-limited_log_limit:]
    if len(limited_log) > limited_log_limit:
        limited_log.pop(0)
logger.add(sink=add_limited_log, level=limited_log_level, colorize=True, backtrace=False, enqueue=True)

@atexit.register
def heartbeat_going_offline():
    global limited_log
    if not CONFIG_SYSTEM:
        return
    logger.complete()
    heartbeat_request(SYSTEM_URL, SYSTEM_ID, SYSTEM_KEY, log=limited_log, going_offline=True)


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
options.limit_refresh_rate_hz = args.led_limit_refresh
if args.led_slowdown_gpio is not None:
    options.gpio_slowdown = args.led_slowdown_gpio
if args.led_no_hardware_pulse:
    options.disable_hardware_pulsing = True
options.daemon = args.daemon
options.drop_privileges = 0

FORK = True  # d3d9/rpi-rgb-led-matrix fork
writeppm = bool(args.write_ppm)
ppmfile = args.write_ppm
options.pixelsvector = writeppm

'''
gpiotest = False
gpiotest_minb = 10
gpiotest_maxb = 65
if gpiotest:
    available_inputs = matrix.GPIORequestInputs(0xffffffff)
'''

resources_dir = "./res/"

### Fonts

fontdir = f"{resources_dir}bdf/"
fontmin = graphics.Font()
fontmin.LoadFont(f"{fontdir}tom-thumb.bdf")
fontnum = graphics.Font()
fontnum.LoadFont(f"{fontdir}4x6.bdf")
fontlargernum = graphics.Font()
fontlargernum.LoadFont(f"{fontdir}5x7-mod.bdf")
propfont = graphics.Font()
propfont.LoadFont(f"{fontdir}uwe_prop_mod.bdf")

fontnormal = propfont if not args.no_prop else fontlargernum
fontsmall = fontnum

fontlinenum = fontsmall if args.small or args.small_linenum else fontnormal
fonttext = fontsmall if args.small or args.small_text else fontnormal
fontcountdown = fontsmall if args.small or args.small_countdown else fontnormal
fontplatform = fontsmall if args.small or args.small_platform else fontnormal

### Colors

# matrixbgColor_t = (0, 16, 19)
matrixbgColor_t = None
textColor = graphics.Color(255, 65, 0)
texthighlightColor = graphics.Color(255, 20, 0)

realtimecolors = RealtimeColors(no_realtime=graphics.Color(190, 190, 190),
                                no_delay=graphics.Color(0, 255, 0),
                                slight_delay=graphics.Color(255, 255, 0),
                                high_delay=graphics.Color(255, 0, 0),
                                cancelled=graphics.Color(255, 0, 0),
                                negative_delay=graphics.Color(0, 255, 115))

graytextColor = graphics.Color(190, 190, 190)
lighttextColor = graphics.Color(100, 100, 100)
barColor = graphics.Color(8, 8, 8)
if options.brightness < 15:
    linebgColor = graphics.Color(0, 12, 12)
    barColor = graphics.Color(12, 12, 12)
else:
    linebgColor = graphics.Color(0, 8, 9)
linefgColor = textColor

### PPM

ppmdir = f"{resources_dir}ppm/"
ppm_info = Image.open(f"{ppmdir}icon-info.ppm")
ppm_warn = Image.open(f"{ppmdir}icon-warn.ppm")
ppm_stop = Image.open(f"{ppmdir}icon-stop.ppm")
ppm_smile = Image.open(f"{ppmdir}icon-smile.ppm")
ppm_ad = Image.open(f"{ppmdir}icon-ad.ppm")
ppm_delay = Image.open(f"{ppmdir}icon-delay.ppm")
ppm_earlyterm = Image.open(f"{ppmdir}icon-earlyterm.ppm")
ppm_no_rt = Image.open(f"{ppmdir}icon-no-rt.ppm")
ppm_no_deps = Image.open(f"{ppmdir}icon-no-deps.ppm")
ppm_fhswf = Image.open(f"{ppmdir}icon-fhswf.ppm")

meldungicons = {
    "info": ppm_info,
    "warn": ppm_warn,
    "stop": ppm_stop,
    "smile": ppm_smile,
    "ad": ppm_ad,
    "delay": ppm_delay,
    "earlyterm": ppm_earlyterm,
    "nort": ppm_no_rt,
    "nodeps": ppm_no_deps,
    "fhswf": ppm_fhswf,
}

symtextoffset = fonttext.height-fonttext.baseline

ppm_whitemin = Image.open(f"{ppmdir}white-min.ppm")
_rtcolors = filter(lambda _: _ is not None, set(getattr(realtimecolors, f.name) for f in fields(realtimecolors)))
ppmmincolordict = {_color: colorppm(ppm_whitemin, _color) for _color in _rtcolors}

supportedcdlhs = (6, 7)
defaultppmcdlh = 6
ppmcdh = fontcountdown.height - 1
ppmcdh = ppmcdh if ppmcdh in supportedcdlhs else defaultppmcdlh
ppm_whitebus = Image.open(f"{ppmdir}white-bus{ppmcdh}.ppm")
ppm_whitetrain = Image.open(f"{ppmdir}white-train{ppmcdh}.ppm")
ppm_whitehispeed = Image.open(f"{ppmdir}white-hispeed{ppmcdh}.ppm")
ppm_whitetram = Image.open(f"{ppmdir}white-tram{ppmcdh}.ppm")
ppm_whitehanging = Image.open(f"{ppmdir}white-hanging{ppmcdh}.ppm")

ppm_whitesofort = Image.open(f"{ppmdir}white-sofort.ppm")
sofort = False  # Alternative: Option zerosofort von CountdownOptions, ggf. Schrift anpassen

if sofort:
    ppmmotdict = dict.fromkeys((MOT.BUS, MOT.TRAIN, MOT.HISPEED, MOT.TRAM, MOT.HANGING), ppm_whitesofort)
else:
    ppmmotdict = {MOT.BUS: ppm_whitebus,
                  MOT.TRAIN: ppm_whitetrain,
                  MOT.HISPEED: ppm_whitehispeed,
                  MOT.TRAM: ppm_whitetram,
                  MOT.HANGING: ppm_whitehanging,
                  }

ppmmotcolordict = {mot: {_color: colorppm(ppm, _color) for _color in ppmmincolordict.keys()} for mot, ppm in ppmmotdict.items()}

ppm_vrr = Image.open(f"{ppmdir}matrix13x13vrr-engebuchstaben-2.ppm").convert('RGB')
ppm_db11 = Image.open(f"{ppmdir}dbkeks.ppm").convert('RGB')
ppm_sonne11 = Image.open(f"{ppmdir}sonne.ppm").convert('RGB')
ppm_wolke11 = Image.open(f"{ppmdir}wolke.ppm").convert('RGB')
ppm_wolkesonne11 = Image.open(f"{ppmdir}wolke mit sonne.ppm").convert('RGB')
ppm_wolkeregen11 = Image.open(f"{ppmdir}wolke mit regen.ppm").convert('RGB')

### linenum, countdown, platform

normalsmalloffset = 1  # in zukunft einfach nur vertikal zentrieren?

linenumopt = LinenumOptions(
    width=args.linenum_width,
    height=fontlinenum.height - 1,
    normalFont=fontlinenum,
    smallFont=fontsmall,
    normalsmalloffset=normalsmalloffset,
    drawbg=linebgColor is not None,
    bgColor=linebgColor,
    fgColor=textColor,
    pattern=linenumpattern,
    retext_1=lambda _s: _s.group(1)+_s.group(2),
    retext_2=lambda _s: _s.group(1))

longausfall = True
ppm_ausfall = Image.open(f"{ppmdir}red-ausfall{'-long' if longausfall else ''}.ppm")
# ppm_ausfall wird nur genutzt, wenn als Option cancelled_symbol von CountdownOptions angegeben.
# Neues Standardverhalten: "entfällt" blinkt abwechselnd mit Zieltext, Countdown zeigt absolute geplante Abfahrtszeit

countdownopt = CountdownOptions(
    font=fontcountdown,
    realtime_colors=realtimecolors,
    mot_symbols=ppmmotdict,
    mot_coloured_symbols=ppmmotcolordict,
    min_symbol=ppm_whitemin,
    min_coloured_symbols=ppmmincolordict,
    mindelay=args.min_delay,
    minslightdelay=args.min_slightdelay,
    minnegativedelay=args.min_negativedelay,
    maxmin=args.max_minutes,
    zerobus=args.show_zero,
    blink=args.disable_blink,
    min_text=args.disable_mintext,
    min_text_offset=1,
    # cancelled_symbol=ppm_ausfall
    )

platformopt = PlatformOptions(
    width=args.platform_width,
    textColor=textColor,
    texthighlightColor=texthighlightColor,
    normalFont=fontplatform,
    smallFont=fontsmall,
    normalsmalloffset=normalsmalloffset)

### Display configuration

dest_replacements = [(ps, "") for ps in args.place_strings]
uncut_destinations = set(args.keep_place_strings)
for dr in args.dest_replacements:
    parts = dr.split('%')
    assert len(parts) == 2, "--dest-replacement string should contain exactly one '%'"
    dest_replacements.append(tuple(parts))

ifopt = args.stop_ifopt
efamenabled = args.enable_efamessages
headername = args.stop_name
headerscroll = args.disable_topscroll
progress = args.show_progress
# zur config (und alles andere eigentlich auch):
stopsymbol = True
melsymbol = True

rightbar = bool(args.rightbar)
rightbarcolor = graytextColor
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

# Abstand Liniennummer - Ziel
spaceld = 2
# Abstand Ziel - Zeit
spacedc = 1
# Abstand Zeit - Steig (falls --platform-width > 0)
spacecp = 1
# Abstand Abfahrtsinfo (bis Zeit bzw. Steig usw.) zum rechten Bereich (Uhr, Logo, Wetter usw.)
spaceDr = 1

header_spacest = 1

countdownlowerlimit = -9

tz = datetime.utcnow().astimezone().tzinfo

call_args_retries_main = 4
call_args_retries_backup = 1
call_args_retries_local = 0

efaserver = 'https://openservice.vrr.de/vrr/XML_DM_REQUEST'
efaserver_backup = 'http://www.efa-bw.de/nvbw/XML_DM_REQUEST'

ext_url = args.ext_data_url
save_msg_path = args.save_msg_path

local_deps = args.local_deps

nina_url = args.nina_url
nina_ags = tuple(args.nina_ags)
nina_ignore_msgType = set(args.nina_ignore_msgType)
nina_ignore_severity = set(args.nina_ignore_severity)
nina_ignore_id = set(args.nina_ignore_id)

# z. B. Aufzugsmeldungen
# ignore_infoTypes = {"stopInfo"}
ignore_infoTypes = set(args.ignore_infotype) if args.ignore_infotype else None

# z. B. Umleitung Wetter; Ausfall Eckeseyer Br.; Sonderburgstr.:
# ignore_infoIDs = {"41354_HST", "28748_HST", "45828_HST"}
ignore_infoIDs = set(args.ignore_infoid) if args.ignore_infoid else None

itdNoTrain_remove_msg = set(args.itdNoTrain_remove_msg) if args.itdNoTrain_remove_msg else None
itdNoTrain_remove_dep = set(args.itdNoTrain_remove_dep) if args.itdNoTrain_remove_dep else None

content_for_short_titles = True

dbrestserver = 'http://d3d9.xyz:3000'
dbrestserver_backup = 'https://2.db.transport.rest'
dbrestibnr = args.ibnr

bvgrestserver = 'http://d3d9.xyz:3001'
bvgrestserver_backup = 'https://2.bvg.transport.rest'
# vbbrestserver = ...
bvgrestid = args.bvg_id
bvgdirectionid = args.bvg_direction
bvgexclremarktypes = {'hint'}

delaymsg_enable = True
delaymsg_mindelay = 2
etermmsg_enable = True
etermmsg_only_visible = True
nodepmsg_enable = True
nortmsg_limit = args.no_rt_msg

nina_msg_priority = 1000
delaymsg_priority = etermmsg_priority = nodepmsg_priority = nortmsg_priority = 500
msg_priority_default = 0

### End of configuration

class NoDatasourceException(Exception):
    pass

class Display:
    def __init__(
            self,
            pe: Executor,
            x_min: int,
            y_min: int,
            x_max: int,
            y_max: int,
            font: graphics.Font,
            text_startr: int,
            textColor: graphics.Color,
            texthighlightColor: graphics.Color,
            clockColor: graphics.Color,
            progressColor: graphics.Color,
            bgColor_t: Optional[Tuple[int, int, int]],
            update_step: int,
            depcolumns: Sequence[Tuple[int, int]],
            depcolumns_zigzag: bool,
            deplines: List[StandardDepartureLine],
            after_dep_lineheight: int,
            stop_scroller: Optional[Union[MultisymbolScrollline, SimpleScrollline]],
            after_stop_lineheight: Optional[int],
            clock_in_header: Optional[bool],
            meldung_scroller: Optional[Union[MultisymbolScrollline, SimpleScrollline]],
            after_meldung_lineheight: Optional[int]):
        self.pe = pe
        self.x_min = x_min
        self.y_min = y_min
        self.x_max = x_max
        self.y_max = y_max
        self.font = font
        self.text_startr = text_startr
        self.textColor = textColor
        self.texthighlightColor = texthighlightColor
        self.clockColor = clockColor
        self.progressColor = progressColor
        self.bgColor_t = bgColor_t
        self.update_step = update_step
        self.depcolumns = depcolumns
        self.depcolumns_zigzag = depcolumns_zigzag
        self.deplines = deplines
        self.after_dep_lineheight = after_dep_lineheight
        self.stop_scroller = stop_scroller
        self.after_stop_lineheight = after_stop_lineheight
        self.clock_in_header = clock_in_header
        self.meldung_scroller = meldung_scroller
        self.after_meldung_lineheight = after_meldung_lineheight

        self.header = self.stop_scroller is not None
        self.header_hiddendeps: int = len(self.depcolumns)
        self.meldung_hiddendeps: int = len(self.depcolumns)

        self.columnaccessfn: Callable[[int, Display], int]
        self.dep_lineheight_gen: Callable[[Display], Iterable]
        if self.depcolumns_zigzag:
            self.columnaccessfn = lambda _dli, disp: _dli % len(disp.depcolumns)
            self.dep_lineheight_gen = lambda disp: cycle((0,)*(len(disp.depcolumns)-1)+(args.line_height,))
        else:
            self.columnaccessfn = lambda _dli, disp: _dli//disp.depcolumnheight
            self.dep_lineheight_gen = lambda disp: cycle((args.line_height,)*(disp.depcolumnheight-1)+(-args.line_height*(disp.depcolumnheight-1),))

        self.i = 0
        self.meldungvisible = False
        self.depsvisible = 0
        self.depcolumnheight = 0

        # aktuell wird angenommen, dass es genug deplines gibt, um auch die header-zeile mit zu benutzen, auch wenn von anfang an klar ist, dass dies nicht so sein wird
        self.limit = len(deplines) - self.header*self.header_hiddendeps
        self.deps: List[Departure] = []
        self.const_meldungs: List[Meldung] = [Meldung(symbol="ad", text=args.message)] if args.message else []
        self.meldungs: List[Meldung] = self.const_meldungs.copy()

        self.datasources: Dict[str, DataSource] = {}

        ds_efa = DataSource("efa-main")
        _efa_args = {
            'serverurl': efaserver,
            'timeout': servertimeout,
            'ifopt': ifopt,
            'limit': self.limit*args.limit_multiplier,
            'tz': tz,
            'ignore_infoTypes': ignore_infoTypes,
            'ignore_infoIDs': ignore_infoIDs,
            'itdNoTrain_remove_msg': itdNoTrain_remove_msg,
            'itdNoTrain_remove_dep': itdNoTrain_remove_dep,
            'content_for_short_titles': content_for_short_titles,
            'message_priority': None # ...
        }
        ds_efa.to_call.append(CallableWithKwargs(getefadeps, _efa_args, call_args_retries_main))

        _efa_args_backup = _efa_args.copy()
        _efa_args_backup['serverurl'] = efaserver_backup
        ds_efa.to_call.append(CallableWithKwargs(getefadeps, _efa_args_backup, call_args_retries_backup))

        if local_deps:
            ds_efa.to_call.append(CallableWithKwargs(getlocaldeps, {'local_dep_path': local_deps, 'limit': self.limit, 'tz': tz}, call_args_retries_local))
            # erstmal nur bei ds_efa local_deps eingebunden.

        ds_efa_notrains = DataSource("efa-notr")
        _efa_notrains_args = _efa_args.copy()
        _efa_notrains_args_backup = _efa_args_backup.copy()
        _efa_notrains_args['exclMOT'] = trainTMOTefa
        _efa_notrains_args_backup['exclMOT'] = trainTMOTefa
        ds_efa_notrains.to_call.append(CallableWithKwargs(getefadeps, _efa_notrains_args, call_args_retries_main))
        ds_efa_notrains.to_call.append(CallableWithKwargs(getefadeps, _efa_notrains_args_backup, call_args_retries_backup))

        ds_bvg = DataSource("bvg-main")
        _bvg_args = {
            'serverurl': bvgrestserver,
            'timeout': servertimeout,
            'station_id': bvgrestid,
            'limit': self.limit*args.limit_multiplier,
            'direction': bvgdirectionid,
            'duration': 90,
            'exclRemarkTypes': bvgexclremarktypes,
            'message_priority': None # ...
        }
        ds_bvg.to_call.append(CallableWithKwargs(getfptfrestdeps, _bvg_args, call_args_retries_main))

        _bvg_args_backup = _bvg_args.copy()
        _bvg_args_backup['serverurl'] = bvgrestserver_backup
        ds_bvg.to_call.append(CallableWithKwargs(getfptfrestdeps, _bvg_args_backup, call_args_retries_backup))

        ds_db = DataSource("dbrest-main")
        _db_args = {
            'serverurl': dbrestserver,
            'timeout': servertimeout,
            'station_id': dbrestibnr,
            'limit': self.limit*args.limit_multiplier,
            'message_priority': None # ...
        }
        ds_db.to_call.append(CallableWithKwargs(getfptfrestdeps, _db_args, call_args_retries_main))

        _db_args_backup = _db_args.copy()
        _db_args_backup['serverurl'] = dbrestserver_backup
        ds_db.to_call.append(CallableWithKwargs(getfptfrestdeps, _db_args_backup, call_args_retries_backup))

        ds_db_trainsonly = DataSource("dbrest-tr")
        _db_trainsonly_args = _db_args.copy()
        _db_trainsonly_args_backup = _db_args_backup.copy()
        _db_trainsonly_args['inclMOT'] = trainMOT
        _db_trainsonly_args_backup['inclMOT'] = trainMOT
        ds_db_trainsonly.to_call.append(CallableWithKwargs(getfptfrestdeps, _db_trainsonly_args, call_args_retries_main))
        ds_db_trainsonly.to_call.append(CallableWithKwargs(getfptfrestdeps, _db_trainsonly_args_backup, call_args_retries_backup))

        _db_trainsonly_efabackup_args = _efa_args.copy()
        _db_trainsonly_efabackup_args_backup = _efa_args_backup.copy()
        _db_trainsonly_efabackup_args['inclMOT'] = trainTMOTefa
        _db_trainsonly_efabackup_args_backup['inclMOT'] = trainTMOTefa
        ds_db_trainsonly.to_call.append(CallableWithKwargs(getefadeps, _db_trainsonly_efabackup_args, 1 + call_args_retries_backup))
        ds_db_trainsonly.to_call.append(CallableWithKwargs(getefadeps, _db_trainsonly_efabackup_args_backup, call_args_retries_backup))

        if bvgrestid:
            self.add_datasource(ds_bvg)
        elif ifopt:
            if dbrestibnr:
                self.add_datasource(ds_efa_notrains)
                self.add_datasource(ds_db_trainsonly)
            else:
                self.add_datasource(ds_efa)
        elif dbrestibnr:
            self.add_datasource(ds_db)
        else:
            # ggf. lokal only erlauben
            raise NoDatasourceException("no ifopt, dbrestibnr or bvgrestid..")

        if ext_url:
            ds_ext = DataSource("ext-m+d", critical=False)
            ds_ext.to_call.append(CallableWithKwargs(getextmsgdata,
                {'url': ext_url, 'timeout': servertimeout, 'save_msg_path': save_msg_path}, call_args_retries_main))
            if save_msg_path:
                ds_ext.to_call.append(CallableWithKwargs(getlocalmsg, {'save_msg_path': save_msg_path}, call_args_retries_local))
            self.add_datasource(ds_ext)

        if nina_url:
            _nina_opt = {'url': nina_url, 'timeout': 10, 'tz': tz, 'symbol': "warn", 'message_priority': nina_msg_priority}
            if nina_ignore_msgType: _nina_opt['ignore_msgType'] = nina_ignore_msgType
            if nina_ignore_severity: _nina_opt['ignore_severity'] = nina_ignore_severity
            if nina_ignore_id: _nina_opt['ignore_id'] = nina_ignore_id
            for ags in nina_ags:
                # evtl. besser: innerhalb 1 Funktionsaufruf alle laden oder anderweitig sicherstellen, dass die Reihenfolge erhalten bleibt
                # ansonsten resettet sich die Scrollzeile zu häufig (da das Array dann anders ist, geht es von vorne los)
                # außerdem Präfix mit Ortsnamen o. ä. ermöglichen
                ds_nina = DataSource(f"nina-{ags}", critical=False, skip=12)
                ds_nina.to_call.append(CallableWithKwargs(getnina, {**_nina_opt, 'ags': ags}, 1))
                self.add_datasource(ds_nina)

        self.pe_f = None
        self.joined = True
        self.heartbeat_step = self.update_step
        self.pe_hb = None
        self.heartbeat_joined = True
        self.prev_limited_log = []
        self.heartbeat_detail_skip = 6
        self.heartbeat_detail_skip_remaining = 0
        self.action_step_pending = int(self.update_step / 2)
        self.action_pending = False
        self.pe_a = None
        self.action_joined = True

    def add_datasource(self, datasource: DataSource) -> None:
        if datasource.name in {ds.name for ds in self.datasources.values()}:
            raise ValueError(f"DataSource name {ds.name} already exists in self.datasources")
        self.datasources[datasource.name] = datasource

    def additional_update(self, nowtime: datetime.datetime = datetime.now(tz), di: int = 0, dep: Optional[Departure] = None) -> None:
        pass

    def action(self, action=None):
        if self.action_joined:
            if action is not None or (self.action_pending and not self.i % self.action_step_pending):
                self.action_joined = False
                self.pe_a = self.pe.submit(check_action, action if action is not None else self.action_pending, SYSTEM_URL, SYSTEM_ID, SYSTEM_KEY)
        elif self.pe_a.done():
            try:
                self.action_pending = self.pe_a.result()
            except Exception as e:
                logger.exception("exception from check_action")
            else:
                pass
            finally:
                self.action_joined = True

    def heartbeat(self):
        global limited_log
        if self.heartbeat_joined and not self.i % self.heartbeat_step:
            self.heartbeat_joined = False
            hb_args = {}
            if self.prev_limited_log != limited_log:
                hb_args["log"] = limited_log
                self.prev_limited_log = limited_log.copy()
            else:
                hb_args["log"] = "unchanged"
            if not self.heartbeat_detail_skip_remaining:
                hb_args["get_system_data"] = ("temperature_cpu", "uptime")
                # hb_args["loaded_data"] = ...
                self.heartbeat_detail_skip_remaining = self.heartbeat_detail_skip
            else:
                self.heartbeat_detail_skip_remaining -= 1
            self.pe_hb = self.pe.submit(
                heartbeat_request,
                url=SYSTEM_URL,
                dfi_id=SYSTEM_ID,
                key=SYSTEM_KEY,
                **hb_args)
        if not self.heartbeat_joined and self.pe_hb.done():
            try:
                response = self.pe_hb.result()
                action = response.get('action')
            except Exception as e:
                logger.warning("exception from heartbeat: " + str(e))
            else:
                if action is False or self.action_pending != action:
                    # hier self.action nur dann aufrufen, wenn "sich was getan hat", ansonsten wird es bei action_pending mit dem action_step_pending regelmäßig aufgerufen
                    self.action(action)
            finally:
                self.heartbeat_joined = True

    def update(self) -> bool:
        if self.joined and not self.i % self.update_step:
            self.joined = False
            self.pe_f = self.pe.submit(
                getdeps,
                datasources=list(self.datasources.values()),
                getdeps_timezone=tz,
                getdeps_lines=self.limit,
                getdeps_dest_replacements=dest_replacements,
                getdeps_dest_replacements_uncut=uncut_destinations,
                getdeps_mincountdown=countdownlowerlimit,
                extramsg_messageexists=bool(self.const_meldungs),
                extramsg_messagelines = self.meldung_hiddendeps,
                delaymsg_enable=delaymsg_enable,
                delaymsg_mindelay=delaymsg_mindelay,
                delaymsg_priority=delaymsg_priority,
                etermmsg_enable=etermmsg_enable,
                etermmsg_only_visible=etermmsg_only_visible,
                etermmsg_priority=etermmsg_priority,
                nodepmsg_enable=nodepmsg_enable,
                nodepmsg_priority=nodepmsg_priority,
                nortmsg_limit=nortmsg_limit,
                nortmsg_priority=nortmsg_priority)

        if not self.joined and self.pe_f.done():
            try:
                self.deps, self.meldungs, _add_data, skip_dict = self.pe_f.result()
            except Exception as e:
                if e.__class__ != GetdepsEndAll:
                    logger.exception("exception from getdeps")
                self.deps = []
                self.meldungs = [Meldung(symbol="warn", text="Fehler bei Datenabruf. Bitte Aushangfahrpläne beachten.")]
            else:
                for datasource_name, result in skip_dict.items():
                    datasource = self.datasources[datasource_name]
                    if datasource._skip_cache is None:
                        datasource._skip_remaining = datasource.skip - 1
                        datasource._skip_cache = result
                    elif datasource._skip_remaining:
                        datasource._skip_remaining -= 1
                    elif datasource._skip_remaining == 0:
                        datasource._skip_remaining = None
                        datasource._skip_cache = None
                self.meldungs.extend(self.const_meldungs)
                nowtime = datetime.now(tz)
                for di, dep in enumerate(self.deps):
                    for _mel in dep.messages:
                        if _mel not in self.meldungs and ((not _mel.efa) or (efamenabled and di < self.limit-self.meldung_hiddendeps)):
                            self.meldungs.append(_mel)
                    self.additional_update(nowtime, di, dep)
                # only to be changed through the configuration in the future
                # _brightness = _add_data.get("brightness")
                # if _brightness is not None and _brightness != matrix.brightness:
                #     matrix.brightness = _brightness
            finally:
                self.joined = True
                self.meldungvisible = bool(self.meldung_scroller is not None and self.meldungs)
                self.depsvisible = min(len(self.deplines), self.limit - self.meldungvisible*self.meldung_hiddendeps)
                self.depcolumnheight = int(Decimal(self.depsvisible / len(self.depcolumns)).quantize(0, ROUND_HALF_UP))
                for _dli, _depline in enumerate(self.deplines):
                    _depline.update(self.deps[_dli] if _dli < len(self.deps) else None)
                    if _dli < self.depsvisible:
                        _depline.lx, _depline.rx = self.depcolumns[self.columnaccessfn(_dli, self)]
                        _depline.setminmax()
                # new: order messages by priority
                self.meldungs.sort(key=lambda x: (x.priority or msg_priority_default), reverse=True)
                if self.meldung_scroller is not None:
                    self.meldung_scroller.update(self.meldungs)
                return True

        return False

    def render_header(self, canvas: FrameCanvas, r: int) -> int:
        self.stop_scroller.update(ppm_stop if stopsymbol else None, headername or (self.deps and self.deps[0].stopname) or "")
        self.stop_scroller.render(canvas, r)

        if self.clock_in_header:
            graphics.DrawText(canvas, self.font, self.stop_scroller.rx+1+header_spacest, r, self.clockColor, clockstr_tt(localtime()))

        return self.after_stop_lineheight

    def render(self, canvas: FrameCanvas) -> None:
        if self.bgColor_t is not None:
            # TODO: nur innerhalb der Grenzen vom Display fillen
            canvas.Fill(*self.bgColor_t)

        blinkon = self.i % 60 < 30
        dep_lineheights = self.dep_lineheight_gen(self)
        r = self.y_min + self.text_startr

        if self.header:
            r += self.render_header(canvas, r)

        _deprs = set()
        _deprs.add(r)
        for _dli, _depline in enumerate(self.deplines):
            _depline.render(canvas, r, blinkon)
            if _dli < self.depsvisible - 1:
                r += next(dep_lineheights)
                _deprs.add(r)
            else:
                r = max(_deprs) + self.after_dep_lineheight
                break

        if self.meldungvisible:
            self.meldung_scroller.render(canvas, r)
            r += self.after_meldung_lineheight

        if progress:
            x_pixels = self.x_max - self.x_min + 1
            x_progress = int(x_pixels-1 - ((self.i % self.update_step)*((x_pixels-1)/self.update_step)))
            graphics.DrawLine(canvas, self.x_min, self.y_max, self.x_min+x_progress, self.y_max, self.progressColor)

    def step(self) -> None:
        self.i += 1


class LocalColorDisplay(Display):
    @staticmethod
    def _get_color_dict():
        raise NotImplementedError

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.linecolordict = dict()
        for product, productcolors in self.__class__._get_color_dict().items():
            self.linecolordict.update(productcolors)
        for k, v in self.linecolordict.items():
            self.linecolordict[k] = v["bg"]
        # todo: bisherige "MOT" durch zu fptf passende product-werte ersetzen..
        self.motcolordict = {
            MOT.BUS: "#922A7D",
        }

    def additional_update(self, nowtime: datetime.datetime = datetime.now(tz), di: int = 0, dep: Optional[Departure] = None) -> None:
        dep.color = self.linecolordict.get(dep.linenum) or self.motcolordict.get(dep.mot)

class BVGDisplay(LocalColorDisplay):
    @staticmethod
    def _get_color_dict():
        _r = get("https://raw.githubusercontent.com/derhuerst/vbb-line-colors/master/index.json")
        _r.raise_for_status()
        return _r.json()

class HSTDisplay(LocalColorDisplay):
    @staticmethod
    def _get_color_dict():
        with open('./res/hstcolors.json', 'r') as hstcolorfile:
            return json_load(hstcolorfile)

class FHSWFIserlohnDisplay(Display):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _rss_opt = {'timeout': 30, 'tz': tz, 'symbol': "fhswf", 'message_priority': None}

        ds_fhswf_presse = DataSource("fhswf-rss-presse", critical=False)
        _rss_opt_presse = {**_rss_opt,
            'url': "https://vpis.fh-swf.de/rss.php/pressemitteilungen",
            'limit_timedelta': timedelta(days=10),
            'filter_categories': {'Studienort Iserlohn'},
            'output_date': True
        }
        ds_fhswf_presse.to_call.append(CallableWithKwargs(getrssfeed, _rss_opt_presse, 1))
        self.add_datasource(ds_fhswf_presse)

        # termine-feed ist sehr langsam! kann man nur zum testen verwenden. daher auch timeout 30.
        ds_fhswf_termine = DataSource("fhswf-rss-termine", critical=False)
        _rss_opt_termine = {**_rss_opt,
            'url': "https://vpis.fh-swf.de/rss.php/de/home/studierende/termine_aktuelles_1/index.php",
            'limit': 3,
            'filter_categories': {'Iserlohn : Veranstaltungen & Meldungen aus Iserlohn'}
        }
        ds_fhswf_termine.to_call.append(CallableWithKwargs(getrssfeed, _rss_opt_termine, 1))
        self.add_datasource(ds_fhswf_termine)

class KVBDisplay(Display):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        countdownopt.use_disp_countdown = True # damit countdown der angezeigt wird verwendet wird und nicht der anhand der uhrzeit berechnete..

        ds_kvb = DataSource("kvb")
        ds_kvb.to_call.append(CallableWithKwargs(getkvbmonitor, {
            "STATION_ID": 632,
            "tz": tz,
            "filter_directions": {"Rochusplatz", "Bocklemünd"}
        }, 4))
        self.datasources = {}
        self.add_datasource(ds_kvb)

    def render_header(self, canvas: FrameCanvas, r: int) -> int:
        toptext = datetime.now().strftime("%A %d.%m.%Y %H:%M")
        graphics.DrawText(canvas, self.font, 0, r, self.clockColor, toptext)
        return self.after_stop_lineheight


def loop(matrix: RGBMatrix, pe: Executor, sleep_interval: int) -> NoReturn:
    canvas = matrix.CreateFrameCanvas(writeppm) if FORK else matrix.CreateFrameCanvas()
    x_min = 0
    y_min = 0
    x_max = canvas.width - 1
    y_max = canvas.height - 1
    display_x_min = x_min
    display_y_min = y_min
    display_x_max = x_max - (rightbar and (rightbarwidth + spaceDr))
    display_y_max = y_max

    scrollColor = graytextColor

    def make_columns(l: int, r: int, c: int, spacing: int = 0) -> Sequence[Tuple[int, int]]:
        colwidth = ((r-l+1) // c) - (c-1)*(spacing - (spacing // 2))
        cols = []
        _startpos = l
        for ci in range(c):
            cols.append((_startpos, _startpos + colwidth - 1))
            _startpos += colwidth + spacing
        return tuple(cols)

    depcolumns = make_columns(display_x_min, display_x_max, args.columns, args.column_spacing)

    calc_limit = (display_y_max - display_y_min + 1 - args.firstrow_y - fonttext.height + fonttext.baseline + args.line_height) // args.line_height
    deplines = [StandardDepartureLine(
        lx=_l,
        rx=_r,
        font=fonttext,
        textColor=textColor,
        texthighlightColor=texthighlightColor,
        space_linenum_direction=spaceld,
        space_direction_countdown=spacedc,
        space_countdown_platform=spacecp,
        linenumopt=linenumopt,
        countdownopt=countdownopt,
        platformopt=platformopt,
    ) for _l, _r in depcolumns for _ in range(args.lines or calc_limit)]

    # xmax hier muss man eigentlich immer neu berechnen
    scrollx_stop_xmax = display_x_max-((not rightbar) and header_spacest+textpx(fonttext, clockstr_tt(localtime())))
    stop_scroller = SimpleScrollline(display_x_min+2, scrollx_stop_xmax, symtextoffset, fonttext, scrollColor, symtextspacing=2, noscroll=not headerscroll)

    scrollx_msg_xmax = x_max if scrollmsg_through_rightbar else display_x_max
    meldung_scroller = MultisymbolScrollline(display_x_min, scrollx_msg_xmax, symtextoffset, fonttext, scrollColor, meldungicons, bgcolor_t=matrixbgColor_t, initial_pretext=2, initial_posttext=10)

    displayclass = HSTDisplay if args.hst_colors else (BVGDisplay if args.bvg_id else Display)
    # displayclass = KVBDisplay
    display = displayclass(
        pe=pe,
        x_min=display_x_min,
        y_min=display_y_min,
        x_max=display_x_max,
        y_max=display_y_max,
        font=fonttext,
        text_startr=args.firstrow_y,
        textColor=textColor,
        texthighlightColor=texthighlightColor,
        clockColor=graytextColor,
        progressColor=barColor,
        bgColor_t=matrixbgColor_t,
        update_step=args.update_steps,
        depcolumns=depcolumns,
        depcolumns_zigzag=args.column_zigzag,
        deplines=deplines,
        after_dep_lineheight=args.line_height,
        stop_scroller=stop_scroller if args.enable_top else None,
        after_stop_lineheight=args.line_height,
        clock_in_header=not rightbar,
        meldung_scroller=meldung_scroller,
        after_meldung_lineheight=args.line_height)

    logger.info(f"started loop with data sources {', '.join(display.datasources.keys())}")
    while True:
        # time_measure = monotonic()
        canvas.Clear()

        if rightbar:
            # x_min, y_min usw. fehlen
            rightbarfn(canvas, display.x_max+1+spaceDr, 0, rightbarwidth, rightbarfont, rightbarcolor, display.i, display.update_step, localtime(), *rightbarargs)

        display.update()
        display.render(canvas)
        if CONFIG_SYSTEM:
            display.heartbeat()
        display.action()

        if writeppm:
            canvas.ppm(ppmfile)

        display.step()
        canvas = matrix.SwapOnVSync(canvas)

        '''
        if gpiotest:
            inputs = matrix.AwaitInputChange(0)
            if inputs & (1 << 21):
                # check_output(["/sbin/shutdown", "now"])
                matrix.brightness = ((matrix.brightness - gpiotest_minb + 1) % (gpiotest_maxb - gpiotest_minb + 1)) + gpiotest_minb
        '''

        # _st = sleep_interval-monotonic()+time_measure
        # if _st > 0:
        #     sleep(_st)
        if sleep_interval > 0:
            sleep(sleep_interval)


if __name__ == "__main__":
    logger.info("started")
    matrix = RGBMatrix(options=options)
    if args.show_start:
        startcanvas = matrix.CreateFrameCanvas(writeppm) if FORK else matrix.CreateFrameCanvas()
        startscreen(startcanvas, fontsmall, lighttextColor, ifopt, ppm_smile)
        matrix.SwapOnVSync(startcanvas)
        sleep(5)
    while True:
        try:
            with ProcessPoolExecutor(max_workers=3) as ppe:
                loop(matrix, ppe, args.sleep_interval)
        except KeyboardInterrupt:
            break
        except NoDatasourceException as nde:
            logger.exception(nde)
            break
        except Exception:
            logger.opt(exception=True).critical("exception in loop or module")
    logger.info("exiting")
