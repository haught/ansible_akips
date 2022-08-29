# Ansible Collection - haught.akips

This collection is in the early stages of supporting **AKiPs Network Monitoring Software**.

## Inventory

To use the inventory plugin provided by this collection you will need to enable the plugin in your *.ansible.cfg*. (You may need to enable some of the defaults if you use them)

```ini
[inventory]
enable_plugins = haught.akips.akips_inventory
```

You will need to create a inventory file that **ends** in *akips.yaml* or *akips.yml*. For example *inventory_akips.yaml*.

```yaml
---
plugin: haught.akips.akips_inventory
host: https://akips.example.com
username: api-ro
password: xxxxxxxx
```

You can limit what goes into the inventory using *restrict_groups*, *exclude_groups*, *exclude_hosts*, and *exclude_networks*. These all work using regexs. Here is an example using a few of them.

```yaml
---
plugin: haught.akips.akips_inventory
host: https://akips.example.com
username: api-ro
password: xxxxxxxx
restrict_groups: 'Cisco-IOS|Cisco-NXOS'
exclude_groups: '^Old-Campus|^Lab'
exclude_hosts: 'bld1.*'
```

Host variables can be added using *group_hostvars* and *host_hostvars*.

```yaml
---
plugin: haught.akips.akips_inventory
host: https://akips.example.com
username: api-ro
password: xxxxxxxx
restrict_groups: '^Cisco-IOS|^Cisco-NXOS'
exclude_groups: '^Old-Campus|^Lab'
exclude_hosts: 'bld1.*'
group_hostvars:
    IOS:
        ansible_network_os: cisco.ios.ios
        ansible_connection: ansible.netcommon.network_cli
    NX-OS:
        ansible_network_os: cisco.nxos.nxos
        ansible_connection: ansible.netcommon.network_cli
host_hostvars:
    3650:
        foo: bar
```



See [akips_inventory.py](https://github.com/haught/ansible_akips/blob/main/plugins/inventory/akips_inventory.py) for additional details and options on how to exclude groups and hosts and add additional host variables.

You can test retreiving hosts using *ansible-inventory*.
```bash
ansible-inventory -i inventory_akips.yaml --list
```

To run a playbook using the inventory you can do something like:
```bash
ansible-playbook -i inventory_akips.yaml -l myswitch test_playbook.yaml
```


## Developing

PRs are always welcome.

Developing is a bit of a pain. First create the hierarchy some of the ansible apps expect. Create directories *ansible_collections/haught/akips* and clone the repo directly into the akips directory.

Next you can symlink the *akips* directory to your default ansible collections folder with a haught subdirectory, for example:

```bash
mkdir ~/.ansible/collections/ansible_collections/haught
ln -s ~/devel/ansible_collections/haught/akips ~/.ansible/collections/ansible_collections/haught/
```

Sanity tests:
```bash
ansible-test sanity --docker --python 3.6 plugins/inventory/akips_inventory.py
```
