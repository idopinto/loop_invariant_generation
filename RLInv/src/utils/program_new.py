from enum import Enum
from typing import List, Set, Dict, Optional
from copy import copy
import re
from .predicate import Predicate


PATCH_LINES = ['void assert(int cond) { if (!(cond)) { ERROR : { reach_error(); abort(); } } }',
               'void assume(int cond) { if (!cond) { abort(); } }']

class AssertionPointAttributes(Enum):
    BeforeLoop = 1
    InLoop = 2
    BeforeAssertion = 3
    BeginningOfLoop = 4
    EndOfLoop = 5

class Program:
    def __init__(self, lines: List[str], replacement: Dict[str, str]):
        self.lines: List[str] = []
        self.assertions: List[Predicate] = []  # The assertion to add after the corresponding line number
        self.lemmas: List[Predicate] = []  # The lemmas to add after the corresponding line number
        self.assertion_points: Dict[int, Set[AssertionPointAttributes]] = {}  # Potentially adding assertions right after these lines