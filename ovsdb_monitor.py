"""
OVSDB Monitor for Open vSwitch

Collects port and interface stats
Connecting using socket
"""

import os
from ovs.db import idl as ovs_idl
from ovsdbapp.backend.ovs_idl import connection
from ovsdbapp.schema.open_vswitch import impl_idl
from os_ken.lib import hub


class OVSDBMonitor:
    """
    Monitor for collecting port stats

    Collects:
     - Port status from Port table
     - RX/TX packets and bytes from interfaces
     - RX/TX errors, drops and collisions from interfaces

    Updates metrics every OVSDB_STATS_INTERVAL (from .env)
    """
    def __init__(self, metrics_exporter, logger, datapaths, config):
        """
        Initialized in switch
        Args:
         - metrics_exporter - MetricsExporter instance
         - logger - OS-Ken logger
         - datapaths - Dict of switches
         - config - Config instance
        """
        self.metrics = metrics_exporter
        self.logger = logger
        self.datapaths = datapaths
        self.idl = None
        self.conn = None
        self.api = None
        self.running = False
        self._counter_cache = {}  # stores metrics values of prev update
        self.config = config

    def connect(self):
        """
        Connecting using socket
        """
        try:
            # Socket folder from .env
            src_dir = self.config.OVSDB_SRC_DIR
            run_dir = self.config.OVSDB_RUN_DIR

            self.logger.info("OVSDB: src_dir=%s, run_dir=%s", src_dir, run_dir)

            # Socket file
            schema_file = os.path.join(src_dir, "vswitch.ovsschema")
            db_sock = os.path.join(run_dir, "db.sock")
            remote = f"unix:{db_sock}"

            schema_helper = ovs_idl.SchemaHelper(schema_file)
            schema_helper.register_all()

            # Connecting
            self.idl = ovs_idl.Idl(remote, schema_helper)
            self.conn = connection.Connection(idl=self.idl, timeout=self.config.OVSDB_CONN_TIMEOUT)
            self.api = impl_idl.OvsdbIdl(self.conn)
            self.running = True
            hub.spawn(self._monitor_loop)

            self.logger.info("OVSDB connected: %s", remote)
            return True

        # File not found error
        except FileNotFoundError as e:
            self.logger.warning("OVSDB file not found: %s", e)
            return False

        # Any other error
        except Exception as e:
            error_type = type(e).__name__
            self.logger.warning("OVSDB connection failed: %s", error_type)
            return False

    def _monitor_loop(self):
        """
        Periodical metrics updates (every OVSDB_STATS_INTERVAL seconds)
        """
        while self.running:
            hub.sleep(self.config.OVSDB_STATS_INTERVAL)
            try:
                self._update_metrics()
            except Exception as e:
                self.logger.debug("OVSDB metrics error: %s", type(e).__name__)

    def _update_metrics(self):
        """
        Checks OVSDB tables and updates metrics

        1. Collects bridges { name: dpid }
        2. Collects interfaces { name: {
            'link_state'
            'admin_state'
            'stats'
            'uuid'
        }}
        3. Collects ports from bridges and sets their statuses from interfaces
        4. Updates metrics for every port
        """
        # 1. Bridges
        bridge_dpid = {}
        bridge_table = self.idl.tables.get('Bridge', {})
        self.logger.debug("OVSDB: Found %s bridges", len(bridge_table.rows))

        for row in bridge_table.rows.values():
            name = row.name
            dpid_hex = row.datapath_id[0]
            if name and dpid_hex:
                try:
                    bridge_dpid[name] = str(int(dpid_hex, 16))
                except (ValueError, TypeError):
                    bridge_dpid[name] = str(dpid_hex)

        # 2. Interfaces
        iface_data = {}
        iface_table = self.idl.tables.get('Interface', {})
        self.logger.debug("OVSDB: Found %s interfaces", len(iface_table.rows))

        for uuid, row in iface_table.rows.items():
            name = row.name

            link_state = row.link_state
            admin_state = row.admin_state

            stats = row.statistics
            if hasattr(stats, 'data'):
                stats = stats.data
            stats = stats or {}

            iface_data[name] = {
                'link_state': link_state,
                'admin_state': admin_state,
                'stats': stats,
                'uuid': str(uuid),
            }

        # 3. Ports
        port_table = self.idl.tables.get('Port', {})
        self.logger.debug("OVSDB: Found %s ports", len(port_table.rows))

        for bridge_row in bridge_table.rows.values():
            bridge_name = bridge_row.name
            dpid = bridge_dpid.get(bridge_name)

            port_uuids = bridge_row.ports
            self.logger.debug("OVSDB: Bridge %s has %s ports", bridge_name, len(port_uuids))

            for port_uuid in port_uuids:
                port_row = port_table.rows.get(port_uuid.uuid)

                port_name = port_row.name

                iface_uuids = port_row.interfaces
                link_state = None
                admin_state = None

                for iface_uuid in iface_uuids:
                    iface_row = iface_table.rows.get(iface_uuid.uuid)
                    if iface_row:
                        link_state = iface_row.link_state
                        admin_state = iface_row.admin_state

                        self.logger.debug(
                            "OVSDB: Port %s -> Interface link_state=%s, admin_state={admin_state}",
                            port_name,
                            link_state,
                        )
                        break

                if link_state == 'up' or admin_state == 'up':
                    status_value = 1
                elif link_state == 'down' or admin_state == 'down':
                    status_value = 0
                else:
                    status_value = 1
                    self.logger.debug(
                        "OVSDB: Port %s: no link_state/admin_state, defaulting to up",
                        port_name,
                    )

                self.logger.debug(
                    "OVSDB: Setting port_status %s/%s = %s",
                    dpid,
                    port_name,
                    status_value,
                )

                # Set port statuses
                self.metrics.port_status.labels(
                    switch_id=dpid,
                    port_name=port_name
                ).set(status_value)

                # 4. Update ports metrics
                for iface_uuid in iface_uuids:
                    iface_row = iface_table.rows.get(iface_uuid.uuid)
                    iface_name = iface_row.name
                    stats = iface_data.get(iface_name).get('stats')

                    self._update_counters(dpid, port_name, stats)

    def _update_counters(self, dpid, port_name, stats):
        """
        Updates ports metrics by deltas since last update
        """
        if not stats:
            return

        def inc(metric, cache_key, val):
            """
            Checks if metric was already set or not
            Counts delta and increases the metric with it
            """
            key = f"{dpid}:{port_name}:{cache_key}"
            if key in self._counter_cache.keys():
                delta = val - self._counter_cache[key]
                metric.labels(switch_id=dpid, port_name=port_name).inc(delta)
            else:
                metric.labels(switch_id=dpid, port_name=port_name).inc(val)
            self._counter_cache[key] = val

        # RX/TX packets and bytes
        inc(self.metrics.rx_count, 'rx', stats.get('rx_packets'))
        inc(self.metrics.tx_count, 'tx', stats.get('tx_packets'))
        inc(self.metrics.port_rx_bytes, 'rx', stats.get('rx_bytes'))
        inc(self.metrics.port_tx_bytes, 'tx', stats.get('tx_bytes'))

        # RX errors (sum)
        rx_err = (
            int(stats.get('rx_errors', 0)) +
            int(stats.get('rx_dropped', 0)) +
            int(stats.get('rx_crc_errors', 0))
        )
        inc(self.metrics.rx_errors, 'rx_err', rx_err)

        # TX errors
        tx_err = (
            int(stats.get('tx_errors', 0)) +
            int(stats.get('tx_dropped', 0))
        )
        inc(self.metrics.tx_errors, 'tx_err', tx_err)
