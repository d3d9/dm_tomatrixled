# -*- coding: utf-8 -*-

from . import config
from dataclasses import dataclass
from datetime import datetime
from time import time
from subprocess import check_output
from sys import stdout
from typing import Callable, Optional

from requests import post
from loguru import logger

from yaml import load as yaml_load
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

_start_time = int(time())

def handle_restart_application(action):
    check_output("systemctl restart matrix", shell=True)
    return False

def handle_restart_system(action):
    check_output("reboot now", shell=True)
    return False

'''
def handle_update_application(action):
    return False

def handle_configuration(action):
    raw_yaml = action["data"]
    assert raw_yaml
    config.raw = raw_yaml
    logger.info("current config version: " + config.version)
    configuration = yaml_load(raw_yaml, Loader=Loader)
    config.configuration = configuration
    config.version = configuration.get("version")
    return config.version
'''

def check_restart_application(action):
    action_ts = int(action["timestamp"])
    return _start_time > action_ts

def check_restart_system(action):
    action_ts = int(action["timestamp"])
    start_ts = int(check_output('date -d "$(</proc/uptime awk \'{print $1}\') seconds ago" "+%s"', shell=True).decode(stdout.encoding).strip())
    return start_ts > action_ts

'''
def check_update_application(action):
    return False

def check_configuration(action):
    return False
'''


@dataclass
class ActionType:
    name: str
    handle: Callable  # return False, wenn action nicht direkt completed. sonst True oder daten
    completed: Optional[Callable] = None  # nur notwendig, wenn handle False returnen kann. sonst True oder daten

_actions = [
    ActionType("restart_application", handle_restart_application, check_restart_application),
    ActionType("restart_system", handle_restart_system, check_restart_system),
    # ActionType("update_application", handle_update_application, check_update_application),
    # ActionType("configuration", handle_configuration),  # , check_configuration),
    # ActionType("screenshot", handle_screenshot, check_screenshot)
]

actions = {obj.name: obj for obj in _actions}

def _action_file(name):
    fp = name
    def _action_file_fn(content: Optional[str] = None):
        if content is None:
            try:
                with open(fp, 'r') as f:
                    return f.read()
            except IOError:
                return ''
        with open(fp, 'w') as f:
            f.write(content)
    return _action_file_fn

pending_action = _action_file('.pending_action')  # sobald empfangen. leeren sobald verarbeitung beendet (.completed_action) und request an KA gemacht wurde.
working_action = _action_file('.working_action')  # setzen wenn verarbeitung beginnt, bei fehler/crash leeren. also gesetzt nur während aktiver verarbeitung und ausstehender completion
completed_action = _action_file('.completed_action')  # setzen wenn verarbeitung beendet und sobald request an KA zsm mit pending leeren
completed_data = _action_file('.completed_data')

def check_action(action, url, dfi_id, key):
    if action is False:
        if (pending_uuid := pending_action()):
            logger.info(f"unsetting action data, previously pending: {pending_uuid}")
            pending_action('')
            working_action('')
            completed_action('')
            completed_data('')
        return False

    # logger.info(f"checking action {action}")
    uuid = action['uuid']
    _type = action['type']
    if _type not in actions:
        raise ValueError(f"unknown action type {_type} (action {action})")
    action_type = actions[_type]
    data = action['data']

    def check_action_completion():
        if (action_type.completed is None): raise ValueError(f"action of type {_type} is supposed to be completed instantly (action {action})")
        return action_type.completed(action)

    def handle_action():  
        return action_type.handle(action)  # returns False, wenn action nicht direkt completed wurde (check notwendig)

    def handle_completion(data=''):
        working_action('')
        completed_action(uuid)
        if not data:
            data = completed_data()
        elif data is True:
            data = ''
        else:
            data = str(data)  # zukünftig ändern?
            # TODO kill handler setzen um completed_data(data) zu machen 
        try:
            payload = {"action": "dfi_action_completed", "id": dfi_id, "key": key, "uuid": uuid}
            if data:
                payload["data"] = data
            r = post(url, data=payload)
            r.raise_for_status()
            response = r.json()
            new_action = response.get('action')
        except Exception as e:
            logger.exception(f"exception while sending completion. content: {r.content}")
            completed_data(data)
            return action  # action pending
        else:
            logger.info(f"action_completed request made for {action}")
            completed_data('')
            completed_action('')
            pending_action('')
            if new_action: return check_action(new_action, url, dfi_id, key)
        return False  # keine action pending

    if pending_action() == uuid:
        if completed_action() == uuid:
            logger.info(f"action was already completed: {action}")
            return handle_completion()
        elif working_action() == uuid:
            completion = check_action_completion()
            if completion:  # Check, ob eine nicht direkt verarbeitbare Aktion bereits beendet wurde erfolgt hier
                logger.info(f"action has completed in the meantime: {action}")
                return handle_completion(completion)
            else:
                logger.info(f"action is still being worked on: {action}")
            return action  # action pending

    # Wenn die vorher geprüften Umstände nicht zu einem return geführt haben, wird die Aktion nun ausgeführt
    logger.info(f"action processing starts: {action}")
    pending_action(uuid)
    working_action(uuid)
    completed_data('')
    action_result = False

    # Hier folgt der Code zur Verarbeitung.
    try:
        action_result = handle_action()
    except Exception as e:
        logger.exception("exception while working on action")
        working_action('')

    # Kann eine Aktion nicht direkt verarbeitet werden, ist die completion-Prüfung im Block `working_action() == uuid:` oben relevant. Ansonsten direkt hier.
    if action_result:
        logger.info(f"action has completed: {action}")
        return handle_completion(action_result)

    logger.info(f"action will be completed at a later point in time: {action}")
    return action  # action pending

