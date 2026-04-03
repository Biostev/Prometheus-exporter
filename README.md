# Prometheus-exporter

## Description

Metrics exporter for Prometheus.

## Features

Provides listed metrics for Open vSwitch and exports them via HTTP /metrics endpoint.

### Metrics

| Category | Metric | Type | Labels | Source |
| ---------- | -------- | ------ | -------- | -------- |
| **Connections** | Active connections | Gauge | - | `self.datapaths` |
| **OpenFlow** | PacketIn count | Counter | `switch_id` | `EventOFPPacketIn` |
| | PacketOut count | Counter | `switch_id` | `send_packet_out` |
| | FlowMod count | Counter | `switch_id` | `EventOFPFlowMod` |
| | StatsRequest count | Counter | `switch_id` | Periodic polling |
| | StatsReply count | Counter | `switch_id` | Stats replies |
| **Latency** | PacketIn processing time | Histogram | `switch_id` | Time measurement |
| **Errors** | OpenFlow errors | Counter | `switch_id`, `error_type` | `EventOFPErrorMsg` |
| **Flows** | Total flows per table | Gauge | `switch_id`, `table_id` | `OFPFlowStatsRequest` |
| | Expired/removed flows | Counter | `switch_id` | Difference calculation |
| | Max table size | Gauge | `switch_id`, `table_id` | `OFPTableFeaturesStatsRequest` |
| | Current table size | Gauge | `switch_id`, `table_id` | Flow stats |
| **Ports** | Port status (up/down) | Gauge | `switch_id`, `port_name` | OVSDB (Port table) |
| | RX/TX packets | Counter | `switch_id`, `port_name` | OVSDB (Interface stats) |
| | RX/TX bytes | Counter | `switch_id`, `port_name` | OVSDB (Interface stats) |
| | RX/TX errors/drops | Counter | `switch_id`, `port_name` | OVSDB (Interface stats) |

## Requirements

- Using Ubuntu 22.04 LTS
- Python 3.8
- Open vSwitch
- Mininet
- OS-Ken
- Prometheus
- And pylibs (check `requirements.txt`)

For easy installation use Makefile. `help` option is provided.

## Usage

### Controller

Make sure that OVS socket file has right permissions.

In created venv run:
`osken-manager --ofp-tcp-listen-port 6633 simple_switch_with_metrics.py`

### Mininet

There is `tests.py` file with implementation of 1 switch, 2 hosts topology and n switches k hosts each.

In another terminal run:
For 1 switch and 2 hosts:
`sudo mn --topo=single,2 --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13`

For K switches 1 host each (replace K with number):
`sudo mn --topo=linear,K --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13`

For K switches N host each (replace K and N with numbers):
`sudo mn --topo=linear,K,N --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13`

### Prometheus

Set `METRICS_HOST` and `METRICS_PORT` in your .env file (or just copy .env_example)

In another terminal run:
`curl http://<METRICS_HOST>:<METRICS_PORT>/metrics` to get all metrics

run:
`curl http://<METRICS_HOST>:<METRICS_PORT>/metrics | grep <metric_name>` to get the requested one

Or check all metrics in browser: `http://<METRICS_HOST>:<METRICS_PORT>/metrics`

## Testing

(Tk) - command run in terminal k

(T1) `osken-manager --ofp-tcp-listen-port 6633 simple_switch_with_metrics.py`

### Connections

Active connections:

(T3) `curl http://localhost:8000/metrics | grep -i active`  // 0
(T2) `sudo mn --topo=single,2 --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13`
(T3) `curl http://localhost:8000/metrics | grep -i active`  // 1
(T2) mininet> exit
(T3) `curl http://localhost:8000/metrics | grep -i active`  // 0
(T2) sudo mn --topo=linear,4,2 --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13
(T3) `curl http://localhost:8000/metrics | grep -i active`  // 4

### OpenFlow

Packet in/out:

(T2) `sudo mn --topo=single,2 --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13`
(T3) `curl http://localhost:8000/metrics | grep -i packet_in_to`  // 15
(T3) `curl http://localhost:8000/metrics | grep -i packet_out_to`  // 15

FlowMod count:

(T2) `mininet> sh ovs-ofctl -O OpenFlow13 del-flows s1`  // clear all flow rules
(T2) `mininet> h1 ping h2 -c 1`
(T3) `curl http://localhost:8000/metrics | grep -i flow_mod_total`  // 1

Stats request/reply:
(generates periodically automatically)

(T3) `curl http://localhost:8000/metrics | grep -i stats_rep`  // 189
(T3) `curl http://localhost:8000/metrics | grep -i stats_rep`  // 1430

### Latency

PacketIn processing time:

(T3) `curl http://localhost:8000/metrics | grep -i in_proc`
osken_packet_in_processing_seconds_bucket{le="0.5",switch_id="1"} 15.0
osken_packet_in_processing_seconds_bucket{le="1.0",switch_id="1"} 15.0
osken_packet_in_processing_seconds_bucket{le="2.5",switch_id="1"} 15.0
osken_packet_in_processing_seconds_bucket{le="5.0",switch_id="1"} 15.0
0osken_packet_in_processing_seconds_bucket{le="10.0",switch_id="1"} 15.0
osken_packet_in_processing_seconds_bucket{le="+Inf",switch_id="1"} 15.0
osken_packet_in_processing_seconds_sum{switch_id="1"} 0.004360430990345776

### Flows

(T2) `sudo mn --topo=linear,3 --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13`

Flows total:
(T3) `curl http://localhost:8000/metrics | grep -i flows_total{`
osken_flows_total{switch_id="1",table_id="0"} 1.0
osken_flows_total{switch_id="2",table_id="0"} 1.0
osken_flows_total{switch_id="3",table_id="0"} 1.0

Expired_flows (generate after flow idle timeout):
(T3) `curl http://localhost:8000/metrics | grep -i exp_flows_total{`
osken_expired_flows_total{switch_id="1"} 6.0
osken_expired_flows_total{switch_id="3"} 1.0
osken_expired_flows_total{switch_id="2"} 1.0

Current and max size:
(T3) `curl http://localhost:8000/metrics | grep -i size`
osken_table_max_size{switch_id="1",table_id="0"} 1e+06
osken_table_max_size{switch_id="3",table_id="0"} 1e+06
osken_table_max_size{switch_id="2",table_id="0"} 1e+06

### Ports

(T2) `sudo mn --topo=linear,3 --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13`

Port statuses:
(T3) `curl http://localhost:8000/metrics | grep -i port_status`
osken_port_status{port_name="s3-eth1",switch_id="3"} 1.0
osken_port_status{port_name="s3-eth2",switch_id="3"} 1.0
osken_port_status{port_name="s3",switch_id="3"} 1.0
osken_port_status{port_name="s1-eth1",switch_id="1"} 1.0
osken_port_status{port_name="s1",switch_id="1"} 1.0
osken_port_status{port_name="s1-eth2",switch_id="1"} 1.0
osken_port_status{port_name="s2-eth3",switch_id="2"} 1.0
osken_port_status{port_name="s2-eth1",switch_id="2"} 1.0
osken_port_status{port_name="s2-eth2",switch_id="2"} 1.0
osken_port_status{port_name="s2",switch_id="2"} 1.0

RX/TX packets and bytes and errors:
(T2) `sudo mn --topo=single,3 --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13`
(T3) `curl -s http://localhost:8000/metrics | grep -E "osken_port_(rx|tx)"`
osken_port_rx_total{port_name="s1",switch_id="1"} 0.0
osken_port_rx_total{port_name="s1-eth1",switch_id="1"} 1.0
osken_port_rx_total{port_name="s1-eth3",switch_id="1"} 1.0
osken_port_rx_total{port_name="s1-eth2",switch_id="1"} 1.0
osken_port_tx_total{port_name="s1",switch_id="1"} 0.0
osken_port_tx_total{port_name="s1-eth1",switch_id="1"} 1.0
osken_port_tx_total{port_name="s1-eth3",switch_id="1"} 1.0
osken_port_tx_total{port_name="s1-eth2",switch_id="1"} 2.0
osken_port_rx_bytes_total{port_name="s1",switch_id="1"} 0.0
osken_port_rx_bytes_total{port_name="s1-eth1",switch_id="1"} 89.0
osken_port_rx_bytes_total{port_name="s1-eth3",switch_id="1"} 89.0
osken_port_rx_bytes_total{port_name="s1-eth2",switch_id="1"} 89.0
osken_port_tx_bytes_total{port_name="s1",switch_id="1"} 0.0
osken_port_tx_bytes_total{port_name="s1-eth1",switch_id="1"} 89.0
osken_port_tx_bytes_total{port_name="s1-eth3",switch_id="1"} 89.0
osken_port_tx_bytes_total{port_name="s1-eth2",switch_id="1"} 178.0

osken_port_rx_errors_total{port_name="s1",switch_id="1"} 0.0
osken_port_rx_errors_total{port_name="s1-eth1",switch_id="1"} 0.0
osken_port_rx_errors_total{port_name="s1-eth3",switch_id="1"} 0.0
osken_port_rx_errors_total{port_name="s1-eth2",switch_id="1"} 0.0
osken_port_tx_errors_total{port_name="s1",switch_id="1"} 0.0
osken_port_tx_errors_total{port_name="s1-eth1",switch_id="1"} 0.0
osken_port_tx_errors_total{port_name="s1-eth3",switch_id="1"} 0.0
osken_port_tx_errors_total{port_name="s1-eth2",switch_id="1"} 0.0
