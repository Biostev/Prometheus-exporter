"""
Config class loads options from .env file
"""

import os
import sys
from dotenv import load_dotenv


# Load vars from .env
load_dotenv()


def must_get(key):
    """
    Get required envvar
    If var is not set, exits with error msg
    """
    res = os.getenv(key)
    if res is None:
        print(f"ERROR: envvar {key} is not set!")
        sys.exit(1)
    return res


def get(key, default_val):
    """
    Gets envvar
    If var is not set, sets it to default_val
    """
    res = os.getenv(key, default_val)
    return res


class Config:
    """
    Loads envvars from .env file
    Metrics host and port are required
    """
    # Exporter
    METRICS_PORT = must_get('METRICS_PORT')
    METRICS_PORT = int(METRICS_PORT)
    METRICS_HOST = must_get('METRICS_HOST')

    # OVSDB
    OVSDB_SRC_DIR = get("OVS_SRCDIR", "/usr/share/openvswitch")
    OVSDB_RUN_DIR = get("OVS_RUNDIR","/var/run/openvswitch")
    OVSDB_STATS_INTERVAL = int(get('OVSDB_STATS_INTERVAL', 5))
    OVSDB_CONN_TIMEOUT = int(get('OVSDB_CONN_TIMEOUT', 10))

    # Switch
    SWITCH_STATS_INTERVAL = int(get('SWITCH_STATS_INTERVAL', 5))
    FLOW_IDLE_TIMEOUT = int(get('FLOW_IDLE_TIMEOUT', 20))

    # Logger
    LOG_LEVEL = get('LOG_LEVEL', 'INFO')
