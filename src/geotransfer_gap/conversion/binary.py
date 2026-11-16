from geotransfer_gap.config import settings
import ast
import struct
from pathlib import Path

BENCH = settings().bench


def load_source_writer():
    """Load BehaviorBench's writer without importing its Python 3.11 C extension."""
    source = BENCH / "pufferlib/ocean/drive/drive.py"
    tree = ast.parse(source.read_text())
    names = {"calculate_area", "dist", "simplify_polyline", "save_map_binary"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == names
    ns = {"struct": struct}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns["save_map_binary"]


def read_binary(path):
    import importlib.util

    source = BENCH / "pufferlib/prediction/binary_reader.py"
    spec = importlib.util.spec_from_file_location("behaviorbench_binary_reader", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_binary_scenario(str(path))
