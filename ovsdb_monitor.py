import os
from ovs.db import idl as ovs_idl
from ovsdbapp.backend.ovs_idl import connection
from ovsdbapp.schema.open_vswitch import impl_idl
from os_ken.lib import hub


class OVSDBMonitor:
    def __init__(self, metrics_exporter, logger, datapaths):
        self.metrics = metrics_exporter
        self.logger = logger
        self.datapaths = datapaths
        self.idl = None
        self.conn = None
        self.api = None
        self.running = False
        self.connected = False
        self._counter_cache = {}
    
    def connect(self):
        try:
            src_dir = os.getenv("OVS_SRCDIR", "/usr/share/openvswitch")
            run_dir = os.getenv("OVS_RUNDIR", "/var/run/openvswitch")
            
            self.logger.info(f"OVSDB: src_dir={src_dir}, run_dir={run_dir}")
            
            schema_file = os.path.join(src_dir, "vswitch.ovsschema")
            db_sock = os.path.join(run_dir, "db.sock")
            remote = f"unix:{db_sock}"
            
            schema_helper = ovs_idl.SchemaHelper(schema_file)
            schema_helper.register_all()
            
            self.idl = ovs_idl.Idl(remote, schema_helper)
            self.conn = connection.Connection(idl=self.idl, timeout=10)
            self.api = impl_idl.OvsdbIdl(self.conn)
            self.running = True
            hub.spawn(self._monitor_loop)
            
            self.connected = True
            self.logger.info(f"OVSDB connected: {remote}")
            return True
            
        except FileNotFoundError as e:
            self.logger.warning(f"OVSDB file not found: {e}")
            self.connected = False
            return False
            
        except Exception as e:
            error_type = type(e).__name__
            self.logger.warning(f"OVSDB connection failed: {error_type}")
            self.connected = False
            return False
    
    def _monitor_loop(self):
        while self.running:
            hub.sleep(5)
            try:
                self._update_metrics()
            except Exception as e:
                self.logger.debug(f"OVSDB metrics error: {type(e).__name__}")
    
    def _update_metrics(self):
        # Bridges
        bridge_dpid = {}
        bridge_table = self.idl.tables.get('Bridge', {})
        self.logger.debug(f"OVSDB: Found {len(bridge_table.rows)} bridges")
        
        for row in bridge_table.rows.values():
            name = row.name
            dpid_hex = row.datapath_id[0]
            if name and dpid_hex:
                try:
                    bridge_dpid[name] = str(int(dpid_hex, 16))
                except (ValueError, TypeError):
                    bridge_dpid[name] = str(dpid_hex)
        
        # Interfaces
        iface_data = {}
        iface_table = self.idl.tables.get('Interface', {})
        self.logger.debug(f"OVSDB: Found {len(iface_table.rows)} interfaces")
        
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
        
        # Ports
        port_table = self.idl.tables.get('Port', {})
        self.logger.debug(f"OVSDB: Found {len(port_table.rows)} ports")
        
        for bridge_row in bridge_table.rows.values():
            bridge_name = bridge_row.name
            dpid = bridge_dpid.get(bridge_name)
            
            port_uuids = bridge_row.ports
            self.logger.debug(f"OVSDB: Bridge {bridge_name} has {len(port_uuids)} ports")
            
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
                        
                        self.logger.debug(f"OVSDB: Port {port_name} -> Interface link_state={link_state}, admin_state={admin_state}")
                        break
                
                if link_state == 'up' or admin_state == 'up':
                    status_value = 1
                elif link_state == 'down' or admin_state == 'down':
                    status_value = 0
                else:
                    status_value = 1
                    self.logger.debug(f"OVSDB: Port {port_name}: no link_state/admin_state, defaulting to up")
                
                self.logger.debug(f"OVSDB: Setting port_status {dpid}/{port_name} = {status_value}")
                
                self.metrics.port_status.labels(
                    switch_id=dpid,
                    port_name=port_name
                ).set(status_value)

                for iface_uuid in iface_uuids:
                    iface_row = iface_table.rows.get(iface_uuid.uuid)
                    iface_name = iface_row.name
                    stats = iface_data.get(iface_name).get('stats')

                    self._update_counters(dpid, port_name, stats)

    def _update_counters(self, dpid, port_name, stats):
        if not stats:
            return
        
        def inc(metric, cache_key, raw_value):
            val = int(raw_value)
            
            key = f"{dpid}:{port_name}:{cache_key}"
            if key in self._counter_cache.keys():
                delta = val - self._counter_cache[key]
                metric.labels(switch_id=dpid, port_name=port_name).inc(delta)
            self._counter_cache[key] = val
        
        # RX packets
        inc(self.metrics.rx_count, 'rx', stats.get('rx_packets'))
        
        # TX packets
        inc(self.metrics.tx_count, 'tx', stats.get('tx_packets'))
        
        # RX errors (сумма)
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
