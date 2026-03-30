import os
import logging
from dotenv import load_dotenv


load_dotenv()


def must_get(key):
    res = os.getenv(key, None)
    if res is not None:
        return (res, None)
    else:
        return (None, "key is not set")


def get(key, default_val):
    res = os.getenv(key, default_val)
    return res


class Config:
    METRICS_PORT = int(get('METRICS_PORT', 8000))
    METRICS_HOST = get('METRICS_HOST', '0.0.0.0')
    
    OVSDB_SRC_DIR = get("OVS_SRCDIR", "/usr/share/openvswitch")
    OVSDB_RUN_DUR = get("OVS_RUNDIR", "/var/run/openvswitch")
    OVSDB_STATS_INTERVAL = int(get('OVSDB_STATS_INTERVAL', 5))
    OVSDB_CONN_TIMEOUT = int(get('OVSDB_CONN_TIMEOUT', 10))
    
    SWITCH_STATS_INTERVAL = int(get('SWITCH_STATS_INTERVAL', 5))
    FLOW_IDLE_TIMEOUT = int(get('FLOW_IDLE_TIMEOUT', 20))
    
    LOG_LEVEL = get('LOG_LEVEL', 'INFO')
