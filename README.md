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

In created venv run:
`osken-manager --ofp-tcp-listen-port 6633 simple_switch_with_metrics.py`

### Mininet

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
