"""Mininet tests: 1_2 and n_k"""
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info


def create_topology1_2():
    """1_2 mininet test"""
    # Create net
    net = Mininet(
        controller=RemoteController,
        switch=OVSSwitch,
        autoSetMacs=True\
    )
    
    # Create controller
    net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=6633,
        protocol='tcp'
    )
    
    # Create switch
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    
    # Add 2 hosts for switch
    h1 = net.addHost('h1', ip='10.0.0.1/8')
    h2 = net.addHost('h2', ip='10.0.0.2/8')
    
    # Build links between hosts and the switch
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    
    net.start()
    
    # h1 and h2 ping each other
    result = net.ping([h1, h2])
    
    CLI(net)
    
    # Stop the net
    net.stop()


def create_topology_n_k(switch_cnt, hosts_cnt):
    """n_k mininet test"""
    # Create net
    net = Mininet(
        controller=RemoteController,
        switch=OVSSwitch,
        waitConnected=True
    )

    # Create controller
    c1 = net.addController( 'c1', port=6633 )

    # Create n switches (names are s1 ... sn)
    switches = []
    for i in range(1, switch_cnt + 1):
        s = net.addSwitch(f's{i}', protocols='OpenFlow13')
        switches.append(s)

    print(f"{switch_cnt} switches created")

    # Create hosts array with hosts of each switch [[s1_hosts] ... [sn_hosts]]
    # [[h1 ... hk] [hk+1 ... h2k] ... [h(n-1)k+1 ... hnk]]
    all_hosts = []
    h_num = 1
    for i in range(switch_cnt):
        all_hosts.append([])
        for j in range(1, hosts_cnt + 1):
            h = net.addHost(f'h{h_num}', ip=f'10.0.0.{h_num}/8')
            all_hosts[i].append(h)
            h_num += 1

    # Add links
    for i, switch in enumerate(switches):
        for host in all_hosts[i]:
            net.addLink(host, switch)

    print(f"{hosts_cnt} hosts created and linked for every switch")

    net.build()

    c1.start()
    
    for s in switches:
        s.start([c1])

    # Each host pings all other hosts of its switch
    # <= 5 attempts for each ping
    for hosts_pack in all_hosts:
        for i in range(len(hosts_pack) - 1):
            for j in range(i + 1, len(hosts_pack)):
                cnt = 1
                result = net.ping([hosts_pack[i], hosts_pack[j]])
                info(result)
                while cnt < 5 and result:
                    result = net.ping([hosts_pack[i], hosts_pack[j]])
                    cnt += 1
                info(f"Ping {hosts_pack[i].name} <-> {hosts_pack[j].name}: {result}")

    CLI( net )

    net.stop()
