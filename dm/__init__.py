# -*- coding: utf-8 -*-

from dataclasses import dataclass

from typing import Dict

# todo
@dataclass
class Configuration:
    version: str
    raw: str
    configuration: Dict

config = Configuration("initial version", "", {})
