.PHONY: help install clean setup-python setup-mininet setup-venv

PYTHON_VERSION = 3.8
VENV_DIR = $(HOME)/ryu-env
RYU_DIR = $(HOME)/ryu
PROJECT_DIR = $(shell pwd)
PIP = $(VENV_DIR)/bin/pip
PYTHON = $(VENV_DIR)/bin/python
OSKEN_MANAGER = $(VENV_DIR)/bin/osken-manager
REQ_FILE = requirements.txt

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

install: setup-python setup-mininet setup-venv
	echo "Everything downloaded!"

setup-python:
	echo "Downloading Python $(PYTHON_VERSION)..."
	sudo add-apt-repository ppa:deadsnakes/ppa -y
	sudo apt update
	sudo apt install -y python$(PYTHON_VERSION) python$(PYTHON_VERSION)-venv python$(PYTHON_VERSION)-dev
	sudo apt install -y curl git build-essential
	curl -sS https://bootstrap.pypa.io/pip/$(PYTHON_VERSION)/get-pip.py | python$(PYTHON_VERSION)
	echo "Python $(PYTHON_VERSION) downloaded with pip"

setup-venv:
	echo "Installing python libs"
	$(VENV_DIR)/bin/activate
	$(PIP) install --upgrade pip
	$(PIP) install -r $(REQ_FILE)
	echo "Python dependencies installed"

setup-mininet:
	echo "Downloading Mininet..."
	sudo apt install -y mininet
	sudo mn --version
	echo "Mininet downloaded"

clean:
	echo "Cleaning..."
	rm -rf $(VENV_DIR)
	echo "venv deleted"

start-mininet:
	echo "starting topology"
	sudo mn --topo=single,2 \
		--controller=remote,ip=127.0.0.1,port=6633 \
		--switch=ovsk,protocols=OpenFlow13

