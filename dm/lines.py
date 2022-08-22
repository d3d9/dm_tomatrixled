# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from re import Pattern, match as re_match
from typing import List, Optional, Callable, Tuple, Dict, Match

from PIL import Image
from RGBMatrixEmulator import graphics
from RGBMatrixEmulator.emulators.canvas import Canvas as FrameCanvas
from webcolors import hex_to_rgb

from .drawstuff import clockstr_tt, drawppm_bottomleft, drawppm_bottomright
from .depdata import Departure, Meldung, MOT, trainMOT


class MultisymbolScrollline:
    @dataclass
    class __Element:
        text: str
        symbol: Image.Image
        textcolor: graphics.Color
        initial_pretext: int
        initial_posttext: int
        letters_passed: int = field(init=False, default=0)
        curr_textxoffset: int = field(init=False, default=0)
        pretext: int = field(init=False)
        posttext: int = field(init=False)

        def __post_init__(self):
            self.pretext = self.initial_pretext
            self.posttext = self.initial_posttext

        def reset(self):
            self.pretext = self.initial_pretext
            self.posttext = self.initial_posttext
            self.letters_passed = 0
            self.curr_textxoffset = 0

    def __init__(self, lx, rx, symoffset, font, defaulttextcolor, symdict, bgcolor_t=None, initial_pretext=2, initial_posttext=5, pretext_zero_if_no_symbol=True, add_end_spacer=True, last_char_separated=False, fixedy: Optional[int] = None):
        # attributes
        self.lx = lx
        self.rx = rx
        self.symoffset = symoffset
        self.font = font
        self.defaulttextcolor = defaulttextcolor
        self.symdict = symdict
        self.bgcolor = graphics.Color(*bgcolor_t) if bgcolor_t else graphics.Color()
        self.initial_posttext = initial_posttext
        self.initial_pretext = initial_pretext
        self.pretext_zero_if_no_symbol = pretext_zero_if_no_symbol
        self.add_end_spacer = add_end_spacer
        self.last_char_separated = last_char_separated
        self.fixedy = fixedy
        # self.staticleftsymtextspacing = staticleftsymtextspacing
        # self.forcescroll = forcescroll
        # self.noscroll = noscroll

        # state
        self.meldungs: List[Meldung] = []
        self.elements: List[MultisymbolScrollline.__Element] = []
        self.currfirstelemi = None
        self.currlastelemi = None
        self.shownelems = 0
        self.startpos = rx

    def update(self, meldungs: List[Meldung]) -> None:
        if meldungs == self.meldungs:
            return
        ...  # todo: schlaue anpassung je nach davor angezeigter meldung; dabei alle anderen zeilen hier anpassen
        self.meldungs = meldungs
        self.elements = []
        self.currfirstelemi = None
        self.currlastelemi = None
        self.shownelems = 0
        self.startpos = self.rx
        for meldung in meldungs:
            _symbol = self.symdict and self.symdict.get(meldung.symbol) or None
            _text = ''.join(_char for _char in meldung.text if characterwidth(self.font, ord(_char)))
            self.elements.append(
                self.__class__.__Element(
                    text=_text,
                    symbol=_symbol,
                    textcolor=graphics.Color(*(int(meldung.color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))) if meldung.color else self.defaulttextcolor,
                    initial_pretext=self.initial_pretext if _text and (_symbol is not None or not self.pretext_zero_if_no_symbol) else 0,
                    initial_posttext=self.initial_posttext
                )
            )
        if self.elements:
            if self.elements[0].symbol is not None:
                self.startpos -= (self.elements[0].symbol.size[0] - 1)
            if self.add_end_spacer:
                self.elements[-1].initial_posttext = 0
                self.elements[-1].posttext = 0
                self.elements.append(self.__class__.__Element(text='', symbol=None, textcolor=self.defaulttextcolor, initial_pretext=0, initial_posttext=self.startpos-self.lx))

        if self.last_char_separated:
            # experimentell
            _i = 0
            for _e in self.elements[:]:
                if _e.text:
                    _i += 1
                    self.elements.insert(_i, self.__class__.__Element(text=_e.text[-1], symbol=None, textcolor=_e.textcolor, initial_pretext=0, initial_posttext=_e.initial_posttext))
                    _e.text = _e.text[:-1]
                    _e.initial_posttext = 1
                    _e.posttext = 1
                _i += 1

    def render(self, canvas: FrameCanvas, texty: int) -> None:
        if not self.elements:
            return
        texty = self.fixedy if self.fixedy is not None else texty
        currx = self.startpos
        if self.currfirstelemi is None:
            self.currfirstelemi = 0
        elemi = self.currfirstelemi
        self.shownelems = 0
        while currx <= self.rx:
            elem = self.elements[elemi]
            isleftelem = currx == self.lx
            if currx + (elem.symbol is not None and (elem.symbol.size[0] - 1)) <= self.rx:
                self.shownelems += 1
                self.currlastelemi = elemi
                if elem.symbol is not None: currx = drawppm_bottomleft(canvas, elem.symbol, currx, texty+self.symoffset, transp=True)
                if isleftelem:
                    currx += elem.pretext
                    text_max = propscroll(self.font, elem.text[elem.letters_passed:], currx+elem.curr_textxoffset, self.rx)
                else:
                    currx += elem.initial_pretext
                    text_max = propscroll(self.font, elem.text, currx, self.rx)
                if text_max or (not elem.text) or (isleftelem and elem.letters_passed == len(elem.text)):
                    if isleftelem:
                        currx += elem.curr_textxoffset
                    # _total_text wird unten verwendet, Wert wird hier gespeichert, damit er bis dahin unverändert bleibt
                    _total_text = (isleftelem and elem.letters_passed) + text_max
                    if text_max:
                        if isleftelem:
                            currx += graphics.DrawText(canvas, self.font, currx, texty, elem.textcolor, elem.text[elem.letters_passed:elem.letters_passed+text_max]) - 1
                            if not elem.pretext:
                                elem.curr_textxoffset -= 1
                            if elem.curr_textxoffset < 0:
                                elem.curr_textxoffset = characterwidth(self.font, ord(elem.text[elem.letters_passed])) - 1
                                elem.letters_passed += 1
                        else:
                            currx += graphics.DrawText(canvas, self.font, currx, texty, elem.textcolor, elem.text[:text_max]) - 1
                    else:  # if ((not elem.text) or (isleftelem and elem.letters_passed = len(elem.text))):
                        if isleftelem and elem.posttext < 0 and elem.symbol is not None:
                            _thissize = elem.symbol.size[0]
                            for _y in range(texty+self.symoffset-elem.symbol.size[1], texty+self.symoffset+1):
                                graphics.DrawLine(canvas, self.lx+_thissize+elem.posttext, _y, self.lx+_thissize-1, _y, self.bgcolor)
                    if isleftelem:
                        currx += elem.posttext
                        if elem.letters_passed == len(elem.text):
                            if elem.curr_textxoffset:
                                elem.curr_textxoffset -= 1
                            elif not elem.pretext:
                                elem.posttext -= 1
                        if elem.pretext: elem.pretext -= 1
                        if elem.posttext <= ((elem.symbol is not None and -elem.symbol.size[0]) or -1):
                            elem.reset()
                            self.currfirstelemi = (self.currfirstelemi + 1) % len(self.elements)
                            self.shownelems -= 1
                    else:
                        currx += elem.initial_posttext
                    if _total_text < len(elem.text):
                        break
                    elemi = (elemi + 1) % len(self.elements)
                else: break
            else: break
        if self.startpos > self.lx: self.startpos -= 1


class SimpleScrollline:
    def __init__(self, lx, rx, symoffset, font, textcolor, symtextspacing=1, forcescroll=False, noscroll=False, fixedy: Optional[int] = None):
        self.lx = lx
        self.rx = rx
        self.symoffset = symoffset
        self.font = font
        self.textcolor = textcolor
        self.symtextspacing = symtextspacing
        self.forcescroll = forcescroll
        self.noscroll = noscroll
        self.fixedy = fixedy

        self.currx = rx
        self.letters_passed = 0
        self.symbol = None
        self.text = ""
        self.textlen = 0
        self.base_start = lx
        self.base_start_static = lx
        self.text_max_theoretical = 0
        self.willscroll = forcescroll

    def update(self, symbol: Optional[Image.Image], text: str) -> None:
        if symbol == self.symbol and text == self.text:
            return
        self.symbol = symbol
        self.text = ''.join(_char for _char in text if characterwidth(self.font, ord(_char)))
        self.textlen = len(self.text)
        self.base_start = self.lx + (self.symbol is not None and self.symbol.size[0])
        self.base_start_static = self.base_start + (self.symbol is not None and self.symtextspacing)
        self.text_max_theoretical = propscroll(self.font, self.text, self.base_start_static, self.rx)
        self.willscroll = (not self.noscroll) and (self.forcescroll or self.textlen > self.text_max_theoretical)

    def render(self, canvas: FrameCanvas, texty: int) -> None:
        texty = self.fixedy if self.fixedy is not None else texty
        if self.symbol: drawppm_bottomleft(canvas, self.symbol, self.lx, texty+self.symoffset, transp=True)
        if not self.text: return
        if self.willscroll:
            if self.letters_passed >= self.textlen:
                self.letters_passed = 0
                self.currx = self.rx
            text_max = propscroll(self.font, self.text[self.letters_passed:], self.currx, self.rx)
            scrolllen = graphics.DrawText(canvas, self.font, self.currx, texty, self.textcolor, self.text[self.letters_passed:self.letters_passed+text_max])
            self.currx -= 1
            if self.currx < self.base_start:
                self.currx = self.base_start + characterwidth(self.font, ord(self.text[self.letters_passed])) - 1
                self.letters_passed += 1
        else: graphics.DrawText(canvas, self.font, self.base_start_static, texty, self.textcolor, self.text[:self.text_max_theoretical])


_retexttype = Callable[[Match], str]

@dataclass
class LinenumOptions:
    width: int
    height: int
    normalFont: graphics.Font
    smallFont: graphics.Font
    normalsmalloffset: int
    drawbg: bool
    bgColor: graphics.Color
    fgColor: graphics.Color
    pattern: Pattern
    retext_1: _retexttype
    retext_2: _retexttype
    align_left: bool = False


@dataclass
class RealtimeColors:
    no_realtime: graphics.Color
    no_delay: graphics.Color
    slight_delay: graphics.Color
    high_delay: graphics.Color
    cancelled: graphics.Color
    negative_delay: graphics.Color


@dataclass
class CountdownOptions:
    font: graphics.Font
    realtime_colors: RealtimeColors
    mot_symbols: Dict[MOT, Image.Image]
    mot_coloured_symbols: Dict[graphics.Color, Dict[MOT, Image.Image]]
    min_symbol: Image.Image
    min_coloured_symbols: Dict[graphics.Color, Image.Image]
    mindelay: int
    minslightdelay: int
    minnegativedelay: int
    maxmin: int
    zerobus: bool
    min_text: bool
    min_text_offset: int
    in_min_text: bool = False
    blink: bool = True
    zerosofort: bool = False
    use_disp_countdown: bool = False
    cancelled_symbol: Optional[Image.Image] = None


@dataclass
class PlatformOptions:
    width: int
    textColor: graphics.Color
    texthighlightColor: graphics.Color
    normalFont: graphics.Font
    smallFont: graphics.Font
    normalsmalloffset: int


class StandardDepartureLine:
    def __init__(
            self,
            lx: int,
            rx: int,
            font: graphics.Font,
            textColor: graphics.Color,
            texthighlightColor: graphics.Color,
            space_linenum_direction: int,
            space_direction_countdown: int,
            space_countdown_platform: int,
            linenumopt: LinenumOptions,
            countdownopt: CountdownOptions,
            platformopt: Optional[PlatformOptions],
            fixedy: Optional[int] = None,
            cancelled_blink_text: Optional[str] = "entfällt"):
        self.lx = lx
        self.rx = rx
        self.font = font
        self.textColor = textColor
        self.texthighlightColor = texthighlightColor
        self.space_linenum_direction = space_linenum_direction
        self.space_direction_countdown = space_direction_countdown
        self.space_countdown_platform = space_countdown_platform
        self.linenumopt = linenumopt
        self.countdownopt = countdownopt
        self.platformopt = platformopt
        self.fixedy = fixedy
        self.cancelled_blink_text = cancelled_blink_text

        self.dep: Optional[Departure] = None
        self.dep_tz: Optional[timezone] = None
        self.rtcolor: graphics.Color = self.countdownopt.realtime_colors.no_realtime
        self.dirtextcolor: graphics.Color = self.textColor

        self.linenum_min: int
        self.linenum_max: int
        self.direction_xpos: int
        self.deptime_x_max: int
        self.platform_min: int
        self.platform_max: int
        self.setminmax()

    def setminmax(self) -> None:
        self.linenum_min = self.lx
        self.linenum_max = self.linenum_min + self.linenumopt.width - 1

        self.direction_xpos = self.linenum_max + 1 + self.space_linenum_direction
        self.deptime_x_max = self.rx

        if self.platformopt is not None and self.platformopt.width > 0:
            self.deptime_x_max -= (self.space_countdown_platform + self.platformopt.width)
            self.platform_min = self.deptime_x_max + self.space_countdown_platform + 1
            self.platform_max = self.platform_min + self.platformopt.width - 1

    def update(self, dep: Departure) -> None:
        if dep == self.dep:
            return

        self.dep = dep
        if self.dep is None:
            return

        self.dep_tz = self.dep.deptime.tzinfo

        rtc = self.countdownopt.realtime_colors
        if self.dep.realtime:
            if self.dep.cancelled:
                self.rtcolor = rtc.cancelled
            elif self.dep.delay >= self.countdownopt.mindelay:
                self.rtcolor = rtc.high_delay
            elif self.dep.delay >= self.countdownopt.minslightdelay:
                self.rtcolor = rtc.slight_delay
            elif self.dep.delay <= self.countdownopt.minnegativedelay:
                self.rtcolor = rtc.negative_delay
            else:
                self.rtcolor = rtc.no_delay
        else:
            self.rtcolor = rtc.no_realtime

    def render(self, canvas: FrameCanvas, texty: int, blinkon: bool) -> None:
        if self.dep is None:
            return

        texty = self.fixedy if self.fixedy is not None else texty

        if self.dep.color:
            linenum_color = graphics.Color(*hex_to_rgb(self.dep.color))
            linenum_bgColor = graphics.Color()
        else:
            linenum_color = self.linenumopt.fgColor
            linenum_bgColor = self.linenumopt.bgColor

        if self.linenumopt.drawbg:
            for y in range(texty-self.linenumopt.height, texty):
                graphics.DrawLine(canvas, self.linenum_min, y, self.linenum_max, y, linenum_bgColor)

        linenum_font, linenum_str, linenum_px, linenum_verticaloffset = fittext(
            self.dep.disp_linenum,
            self.linenumopt.width,
            self.linenum_min,
            self.linenum_max,
            self.linenumopt.normalFont,
            self.linenumopt.smallFont,
            smallpxoffset=self.linenumopt.normalsmalloffset,
            pattern=self.linenumopt.pattern,
            alt_retext_1=self.linenumopt.retext_1,
            alt_retext_2=self.linenumopt.retext_2)
        linenum_xpos = self.linenum_min if self.linenumopt.align_left else (self.linenum_max - linenum_px + (linenum_px == self.linenumopt.width))

        graphics.DrawText(canvas, linenum_font, linenum_xpos, texty-linenum_verticaloffset, linenum_color, linenum_str)

        directionpixel = self.deptime_x_max - self.direction_xpos
        timeoffset = 0

        dep_countdown: int
        if self.countdownopt.use_disp_countdown:
            dep_countdown = self.dep.disp_countdown
        else:
            dep_countdown_secs: int = (self.dep.deptime - datetime.now(self.dep_tz)).total_seconds()
            dep_countdown = 0 if (-75 < dep_countdown_secs < 30) else int((dep_countdown_secs + 60) // 60)

        if self.dep.cancelled and self.countdownopt.cancelled_symbol is not None:
            drawppm_bottomright(canvas, self.countdownopt.cancelled_symbol, self.deptime_x_max, texty, transp=True)
            timeoffset += self.countdownopt.cancelled_symbol.size[0]
        elif dep_countdown > self.countdownopt.maxmin or self.dep.cancelled:
            timestr = clockstr_tt(self.dep.deptime.timetuple())
            timestrpx = textpx(self.countdownopt.font, timestr)
            graphics.DrawText(canvas, self.countdownopt.font, self.deptime_x_max - timestrpx + 1, texty, self.rtcolor, timestr)
            timeoffset += timestrpx
        elif not dep_countdown and (self.countdownopt.zerobus or self.countdownopt.zerosofort):
            if blinkon or not self.countdownopt.blink:
                if self.countdownopt.zerobus:
                    drawppm_bottomright(canvas, self.countdownopt.mot_coloured_symbols[self.dep.mot][self.rtcolor], self.deptime_x_max, texty, transp=True)
                    timeoffset += self.countdownopt.mot_symbols[self.dep.mot].size[0]
                elif self.countdownopt.zerosofort:
                    timestr = " sofort"
                    timestrpx = textpx(self.countdownopt.font, timestr)
                    graphics.DrawText(canvas, self.countdownopt.font, self.deptime_x_max - timestrpx + 1, texty, self.rtcolor, timestr)
                    timeoffset += timestrpx
        elif dep_countdown or blinkon or not self.countdownopt.blink:  # mehr als 0, oder es ist 0 und kein zerobus/zerosofort
            min_text = self.countdownopt.min_text and not self.countdownopt.in_min_text
            timestr = (f" in {dep_countdown} min" if dep_countdown >= 0 else f" vor {abs(dep_countdown)} min") if self.countdownopt.in_min_text else str(dep_countdown)
            timestrpx = textpx(self.countdownopt.font, timestr)
            graphics.DrawText(canvas, self.countdownopt.font, self.deptime_x_max - timestrpx - ((self.countdownopt.min_symbol.size[0]-1+self.countdownopt.min_text_offset) if min_text else -1), texty, self.rtcolor, timestr)
            timeoffset += timestrpx
            if min_text:
                drawppm_bottomright(canvas, self.countdownopt.min_coloured_symbols[self.rtcolor], self.deptime_x_max, texty, transp=True)
                timeoffset += self.countdownopt.min_symbol.size[0] + self.countdownopt.min_text_offset

        if self.platformopt is not None and self.platformopt.width > 0 and self.dep.platformno:
            platprefix = self.dep.platformtype or ("Gl." if self.dep.mot in trainMOT else "Bstg.")
            full_str = platprefix + str(self.dep.platformno)
            short_str = str(self.dep.platformno)
            if any((hit := _) in short_str for _ in {"Gleis", "Gl.", "Bstg.", "Bstg", "Bussteig", "Bahnsteig", "Steig", "Platform", "Pl."}):
                full_str = short_str
                short_str = short_str.replace(hit, "").strip()
            platform_font, platform_str, platpx, platform_verticaloffset = fittext(
                full_str,
                self.platformopt.width,
                self.platform_min,
                self.platform_max,
                self.platformopt.normalFont,
                self.platformopt.smallFont,
                smallpxoffset=self.platformopt.normalsmalloffset,
                alt_text=short_str)
            platformchanged = self.dep.platformno_planned and (self.dep.platformno_planned != self.dep.platformno)
            platform_color = self.platformopt.texthighlightColor if platformchanged else self.platformopt.textColor
            platform_xpos = self.platform_max - platpx + 1
            graphics.DrawText(canvas, platform_font, platform_xpos, texty-platform_verticaloffset, platform_color, platform_str)

        directionpixel -= (timeoffset + self.space_direction_countdown*bool(timeoffset))
        dirtext = self.cancelled_blink_text if (self.cancelled_blink_text and self.dep.cancelled and blinkon) else self.dep.disp_direction
        directionlimit = propscroll(self.font, dirtext, self.direction_xpos, self.direction_xpos+directionpixel)
        dirtextcolor = self.texthighlightColor if self.dep.earlytermination else self.textColor
        graphics.DrawText(canvas, self.font, self.direction_xpos, texty, dirtextcolor, dirtext[:directionlimit])


# beides ohne extra_spacing
@lru_cache(maxsize=4096)
def propscroll(font: graphics.Font, text: str, start: int, end: int) -> int:
    c = 0
    cpx = 0
    pixel = end - start + 1 + 1  # + 1 wegen space am ende jedes zeichens, was am ende egal ist
    while c < len(text):
        _cpx = cpx + characterwidth(font, ord(text[c]))
        if _cpx > pixel:
            break
        c += 1
        cpx = _cpx
    return c


@lru_cache(maxsize=64)
def textpx(font: graphics.Font, text: str) -> int:
    return sum(characterwidth(font, ord(c)) for c in text) - 1


@lru_cache(maxsize=None)
def characterwidth(font: graphics.Font, cp: int) -> int:
    _cw = font.CharacterWidth(cp)
    if _cw == -1:
        _cw = font.CharacterWidth(65533)
        if _cw == -1:
            _cw = 0
    return _cw


@lru_cache(maxsize=64)
def fittext(text: str,
            avail_width: int,
            start: int,
            end: int,
            normalfont: graphics.Font,
            smallfont: graphics.Font,
            smallpxoffset: int = 0,
            alt_text: str = None,
            pattern: Optional[Pattern] = None,
            alt_retext_1: Optional[_retexttype] = None,
            alt_retext_2: Optional[_retexttype] = None
            ) -> Tuple[graphics.Font, str, int, int]:
    _font = normalfont
    _text = text
    _textpx = textpx(_font, _text)
    _roff = 0
    if _textpx > avail_width:
        shownchars_normal = propscroll(normalfont, _text, start, end)
        shownchars_small = propscroll(smallfont, _text, start, end)
        _search = pattern.search(_text) if pattern is not None else None
        if _search is not None:
            _text = alt_retext_1(_search)
            shownchars_normal = propscroll(normalfont, _text, start, end)
            shownchars_small = propscroll(smallfont, _text, start, end)
            if shownchars_small < len(_text):
                _text = alt_retext_2(_search)
                shownchars_normal = propscroll(normalfont, _text, start, end)
                shownchars_small = propscroll(smallfont, _text, start, end)
        elif alt_text is not None and shownchars_small < len(_text):
            _text = _text.replace(" ", "")
            shownchars_normal = propscroll(normalfont, _text, start, end)
            shownchars_small = propscroll(smallfont, _text, start, end)
            if shownchars_small < len(_text):
                _text = alt_text
                shownchars_normal = propscroll(normalfont, _text, start, end)
                shownchars_small = propscroll(smallfont, _text, start, end)
        if shownchars_small > shownchars_normal and not _text[shownchars_small-1] in {'(', '/'}:
            _text = _text[:shownchars_small]
            _font = smallfont
            _roff = smallpxoffset
        else:
            _text = _text[:shownchars_normal]
            _font = normalfont
        _textpx = textpx(_font, _text)
    return _font, _text, _textpx, _roff
