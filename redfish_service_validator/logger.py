# Copyright Notice:
# Copyright 2016-2025 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import logging
import sys
from enum import IntEnum
from types import SimpleNamespace

# List and set up custom debug levels
class Level(IntEnum):
    DEBUG = logging.DEBUG
    VERBOSE2 = logging.INFO-2
    VERBOSE1 = logging.INFO-1
    INFO = logging.INFO
    WARN = logging.WARN
    ERROR = logging.ERROR

logging.addLevelName(Level.VERBOSE1, "Level.VERBOSE1")
logging.addLevelName(Level.VERBOSE2, "Level.VERBOSE2")

# Entries for HTML log
LOG_ENTRY = ('name', 'value', 'type', 'exists', 'result')
COUNT_ENTRY = ('id', 'msg', 'level')

def create_entry(name, value, my_type, exists, result):
    return SimpleNamespace(**{
        "name": name,
        "value": value,
        "type": my_type,
        "exists": exists,
        "result": result
    })

def create_count(id_, msg, level):
    return SimpleNamespace(**{
        "id": id_,
        "msg": msg,
        "level": level
    })

# Handler for log counts to flush (example: per Resource validated)
class RecordHandler(logging.Handler):
    def __init__(self):
        self.record_collection = []
        super().__init__()
    
    def emit(self, record):
        result = record.__dict__.get('result')
        if record.levelno > logging.INFO or result is not None:
            self.record_collection.append(record)
    
    def flush(self):
        output = self.record_collection
        self.record_collection = []
        return output

class RecordFormatter(logging.Formatter):
    def __init__(self):
        self.current_uri = [None]
        super().__init__()

    def format(self, record):
        msg = "{} - {}".format(record.levelname, record.getMessage())
        result = record.__dict__.get('result')
        record.result = result
        uri = record.__dict__.get('uri', self.current_uri[-1])
        record.uri = uri
        if result or record.levelno > logging.INFO:
            append = " ... "
            append += "{} ".format(result) if result else " "
            append += "at {}".format(uri) if uri else ""
            msg += append
        return msg

def create_logging_file_handler(level, file_name):
    file_handler = logging.FileHandler(file_name)
    file_handler.setLevel(min(level, standard_out.level))
    file_handler.setFormatter(RecordFormatter())
    my_logger.addHandler(file_handler)

def push_uri(self, uri):
    """Pushes uri of text logger formatter. 

    Args:
        uri (str, optional): URI to change to. Defaults to None.
    """    
    
    for handler in self.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.formatter.current_uri.append(uri)

def pop_uri(self):
    """Pops uri of text logger formatter. 
    """    
    
    for handler in self.handlers:
        if isinstance(handler, logging.FileHandler):
            if len(handler.formatter.current_uri) > 1:
                handler.formatter.current_uri.pop()

my_logger = logging.getLogger('rsv')
my_logger.setLevel(logging.DEBUG)

standard_out = logging.StreamHandler(sys.stdout)
standard_out.setLevel(logging.INFO)
my_logger.addHandler(standard_out)

# Functions to set up externally
def set_standard_out(new_level):
    standard_out.setLevel(new_level)

record_capture = RecordHandler()
my_logger.addHandler(record_capture)

# Verbose printing functions
def print_verbose_1(self, msg, *args, **kwargs):
    if self.isEnabledFor(Level.VERBOSE1):
        self._log(Level.VERBOSE1, msg, args, **kwargs)

def print_verbose_2(self, msg, *args, **kwargs):
    if self.isEnabledFor(Level.VERBOSE2):
        self._log(Level.VERBOSE2, msg, args, **kwargs)
        
logging.Logger.verbose1 = print_verbose_1
logging.Logger.verbose2 = print_verbose_2
logging.Logger.push_uri = push_uri
logging.Logger.pop_uri = pop_uri

