import os
import io
from pprint import pprint
from scbr.lang.parser import parse_scene
from scbr.topo import CadtsTopologyExporter


def scene_file(name):
    return os.path.join(os.path.dirname(__file__), '..', 'data', 'scene-lang', name + '.scene')


def template_file(name):
    return os.path.join(os.path.dirname(__file__), '..', 'data', 'scene-lang', name + '.st')


def env_file(name):
    return os.path.join(os.path.dirname(__file__), '..', 'data', 'scene-lang', name + '.env')


scene = parse_scene(env_file("demo00"), template_file('demo00'), scene_file('demo00'))
topology = scene.extract_topology()
# pprint(topology.nodes)
# pprint(topology.query_node('router').ports)
exporter = CadtsTopologyExporter()
f = io.BytesIO()
print(exporter.export(topology))

