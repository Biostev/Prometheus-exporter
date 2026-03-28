.PHONY: help install clean setup-python setup-os-ken setup-mininet setup-ovs setup-prometheus-client

PYTHON_VERSION = 3.8
VENV_DIR = $(HOME)/ryu-env
RYU_DIR = $(HOME)/ryu
PROJECT_DIR = $(shell pwd)
PIP = $(VENV_DIR)/bin/pip
PYTHON = $(VENV_DIR)/bin/python
OSKEN_MANAGER = $(VENV_DIR)/bin/osken-manager

help:
	echo "Commands:"
	echo "  make install			- Install all dependencies"
	echo "  make setup-python		- Python $(PYTHON_VERSION) download"
	echo "  make setup-ryu			- Install os-ken into env"
	echo "  make setup-mininet		- Mininet download"
	echo "  make setup-ovs			- Open vSwitch download"
	echo "  make setup-prometheus-client	- Install prometheus-client into env"
	echo "  make clean			- Delete created env"
	echo "  start-mininet			- create topology with 1 vSwitch and 2 hosts"

install: setup-python setup-ovs setup-mininet setup-os-ken setup-prometheus-client
	echo "Everything downloaded!"

setup-python:
	echo "Downloading Python $(PYTHON_VERSION)..."
	sudo add-apt-repository ppa:deadsnakes/ppa -y
	sudo apt update
	sudo apt install -y python$(PYTHON_VERSION) python$(PYTHON_VERSION)-venv python$(PYTHON_VERSION)-dev
	sudo apt install -y curl git build-essential
	curl -sS https://bootstrap.pypa.io/pip/$(PYTHON_VERSION)/get-pip.py | python$(PYTHON_VERSION)
	echo "Python $(PYTHON_VERSION) downloaded with pip"

setup-os-ken:
	echo "Installing os-ken into env..."
	test -d $(VENV_DIR) || python$(PYTHON_VERSION) -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install setuptools==59.6.0 wheel
	$(PIP) install dnspython==1.16.0
	$(PIP) install eventlet==0.30.2
	$(PIP) install os-ken
	$(OSKEN_MANAGER) --version
	echo "os-ken installed"

setup-prometheus-client:
	echo "Installing prometheus-client into env..."
	test -d $(VENV_DIR) || python$(PYTHON_VERSION) -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install prometheus-client
	echo "prometheus-client installed"

setup-ovs:
	echo "Downloading Open vSwitch..."
	sudo apt install -y openvswitch-switch openvswitch-common
	sudo systemctl start openvswitch-switch
	sudo systemctl enable openvswitch-switch
	sudo ovs-vsctl --version
	echo "Open vSwitch downloaded"

setup-mininet:
	echo "Downloading Mininet..."
	sudo apt install -y mininet
	sudo mn --version
	echo "Mininet downloaded"

clean:
	echo "Cleaning..."
	rm -rf $(VENV_DIR)
	echo "env deleted"

start-mininet:
	echo "starting topology"
	sudo mn --topo=single,2 \
		--controller=remote,ip=127.0.0.1,port=6633 \
		--switch=ovsk,protocols=OpenFlow13

