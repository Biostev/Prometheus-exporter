from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER, MAIN_DISPATCHER,
    set_ev_cls
)
from os_ken.controller.controller import Datapath
from os_ken.controller import event
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import (
    packet, ethernet, ether_types,
)
from os_ken.lib import hub

import time
import logging

from metrics_exporter import MetricsExporter
from ovsdb_monitor import OVSDBMonitor
from config import Config


class SimpleSwitch13(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.current_active_tables = set()
        self.previous_flow_count = {}
        self.config = Config

        logging.getLogger("os_ken").setLevel(self.config.LOG_LEVEL)

        # Initialize metrics exporter
        self.metrics = MetricsExporter(self.config)

        self.ovsdb_monitor = OVSDBMonitor(
            self.metrics,
            self.logger,
            self.datapaths,
            self.config,
        )
        
        if not self.ovsdb_monitor.connect():
            self.logger.warning("OVSDB connection error")

        self.logger.info("SimpleSwitch13 with Prometheus metrics started")
        self.logger.info(f"Metrics available at http://{self.config.METRICS_HOST}:{self.config.METRICS_PORT}/metrics")
        
        hub.spawn(self._send_periodic_stats)
    
    def _send_periodic_stats(self):
        while True:
            hub.sleep(self.config.SWITCH_STATS_INTERVAL)
            active_count = 0
            for dpid, datapath in list(self.datapaths.items()):
                if datapath and hasattr(datapath, 'is_active') and datapath.is_active:
                    active_count += 1
                    self._request_flow_stats(datapath)
                    self._request_table_stats(datapath)
                    self._request_table_features(datapath)
                else:
                    if dpid in self.datapaths:
                        del self.datapaths[dpid]
                        self.logger.info(f"Switch {dpid} disconnected (is_active=False)")
            
            self.metrics.active_connections.set(active_count)
    
    def _request_flow_stats(self, datapath):
        parser = datapath.ofproto_parser
        dpid = str(datapath.id)
        
        # Increment StatsRequest counter
        self.metrics.stats_request_count.labels(switch_id=dpid).inc()
        
        req = parser.OFPFlowStatsRequest(
            datapath=datapath,
            table_id=ofproto_v1_3.OFPTT_ALL,
            out_port=ofproto_v1_3.OFPP_ANY,
            out_group=ofproto_v1_3.OFPG_ANY,
        )
        datapath.send_msg(req)

    def _request_table_stats(self, datapath):
        parser = datapath.ofproto_parser
        dpid = str(datapath.id)
        
        # Increment StatsRequest counter
        self.metrics.stats_request_count.labels(switch_id=dpid).inc()
        
        req = parser.OFPTableStatsRequest(datapath)
        datapath.send_msg(req)

    def _request_table_features(self, datapath):
        parser = datapath.ofproto_parser
        dpid = str(datapath.id)
        
        # Increment StatsRequest counter
        self.metrics.stats_request_count.labels(switch_id=dpid).inc()
        
        req = parser.OFPTableFeaturesStatsRequest(datapath)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Store datapath info
        dpid = datapath.id
        self.datapaths[dpid] = datapath

        # Update active connections metric
        self.metrics.active_connections.inc()
        self.logger.info(f"Switch {dpid} connected")

        # install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(
            ofproto.OFPP_CONTROLLER,
            ofproto.OFPCML_NO_BUFFER,
        )]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=20):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        dpid = str(datapath.id)

        # Increase FlowMod counter
        self.metrics.flow_mod_count.labels(switch_id=dpid).inc()

        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS,
            actions,
        )]
        flags = ofproto.OFPFF_SEND_FLOW_REM
        if buffer_id is not None:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst,
                flags=flags,
                idle_timeout=idle_timeout,
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
                flags=flags,
                idle_timeout=idle_timeout,
            )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        start_time = time.perf_counter()

        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug(
                f"packet truncated: only {ev.msg.msg_len} \
                    of {ev.msg.total_len} bytes",
            )
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = str(datapath.id)

        # Increase PacketIn counter
        self.metrics.packet_in_count.labels(switch_id=dpid).inc()

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src

        self.mac_to_port.setdefault(dpid, {})

        self.logger.info(f"packet in {dpid} {str} {dst} {in_port}")

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                # Record processing time
                processing_time = time.perf_counter() - start_time
                self.metrics.packet_in_processing_time.labels(switch_id=dpid).observe(processing_time)
                return
            else:
                self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        
        self.metrics.packet_out_count.labels(switch_id=dpid).inc()
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

        # Record processing time
        processing_time = time.perf_counter() - start_time
        self.metrics.packet_in_processing_time.labels(switch_id=dpid).observe(processing_time)

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    def error_msg_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)
        
        # Increment error counter
        self.metrics.error_msg_count.labels(switch_id=dpid, error_type=msg.type).inc()
        
        self.logger.warning(f"OpenFlow error: switch={dpid} type={msg.type}")
    
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        """Handle flow stats reply."""
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)
        
        self.logger.debug(f"Received flow stats reply from switch {dpid}")
        
        # Increment StatsReply counter
        self.metrics.stats_reply_count.labels(switch_id=dpid).inc()
        
        if msg.body:
            self._handle_flow_stats(dpid, msg.body)
        else:
            self._handle_flow_stats(dpid, [])

    def _handle_flow_stats(self, dpid, body):
        flows_per_table = {}
        
        for stat in body:
            table_id = stat.table_id
            flows_per_table[table_id] = flows_per_table.get(table_id, 0) + 1
        
        current_total = sum(flows_per_table.values())
        previous_total = self.previous_flow_count.get(dpid, 0)
        if current_total < previous_total:
            expired = previous_total - current_total
            self.metrics.expired_flows_count.labels(
                switch_id=dpid
            ).inc(expired)
            self.logger.info(f"Detected {expired} expired/removed flows on switch {dpid}")
        self.previous_flow_count[dpid] = current_total

        for table_id, count in flows_per_table.items():
            # Set current number of flows for tables
            self.metrics.flows_count.labels(
                switch_id=dpid,
                table_id=table_id
            ).set(count)
    
    @set_ev_cls(ofp_event.EventOFPTableStatsReply, MAIN_DISPATCHER)
    def table_stats_reply_handler(self, ev):
        """Handle table stats reply."""
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)
        
        self.logger.debug(f"Received table stats reply from switch {dpid}")
        
        # Increment StatsReply counter
        self.metrics.stats_reply_count.labels(switch_id=dpid).inc()
        
        if msg.body:
            self._handle_table_stats(dpid, msg.body)

    def _handle_table_stats(self, dpid, body):
        for stat in body:
            table_id = stat.table_id
            active_count = stat.active_count
            
            # Set current table size
            if active_count > 0 or table_id == 0:
                self.current_active_tables.add(table_id)
                self.metrics.cur_table_size.labels(
                    switch_id=dpid,
                    table_id=table_id
                ).set(active_count)
            else:
                self.current_active_tables.discard(table_id)
    
    @set_ev_cls(ofp_event.EventOFPTableFeaturesStatsReply, MAIN_DISPATCHER)
    def table_features_stats_reply_handler(self, ev):
        """Handle table features stats reply."""
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)
        
        self.logger.debug(f"Received table features stats reply from switch {dpid}")
        
        # Increment StatsReply counter
        self.metrics.stats_reply_count.labels(switch_id=dpid).inc()
        
        if msg.body:
            self._handle_table_features_stats(dpid, msg.body)

    def _handle_table_features_stats(self, dpid, body):
        for stat in body:
            table_id = stat.table_id
            max_entries = stat.max_entries
            
            # Set capacities for tables
            if table_id in self.current_active_tables:
                self.metrics.max_table_size.labels(
                    switch_id=dpid,
                    table_id=table_id
                ).set(max_entries)
