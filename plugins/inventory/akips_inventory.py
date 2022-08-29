# Copyright (c) 2018 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
    name: akips_inventory
    author:
        - Matt Haught (@haught)

    short_description: Akips inventory source.

    description:
        - Bring in Akips groups and devices. Without options it will bring in everything.
        - Using restrict and exclude, you can limit what is pulled in.
        - Host variables can be added by the group or individually for a host.
        - Group variables are overwritten by matching individual host variabless.
        - Uses *_akips.(yml|yaml) YAML configuration file to set parameter values.

    extends_documentation_fragment:
        - constructed
        - inventory_cache

    requirements:
        - python requests (requests)
        - netaddr

    options:
        plugin:
            description: The name of the Akips Inventory Plugin, this should always be 'haught.akips.akips_inventory'.
            required: True
            choices: ['haught.akips.akips_inventory']
        host:
            description:
            - The Akips hostname.
            - This value is FQDN for Akips host.
            - If the value is not specified in the task, the value of environment variable C(AKIPS_HOST) will be used instead.
            - Mutually exclusive with C(instance).
            type: str
            required: true
            env:
                - name: AKIPS_HOST
        username:
            description:
            - Name of user for connection to Akips.
            - If the value is not specified, the value of environment variable C(AKIPS_USERNAME) will be used instead.
            required: true
            type: str
            env:
                - name: AKIPS_USERNAME
        password:
            description:
            - Password for username.
            - If the value is not specified, the value of environment variable C(AKIPS_PASSWORD) will be used instead.
            required: true
            type: str
            env:
                - name: AKIPS_PASSWORD
        group_hostvars:
            description:
            - Add additional hostvars to a group of host devices
            - Contains a list of Regexes to match against the host's group and a dictionary of hostvars
            type: dict
        host_hostvars:
            description:
            - Add additional hostvars to a host device
            - Contains a list of Regexes to match against the host's name and a dictionary of hostvars
            type: dict
        restrict_groups:
            description:
            - A regex to match aginst Akips group names to only include
            - Only hosts in matching groups will be in the inventory
            type: str
            env:
                - name: AKIPS_RESTRICT_GROUPS
        exclude_groups:
            description:
            - A regex to match aginst Akips group names to excude
            type: str
            env:
                - name: AKIPS_EXCLUDE_GROUPS
        exclude_hosts:
            description:
            - A regex to match aginst host's name to excude
            type: str
            env:
                - name: AKIPS_EXCLUDE_HOSTS
        exclude_networks:
            description:
            - A regex to match aginst host's ip to excude
            type: str
            env:
                - name: AKIPS_EXCLUDE_NETWORKS
        proxy:
            description:
            - Proxy server to use for requests to Akips.
            type: string
            default: ''
'''

EXAMPLES = r'''
# Simple Inventory Plugin example
plugin: haught.akips.akips_inventory
host: https://akips.example.com
username: api-ro
password: xxxxxxxxxxx

# Inventory Plugin example with extra hostvars
plugin: haught.akips.akips_inventory
host: https://akips.example.com
username: api-ro
password: xxxxxxxxxxx
group_hostvars:
    IOS:
        ansible_network_os: cisco.ios.ios
        ansible_connection: ansible.netcommon.network_cli
    NX-OS:
        ansible_network_os: cisco.nxos.nxos
        ansible_connection: ansible.netcommon.network_cli
host_hostvars:
    3650:
        ansible_network_os: cisco.ios.ios
        ansible_connection: ansible.netcommon.network_cli

# Inventory Plugin example with excludes defined
plugin: haught.akips.akips_inventory
host: https://akips.example.com
username: api-ro
password: xxxxxxxxxxx
exclude_groups: ^Linux$|maintenance_mode
exclude_hosts: testing
exclude_networks: 10\.11\.12\.

# Inventory Plugin example with restrict_groups
plugin: haught.akips.akips_inventory
host: https://akips.example.com
username: api-ro
password: xxxxxxxxxxx
restrict_groups: Cisco|Juniper
'''

try:
    import re
    HAS_REGEX = True
except ImportError:
    HAS_REGEX = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from ansible.errors import AnsibleError, AnsibleParserError
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable, to_safe_group_name


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):

    NAME = 'haught.akips.akips_inventory'

    def verify_file(self, path):
        ''' Check if inventory file is name correctly '''
        valid = False
        if super(InventoryModule, self).verify_file(path):
            if path.endswith(('akips.yaml', 'akips.yml')):
                valid = True
            else:
                self.display.vvv('Skipping due to inventory source not ending in "akips.yaml" nor "akips.yml"')
        return valid

    def _get_all_groups(self):
        ''' Get all Akips groups '''
        session = requests.Session()

        groupurl = '{host}/api-db?username={username}&password={password};cmds=list+device+group'
        groupurl = groupurl.format(host=self.get_option('host'), username=self.get_option('username'), password=self.get_option('password'))

        groupresponse = session.get(
            groupurl,
            proxies={'http': self.get_option('proxy'), 'https': self.get_option('proxy')})
        grouplines = groupresponse.text.splitlines()

        groupsuperurl = '{host}/api-db?username={username}&password={password};cmds=list+device+super+group'
        groupsuperurl = groupsuperurl.format(host=self.get_option('host'), username=self.get_option('username'), password=self.get_option('password'))

        groupsuperresponse = session.get(
            groupsuperurl,
            proxies={'http': self.get_option('proxy'), 'https': self.get_option('proxy')})
        groupsuperlines = groupsuperresponse.text.splitlines()

        groups = grouplines + groupsuperlines
        return groups

    def _get_hosts_in_group(self, group):
        ''' Lookup hosts in an Akips group '''
        session = requests.Session()
        url = '{host}/api-db?username={username}&password={password};cmds=mget+*+*+ping4+PING.icmpState+value+/up/+any+group+{group}'
        url = url.format(host=self.get_option('host'), username=self.get_option('username'), password=self.get_option('password'), group=group)

        response = session.get(
            url,
            proxies={'http': self.get_option('proxy'), 'https': self.get_option('proxy')})
        lines = response.text.splitlines()

        return lines

    def _get_group_hostvars(self, group):
        ''' Return group specific host variables '''
        hostvars = {}
        group_hostvars = self.get_option('group_hostvars') or {}
        for regex in group_hostvars:
            if re.search(regex, group, re.IGNORECASE):
                for key, value in group_hostvars[regex].items():
                    hostvars[key] = value
        return hostvars

    def _get_host_hostvars(self, host):
        ''' Return host specific host variables '''
        hostvars = {}
        host_hostvars = self.get_option('host_hostvars') or {}
        for regex in host_hostvars:
            if re.search(regex, host, re.IGNORECASE):
                for key, value in host_hostvars[regex].items():
                    hostvars[key] = value
        return hostvars

    def _get_inventory(self):
        ''' Return hosts and their attributes '''
        output = {}
        groups = self._get_all_groups()

        if self.get_option('restrict_groups'):
            restrict_groups_re = re.compile(self.get_option('restrict_groups'))

        if self.get_option('exclude_hosts'):
            exclude_hosts_re = re.compile(self.get_option('exclude_hosts'))

        if self.get_option('exclude_networks'):
            exclude_networks_re = re.compile(self.get_option('exclude_networks'))

        for group in groups:
            # groups to ignore
            if self.get_option('exclude_groups') and (group == '' or re.search(self.get_option('exclude_groups'), group)):
                self.display.vv('Excluding group {group} using AKIPS_EXCLUDE_GROUPS'.format(group=group))
                continue

            hosts = self._get_hosts_in_group(group)

            for line in hosts:
                if line == '':
                    continue
                host = line.split(' ')[0]
                ip = line.split(',')[-1]

                if host == '':
                    self.display.vv('Ignoring empty host')
                    continue

                if ip == '':
                    self.display.vv('Ignoring host {host} with empty IP address'.format(host=host))
                    continue

                if host in groups:
                    self.display.warning('Host has same name as a group, cannot add {host}'.format(host=host))
                    continue

                # exclude hosts
                if self.get_option('exclude_hosts') and (exclude_hosts_re.search(host)):
                    self.display.vv('Excluding host {host} using AKIPS_EXCLUDE_HOSTS'.format(host=host))
                    continue

                # exclude networks
                if self.get_option('exclude_networks') and (exclude_networks_re.search(ip)):
                    self.display.vv('Excluding host {host} using AKIPS_EXCLUDE_NETWORKS'.format(host=host))
                    continue

                if host not in output:
                    output[host] = {'groups': [], 'hostvars': {'ansible_host': ip}}

                if group not in output[host]['groups']:
                    output[host]['groups'].append(group)

                output[host]['hostvars'].update(self._get_group_hostvars(group))

        # host hostvars should take precedence over group hostvars
        for host in output:
            output[host]['hostvars'].update(self._get_host_hostvars(host))

        # remove any hosts not in restrict_groups
        if self.get_option('restrict_groups'):
            restricted_output = {}
            for host, values in output.items():
                if list(filter(restrict_groups_re.search, values['groups'])):
                    restricted_output[host] = output[host]
            return restricted_output

        return output

    def parse(self, inventory, loader, path, cache=True):
        ''' Add Akips inventory to ansible inventory '''
        super(InventoryModule, self).parse(inventory, loader, path)

        if not HAS_REQUESTS:
            raise AnsibleParserError(
                'Please install "requests" Python module as this is required'
                ' for Akips dynamic inventory plugin.')

        if not HAS_REGEX:
            raise AnsibleParserError(
                'Please install "re" Python module as this is required'
                ' for Akips dynamic inventory plugin.')

        self._read_config_data(path)

        self.cache_key = self.get_cache_key(path)

        self.use_cache = self.get_option('cache') and cache
        self.update_cache = self.get_option('cache') and not cache
        akips_inventory = None

        if self.use_cache:
            try:
                akips_inventory = self._cache[self.cache_key]
            except KeyError:
                self.update_cache = True

        if not akips_inventory:
            akips_inventory = self._get_inventory()

        if self.update_cache:
            self._cache[self.cache_key] = akips_inventory

        for host, attributes in akips_inventory.items():
            self.inventory.add_host(host)
            for group in attributes['groups']:
                self.inventory.add_group(group)
                self.inventory.add_child(group, host)
            for key, value in attributes['hostvars'].items():
                self.inventory.set_variable(host, key, value)
