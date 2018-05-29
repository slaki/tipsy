#!/usr/bin/env python2

# TIPSY: Telco pIPeline benchmarking SYstem
#
# Copyright (C) 2017-2018 by its authors (See AUTHORS)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""
TIPSY controller for T4P4S pipeline
Run as:

   $ ./tipsy.py

"""

import requests
import json
import os
import signal
import subprocess
import sys
import time
from subprocess import Popen

sys.path.append(os.path.dirname(__file__) + '/../lib')
from object_with_config import ObjectWithConfig

conf_file = '/tmp/pipeline.json'
bm_conf_file = '/tmp/benchmark.json'
t4p4s_conf_l2fwd = '/tmp/l2fwd_conf.txt'
t4p4s_conf_portfwd = '/tmp/portfwd_conf.txt'
t4p4s_conf_l3fwd = '/tmp/l3fwd_conf.txt'
t4p4s_conf_smgw = '/tmp/smgw_conf.txt'

webhook_configured = 'http://localhost:9000/configured'

###########################################################################

def call_cmd(cmd):
    print(' '.join(cmd))
    return subprocess.call(cmd)

def gen_t4p4s_config(sut_conf, cores):
    cpumask = sut_conf.coremask
    portmask = sut_conf.portmask

    cpum = int(cpumask, 16) ## given in hexa
    portm = int(portmask, 16)

    portmapping = []
    available_cores = [ i for i in range(32) if (cpum >> i) & 1 == 1 ]
    available_ports = [ i for i in range(256) if (portm >> i) & 1 == 1 ]

    for p in available_ports:
        rxqueue = 0
        for c in available_cores[0:cores]:
            portmapping.append('(%d,%d,%d)' % (p,rxqueue,c))
            rxqueue += 1

    cfg = ''
    cfg += ' -w %s' % sut_conf.uplink_port
    cfg += ' -w %s' % sut_conf.downlink_port
    cfg += ' -c %s' % cpumask
    cfg += ' -n 4 - --log-level 0 -- '
    cfg += ' -p %s' % portmask
    cfg += ' --config "%s"' % ','.join(portmapping)
    return cfg


class PL(object):
    def __init__(self, parent, conf):
        self.conf = conf
        self.parent = parent
        self.cont_config = None
        self.p4_source = None
        self.p4_version = 'v14'
        # '/home/eptevor/t4p4s16/t4p4s-16/'
        self.t4p4s_home = parent.bm_conf.sut.t4p4s_dir
        self._process = None
        # '-c 0x3 -n 4 - --log-level 3 -- -p 0x3 --config "(0,0,0),(1,0,0)"'
        self.dpdk_config = gen_t4p4s_config(parent.bm_conf.sut, conf.core)
        self.controller = 'dpdk_controller'
        self.ul_port = 0
        self.dl_port = 1

    def compile_and_start(self):
        cmd = './launch.sh'
        p4src = os.path.join(self.t4p4s_home, self.p4_source)
        cmd = [cmd, p4src, self.controller, self.cont_config, '--', self.dpdk_config]
        cmd = ['sudo'] + cmd
        print(cmd, 'cwd=', self.t4p4s_home)
        self._process = subprocess.Popen(cmd, cwd = self.t4p4s_home)

    def stop(self):
        if self._process:
            self._process.terminate()


class PL_new(object):
    def __init__(self, parent, conf):
        self.conf = conf
        self.parent = parent
        self.cont_config = None
        self.p4_source = None
        self.p4_version = 'v14'
        self.t4p4s_home = parent.bm_conf.sut.t4p4s_dir # '/home/p4/t4p4s-16/'
        self._process = None

    def compile_and_start(self):
        cmd = './t4p4s.sh'
        p4src = os.path.join(self.t4p4s_home, self.p4_source)
        print([cmd, self.p4_version, 'ctrcfg', self.cont_config, p4src], 'cwd=', self.t4p4s_home)
        self._process = subprocess.Popen([cmd, self.p4_version, 'ctrcfg', self.cont_config, p4src], cwd = self.t4p4s_home)

    def stop(self):
        if self._process:
            self._process.terminate()


class PL_l2fwd(PL_new):
    """L2 Packet Forwarding

    Upstream the L2fwd pipeline will receive packets from the downlink
    port, perform a lookup for the destination MAC address in a static
    MAC table, and if a match is found the packet will be forwarded to
    the uplink port or otherwise dropped (or likewise forwarded upstream
    if the =fakedrop= parameter is set to =true=).    The downstream
    pipeline is just the other way around, but note that the upstream
    and downstream pipelines use separate MAC tables.
    """

    def __init__(self, parent, conf):
        super(PL_l2fwd, self).__init__(parent, conf)
        self.p4_source = 'examples/l2-switch-test.p4'
        self.p4_version = 'v14'
        self.cont_config = t4p4s_conf_l2fwd

    def config_switch(self):
        # Create a config file for t4p4s controller
        with open(t4p4s_conf_l2fwd, 'w') as conf_file:
            for entry in self.conf.upstream_table:
                out_port = entry.out_port or self.ul_port
                conf_file.write("%s %d\n" % (entry.mac, out_port))

            for entry in self.conf.downstream_table:
                out_port = entry.out_port or self.dl_port
                conf_file.write("%s %d\n" % (entry.mac, out_port))

class PL_portfwd(PL_new):
    """Port Forwarding

    TBA
    """

    def __init__(self, parent, conf):
        super(PL_portfwd, self).__init__(parent, conf)
        self.p4_source = 'examples/portfwd.p4'
        self.p4_version = 'v14'
        self.cont_config = t4p4s_conf_portfwd
        self.controller = 'dpdk_portfwd_controller'

    def config_switch(self):
        # Create a config file for t4p4s controller
        with open(t4p4s_conf_portfwd, 'w') as conf_file:
            if self.conf.mac_swap_downstream:
                conf_file.write("0 1 1 %s\n" % self.conf.mac_swap_downstream)
            else:
                conf_file.write("0 1 0 11:11:11:11:11:11\n")
            if self.conf.mac_swap_upstream:
                conf_file.write("1 0 1 %s\n" % self.conf.mac_swap_upstream)
            else:
                conf_file.write("1 0 0 11:11:11:11:11:11\n")

class PL_l3fwd(PL_new):
    """L3 Forwarding

    TBA
    """

    def __init__(self, parent, conf):
        super(PL_l3fwd, self).__init__(parent, conf)
        self.p4_source = 'examples/l3fwd.p4'
        self.p4_version = 'v14'
        self.cont_config = t4p4s_conf_smgw
        self.controller = 'dpdk_l3fwd_controller'

    def config_switch(self):
        # Create a config file for t4p4s controller
        with open(t4p4s_conf_l3fwd, 'w') as conf_file:
            # Processing nexthop groups
            nhg_idx = 0
            for nhg in self.conf.downstream_group_table:
                out_port = nhg.port or self.dl_port
                conf_file.write("N %d %d %s %s\n" % (nhg_idx, out_port, nhg.smac, nhg.dmac))
                nhg_idx += 1

            nhg_offset = nhg_idx #len(self.conf.downstream_group_table)

            for nhg in self.conf.upstream_group_table:
                out_port = nhg.port or self.ul_port
                conf_file.write("N %d %d %s %s\n" % (nhg_idx, out_port, nhg.smac, nhg.dmac))
                nhg_idx += 1

            # Filling L3fwd tables
            for l3entry in self.conf.downstream_l3_table:
                conf_file.write("E %s %d %d\n" % (l3entry.ip, l3entry.prefix_len, l3entry.nhop))

            for l3entry in self.conf.upstream_l3_table:
                conf_file.write("E %s %d %d\n" % (l3entry.ip, l3entry.prefix_len, nhg_offset + l3entry.nhop))

            # SUT
            conf_file.write("M %s\n" % self.conf.sut.dl_port_mac)
            conf_file.write("M %s\n" % self.conf.sut.ul_port_mac)


class PL_mgw(PL_new):
    """L3 Forwarding

    TBA
    """

    def __init__(self, parent, conf):
        super(PL_mgw, self).__init__(parent, conf)
        self.p4_source = 'examples/vsmgw-no-typedef.p4_16'
        self.p4_version = 'v16'
        self.cont_config = t4p4s_conf_smgw
        self.controller = 'dpdk_smgw_controller'
        self.ul_port = 0
        self.dl_port = 1

    def config_switch(self):

        gwip = self.conf.gw.ip
        gwmac = self.conf.gw.mac

        # Create a config file for t4p4s controller
        with open(t4p4s_conf_smgw, 'w') as conf_file:
            # Processing nexthop groups
            nhg_idx = 0
            for nhg in self.conf.nhops:
                out_port = nhg.port or self.ul_port
                conf_file.write("N %d %d %s %s\n" % (nhg_idx, out_port, nhg.smac, nhg.dmac))
                nhg_idx += 1

            nhg_offset = nhg_idx #len(self.conf.downstream_group_table)

            for bs in self.conf.bsts:
                out_port = bs.port or self.dl_port
                conf_file.write("N %d %d %s %s\n" % (nhg_idx, out_port, gwmac, bs.mac))
                nhg_idx += 1

            #------------------- nhgrp filled -------------------
            # Filling ue_selector tables

            conf_file.write("U %s %d %d %d 0 0.0.0.0\n" % ( gwip, 32, 2152, 0 ))
            for user in self.conf.users:
                conf_file.write("U %s %d %d %d %d %s\n" % (user.ip, 32, 0, 1, user.teid, self.conf.bsts[user.tun_end].ip))

            for srv in self.conf.srvs:
                conf_file.write("E %s %d %d\n" % (srv.ip, srv.prefix_len, srv.nhop))

            for bst in self.conf.bsts:
                conf_file.write("E %s %d %d\n" % (bst.ip, 32, nhg_offset + bst.id))

            # SUT
            conf_file.write("M %s\n" % gwmac) #self.conf.sut.dl_port_mac)
            for bs in self.conf.bsts:
                conf_file.write("M %s\n" % bs.mac) #self.conf.sut.ul_port_mac)


class Tipsy(ObjectWithConfig):

    def __init__(self, *args, **kwargs):
        super(Tipsy, self).__init__(*args, **kwargs)
class Tipsy(ObjectWithConfig):

    def __init__(self, *args, **kwargs):
        super(Tipsy, self).__init__(*args, **kwargs)
        Tipsy._instance = self

        self.conf_file = conf_file
        self.parse_conf('pl_conf', conf_file)
        self.parse_conf('bm_conf', bm_conf_file)

        try:
            self.pl = globals()['PL_%s' % self.pl_conf.name](self, self.pl_conf)
        except (KeyError, NameError) as e:
            print('Failed to instanciate pipeline (%s): %s' %
                  (self.pl_conf.name, e))
            raise(e)

    def start_datapath(self):
        self.pl.compile_and_start()

        time.sleep(60)
        try:
            requests.get(webhook_configured)
        except requests.ConnectionError:
            pass

    def stop_datapath(self):
        self.pl.stop()

    def configure(self):
        self.pl.config_switch()

    def stop(self):
        self.stop_datapath()


def handle_sigint(sig_num, stack_frame):
    Tipsy().stop()

signal.signal(signal.SIGINT, handle_sigint)

if __name__ == "__main__":
    Tipsy().configure()
    print('DataPath configured...')
    Tipsy().start_datapath()
    print('DataPath started...')
    signal.pause()

