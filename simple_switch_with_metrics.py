"""
L2 learning Switch with Prometheus metrics exporter
Using OpenFlow 1.3
"""

import time
import logging

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER, MAIN_DISPATCHER,
    set_ev_cls
)
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import (
    packet, ethernet, ether_types,
)
from os_ken.lib import hub

from metrics_exporter import MetricsExporter
from ovsdb_monitor import OVSDBMonitor
from config import Config


class SimpleSwitch13(app_manager.OSKenApp):
    """
    OpenFlow 1.3 L2 learning switch with Prometheus metrics
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        """
        Initialize the switch application.
        
        Sets up:
         - MAC learning table
         - Datapath storage
         - Prometheus metrics exporter
         - OVSDB monitor
         - Periodic stats collection thread
        """
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}  # { dpid: { mac: port } }
        self.datapaths = {}  # { dpid: datapath }
        self.current_active_tables = set()  # tracks tables with active flows
        self.previous_flow_count = {}  # for expired flows
        self.config = Config  # load config

        logging.getLogger("os_ken").setLevel(self.config.LOG_LEVEL)

        # Initialize metrics exporter
        self.metrics = MetricsExporter(self.config)

        # Initialize OVSDB
        self.ovsdb_monitor = OVSDBMonitor(
            self.metrics,
            self.logger,
            self.datapaths,
            self.config,
        )

        if not self.ovsdb_monitor.connect():
            self.logger.warning("OVSDB connection error")

        self.logger.info("SimpleSwitch13 with Prometheus metrics started")
        self.logger.info(
            "Metrics available at http://%s:%s/metrics",
            self.config.METRICS_HOST,
            self.config.METRICS_PORT
        )

        # Start periodic stats collection
        hub.spawn(self._send_periodic_stats)

    def _send_periodic_stats(self):
        """
        Periodical metrics updates (every SWITCH_STATS_INTERVAL seconds)
        Checks active switches using datapath dict
        Sends stats requests to active switches
        """
        while True:
            hub.sleep(self.config.SWITCH_STATS_INTERVAL)
            active_count = 0
            for dpid, datapath in list(self.datapaths.items()):
                if datapath and hasattr(datapath, 'is_active') and datapath.is_active:
                    active_count += 1
                    # Request all 3 metrics
                    self._request_flow_stats(datapath)
                    self._request_table_stats(datapath)
                    self._request_table_features(datapath)
                else:
                    # Removes inactive switches
                    if dpid in self.datapaths:
                        del self.datapaths[dpid]
                        self.logger.info("Switch %s disconnected (is_active=False)", dpid)

            # Set current active connections
            self.metrics.active_connections.set(active_count)

    def _request_flow_stats(self, datapath):
        """
        Sends OFPFlowStatsRequest to switch
        Requests statistics about all flows in all tables
        Response is handled in flow_stats_reply_handler
        """
        parser = datapath.ofproto_parser
        dpid = str(datapath.id)

        # Increment StatsRequest counter
        self.metrics.stats_request_count.labels(switch_id=dpid).inc()

        # Request all flows from all tables
        req = parser.OFPFlowStatsRequest(
            datapath=datapath,
            table_id=ofproto_v1_3.OFPTT_ALL,
            out_port=ofproto_v1_3.OFPP_ANY,
            out_group=ofproto_v1_3.OFPG_ANY,
        )
        datapath.send_msg(req)

    def _request_table_stats(self, datapath):
        """
        Sends OFPTableStatsRequest to switch
        Requests statistics about all flow tables
        Response is handled in table_stats_reply_handler
        """
        parser = datapath.ofproto_parser
        dpid = str(datapath.id)

        # Increment StatsRequest counter
        self.metrics.stats_request_count.labels(switch_id=dpid).inc()

        req = parser.OFPTableStatsRequest(datapath)
        datapath.send_msg(req)

    def _request_table_features(self, datapath):
        """
        Sends OFPTableFeaturesStatsRequest to switch
        Requests features of all flow tables
        Response is handled in table_features_stats_reply_handler
        """
        parser = datapath.ofproto_parser
        dpid = str(datapath.id)

        # Increment StatsRequest counter
        self.metrics.stats_request_count.labels(switch_id=dpid).inc()

        req = parser.OFPTableFeaturesStatsRequest(datapath)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Handles switch connections
        Called automatically when switch connects
        Installs table-miss flow entry
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Store datapath info
        dpid = datapath.id
        self.datapaths[dpid] = datapath

        # Increment active connections metric
        self.metrics.active_connections.inc()
        self.logger.info("Switch %s connected", dpid)

        # Install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(
            ofproto.OFPP_CONTROLLER,
            ofproto.OFPCML_NO_BUFFER,
        )]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=20):
        """Adds a flow to the switch"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        dpid = str(datapath.id)

        # Increment FlowMod counter
        self.metrics.flow_mod_count.labels(switch_id=dpid).inc()

        # Apply actions
        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS,
            actions,
        )]

        # Requests event when flow expires
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
        """
        Handles PacketIn messages from switch
        Calculates processing time
        """
        # Start processing timer
        start_time = time.perf_counter()

        # Check truncated packets
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug(
                "packet truncated: only %s of %s bytes",
                ev.msg.msg_len,
                ev.msg.total_len,
            )
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = str(datapath.id)

        # Increment PacketIn counter
        self.metrics.packet_in_count.labels(switch_id=dpid).inc()

        # Parse Ethernet packet
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore  LLDP
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst  # dst MAC
        src = eth.src  # src MAC

        # Initialize MAC table for the switch
        self.mac_to_port.setdefault(dpid, {})

        self.logger.debug("packet in %s %s %s %s", dpid, str, dst, in_port)

        # Learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        # Get output port
        out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            # If switch has buffer, send FlowMod with buffer
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                # Record processing time
                processing_time = time.perf_counter() - start_time
                self.metrics.packet_in_processing_time.labels(
                    switch_id=dpid).observe(processing_time)
                return
            # Else install flow only
            self.add_flow(datapath, 1, match, actions)

        # Make PacketOut
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        # Increment PacketOut  counter
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
        """Handles OpenFlow error messages"""
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)

        # Increment error counter for error type
        self.metrics.error_msg_count.labels(switch_id=dpid, error_type=msg.type).inc()

        self.logger.warning("OpenFlow error: switch=%s type=%s", dpid, msg.type)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        """Handles flow stats reply"""
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)

        self.logger.debug("Received flow stats reply from switch %s", dpid)

        # Increment StatsReply counter
        self.metrics.stats_reply_count.labels(switch_id=dpid).inc()

        if msg.body:
            self._handle_flow_stats(dpid, msg.body)
        else:
            self._handle_flow_stats(dpid, [])

    def _handle_flow_stats(self, dpid, body):
        """
        Processes flow stats
        Detects expired flows by comparing with prev count
        Updates flows_count for tables
        """
        # Counts flows per table
        flows_per_table = {}
        for stat in body:
            table_id = stat.table_id
            flows_per_table[table_id] = flows_per_table.get(table_id, 0) + 1

        # Detects expired flows
        current_total = sum(flows_per_table.values())
        previous_total = self.previous_flow_count.get(dpid, 0)
        if current_total < previous_total:
            expired = previous_total - current_total
            self.metrics.expired_flows_count.labels(
                switch_id=dpid
            ).inc(expired)
            self.logger.info("Detected %s expired/removed flows on switch %s", expired, dpid)
        self.previous_flow_count[dpid] = current_total

        for table_id, count in flows_per_table.items():
            # Set current number of flows for tables
            self.metrics.flows_count.labels(
                switch_id=dpid,
                table_id=table_id
            ).set(count)

    @set_ev_cls(ofp_event.EventOFPTableStatsReply, MAIN_DISPATCHER)
    def table_stats_reply_handler(self, ev):
        """Handles table stats reply"""
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)

        self.logger.debug("Received table stats reply from switch %s", dpid)

        # Increment StatsReply counter
        self.metrics.stats_reply_count.labels(switch_id=dpid).inc()

        if msg.body:
            self._handle_table_stats(dpid, msg.body)

    def _handle_table_stats(self, dpid, body):
        """
        Processes table stats
        Updates cur_size for active tables
        """
        for stat in body:
            table_id = stat.table_id
            active_count = stat.active_count

            # Set current size for active tables
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
        """Handles table features stats reply"""
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)

        self.logger.debug("Received table features stats reply from switch %s", dpid)

        # Increment StatsReply counter
        self.metrics.stats_reply_count.labels(switch_id=dpid).inc()

        if msg.body:
            self._handle_table_features_stats(dpid, msg.body)

    def _handle_table_features_stats(self, dpid, body):
        """
        Processes table features stats
        Updates max_size for active tables
        """
        for stat in body:
            table_id = stat.table_id
            max_entries = stat.max_entries

            # Set capacities for active tables
            if table_id in self.current_active_tables:
                self.metrics.max_table_size.labels(
                    switch_id=dpid,
                    table_id=table_id
                ).set(max_entries)
