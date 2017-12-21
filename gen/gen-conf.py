#!/usr/bin/env python3
import argparse
import json
import sys
from copy import deepcopy

pipeline_args = {}
def cli_arg(*args, **kw):
  def decorator(method):
    def wrap(self):
      return method(self)
    component = method.__name__[len('add_'):]
    pipeline_args[component] = pipeline_args.get(component, []) + [(args, kw)]
    wrap.__name__ = method.__name__
    return wrap
  return decorator


class PL (object):

  def __init__ (self, args):
    self.args = args
    self.components = ['base']
    self.conf = {}

  def create_conf (self):
    for c in self.components:
      method = getattr(self, 'add_%s' % c)
      method()
    return self.conf

  def add_base (self):
    self.conf['pipeline'] = args.pipeline
    self.conf['fakedrop'] = args.fakedrop
    self.conf['run_time'] = [] # Commands to be executed in every second

  @cli_arg('--bst', '-b', type=int, default=1,
            help='Number of base stations (max: 64516)')
  def add_bsts (self):
    bsts = []
    for b in range(self.args.bst):
      bsts.append({
        'id': b,
        'mac': 'aa:cc:dd:cc:%02x:%02x' % (int(b / 254), (b % 254) + 1),
        'ip': '1.1.%d.%d' % (int(b / 254), (b % 254) + 1),
        'port': None,
      })
    self.conf['bsts'] = bsts

  @cli_arg('--server', '-s', type=int, default=1,
           help='Number of servers (max: 64516)')
  def add_servers (self):
    srvs = []
    for s in range(self.args.server):
      srvs.append({
        'ip': '2.%d.%d.2' % (int(s / 254), (s % 254) + 1),
        'nhop': s % self.args.nhop
      })
    self.conf['srvs'] = srvs

  @cli_arg('--nhop', '-n', type=int, default=2,
           help='Number of next-hops towards the servers')
  def add_nhops (self):
    nhops = []
    for n in range(self.args.nhop):
      nhops.append({
        'dmac': 'aa:bb:bb:aa:%02x:%02x' % (int(n / 254), (n % 254) + 1),
        'smac': 'ee:dd:dd:aa:%02x:%02x' % (int(n / 254), (n % 254) + 1),
        'port': None,
      })
    self.conf['nhops'] = nhops

  @cli_arg('--user', '-u', type=int, default=1,
           help='Number of users (max: 64516)')
  @cli_arg('--rate-limit', '-r', type=int, default=10000,
           help='Rate limiter [bit/s]')
  def add_users (self):
    users = []
    for u in range(self.args.user):
      users.append({
        'ip': '3.3.%d.%d' % (int(u / 254), (u % 254) + 1),
        'tun_end': u % self.args.bst,
        'teid': u + 1,
        'rate_limit': self.args.rate_limit,
      })
    self.users = users
    self.conf['users'] = users

  @cli_arg('--fw-rules', '-f', type=int, default=1,
           help='Number of firewall rules')
  def add_fw (self):
    ul_fw_rules = []
    dl_fw_rules = []
    for i in range(self.args.fw_rules):
      ul_fw_rules.append({
        'src_ip': '25.%d.1.1' % i,
        'dst_ip': '26.%d.2.2' % (200 - i),
        'src_port': 1000 + i,
        'dst_port': 1500 - i,
      })
      dl_fw_rules.append({
        'src_ip': '27.%d.1.1' % i,
        'dst_ip': '28.%d.2.2' % (200 - i),
        'src_port': 1000 + i,
        'dst_port': 1500 - i,
      })
    self.conf.update(
      {'ul_fw_rules': ul_fw_rules,
       'dl_fw_rules': dl_fw_rules,
      })


  @cli_arg('--user-conn', type=int, default=1,
                    help='Number of connections for each user (max: 65535)')
  def add_nat (self):
    # The 'nat' component depends on the 'users' component
    # NB: this requirement is not checked.
    nat = []
    pub_ip_format_str = '200.1.%d.%d'  # TODO: Make this configurable
    max_port = 65534
    for user in self.users:
      priv_ip = user['ip']
      for c in range(self.args.user_conn):
        priv_port = c + 1
        port_idx = (user['teid']-1) * self.args.user_conn + c
        pub_port = (port_idx % max_port) + 1
        incr = int((port_idx / max_port))
        pub_ip = pub_ip_format_str % (int(incr / 254), (incr % 254) + 1)
        nat.append({'priv_ip': priv_ip,
                    'priv_port': priv_port,
                    'pub_ip': pub_ip,
                    'pub_port': pub_port,
                    'proto': 6, # TCP
        })
    self.conf['nat_table'] = nat

  def add_dcgw (self):
    self.conf['dcgw'] = {
      'vni': 666,
      'ip': '211.0.0.1',
      'mac':'ac:dc:AC:DC:ac:dc',
    }

  @cli_arg('--gw-ip', type=str, default='200.0.0.1',
           help='Gateway IP address')
  @cli_arg('--gw-mac', type=str, default='aa:22:bb:44:cc:66',
           help='Gateway MAC address')
  @cli_arg('--downlink-default-gw-ip', type=str, default='200.0.0.222',
           help='Default gateway IP address, downlink direction')
  @cli_arg('--downlink-default-gw-mac', type=str, default='aa:22:bb:44:cc:67',
           help='Default gateway MAC address, downlink direction')
  def add_gw (self):
    self.conf['gw'] = {
      'ip': self.args.gw_ip,
      'mac': self.args.gw_mac,
      'default_gw' : {'ip': self.args.downlink_default_gw_ip,
                      'mac': self.args.downlink_default_gw_mac,
      },
    }

  @cli_arg('--fluct-user', type=int, default=0,
           help='Number of fluctuating users per second')
  def add_fluct_user (self):
    # Generate extra users to fluctuate
    extra_users = []
    for u in range(self.args.fluct_user):
        extra_users.append({
            'ip': '4.4.%d.%d' % (int(u / 254), (u % 254) + 1),
            'bst': u % self.args.bst,
            'teid': u + self.args.user + 1,
            'rate_limit': self.args.rate_limit,
        })
    fl_u_add = []
    fl_u_del = []
    for i in range(self.args.fluct_user):
        user = extra_users[i]
        fl_u_add = fl_u_add + [{'action': 'add_user', 'args': user}]
        fl_u_del = [{'action': 'del_user', 'args': user}] + fl_u_del

    self.conf['run_time'] = fl_u_add + self.conf['run_time'] + fl_u_del

  @cli_arg('--fluct-server', type=int, default=0,
           help='Number of fluctuating servers per second')
  def add_fluct_server (self):
    # Generate extra servers to fluctuate
    extra_servers = []
    for s in range(self.args.fluct_server):
        extra_servers.append({
            'ip': '5.%d.%d.2' % (int(s / 254), (s % 254) + 1),
            'nhop': s % self.args.nhop
        })
    fl_s_add = []
    fl_s_del = []
    for i in range(self.args.fluct_server):
        server = extra_servers[i]
        fl_s_add = fl_s_add + [{'action': 'add_server', 'args': server}]
        fl_s_del = [{'action': 'del_server', 'args': server}] + fl_s_del

    self.conf['run_time'] = fl_s_add + self.conf['run_time'] + fl_s_del


class PL_mgw (PL):
  "Mobile Gateway"

  def __init__ (self, args):
    super(PL_mgw, self).__init__(args)
    self.components += ['gw', 'bsts', 'servers', 'nhops', 'users',
                        'handover', 'fluct_server', 'fluct_user']


  @cli_arg('--handover', type=int, default=0,
           help='Number of handovers per second')
  def add_handover (self):
    run_time = []
    for i in range(self.args.handover):
      # new_bst_id = (old_bst_id + bst_shift) % args.bst
      user = self.users[i % self.args.user]
      run_time.append({'action': 'handover',
                       'args': {
                         'user_teid': user['teid'],
                         'bst_shift': i + 1,
                       }})

    self.conf['run_time'].append(run_time)


class PL_vmgw (PL_mgw):
  "Virtual Mobile Gateway"

  def __init__ (self, args):
    super(PL_vmgw, self).__init__(args)
    self.components += ['dcgw', 'fw', 'apps']

  @cli_arg('--napps', type=int, default=1,
           help='Number of apps')
  def add_apps (self):
    if self.args.napps != 1:
      raise NotImplementedError('Currently, one app is supported.')
    self.conf['napps'] = self.args.napps


class PL_bng (PL):
  "Broadband Network Gateway"

  def __init__ (self, args):
    super(PL_bng, self).__init__(args)
    self.components += ['fw', 'cpe', 'gw', 'users', 'nat',
                        'servers', 'nhops', 'fluct_server', 'fluct_user']


  @cli_arg('--cpe', type=int, default=1,
            help='Number of Customer Premises Equipments (max: 64516)')
  def add_cpe (self):
    cpe = []
    for b in range(self.args.cpe):
      cpe.append({
        'id': b,
        'mac': 'aa:cc:dd:cc:%02x:%02x' % (int(b / 254), (b % 254) + 1),
        'ip': '1.1.%d.%d' % (int(b / 254), (b % 254) + 1),
        'port': None,
      })
    self.conf['cpe'] = cpe

  def add_users (self):
    users = []
    for u in range(self.args.user):
      users.append({
        'ip': '3.3.%d.%d' % (int(u / 254), (u % 254) + 1),
        'tun_end': u % self.args.cpe,
        'teid': u + 1,
        'rate_limit': self.args.rate_limit,
      })
    self.users = users
    self.conf['users'] = users


def list_pipelines():
  l = [n[3:] for n in globals() if n.startswith('PL_')]
  return sorted(l)

def show_per_pipeline_help(args):
  parser = argparse.ArgumentParser()
  parser.formatter_class = argparse.ArgumentDefaultsHelpFormatter
  pl = globals()['PL_%s' % args.pipeline]({})
  for component in pl.components:
    for arg_def in pipeline_args.get(component, []):
      parser.add_argument(*arg_def[0], **arg_def[1])
  parser.usage = "\n\n%s (%s)"  % (pl.__doc__, args.pipeline)
  parser.parse_args(['-h'])

parser = argparse.ArgumentParser()
parser.add_argument('--json', '-j', type=argparse.FileType('r'),
                    help='Override default settings from config file')
parser.add_argument('--output', '-o', type=argparse.FileType('w'),
                    help='Output file',
                    default='/dev/stdout')
parser.add_argument('--pipeline', '-p', type=str, choices=list_pipelines(),
                    help='Name of the pipeline', default='mgw')
parser.add_argument('--fakedrop', dest='fakedrop',
                    help='If enabled, packages to drop are '
                    'forwarded to outport instead of drop. '
                    '(default)',
                    action='store_true')
parser.add_argument('--no-fakedrop', dest='fakedrop',
                    help='If disabled, packages to drop are '
                    'really droped.',
                    action='store_false')
parser.set_defaults(fakedrop=True)
parser.add_argument('--info', action='store_true',
                    help='Show detailed info of a pipeline and exit')
parser.set_defaults(info=False)

# Map components to pipelines
comp2pl = {}
for pl_name in list_pipelines():
  pl = globals()['PL_%s' % pl_name]({})
  for c in pl.components:
    comp2pl[c] = comp2pl.get(c, []) + [pl_name]

group = parser.add_argument_group('pipeline agruments')
for component, arg_defs in pipeline_args.items():
  available_in = ','.join(comp2pl[component])
  for arg_def in arg_defs:
    kw = deepcopy(arg_def[1])
    kw['help'] = kw.get('help', '') + ' [%s]' % available_in
    group.add_argument(*arg_def[0], **kw)

args = parser.parse_args()

if args.json:
  new_defaults = json.load(args.json)
  parser.set_defaults(**new_defaults)
  args = parser.parse_args()

if args.info:
  show_per_pipeline_help(args)
else:
  pl = globals()['PL_%s' % args.pipeline](args)
  conf = pl.create_conf()
  json.dump(conf, args.output, sort_keys=True, indent=4)
  args.output.write("\n")
