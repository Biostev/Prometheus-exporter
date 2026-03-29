from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from os_ken.controller.handler import set_ev_cls
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import packet
from os_ken.lib.packet import ethernet
from os_ken.lib.packet import ether_types
from os_ken.lib import hub

import time

from metrics_exporter import MetricsExporter


class SimpleSwitch13(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

        # Initialize metrics exporter
        self.metrics = MetricsExporter(port=8000)

        # Track datapaths
        self.datapaths = {}

        self.logger.info("SimpleSwitch13 with Prometheus metrics started")
        self.logger.info("Metrics available at http://localhost:8000/metrics")
        
        self.start_timer()
    
    def start_timer(self):
        hub.spawn(self._send_periodic_stats)
    
    def _send_periodic_stats(self):
        while True:
            hub.sleep(10)
            for dpid, datapath in self.datapaths.items():
                if datapath.id in self.datapaths.items():
                    self.send_stats_request(datapath, 'flow')
                    self.send_stats_request(datapath, 'table')

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Store datapath info
        dpid = datapath.id
        self.datapaths[dpid] = datapath

        # Update active connections metric
        self.metrics.active_connections.labels(switch_id=str(dpid)).set(1)
        self.logger.info(f"Switch {dpid} connected")

        # install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(
            ofproto.OFPP_CONTROLLER,
            ofproto.OFPCML_NO_BUFFER,
        )]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        dpid = str(datapath.id)

        # Increase FlowMod counter
        self.metrics.flow_mod_count.labels(switch_id=dpid).inc()

        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS,
            actions,
        )]
        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                match=match,
                instructions=inst,
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
            )
        datapath.send_msg(mod)
    
    def send_packet_out(self, datapath, buffer_id, in_port, actions, data=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        dpid = str(datapath.id)

        # Increase PacketOut counter
        self.metrics.packet_out_count.labels(switch_id=dpid).inc()

        msg = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(msg)

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

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

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
        
        self.send_packet_out(datapath, msg.buffer_id, in_port, actions, data)

        # Record processing time
        processing_time = time.perf_counter() - start_time
        self.metrics.packet_in_processing_time.labels(switch_id=dpid).observe(processing_time)

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    def error_msg_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)
        
        # Increment error counter
        self.metrics.error_msg_count.labels(switch_id=dpid).inc()
        
        self.logger.warning(f"OpenFlow error: switch={dpid} type={msg.type}")
    
    @set_ev_cls(ofp_event.EventOFPFlowRemoved, MAIN_DISPATCHER)
    def flow_removed_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)
        
        # Increment expired flows counter
        self.metrics.expired_flows_count.labels(switch_id=dpid).inc()
        
        self.logger.debug(f"Flow removed: switch={dpid} reason={msg.reason}")
    
    @set_ev_cls(ofp_event.EventOFPStatsReply, MAIN_DISPATCHER)
    def stats_reply_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = str(datapath.id)

        # Increment StatsReply counter
        self.metrics.stats_reply_count.labels(switch_id=dpid).inc()
    
        for stat in msg.body:
            port_no = stat.port_no
            port_name = f"port_{port_no}"
            
            self.metrics.rx_count.labels(
                switch_id=dpid, port_name=port_name
            ).inc(stat.rx_packets)
            
            self.metrics.tx_count.labels(
                switch_id=dpid, port_name=port_name
            ).inc(stat.tx_packets)
            
            rx_errors = stat.rx_errors + stat.rx_dropped + stat.rx_over_errors + stat.rx_crc_errors
            tx_errors = stat.tx_errors + stat.tx_dropped
            
            if rx_errors > 0:
                self.metrics.rx_errors.labels(
                    switch_id=dpid, port_name=port_name
                ).inc(rx_errors)
            
            if tx_errors > 0:
                self.metrics.tx_errors.labels(
                    switch_id=dpid, port_name=port_name
                ).inc(tx_errors)
    
    def send_stats_request(self, datapath, stats_type='flow'):
        parser = datapath.ofproto_parser
        dpid = str(datapath.id)
        
        # Increment StatsRequest counter
        self.metrics.stats_request_count.labels(switch_id=dpid).inc()
        
        if stats_type == 'flow':
            req = parser.OFPFlowStatsRequest(datapath)
            datapath.send_msg(req)
        elif stats_type == 'table':
            req = parser.OFPTableStatsRequest(datapath)
            datapath.send_msg(req)
