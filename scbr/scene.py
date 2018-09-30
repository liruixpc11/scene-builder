from enum import Enum
import ipaddress
import logging

from scbr.topo import Topology, Node, NodeCategory
from scbr.utils import auto_str

LOG = logging.getLogger(__name__)


class NodeRole(Enum):
    SWITCH = 1
    HOST = 2
    SERVER = 3
    ATTACKER = 4
    TERMINAL = 5
    ROUTER = 6


@auto_str()
class Scene:
    def __init__(self):
        self.routers = dict()
        self.hosts = dict()
        self.lans = dict()
        self.templates = dict()
        self.env = Environment()

    def add_entity(self, entity):
        if isinstance(entity, Host):
            self.hosts[entity.id] = entity
        elif isinstance(entity, Router):
            self.routers[entity.id] = entity
        elif isinstance(entity, Lan):
            self.lans[entity.id] = entity
        elif isinstance(entity, NodeTemplate):
            self.templates[entity.id] = entity
        else:
            raise Exception("unknown child type {}".format(type(entity)))

    def adjust(self):
        for node in self.node_list:
            if node.template_id:
                template = self.find_template(node.template_id)
                if not template:
                    template = NodeTemplate.default_template(node.template_id, node.role)
                    self.templates[template.id] = template
                node.template = template

            # add host or router to lan
            for port in node.ports:
                if port.in_lan:
                    port.lan = self.lans[port.in_lan.lan_id]
                    if node not in port.lan.hosts:
                        port.lan.hosts.append(node)
                elif port.to_port:
                    to_port = port.to_port
                    to_port.peer_node = self.query_node(to_port.peer_node_id)
                    if to_port.peer_port_name:
                        to_port.peer_port = to_port.peer_node.query_port(to_port.peer_port_name)

    @property
    def node_list(self):
        nodes = list(self.routers.values())
        nodes.extend(self.hosts.values())
        return nodes

    def query_node(self, node_id):
        if node_id in self.hosts:
            return self.hosts[node_id]
        elif node_id in self.routers:
            return self.routers[node_id]
        else:
            raise Exception('host/router {} not found'.format(node_id))

    def extract_topology(self):
        topology = Topology()
        for lan in self.lans.values():
            node = lan.to_node(self)
            topology.add_node(node)

        for host in self.hosts.values():
            node = host.to_node(self)
            topology.add_node(node)

        for router in self.routers.values():
            node = router.to_node(self)
            topology.add_node(node)

        for node in self.node_list:
            host = topology.query_node(node.id)
            self.handle_ports(topology, node, host)

        return topology

    def handle_ports(self, topology, entity, host):
        for port in entity.ports:
            self.handle_port(topology, host, port)

    def handle_port(self, topology, host, node_port):
        if node_port.in_lan:
            switch = topology.query_node(node_port.in_lan.lan_id)
            lan = self.lans[node_port.in_lan.lan_id]
            ip = node_port.in_lan.ip
            port, _ = host.link_to_node(switch)
            if ip:
                port.config_ip(ip, lan.net.netmask)
        elif node_port.to_port:
            to_port = node_port.to_port
            other_host = topology.query_node(node_port.to_port.peer_node_id)

            if to_port.peer_port:
                if to_port.peer_port.connected:
                    return
                p2 = other_host.add_port()
                to_port.peer_port.connected = True
            else:
                p2 = other_host.add_port()

            p1 = host.add_port()
            p1.link_to_port(p2)
            if to_port.self_ip:
                p1.config_ip(to_port.self_ip.ip, to_port.self_ip.netmask)
            if to_port.peer_ip:
                p2.config_ip(to_port.peer_ip.ip, to_port.peer_ip.netmask)

            node_port.connected = True
        else:
            LOG.info("port of %s without connection", host.name)

    def find_template(self, template_id):
        if template_id in self.templates:
            return self.templates[template_id]
        else:
            return None


@auto_str()
class Environment:
    def __init__(self):
        self.external_net_list = []
        self.control_net_gateway = None


@auto_str()
class NodeTemplate:
    def __init__(self, template_id):
        self.id = template_id
        self.category = NodeCategory.Host
        self.emulation = "vsphere"
        self.os = 'windows'
        self.image = "/images/计算机.png"

    def validate(self):
        pass

    @staticmethod
    def default_template(template_id, role):
        template = NodeTemplate(template_id)

        if role == NodeRole.ATTACKER:
            template.image = '/images/虚拟PC.png'
        elif role == NodeRole.SERVER:
            template.image = '/images/服务器.png'
            template.os = 'linux'
        elif role == NodeRole.TERMINAL:
            template.image = '/images/计算机.png'
        elif role == NodeRole.ROUTER:
            template.image = '/images/路由器.png'
            template.os = 'linux'
        elif role == NodeRole.SWITCH:
            template.os = ''
            template.image = '/images/交换机.png'
            template.emulation = ''
        return template


class RouteEntry:
    def __init__(self, target_net, gateway):
        self.target_net = target_net
        self.gateway = gateway


@auto_str()
class RouteTable:
    def __init__(self, entries=None):
        self.entries = entries if entries else []

    def add_entry(self, target_net, gateway):
        self.entries.append(RouteEntry(target_net, gateway))

    def merge(self, other):
        self.entries.extend(other.entries)


class HostBase:
    def __init__(self, id_, role):
        self.id = id_
        self.role = role
        self.name = id_
        self.template = None
        self.template_id = None
        self.ports = []
        self.options = dict()
        self.flags = []

    def to_node(self, scene):
        node = Node(self.id, self.name, NodeCategory.Host, self.template_id, self.options)
        if self.template_id:
            node.emulation = self.template.emulation
            node.os = self.template.os
            node.image = self.template.image

        if self.role == NodeRole.ATTACKER:
            if scene.env.control_net_gateway:
                for external_net in scene.env.external_net_list:
                    node.add_route_entry(external_net, scene.env.control_net_gateway)
        else:
            node.remove_control_nic()

        node.use_default_physic()
        return node

    def query_port(self, port_name):
        for port in self.ports:
            if port.name == port_name:
                return port

        raise Exception('port {} on node {} not found'.format(port_name, self.name))


@auto_str()
class Host(HostBase):
    def __init__(self, id_, role):
        super().__init__(id_, role)
        self.in_lan = None
        self.is_global_dns_server = False


@auto_str()
class Router(HostBase):
    def __init__(self, id_):
        super().__init__(id_, NodeRole.ROUTER)
        self.route_table = RouteTable()

    def to_node(self, scene):
        node = super().to_node(scene)
        self.fill_route_table(node)
        return node

    def fill_route_table(self, node):
        for entry in self.route_table.entries:
            node.add_route_entry(entry.target_net, entry.gateway)


@auto_str()
class Lan:
    def __init__(self, id_):
        self.id = id_
        self.name = id_
        self.net = None
        self.hosts = []
        self.role = NodeRole.SWITCH

    def add_host(self, host):
        host.in_lan = HostInLan(self.id, None)
        self.hosts.append(host)

    def to_node(self, scene):
        node = Node(self.id, self.name, NodeCategory.Switch, "/switch")
        node.os = ''
        node.image = '/images/交换机.png'
        node.emulation = ''
        return node


@auto_str()
class IpWithMask:
    def __init__(self, s):
        ip, _ = s.split('/')
        self.ip = ipaddress.ip_address(ip)
        self.net = ipaddress.ip_network(s, strict=False)

    @property
    def prefixlen(self):
        return self.net.prefixlen

    @property
    def netmask(self):
        return self.net.netmask


@auto_str()
class PortToPort:
    def __init__(self, node_id):
        self.peer_node_id = node_id
        self.peer_port_name = None

        self.self_ip = None
        self.peer_ip = None

        # fill with scene.adjust()
        self.peer_node = None
        self.peer_port = None


@auto_str()
class NodePort:
    def __init__(self, in_lan_or_to_port, name=None):
        self.name = name
        self.in_lan = in_lan_or_to_port if isinstance(in_lan_or_to_port, HostInLan) else None
        self.to_port = in_lan_or_to_port if isinstance(in_lan_or_to_port, PortToPort) else None
        self.connected = False


@auto_str()
class HostInLan:
    def __init__(self, lan_id, ip):
        self.lan_id = lan_id
        self.ip = ip


class FlagType(Enum):
    RANDOM = 1
    FIXED = 2


class Flag:
    def __init__(self, type_, name, score, content):
        self.type = type_
        self.name = name
        self.score = score
        self.content = content

