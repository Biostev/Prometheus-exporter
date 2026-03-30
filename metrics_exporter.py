"""
Prometheus metrics exporter

Creates http /metrics endpoint for returning metrics

Provided metrics:
 - active_connections
 - packet_in_count
 - packet_out_count
 - stats_reply_count
 - packet_in_processing_time
 - error_msg_count
 - flows_count
 - expired_flows_count
 - max_table_size
 - cur_table_size
 - port_status
 - rx_count
 - tx_count
 - port_rx_bytes
 - port_tx_bytes
 - rx_errors
 - tx_errors
"""

import threading
import http.server
from prometheus_client import (
    Counter, Gauge, Histogram,
    generate_latest, REGISTRY
)

class MetricsExporter:
    """
    Class for creating metrics with right pattern
    """
    def __init__(self, config):
        """
        Initialized in switch
        All requested metrics are set here

        Config:
        Type(
            name,
            description,
            [labels]
        )
        """
        self.config = config

        # Connections
        # Number of active connections with switches
        self.active_connections = Gauge(
            'osken_active_connections',
            'Number of active datapath connections',
        )

        # OpenFlow msgs
        # Number of PacketIn
        self.packet_in_count = Counter(
            'osken_packet_in_total',
            'Total number of PacketIn messages received',
            ['switch_id']
        )

        # Number of PacketOut
        self.packet_out_count = Counter(
            'osken_packet_out_total',
            'Total number of PacketOut messages sent',
            ['switch_id']
        )

        # Number of FlowMod
        self.flow_mod_count = Counter(
            'osken_flow_mod_total',
            'Total number of FlowMod messages sent',
            ['switch_id']
        )

        # Number of StatsRequest
        self.stats_request_count = Counter(
            'osken_stats_request_total',
            'Total number of StatsRequest messages',
            ['switch_id']
        )

        # Number of StatsReply
        self.stats_reply_count = Counter(
            'osken_stats_reply_total',
            'Total number of StatsReply messages',
            ['switch_id']
        )

        # Processing latency
        # PacketIn processing time
        self.packet_in_processing_time = Histogram(
            'osken_packet_in_processing_seconds',
            'Time to process a PacketIn message',
            ['switch_id'],
            buckets=(0.01, 0.05, 0.1, 0.5, 1, 2.5, 5, 10)
        )

        # Errors
        # Number of OpenFlow error messages
        self.error_msg_count = Counter(
            'osken_error_messages_total',
            'Total number of OpenFlow error messages',
            ['switch_id', 'error_type']
        )

        # Flows
        # Number of flows
        self.flows_count = Gauge(
            'osken_flows_total',
            'Total number of flows in flow tables',
            ['switch_id', 'table_id']
        )

        # Number of deleted/expired flows
        self.expired_flows_count = Counter(
            'osken_expired_flows_total',
            'Total number of expired or removed flows',
            ['switch_id']
        )

        # Max table size
        self.max_table_size = Gauge(
            'osken_table_max_size',
            'Max number of flows for table',
            ['switch_id', 'table_id']
        )

        # Current table size
        self.cur_table_size = Gauge(
            'osken_table_current_size',
            'Current number of flows in table',
            ['switch_id', 'table_id']
        )

        # Ports
        # Current port status
        self.port_status = Gauge(
            'osken_port_status',
            'Port status (1 = up, 0 = down)',
            ['switch_id', 'port_name']
        )

        # Number of RX packets for port
        self.rx_count = Counter(
            'osken_port_rx_total',
            'Total number of recieved packets for port',
            ['switch_id', 'port_name']
        )

        # Number of TX packets for port
        self.tx_count = Counter(
            'osken_port_tx_total',
            'Total number of transmitted packets for port',
            ['switch_id', 'port_name']
        )

        # Number of RX bytes for port
        self.port_rx_bytes = Counter(
            'osken_port_rx_bytes_total',
            'Total number of received bytes on port',
            ['switch_id', 'port_name']
        )

        # Number of TX bytes for port
        self.port_tx_bytes = Counter(
            'osken_port_tx_bytes_total',
            'Total number of transmitted bytes on port',
            ['switch_id', 'port_name']
        )

        # Number of RX errors/collisions/drops
        self.rx_errors = Counter(
            'osken_port_rx_errors',
            'Total number of recieved errors for port',
            ['switch_id', 'port_name']
        )

        # Number of TX errors/collisions/drops
        self.tx_errors = Counter(
            'osken_port_tx_errors',
            'Total number of transmitted errors for port',
            ['switch_id', 'port_name']
        )

        self._start_http_server()

    def _start_http_server(self):
        """
        Creating /metrics endpoint using http.server pylib
        server starts in a separate daemon thread
        """
        class MetricsHandler(http.server.BaseHTTPRequestHandler):
            """Simple class for handling http requests"""
            def do_GET(self):
                """GET handler"""
                # Set /metrics endpoint
                if self.path == '/metrics':
                    self.send_response(200)
                    # Prometheus uses text/plain format
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(generate_latest(REGISTRY))
                # Set 404 for others
                else:
                    self.send_response(404)
                    self.end_headers()

        # Creating server in a daemon thread
        server = http.server.HTTPServer(
            (self.config.METRICS_HOST, self.config.METRICS_PORT),
            MetricsHandler
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
