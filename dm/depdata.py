# -*- coding: utf-8 -*-
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from csv import reader
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from json import dumps as json_dumps, loads as json_loads
from re import compile as re_compile
from requests import get
from requests.exceptions import RequestException
from subprocess import call
from time import asctime, sleep
from typing import Set, List, Dict, Callable, Union, Optional, Any, Tuple, Iterable
import xml.etree.ElementTree as ET

from loguru import logger


@dataclass
class Meldung:
    symbol: str
    text: str
    color: Optional[str] = None
    efa: bool = False
    # blocking: bool = False

    def __post_init__(self):
        if self.text is None:
            self.text = ""


class MOT(Enum):
    TRAIN = 1
    HISPEED = 2
    TRAM = 3
    BUS = 4
    HANGING = 5

trainTMOTefa = {0, 1, 13, 14, 15, 16, 18}
trainMOT = {MOT.TRAIN, MOT.HISPEED}


@dataclass
class Departure:
    linenum: str
    direction: str
    direction_planned: str
    deptime: datetime
    deptime_planned: datetime
    realtime: bool
    delay: int = 0  # minutes
    messages: Union[List[str], List[Meldung]] = field(default_factory=list)  # str als Zwischenschritt
    coursesummary: Optional[str] = None
    mot: Optional[MOT] = None
    # accessibility?
    # operator?
    platformno: Optional[str] = None
    platformno_planned: Optional[str] = None
    platformtype: Optional[str] = None
    stopname: Optional[str] = None
    stopid: Optional[str] = None
    place: Optional[str] = None
    cancelled: Optional[bool] = None
    earlytermination: Optional[bool] = None
    headsign: Optional[str] = None
    color: Optional[str] = None
    arrtime: Optional[datetime] = None
    arrtime_planned: Optional[datetime] = None
    disp_countdown: Optional[int] = None  # minutes
    disp_linenum: Optional[str] = None
    disp_direction: Optional[str] = None


type_data = Dict[str, Any]
type_depmsgdata = Tuple[List[Departure], List[Meldung], type_data]

def readefaxml(root: ET.Element, tz: timezone,
               ignore_infoTypes: Optional[Set] = None, ignore_infoIDs: Optional[Set] = None,
               content_for_short_titles: bool = True) -> type_depmsgdata:
    deps: List[Departure] = []
    stop_messages: List[Meldung] = []
    # (itdStopInfoList bei Abfahrten bzw. infoLink bei itdOdvName)
    # treten (alle?) auch bei einzelnen Abfahrten auf.. erstmal keine daten hierbei
    # evtl. auslesen und schauen, was wirklich haltbezogen ist und nicht anderswo dabei ist

    _itdOdv = root.find('itdDepartureMonitorRequest').find('itdOdv')
    _itdOdvPlace = _itdOdv.find('itdOdvPlace')
    if _itdOdvPlace.get('state') != "identified":
        return deps, stop_messages, {}
    place = _itdOdvPlace.findtext('odvPlaceElem')

    _itdOdvName = _itdOdv.find('itdOdvName')
    if _itdOdvName.get('state') != "identified":
        return deps, stop_messages, {}
    _itdOdvNameElem = _itdOdvName.find('odvNameElem')
    stopname = _itdOdvNameElem.text or _itdOdvNameElem[0].tail or next((t.tail for t in _itdOdvNameElem if t is not None), None)

    for dep in root.iter('itdDeparture'):
        servingline = dep.find('itdServingLine')
        _itdNoTrain = servingline.find('itdNoTrain')
        _itdNoTrainName = _itdNoTrain.get('name', '')
        linenum = servingline.attrib['number']
        if linenum.endswith(" "+_itdNoTrainName):
            linenum = linenum.replace(" "+_itdNoTrainName, "")
        countdown = int(dep.attrib['countdown'])

        isrealtime = bool(int(servingline.attrib['realtime']))
        if isrealtime:
            delay = int(_itdNoTrain.attrib['delay'])
        else:
            delay = 0
        cancelled = delay == -9999

        messages: List[str] = []
        genAttrList = dep.find('genAttrList')

        direction_planned = servingline.get('direction')
        direction_actual = direction_planned
        earlytermination = False
        _earlytermv = genAttrList.findtext("./genAttrElem[name='EarlyTermination']/value") if genAttrList else None
        if (not cancelled) and _earlytermv:
            direction_actual = _earlytermv
            earlytermination = True
        # Beobachtungen bzgl. Steigänderung:
        # genAttrElem mit name platformChange und value changed
        # platform bei itdDeparture entspricht originaler, platformName der neuen..
        # haben aber eigentlich unterschiedliche Bedeutungen
        # (bei Bussen steht dann da z. B. "Bstg. 1" in platformName
        # Auseinanderhalten eigentlich sinnvoll, bei platformChange muss aber wohl ne Ausnahme gemacht werden
        # weiter beobachten, wie sowas in weiteren Fällen aussieht..

        # Sowas wie "Aachen, Hbf,Aachen" verbessern
        _ds = direction_actual.split(",")
        if len(_ds) > 1 and direction_actual.startswith(_ds[-1].strip()):
            disp_direction = ",".join(_ds[:-1])
        else:
            disp_direction = direction_actual

        itddatetime = dep.find('itdDateTime')
        itddatea = itddatetime.find('itdDate').attrib
        itdtimea = itddatetime.find('itdTime').attrib
        deptime_planned = datetime(int(itddatea['year']), int(itddatea['month']), int(itddatea['day']), int(itdtimea['hour']), int(itdtimea['minute']), tzinfo=tz)
        deptime = deptime_planned
        if isrealtime and not cancelled:
            itdrtdatetime = dep.find('itdRTDateTime')
            itdrtdatea = itdrtdatetime.find('itdDate').attrib
            itdrttimea = itdrtdatetime.find('itdTime').attrib
            deptime = datetime(int(itdrtdatea['year']), int(itdrtdatea['month']), int(itdrtdatea['day']), int(itdrttimea['hour']), int(itdrttimea['minute']), tzinfo=tz)

        for _infoLink in dep.iter('infoLink'):
            if ((ignore_infoTypes and _infoLink.findtext("./paramList/param[name='infoType']/value") in ignore_infoTypes)
                    or (ignore_infoIDs and _infoLink.findtext("./paramList/param[name='infoID']/value") in ignore_infoIDs)):
                continue
            _iLTtext = _infoLink.findtext('infoLinkText')
            if _iLTtext:
                # kurze, inhaltslose (DB-)Meldungstitel
                if content_for_short_titles and _iLTtext in {"Störung.", "Bauarbeiten.", "Information."}:
                    _infoLink_infoText = _infoLink.find('infoText')
                    if _infoLink_infoText is None: continue
                    _iLiTcontent = _infoLink_infoText.findtext('content')
                    if _iLiTcontent:
                        messages.append(f"{_iLTtext[:-1]}: {_iLiTcontent}")
                        continue
                    # else: weiter, nächste Zeile
                messages.append(_iLTtext)
            else:
                _infoLink_infoText = _infoLink.find('infoText')
                if _infoLink_infoText is None: continue
                _iLiTsubject = _infoLink_infoText.findtext('subject')
                _iLiTsubtitle = _infoLink_infoText.findtext('subtitle')
                _msg = ""
                if _iLiTsubject: _msg += (_iLiTsubject + (" " if _iLiTsubject.endswith(":") else ": "))
                if _iLiTsubtitle: _msg += _iLiTsubtitle
                if _msg: messages.append(_msg)

        itdNoTrainText = servingline.findtext('itdNoTrain')
        if itdNoTrainText:
            messages.append(f"{linenum}: {itdNoTrainText}")

        mot = None
        motType = int(servingline.get('motType'))
        if motType in {5, 6, 7, 10, 17, 19}:
            mot = MOT.BUS
        elif motType in {0, 1, 13, 14, 15, 16, 18}:
            if motType in {15, 16} or (genAttrList and any(s in {"HIGHSPEEDTRAIN", "LONG_DISTANCE_TRAINS"} for s in (x.findtext('value') for x in genAttrList.findall('genAttrElem')))):
                mot = MOT.HISPEED
            else:
                mot = MOT.TRAIN
        elif motType in {2, 3, 4, 8}:
            mot = MOT.TRAM
        elif motType == 11:
            mot = MOT.HANGING

        deps.append(Departure(linenum=linenum,
                              direction=direction_actual,
                              direction_planned=direction_planned,
                              deptime=deptime,
                              deptime_planned=deptime_planned,
                              realtime=isrealtime,
                              delay=delay,
                              messages=messages,
                              coursesummary=servingline.findtext('itdRouteDescText'),
                              mot=mot,
                              platformno=dep.get('platform'),
                              platformtype=dep.get('pointType', ""),
                              stopname=(dep.get('nameWO') or stopname),
                              stopid=dep.get('gid'),
                              place=place,
                              cancelled=cancelled,
                              earlytermination=earlytermination,
                              disp_countdown=countdown,
                              disp_direction=disp_direction))
    return deps, stop_messages, {}


type_getpayload = Dict[str, Union[str, int, Iterable[Union[str, int]]]]

def getefadeps(serverurl: str, timeout: Union[int, float], ifopt: str, limit: int, tz: timezone,
        userealtime: bool = True, exclMOT: Optional[Set[int]] = None, inclMOT: Optional[Set[int]] = None,
        ignore_infoTypes: Optional[Set] = None, ignore_infoIDs: Optional[Set] = None, content_for_short_titles: bool = True) -> type_depmsgdata:
    payload: type_getpayload = {'name_dm': ifopt, 'type_dm': 'any', 'mode': 'direct', 'useRealtime': int(userealtime), 'limit': str(limit)}
    if inclMOT:
        payload['includedMeans'] = inclMOT
    elif exclMOT:
        payload['excludedMeans'] = exclMOT
    r = get(serverurl, timeout=timeout, params=payload)
    r.raise_for_status()
    try:
        root = ET.fromstring(r.content)
        result = readefaxml(root, tz, ignore_infoTypes, ignore_infoIDs, content_for_short_titles)
    except Exception:
        logger.debug(f"request data:\n{r.content}")
        raise
    return result


def getlocaldeps(local_dep_path: str, limit: int, tz: timezone, lookbehind_sec: int = 135) -> type_depmsgdata:
    deps: List[Departure] = []
    logger.trace("getlocaldeps called")
    nowtime = datetime.now(tz)
    # in csv z. B. 2018-10-31;20:50:00;A.2;512;Hagen Stadtmitte/Volme Galerie
    with open(local_dep_path, 'r', encoding='utf-8') as depf:
        for deprow in reader(depf, delimiter=';'):
            deptime = ptstrptime(deprow[0], deprow[1], tz)
            if deptime < (nowtime - timedelta(seconds=lookbehind_sec)):
                continue
            arrtime = None
            deps.append(Departure(linenum=str(deprow[3]),
                                  direction=str(deprow[4]),
                                  direction_planned=str(deprow[4]),
                                  deptime=deptime,
                                  deptime_planned=deptime,
                                  realtime=False,
                                  messages=[],
                                  platformno=str(deprow[2]),
                                  # coursesummary=,
                                  # stopname=,
                                  # stopid=,
                                  # place=,
                                  # headsign=,
                                  arrtime=arrtime,
                                  arrtime_planned=arrtime))
            if len(deps) >= limit: break
    return deps, [], {}


# basiert hauptsächlich auf db-rest. code insgesamt noch kaum getestet
def readfptfjson(jsondata: List[Dict[str, Any]], limit: int,
        inclMOT: Optional[Set[MOT]] = None, exclMOT: Optional[Set[MOT]] = None,
        exclRemarkTypes: Optional[Set[str]] = None, exclRemarkCodes: Optional[Set[str]] = None,
        stripstart: Set[str] = {'Bus ', 'STR ', 'ABR ', 'ERB ', 'NWB ', 'WFB '}) -> type_depmsgdata:
    deps: List[Departure] = []
    for dep in jsondata:
        if len(deps) >= limit: break
        _line = dep.get("line")
        linenum = _line.get("name")
        for _s in stripstart:
            if linenum.startswith(_s):
                linenum = linenum.replace(_s, "")
        mot = _line.get("product")
        if mot in {"bus"}:
            mot = MOT.BUS
        elif mot in {"nationalExp", "national"}:
            mot = MOT.HISPEED
        elif mot in {"tram", "subway"}:
            mot = MOT.TRAM
        elif _line.get("mode") == "train":
            # regional, suburban usw.
            mot = MOT.TRAIN
        else:
            mot = None
        if (exclMOT and mot in exclMOT) or (inclMOT and mot not in inclMOT):
            continue
        _stop = dep.get("stop")
        _station = _stop.get("station")
        if _station:
            stopname = _station.get("name")
        else:
            stopname = _stop.get("name")
        delaymins = None
        delaysecs = dep.get("delay")
        if delaysecs is not None: delaymins = int(round(delaysecs / 60))
        cancelled = dep.get("cancelled")
        isrealtime = delaysecs is not None or cancelled == True
        deptime = dep.get("when")
        # todo: anpassen auf scheduledWhen und realtimeWhen??
        if deptime is None:
            _former = dep.get("formerScheduledWhen")
            _scheduled = dep.get("scheduledWhen")
            if _former is None and _scheduled is None:
                logger.error(f"fptf departure without any time, skipping: {dep}")
                continue
            deptime = datetime.fromisoformat(_scheduled or _former)
            deptime_planned = deptime
        else:
            deptime = datetime.fromisoformat(deptime)
            if delaysecs is not None:
                deptime_planned = deptime - timedelta(seconds=delaysecs)
            else:
                deptime_planned = deptime

        direction = dep.get("direction")
        messages = []
        for msg in dep.get("remarks"):
            # eventuell "heute nur bis ..." auswerten zu den variablen s. u.?
            _msg_type = msg.get("type")
            _msg_code = msg.get("code")  # auswerten?
            if (exclRemarkTypes and _msg_type in exclRemarkTypes) or (exclRemarkCodes and _msg_code in exclRemarkCodes):
                continue
            _msg_summary = msg.get("summary")
            if _msg_summary and _msg_summary.endswith('.'):
                _msg_summary = _msg_summary[:-1]
            _msg_text = msg.get("text")
            messages.append((((_msg_summary+": ") if _msg_summary else "") + _msg_text).replace("\n", " "))
        # wie wird das dargestellt?
        direction_planned = direction
        earlytermination = None
        deps.append(Departure(linenum=linenum,
                              direction=direction,
                              direction_planned=direction_planned,
                              deptime=deptime,
                              deptime_planned=deptime_planned,
                              realtime=isrealtime,
                              delay=delaymins,
                              messages=messages,
                              #coursesummary=...,
                              mot=mot,
                              platformno=dep.get("platform"),
                              platformno_planned=dep.get("formerScheduledPlatform"),
                              stopname=stopname,
                              stopid=_stop.get("id"),
                              cancelled=cancelled,
                              earlytermination=earlytermination))
    return deps, [], {}


def getfptfrestdeps(serverurl: str, timeout: Union[int, float],
        station_id: str, limit: int, direction: Optional[str] = None,
        inclMOT: Optional[Set[MOT]] = None, exclMOT: Optional[Set[MOT]] = None,
        exclRemarkTypes: Optional[Set[str]] = None, exclRemarkCodes: Optional[Set[str]] = None,
        duration: int = 120, language: str = "de") -> type_depmsgdata:
    payload: type_getpayload = {'language': language, 'duration': duration}
    if direction:
        payload['direction'] = direction
    r = get(f"{serverurl}/stations/{station_id}/departures", timeout=timeout, params=payload)
    r.raise_for_status()
    try:
        requestdata = r.json()
        result = readfptfjson(requestdata, limit, inclMOT, exclMOT, exclRemarkTypes, exclRemarkCodes)
    except Exception:
        logger.debug(f"request data:\n{r.content}")
        raise
    return result


def getextmsgdata(url: str, timeout: Union[int, float], save_msg_path: Optional[str] = None) -> type_depmsgdata:
    messages: List[Meldung] = []
    data: type_data = {}
    r = get(url, timeout=timeout)
    if r.status_code == 404:
        logger.warning(f"ignoring 404 for {url}, returning nothing")
    else:
        r.raise_for_status()
        try:
            requestdata = r.json()
            # example:
            # {
            #     "messages": [
            #                     {
            #                         "symbol": "info",
            #                         "text": "Testinformation",
            #                         "color": undefined
            #                     },
            #                     {
            #                         "symbol": "ad",
            #                         "text": "Testwerbung",
            #                         "color": "#00FFFF"
            #                     }
            #                 ],
            #     "config": {
            #                   "brightness": 15
            #               },
            #     "command": "shutdown 19:30"
            # }
            # ("command" sollte nach der "auswertung" wieder leer gesetzt werden..)
            # todo: mit dem GET z. B. logdaten mitsenden; auf dem Server irgendwas laufen haben
            # , was mit https+basicauth+sqlite+weboberflaeche oderso die konfiguration/beobachtung ermoeglicht
            # + guten weg finden, run.env/run.sh anzupassen, langfristig
            _json_msg = requestdata.get("messages")
            if _json_msg is not None:
                messages = [Meldung(symbol=msg.get("symbol"), text=msg.get("text"), color=msg.get("color")) for msg in _json_msg]
            if save_msg_path:
                _saved = ""
                _dump = json_dumps(_json_msg or "[]")
                try:
                    with open(save_msg_path, 'r') as f:
                        _saved = f.read()
                except IOError:
                    pass
                if _saved != _dump:
                    with open(save_msg_path, 'w') as f:
                       f.write(_dump)
            _json_config = requestdata.get("config")
            if _json_config is not None:
                data = _json_config
            command = requestdata.get("command")
            if command:
                if command.startswith("shutdown "):
                    _s = command.split(" ")
                    if len(_s) == 2:
                        logger.info(f"calling {_s}")
                        call(_s)
                    else:
                        logger.warning(f"unknown shutdown command: {_s}")
                elif command == "rebootnow":
                    logger.info("rebooting")
                    call(["reboot"])
                elif command == "reload":
                    logger.info("requested reload")
                    if call(["systemctl", "is-active", "matrix"]) == 0:
                        call(["systemctl", "restart", "matrix"])
                    else:
                        call(["systemctl", "start", "matrix"])
                        raise KeyboardInterrupt
                elif command == "gitpull":
                    _e = call(["sudo", "-u", "pi", "git", "pull"])
                    if _e == 0:
                        logger.success("git pull")
                    else:
                        logger.warning(f"git pull failed with exit code {_e}")
                else:
                    logger.warning(f"unknown command: {command}")
        except Exception:
            logger.debug(f"request data:\n{r.content}")
            raise
    return [], messages, data


def getlocalmsg(save_msg_path: str) -> type_depmsgdata:
    messages: List[Meldung] = []
    logger.trace("getlocalmsg called")
    try:
        with open(save_msg_path, 'r') as f:
            _saved = f.read()
    except IOError:
        pass
    else:
        _json_msg = json_loads(_saved)
        messages = [Meldung(symbol=msg.get("symbol"), text=msg.get("text"), color=msg.get("color")) for msg in _json_msg]
    return [], messages, {}


@dataclass
class CallableWithKwargs:
    callable: Callable[..., type_depmsgdata]
    kwargs: Dict[str, Any]
    retries: int

@dataclass
class DataSource:
    name: str
    critical: bool = True
    to_call: List[CallableWithKwargs] = field(default_factory=list)

class GetdepsEndAll(Exception):
    pass


def _getdeps_depf_list(datasource: DataSource, sleep_on_retry_factor: float = 0.5) -> Optional[type_depmsgdata]:
    for call_args in datasource.to_call:
        _result = None
        _namestr = f"'{datasource.name}'{call_args.callable}{call_args.kwargs}"
        retryc = 0
        while retryc <= call_args.retries:
            if retryc and sleep_on_retry_factor:
                sleep(retryc * sleep_on_retry_factor)
            try:
                _result = call_args.callable(**call_args.kwargs)
                break
            except Exception as e:
                if isinstance(e, RequestException):
                    logger.warning(f"{_namestr} retry{retryc}\n{e.__class__.__name__}, {e}")
                else:
                    logger.exception(f"{_namestr} retry{retryc}")
                retryc += 1
        if _result is not None:
            return _result
        logger.warning(f"{_namestr} failed {call_args.retries+1} times, continuing with next callable+kwargs if exists")
    return None


def getdeps(
        datasources: List[DataSource],
        getdeps_timezone: timezone,
        getdeps_lines: int,
        getdeps_placelist: Optional[List[str]] = None,
        getdeps_mincountdown: int = -9,
        extramsg_messageexists: Optional[bool] = None,
        extramsg_messagelines: int = 1,
        delaymsg_enable: bool = True,
        delaymsg_mindelay: int = 1,
        etermmsg_enable: bool = True,
        etermmsg_only_visible: bool = True,
        nodepmsg_enable: bool = True,
        nortmsg_limit: Optional[int] = 20
        ) -> type_depmsgdata:
    deps: List[Departure] = []
    messages: List[Meldung] = []
    data: type_data = {}
    nowtime = datetime.now(getdeps_timezone)
    with ThreadPoolExecutor() as tpe:
        fs = {tpe.submit(_getdeps_depf_list, _ds): _ds for _ds in datasources}
        for f in as_completed(fs):
            _result = f.result()
            datasource = fs[f]
            if _result is None:
                logger.error(f"'{datasource.name}' failed, " + ("raising from getdeps now!" if datasource.critical else "going on ..."))
                if datasource.critical:
                    raise GetdepsEndAll()
            else:
                _result_deps, _result_msgs, _result_data = _result
                # logger.success(datasource.name)
                deps.extend(_result_deps)
                # for dep in _result_deps:
                #     logger.success(f"{dep.deptime}\t{dep.linenum}\t{dep.direction}")
                messages.extend(_result_msgs)
                # for msg in _result_msgs:
                #     logger.success(str(msg))
                data.update(_result_data)
                # for _k, _v in _result_data.items():
                #     logger.success(f"{_k}:\t{_v}")
                logger.trace(f"'{datasource.name}' returned {len(_result_deps)} deps"
                             + f" ({sum(dep.realtime for dep in _result_deps)} rt)" * bool(_result_deps)
                             + f", {len(_result_msgs)} msgs, {len(_result_data)} data items")
    extramsg_messageexists = bool(messages)
    # allg. Datenverschoenerung
    for dep in deps:
        # ggf. anders runden?
        # dep.disp_countdown = dep.disp_countdown if dep.disp_countdown is not None else int(round((dep.deptime-nowtime).total_seconds()/60))
        dep.disp_countdown = dep.disp_countdown if dep.disp_countdown is not None else int((dep.deptime-nowtime.replace(second=0, microsecond=0)).total_seconds()/60)
        dep.disp_linenum = (dep.disp_linenum or dep.linenum)
        if not dep.disp_direction:
            if dep.headsign:
                dep.disp_direction = dep.headsign.replace("\n", "/")
            else:
                dep.disp_direction = dep.direction
        if getdeps_placelist:
            for place in getdeps_placelist:  # auslagern, feiner machen, +abk.verz.?
                dep.disp_direction = dep.disp_direction.replace(place, "")
        if dep.mot is None:
            dep.mot = MOT.BUS
        if dep.delay is None:
            dep.delay = 0
    sorteddeps = sorted([dep for dep in deps if (dep.disp_countdown or 0) >= getdeps_mincountdown],
                        key=lambda dep: (dep.disp_countdown, not dep.cancelled, -dep.delay, not dep.earlytermination))
    if _makemessages(sorteddeps, getdeps_lines - extramsg_messagelines): extramsg_messageexists = True
    messages.extend(_extramessages(sorteddeps, getdeps_lines,
                                   extramsg_messageexists, extramsg_messagelines,
                                   delaymsg_enable, delaymsg_mindelay,
                                   etermmsg_enable, etermmsg_only_visible,
                                   nodepmsg_enable, nortmsg_limit))  # erweitert selber schon die dep.messages
    return sorteddeps, messages, data

linenumpattern = re_compile('([a-zA-Z]+) *([0-9]+)')

def _makemessages(sorteddeps: List[Departure], depline_count: int) -> bool:
    # Mehrfach vorkommende messages reduzieren, weiterhin doppelte vermeiden
    _msgsets: defaultdict = defaultdict(lambda: [set(), set()])
    for di, dep in enumerate(sorteddeps[:depline_count]):
        _lnsearchs: Set[str] = {dep.disp_linenum, dep.linenum, dep.disp_linenum.replace(" ", ""), dep.linenum.replace(" ", "")}
        _search = linenumpattern.search(dep.disp_linenum)
        if _search is not None:
            _lnsearchs.add(_search.group(1)+_search.group(2))
            _lnsearchs.add(_search.group(1)+" "+_search.group(2))
        for mi, _msg in ((mi, _msg) for mi, _msg in enumerate(dep.messages) if not any(_ln in _msg for _ln in _lnsearchs)):
            _msgsets[_msg][0].add(dep.disp_linenum)
            _msgsets[_msg][1].add((di, mi))
    for di, dep in enumerate(sorteddeps[:depline_count]):
        for _msg, (_linenums, _indices) in _msgsets.items():
            for mi in (mi for set_di, mi in _indices if set_di == di):
                dep.messages[mi] = f"{', '.join(sorted(_linenums))}: {_msg}"
    visible_message_exists = False
    for di, dep in enumerate(sorteddeps):
        for mi, msg in enumerate(dep.messages):
            if di < depline_count:
                visible_message_exists = True
            dep.messages[mi] = Meldung(symbol="info", text=msg, efa=True)
    return visible_message_exists


def _extramessages(sorteddeps: List[Departure], departure_lines: int,
                   message_exists: bool, message_lines: int,
                   delaymsg_enable: bool = True, delaymsg_mindelay: int = 1,
                   etermmsg_enable: bool = True, etermmsg_only_visible: bool = True,
                   nodepmsg_enable: bool = True, nortmsg_limit: Optional[int] = 20) -> List[Meldung]:
    general_messages: List[Meldung] = []
    delaymsg_i: Set[int] = set()
    etermmsg_i: Set[int] = set()
    hidden_i = set(range(departure_lines - message_lines, departure_lines))
    message_from_i = min(hidden_i, default=departure_lines)
    pot_last_dep_i = message_from_i - 1
    last_dep_i = (message_from_i if message_exists else departure_lines) - 1
    message_needed = message_exists
    for di, dep in enumerate(sorteddeps):
        if (delaymsg_enable and dep.delay >= delaymsg_mindelay and di >= message_from_i
                and dep.deptime_planned <= sorteddeps[pot_last_dep_i if di in hidden_i else last_dep_i].deptime):
            delaymsg_i.add(di)
            if di > last_dep_i:
                message_needed = True
        if etermmsg_enable and dep.earlytermination:
            etermmsg_i.add(di)
    if message_needed:
        for delay_di in sorted(delaymsg_i):
            dep = sorteddeps[delay_di]
            dephr, depmin = dep.deptime_planned.timetuple()[3:5]
            delaystr = (f"{dep.delay // 60}:{(dep.delay % 60):02} std") if dep.delay > 60 else (f"{dep.delay} min")
            if delay_di in etermmsg_i:
                etermmsg_i.remove(delay_di)
                _txt = f"{dep.disp_linenum}→{dep.direction_planned} ({dephr:02}:{depmin:02}) heute {delaystr} später und nur bis {dep.disp_direction}"
            else:
                _txt = f"{dep.disp_linenum}→{dep.disp_direction} ({dephr:02}:{depmin:02}) heute {delaystr} später"
            # erstmal das gleiche symbol, eigenes sah nach etwas zu viel aus..
            dep.messages.append(Meldung(symbol="delay", text=_txt))
    for eterm_di in sorted(etermmsg_i):
        # >= departure_lines weil wenn es durch eine Meldung verdeckt wird ist es auch ok, "überschreibend"..
        if etermmsg_only_visible and eterm_di >= departure_lines:
            break
        dep = sorteddeps[eterm_di]
        dephr, depmin = dep.deptime_planned.timetuple()[3:5]
        # delaystr: für die sichtbaren (weil schon bald) aber verspäteten Fahrten
        # ggf. optional oder ersetzen durch anzeige in der Zeile selbst oderso..
        delaystr = f", heute +{dep.delay}" if dep.delay > 0 else ""
        dep.messages.append(Meldung(symbol="earlyterm", text=f"{dep.disp_linenum}→{dep.direction_planned} ({dephr:02}:{depmin:02}{delaystr}) fährt nur bis {dep.disp_direction}"))
    if sorteddeps:
        if nortmsg_limit is not None and not any(dep.realtime for dep in sorteddeps) and sorteddeps[0].disp_countdown <= nortmsg_limit:
            general_messages.append(Meldung(symbol="nort", text="aktuell sind keine Echtzeitdaten vorhanden..."))
    else:
        if nodepmsg_enable:
            general_messages.append(Meldung(symbol="nodeps", text="aktuell keine Abfahrten"))
    return general_messages


def ptstrptime(datestr: str, timestr: str, tz: Optional[timezone] = None) -> datetime:
    ts = timestr.split(":")
    hr = int(ts[0])
    dateinc = 0
    if hr >= 24:
        ts[0] = str(hr % 24)
        dateinc = hr // 24
    dt = datetime.strptime(datestr + " " + ":".join(ts), '%Y-%m-%d %H:%M:%S') + timedelta(days=dateinc)
    if tz:
        dt = dt.replace(tzinfo=tz)
    return dt
