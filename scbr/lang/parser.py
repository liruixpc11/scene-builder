import abc
import os
from pprint import pprint
import ipaddress
from lark import Lark, Transformer, Tree
from lark.lexer import Token

from scbr.scene import Scene, Lan, Host, HostInLan, Router, NodePort, NodeRole, NodeTemplate, Environment, RouteEntry, \
    RouteTable, IpWithMask, PortToPort, Flag, FlagType
from scbr.topo import Option

with open(os.path.join(os.path.dirname(__file__), "scene.lark")) as f:
    _lark_content = f.read()

_parser = Lark(_lark_content, start='scene')


def parse_role(role_string):
    return NodeRole[role_string.upper()]


class Alias:
    def __init__(self, value):
        self.value = value


class TemplateOption:
    def __init__(self, template_id):
        self.template_id = template_id


class EntityOption(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def config(self, entity):
        pass


class ControlNetGateway(EntityOption):
    def __init__(self, ip):
        self.ip = ip

    def config(self, entity):
        entity.control_net_gateway = self.ip


class ExternalNet(EntityOption):
    def __init__(self, net_list):
        self.net_list = net_list

    def config(self, entity):
        entity.external_net_list = self.net_list


class GenericOption(EntityOption):
    def __init__(self, key, value):
        self.key = key
        self.value = value

    def config(self, entity):
        entity.options[self.key] = self.value


class DictOptionEntry:
    def __init__(self, key, value):
        self.key = key
        self.value = value


class EntityName:
    def __init__(self, name):
        self.name = name


class FlagOption(EntityOption):
    def config(self, entity):
        entity.flags.append(self.flag)

    def __init__(self, flag):
        self.flag = flag



class SceneTransformer(Transformer):
    def __init__(self, scene=None):
        self._scene = scene if scene else Scene()

    def scene(self, matches):
        for entity in matches:
            if isinstance(entity, Environment):
                self._scene.env = entity
            else:
                self._scene.add_entity(entity)

                if isinstance(entity, Lan):
                    for host in entity.hosts:
                        self._scene.add_entity(host)
        self._scene.adjust()
        return self._scene

    def lan(self, matches):
        lan = Lan(matches[1].value)
        for option in matches[2:]:
            if isinstance(option, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
                lan.net = option
            elif isinstance(option, Alias):
                lan.name = option.value
            elif isinstance(option, Host):
                lan.add_host(option)
            else:
                raise Exception("Unknown element: {} {}".format(type(option), option))
        return lan

    def host(self, matches):
        role = matches[0].value
        host = Host(matches[1].value, parse_role(role))
        for option in matches[2:]:
            if isinstance(option, Alias):
                host.name = option.value
            elif isinstance(option, HostInLan):
                host.in_lan = option
                host.ports.append(NodePort(option))
            elif isinstance(option, TemplateOption):
                host.template_id = option.template_id
            elif isinstance(option, NodePort):
                host.ports.append(option)
            elif isinstance(option, Tree):
                if option.data == 'global_dns_line':
                    host.is_global_dns_server = option.children[0].value == "true"
                elif option.data == 'use_template':
                    host.template_id = _extract_str(option.children[1])
            elif isinstance(option, EntityOption):
                option.config(host)
            else:
                raise Exception("Unknown element: {} {}".format(type(option), option))
        return host

    def router(self, matches):
        router = Router(matches[1].value)
        for option in matches[2:]:
            if isinstance(option, Alias):
                router.name = option.value
            elif isinstance(option, TemplateOption):
                router.template_id = option.template_id
            elif isinstance(option, NodePort):
                router.ports.append(option)
            elif isinstance(option, RouteTable):
                router.route_table.merge(option)
            elif isinstance(option, Tree):
                if option.data == 'use_template':
                    router.template_id = _extract_str(option.children[1])
            elif isinstance(option, EntityOption):
                option.config(router)
            else:
                raise Exception("Unknown element: {} {}".format(type(option), option))
        return router

    def ipv4_net_line(self, matches):
        return ipaddress.ip_network(matches[1].value, strict=True)

    def ipv4_addr_line(self, matches):
        return ipaddress.ip_address(matches[1].value)

    def host_in_lan(self, matches):
        if len(matches) == 3:
            return HostInLan(matches[1].value, matches[2].value)
        else:
            return HostInLan(matches[1].value, None)

    def alias(self, matches):
        return Alias(_extract_str(matches[1]))

    def template_line(self, matches):
        return TemplateOption(_extract_str(matches[1]))

    def port(self, matches):
        if isinstance(matches[1], Token):
            port = NodePort(matches[2] if len(matches) > 2 else None, name=matches[1].value)
        else:
            port = NodePort(matches[1])
        for option in matches[2:]:
            if isinstance(option, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
                port.in_lan.ip = str(option)
        return port

    def port_to_port(self, matches):
        if matches[0].type == 'IPV4_NET':
            base = 1
            self_ip = IpWithMask(matches[0])
        else:
            base = 0
            self_ip = None

        to_port = PortToPort(matches[base + 1].value)
        to_port.self_ip = self_ip

        m = matches[base + 2]
        if isinstance(m, EntityName):
            to_port.peer_port_name = m.name
        elif isinstance(m, IpWithMask):
            to_port.peer_ip = m

        return to_port

    def node_port_id(self, matches):
        return EntityName(matches[0])

    def node_port_ip(self, matches):
        return IpWithMask(matches[0])

    def template(self, matches):
        template = NodeTemplate(_extract_str(matches[1]))
        for option in matches[2:]:
            if isinstance(option, Tree):
                if option.data == 'template_os_attr':
                    template.os = option.children[0].value
                elif option.data == 'template_emulation_attr':
                    template.emulation = option.children[0].value
                elif option.data == 'template_image_attr':
                    template.image = _extract_str(option.children[0])
                else:
                    raise Exception("unknown template option: {}".format(option.data))
        template.validate()
        return template

    def route_table(self, matches):
        route_table = RouteTable(matches)
        return route_table

    def route_entry(self, matches):
        return RouteEntry(ipaddress.ip_network(matches[0].value, strict=True), ipaddress.ip_address(matches[1].value))

    def env(self, matches):
        env = Environment()
        for option in matches:
            if isinstance(option, EntityOption):
                option.config(env)
        return env

    def external_net(self, matches):
        return ExternalNet(map(lambda m: ipaddress.IPv4Network(m.value), matches))

    def control_net_gateway(self, matches):
        return ControlNetGateway(ipaddress.IPv4Address(matches[0].value))

    def generic_option(self, matches):
        return GenericOption(matches[1].value, matches[2])

    def leaf_value(self, matches):
        value = matches[0]
        type_ = value.type
        if type_ == 'SIGNED_NUMBER':
            return Option(int(value))
        elif type_ ==  'ESCAPED_STRING':
            return Option(_extract_str(value))
        elif type_ == 'IPV4_ADDR':
            return Option(ipaddress.ip_address(value))
        elif type_ == 'IPV4_NET':
            return Option(ipaddress.ip_network(value))
        else:
            raise Exception("Unknown type {}".format(type_))

    def list_value(self, matches):
        return list(matches)

    def dict_value(self, matches):
        d = dict()
        for m in matches:
            d[m.key] = m.value
        return d

    def dict_entry(self, matches):
        key = matches[0]
        value = matches[1]
        if key.type == 'ESCAPED_STRING':
            key = _extract_str(key)
        return DictOptionEntry(key, value)

    def flag(self, matches):
        if matches[0].value == 'fixed_flag':
            type_ = FlagType.FIXED
        else:
            type_ = FlagType.RANDOM

        return FlagOption(Flag(type_, matches[1].value, int(matches[2].value), matches[3].value))


def _extract_str(token):
    return token.value[1:-1]


def parse_scene(*scene_files):
    scene = Scene()
    for scene_file in scene_files:
        with open(scene_file, 'r', encoding="utf-8") as f:
            ast = _parser.parse(f.read())

        SceneTransformer(scene).transform(ast)
    scene.adjust()
    return scene
