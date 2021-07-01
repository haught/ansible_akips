

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
    name: haught.akips.akips_inventory
    plugin_type: inventory
    author:
        - Matt Haught (@haught)
    short_description: Akips Inventory Plugin
    version_added: "2.10"
    description:
        - Akips Inventory plugin.
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
            required: false
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
            - Add additional hostvars to a host device
            - Contains a list of Regexes to match against the host's group and a dictionary of hostvars
            type: dict
        exclude_groups:
            description:
            - A regex to match aginst retreived group names to excude
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
            description: Proxy server to use for requests to Akips.
            type: string
            default: ''
'''

EXAMPLES = r'''
# Simple Inventory Plugin example
plugin: haught.akips.akips_inventory
host: akips.example.com
username: api-ro
password: password

# Inventory Plugin example with extra hostvars
plugin: haught.akips.akips_inventory
host: akips.example.com
username: api-ro
password: password
group_hostvars:
    IOS:
        ansible_network_os: ios
        ansible_connection: network_cli
    NX-OS:
        ansible_network_os: nxos
        ansible_connection: network_cli

# Inventory Plugin example with excludes defined
plugin: haught.akips.akips_inventory
host: akips.example.com
username: api-ro
password: password
exclude_groups: ^Linux$|maintenance_mode
exclude_hosts: testing
exclude_networks: 10\.11\.12\.
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
        valid = False
        if super(InventoryModule, self).verify_file(path):
            if path.endswith(('akips.yaml', 'akips.yml')):
                valid = True
            else:
                self.display.vvv('Skipping due to inventory source not ending in "akips.yaml" nor "akips.yml"')
        return valid

    def groups(self):
        session = requests.Session()

        groupurl = '{host}/api-db?password={password};cmds=list+device+group'
        groupurl = groupurl.format(host=self.get_option('host'), password=self.get_option('password'))
        grouplines = []

        if not self.update_cache:
            try:
                grouplines = self._cache[self.cache_key][groupurl]
            except KeyError:
                pass

        if not grouplines:
            if self.cache_key not in self._cache:
                self._cache[self.cache_key] = {groupurl: ''}
            groupresponse = session.get(
                groupurl,
                proxies={'http': self.get_option('proxy'), 'https': self.get_option('proxy')})
            grouplines = groupresponse.text.splitlines()
            self._cache[self.cache_key] = {groupurl: grouplines}

        groupsuperurl = '{host}/api-db?password={password};cmds=list+device+super+group'
        groupsuperurl = groupsuperurl.format(host=self.get_option('host'), password=self.get_option('password'))
        groupsuperlines = []

        if not self.update_cache:
            try:
                groupsuperlines = self._cache[self.cache_key][groupsuperurl]
            except KeyError:
                pass

        if not groupsuperlines:
            if self.cache_key not in self._cache:
                self._cache[self.cache_key] = {groupsuperurl: ''}
            groupsuperresponse = session.get(
                groupsuperurl,
                proxies={'http': self.get_option('proxy'), 'https': self.get_option('proxy')})
            groupsuperlines = groupsuperresponse.text.splitlines()
            self._cache[self.cache_key] = {groupsuperurl: groupsuperlines}
        groups = grouplines + groupsuperlines
        return groups

    def hostsInGroup(self, group):
        session = requests.Session()
        url = '{host}/api-db?password={password};cmds=mget+*+*+ping4+PING.icmpState+value+/up/+any+group+{group}'
        url = url.format(host=self.get_option('host'), password=self.get_option('password'), group=group)
        lines = []

        if not self.update_cache:
            try:
                lines = self._cache[self.cache_key][url]
            except KeyError:
                pass

        if not lines:
            if self.cache_key not in self._cache:
                self._cache[self.cache_key] = {url: ''}
            response = session.get(
                url,
                proxies={'http': self.get_option('proxy'), 'https': self.get_option('proxy')})
            lines = response.text.splitlines()
            self._cache[self.cache_key] = {url: lines}
        return lines

    def addGroupHostVars(self, host, group):
        group_hostvars = self.get_option('group_hostvars') or {}
        for regex in group_hostvars:
            if re.search(regex, group, re.IGNORECASE):
                for key, value in group_hostvars[regex].items():
                    self.inventory.set_variable(host, key, value)

    def parse(self, inventory, loader, path, cache=True):
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

        groups = self.groups()

        for group in groups:
            # groups to ignore
            if self.get_option('exclude_groups') and (group == '' or re.search(self.get_option('exclude_groups'), group)):
                self.display.vvv('Excluding group ' + group)
                continue

            group_name = self.inventory.add_group(group)

            hosts = self.hostsInGroup(group)

            for line in hosts:
                if line == '':
                    continue
                host = line.split(' ')[0]
                ip = line.split(',')[-1]

                # hosts to ignore
                if self.get_option('exclude_hosts') and (host == '' or re.search(self.get_option('exclude_hosts'), host)):
                    self.display.vvv('Excluding host ' + host + ' using name')
                    continue
                # ips to ignore
                if self.get_option('exclude_networks') and (ip == '' or re.search(self.get_option('exclude_networks'), ip)):
                    self.display.vvv('Excluding host ' + host + ' using ip')
                    continue

                self.inventory.add_host(host)
                self.inventory.add_child(group_name, host)
                self.inventory.set_variable(host, 'ansible_host', ip)
                self.addGroupHostVars(host, group)
