import threading
import http.server
from prometheus_client import Counter, Gauge, generate_latest, REGISTRY


class MetricsExporter:
    def __init__(self, port=8000):
        self.port = port

        self.active_connections = Gauge(
            'osken_active_connections',
            'Number of active datapath connections',
            ['switch_id']
        )

        self.stats_request_count = Counter(
            'osken_stats_request_total',
            'Total number of StatsRequest messages',
            ['switch_id', 'stats_type']
        )

        self.stats_reply_count = Counter(
            'osken_stats_reply_total',
            'Total number of StatsReply messages',
            ['switch_id', 'stats_type']
        )

        self._start_http_server()

    def _start_http_server(self):
        class MetricsHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/metrics':
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(generate_latest(REGISTRY))
                else:
                    self.send_response(404)
                    self.end_headers()

        server = http.server.HTTPServer(('0.0.0.0', self.port), MetricsHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
