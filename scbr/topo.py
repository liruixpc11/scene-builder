import ipaddress
import uuid
import io
import abc
import numbers
import re
from enum import Enum
import xml.etree.cElementTree as ET
from xml.dom import minidom

from scbr.utils import auto_str


IP_PATTERN = re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')


class NodeCategory(Enum):
    Host = 1
    Switch = 2


@auto_str()
class Topology:
    def __init__(self):
        self.nodes = dict()

    def add_node(self, node):
        self.nodes[node.id] = node

    def query_node(self, node_id):
        return self.nodes[node_id]


@auto_str()
class Node:
    def __init__(self, id_, name, category, template_id, options=None):
        self.id = id_
        self.name = name
        self.category = category.name
        self.template_id = template_id if template_id else ''
        self.emulation = "vsphere"
        self.image = ''
        self.os = ''
        self.options = options if options else dict()
        self.ports = []
        self.next_port_index = 1

    def use_default_physic(self):
        if self.os == 'windows':
            self.options['cpuCount'] = Option(2, unit='个')
            self.options['ram'] = Option(2048, unit='MB')
        else:
            self.options['cpuCount'] = Option(1, unit='个')
            self.options['ram'] = Option(1024, unit='MB')

    def add_port(self):
        index = self.next_port_index
        self.next_port_index += 1

        port = Port(self, index)
        self.ports.append(port)
        return port

    def link_to_node(self, other, **kwargs):
        port1 = self.add_port()
        port2 = other.add_port()
        Link(port1, port2, **kwargs)
        return port1, port2

    def remove_control_nic(self):
        self.options['_noControlNic'] = Option("true")

    def add_route_entry(self, target_net, gateway_ip):
        ROUTE_TABLE = 'route_list'
        route_table = self.options.get(ROUTE_TABLE, None)
        if route_table is None:
            self.options[ROUTE_TABLE] = route_table = []

        route_table.append({
            "targetNete": Option(target_net.network_address),
            "networkLength": Option(target_net.prefixlen),
            "nicIp": Option(gateway_ip),
        })


@auto_str(filter_attrs='node')
class Port:
    def __init__(self, node, index, **kwargs):
        self.node = node
        self.index = index
        self.options = kwargs if kwargs else dict()
        self.link = None

    def config_ip(self, ip, netmask, default_gateway='', dns=''):
        self.options['ip'] = Option(ip, 'ip')
        self.options['netmask'] = Option(netmask, 'ip')
        self.options['defaultGateway'] = Option(default_gateway, 'ip')
        self.options['dns'] = Option(dns, 'ip')


@auto_str()
class Option:
    def __init__(self, value, subtype=None, unit=''):
        self.value = value
        if not subtype:
            self.subtype = self.guess_type(value)
        else:
            self.subtype = subtype
        self.unit = unit

    def guess_type(self, value):
        if isinstance(value, numbers.Number):
            return "number"
        elif isinstance(value, (ipaddress.IPv6Address, ipaddress.IPv4Address)):
            return "ip"
        else:
            s = str(value)
            if IP_PATTERN.match(s):
                return "ip"
            else:
                return "string"


@auto_str(filter_attrs={'port1', 'port2'})
class Link:
    def __init__(self, port1, port2, **kwargs):
        self.id = uuid.uuid4().hex
        self.port1 = port1
        self.port1.link = self
        self.port2 = port2
        self.port2.link = self
        self.options = kwargs

    def adjacent_port(self, port):
        if port == self.port1:
            return self.port2
        elif port == self.port2:
            return self.port1
        else:
            raise Exception("port {} not in link {}".format(port, self))


class TopologyExporter(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def export(self, topology: Topology):
        pass


class CadtsTopologyExporter(TopologyExporter):
    def __init__(self):
        pass

    def export(self, topology: Topology):
        root = ET.Element("topo")
        root.attrib['_v'] = '2.0'

        for node in topology.nodes.values():
            n = ET.SubElement(root, "node")
            n.attrib['id'] = node.id
            n.attrib['name'] = node.name
            n.attrib['templateId'] = node.template_id
            n.attrib['category'] = str(node.category)
            n.attrib['emulation'] = node.emulation
            n.attrib['os'] = node.os
            n.attrib['image'] = node.image
            fill_options(n, node.options)

            for port in node.ports:
                p = ET.SubElement(n, 'interface')
                p.attrib['name'] = ''
                p.attrib['index'] = str(port.index)
                other = port.link.adjacent_port(port)
                p.attrib['toNode'] = other.node.name
                p.attrib['toPort'] = str(other.index)
                fill_options(p, port.options)

        return pretty_xml(root)


def fill_options(entity, options):
    if isinstance(options, dict):
        for k, v in options.items():
            if isinstance(v, (list, tuple)):
                for i, item in enumerate(v):
                    config = ET.SubElement(entity, "config")
                    config.attrib['name'] = k
                    config.attrib['index'] = str(i)
                    fill_options(config, item)
            else:
                config = ET.SubElement(entity, "config")
                config.attrib['name'] = k
                fill_options(config, v)
    elif isinstance(options, (tuple, list)):
        raise Exception("raw list is not support")
    elif isinstance(options, Option):
        entity.attrib['value'] = str(options.value)
        entity.attrib['type'] = options.subtype
        entity.attrib['unit'] = options.unit
    else:
        raise Exception("unknown type {}".format(type(options)))


def pretty_xml(root):
    f = io.BytesIO()
    ET.ElementTree(root).write(f, encoding='UTF-8', xml_declaration=True)
    f.seek(0)
    return minidom.parse(f).toprettyxml(encoding='UTF-8').decode('UTF-8')
