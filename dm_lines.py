# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from functools import lru_cache
from re import Pattern, match as re_match
from typing import List, Optional, Callable, Tuple, Dict, Match

from PIL import Image
from rgbmatrix import graphics
from rgbmatrix.core import FrameCanvas

from dm_drawstuff import clockstr_tt, drawppm_bottomleft, drawppm_bottomright
from dm_depdata import Departure, Meldung, MOT, trainMOT


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

    def __init__(self, lx, rx, symoffset, font, defaulttextcolor, symdict, bgcolor_t=None, initial_pretext=2, initial_posttext=5, pretext_zero_if_no_symbol=True, add_end_spacer=True):
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
            self.elements.append(self.__class__.__Element(text=''.join(_char for _char in meldung.text if characterwidth(self.font, ord(_char))),
                                                          symbol=_symbol,
                                                          textcolor=graphics.Color(*(int(meldung.color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))) if meldung.color else self.defaulttextcolor,
                                                          initial_pretext=self.initial_pretext if (_symbol is not None or not self.pretext_zero_if_no_symbol) else 0,
                                                          initial_posttext=self.initial_posttext))
        if self.elements:
            if self.elements[0].symbol is not None:
                self.startpos -= (self.elements[0].symbol.size[0] - 1)
            if self.add_end_spacer:
                self.elements[-1].initial_posttext = 0
                self.elements[-1].posttext = 0
                self.elements.append(self.__class__.__Element(text='', symbol=None, textcolor=self.defaulttextcolor, initial_pretext=0, initial_posttext=self.startpos-self.lx))

    def render(self, canvas: FrameCanvas, texty: int) -> None:
        if not self.elements:
            return
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
                    elemi = (elemi + 1) % len(self.elements)
                else: break
            else: break
        if self.startpos > self.lx: self.startpos -= 1


class SimpleScrollline:
    def __init__(self, lx, rx, symoffset, font, textcolor, symtextspacing=1, forcescroll=False, noscroll=False):
        self.lx = lx
        self.rx = rx
        self.symoffset = symoffset
        self.font = font
        self.textcolor = textcolor
        self.symtextspacing = symtextspacing
        self.forcescroll = forcescroll
        self.noscroll = noscroll

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


@dataclass
class CountdownOptions:
    font: graphics.Font
    cancelled_symbol: Image.Image
    mot_symbols: Dict[MOT, Image.Image]
    mot_coloured_symbols: Dict[graphics.Color, Dict[MOT, Image.Image]]
    min_symbol: Image.Image
    min_coloured_symbols: Dict[graphics.Color, Image.Image]
    mindelay: int
    minslightdelay: int
    maxmin: int
    zerobus: bool
    mintext: bool
    minoffset: int


@dataclass
class PlatformOptions:
    width: int
    textColor: graphics.Color
    texthighlightColor: graphics.Color
    normalFont: graphics.Font
    smallFont: graphics.Font
    normalsmalloffset: int


@dataclass
class RealtimeColors:
    no_realtime: graphics.Color
    no_delay: graphics.Color
    slight_delay: graphics.Color
    high_delay: graphics.Color
    negative_delay: graphics.Color


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
            realtimecolors: RealtimeColors):
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
        self.realtimecolors = realtimecolors

        self.dep: Optional[Departure] = None

        self.linenum_font: graphics.Font = self.linenumopt.normalFont
        self.linenum_str: str = ""
        self.linenum_xpos: int = 0
        self.linenum_verticaloffset: int = 0

        self.platform_display: bool = False
        self.platform_font: graphics.Font
        self.platform_str: str
        self.platform_xpos: int
        self.platform_verticaloffset: int
        self.platform_color: graphics.Color

        self.rtcolor: graphics.Color = self.realtimecolors.no_realtime
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

        self.linenum_font, self.linenum_str, linenum_px, self.linenum_verticaloffset = fittext(
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
        self.linenum_xpos = self.linenum_max - linenum_px + (linenum_px == self.linenumopt.width)

        if self.dep.realtime:
            if self.dep.delay >= self.countdownopt.mindelay or self.dep.cancelled:
                self.rtcolor = self.realtimecolors.high_delay
            elif self.dep.delay >= self.countdownopt.minslightdelay:
                self.rtcolor = self.realtimecolors.slight_delay
            elif self.dep.delay < 0:
                self.rtcolor = self.realtimecolors.negative_delay
            else:
                self.rtcolor = self.realtimecolors.no_delay
        else:
            self.rtcolor = self.realtimecolors.no_realtime

        self.platform_display = self.platformopt is not None and self.platformopt.width > 0 and self.dep.platformno
        if self.platform_display:
            platprefix = self.dep.platformtype or ("Gl." if self.dep.mot in trainMOT else "Bstg.")
            self.platform_font, self.platform_str, platpx, self.platform_verticaloffset = fittext(
                platprefix + str(self.dep.platformno),
                self.platformopt.width,
                self.platform_min,
                self.platform_max,
                self.platformopt.normalFont,
                self.platformopt.smallFont,
                smallpxoffset=self.platformopt.normalsmalloffset,
                alt_text=str(self.dep.platformno))
            platformchanged = self.dep.platformno_planned and (self.dep.platformno_planned != self.dep.platformno)
            self.platform_color = self.platformopt.texthighlightColor if platformchanged else self.platformopt.textColor
            self.platform_xpos = self.platform_max - platpx + 1

        self.dirtextcolor = self.texthighlightColor if self.dep.earlytermination else self.textColor

    def render(self, canvas: FrameCanvas, texty: int, blinkon: bool) -> None:
        if self.dep is None:
            return

        if self.linenumopt.drawbg:
            for y in range(texty-self.linenumopt.height, texty):
                graphics.DrawLine(canvas, self.linenum_min, y, self.linenum_max, y, self.linenumopt.bgColor)

        graphics.DrawText(canvas, self.linenum_font, self.linenum_xpos, texty-self.linenum_verticaloffset, self.linenumopt.fgColor, self.linenum_str)

        directionpixel = self.deptime_x_max - self.direction_xpos
        timeoffset = 0

        if self.dep.cancelled:
            drawppm_bottomright(canvas, self.countdownopt.cancelled_symbol, self.deptime_x_max, texty, transp=True)
            timeoffset += self.countdownopt.cancelled_symbol.size[0]
        elif self.dep.disp_countdown > self.countdownopt.maxmin:
            timestr = clockstr_tt(self.dep.deptime.timetuple())
            timestrpx = textpx(self.countdownopt.font, timestr)
            graphics.DrawText(canvas, self.countdownopt.font, self.deptime_x_max - timestrpx + 1, texty, self.rtcolor, timestr)
            timeoffset += timestrpx
        elif blinkon and self.dep.disp_countdown == 0 and self.countdownopt.zerobus:
            drawppm_bottomright(canvas, self.countdownopt.mot_coloured_symbols[self.dep.mot][self.rtcolor], self.deptime_x_max, texty, transp=True)
            timeoffset += self.countdownopt.mot_symbols[self.dep.mot].size[0]
        elif self.dep.disp_countdown or blinkon:
            timestr = str(self.dep.disp_countdown)
            timestrpx = textpx(self.countdownopt.font, timestr)
            graphics.DrawText(canvas, self.countdownopt.font, self.deptime_x_max - timestrpx - ((self.countdownopt.min_symbol.size[0]-1+self.countdownopt.minoffset) if self.countdownopt.mintext else -1), texty, self.rtcolor, timestr)
            timeoffset += timestrpx
            if self.countdownopt.mintext:
                drawppm_bottomright(canvas, self.countdownopt.min_coloured_symbols[self.rtcolor], self.deptime_x_max, texty, transp=True)
                timeoffset += self.countdownopt.min_symbol.size[0] + self.countdownopt.minoffset

        if self.platform_display:
            graphics.DrawText(canvas, self.platform_font, self.platform_xpos, texty-self.platform_verticaloffset, self.platform_color, self.platform_str)

        directionpixel -= (timeoffset + self.space_direction_countdown*bool(timeoffset))
        directionlimit = propscroll(self.font, self.dep.disp_direction, self.direction_xpos, self.direction_xpos+directionpixel)
        graphics.DrawText(canvas, self.font, self.direction_xpos, texty, self.dirtextcolor, self.dep.disp_direction[:directionlimit])


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
