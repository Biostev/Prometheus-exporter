.PHONY: help install clean setup-python setup-ryu setup-mininet setup-ovs

PYTHON_VERSION = 3.8
VENV_DIR = $(HOME)/ryu-env
RYU_DIR = $(HOME)/ryu
PROJECT_DIR = $(shell pwd)
PIP = $(VENV_DIR)/bin/pip
PYTHON = $(VENV_DIR)/bin/python
RYU_MANAGER = $(VENV_DIR)/bin/ryu-manager

help:
	echo "Commands:"
	echo "  make install      - Install all dependencies"
	echo "  make setup-python - Python $(PYTHON_VERSION) download"
	echo "  make setup-ryu    - Install Ryu into env"
	echo "  make setup-mininet - Mininet download"
	echo "  make setup-ovs    - Open vSwitch download"
	echo "  make clean    - Delete created env"

install: setup-python setup-ovs setup-mininet setup-prometheus setup-ryu test
	echo "Everything downloaded!"

setup-python:
	echo "Downloading Python $(PYTHON_VERSION)..."
	sudo add-apt-repository ppa:deadsnakes/ppa -y
	sudo apt update
	sudo apt install -y python$(PYTHON_VERSION) python$(PYTHON_VERSION)-venv python$(PYTHON_VERSION)-dev
	sudo apt install -y curl git build-essential
	curl -sS https://bootstrap.pypa.io/pip/$(PYTHON_VERSION)/get-pip.py | python$(PYTHON_VERSION)
	echo "Python $(PYTHON_VERSION) downloaded with pip"

setup-ryu:
	echo "Installing Ruy into env..."
	test -d $(VENV_DIR) || python$(PYTHON_VERSION) -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install setuptools==59.6.0 wheel
	$(PIP) install dnspython==1.16.0
	$(PIP) install ryu==4.34
	$(RYU_MANAGER) --version
	echo "Ryu installed"

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
