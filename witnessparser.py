"""
Copyright 2026 Budapest University of Technology and Economics

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Format-independent parsing of violation witnesses.

Two witness formats are supported:

* GraphML (witness format 1.0): the witness is an automaton; the single
  non-branching path from the entry node is read off edge by edge.
* YAML (witness format 2.0--2.2): the witness is a ``violation_sequence``
  of segments; the ``follow`` waypoints are read off in segment order.
  This includes the concurrency extension of format 2.2, where waypoints
  may carry a ``thread_id`` and a ``no-data-race`` witness ends in a
  multi-follow segment holding the two racing ``target`` waypoints.

Both parsers produce the same intermediate representation -- a
``ParsedWitness`` whose ``steps`` are ``(coords, metadata)`` pairs in
execution (happens-before) order -- so that the AST instrumentation in
``witness2ast`` does not need to know which format the witness came in.

``coords`` describes the source location in the C file (``startline``,
``endline``, ``column``, ``length``, ``content``) or is ``None`` when the
witness gives no usable location. ``metadata`` may contain:

* ``assumption``: a C expression that holds at this step (for assumption
  and function_return waypoints), or the recorded branch direction/case
  (for branching waypoints: ``"true"``/``"false"``, or an integer/``"default"``
  for switch),
* ``threadId``: the thread executing this step (``0`` = main thread),
* ``type``: the waypoint type (YAML witnesses only, e.g. ``target``).
"""

import yaml
import networkx as nx

from Exceptions import KnownErrorVerdict

FORMAT_GRAPHML = "graphml"
FORMAT_YAML = "yaml"


class ParsedWitness:
    """A violation witness reduced to a linear sequence of steps."""

    def __init__(self, steps, specification, witness_format):
        self.steps = steps
        self.specification = specification or ""
        self.format = witness_format

    @property
    def data_race(self):
        """Whether the witness claims a data race (no-data-race property)."""
        return "data-race" in self.specification

    @property
    def no_overflow(self):
        """Whether the witness claims an integer overflow (no-overflow property)."""
        return "overflow" in self.specification

    @property
    def memory_safety(self):
        """Whether the witness claims a memory-safety violation.

        Covers the SV-COMP valid-free, valid-deref, and valid-memtrack
        properties, whose specifications read ``G valid-free`` etc.
        """
        return "valid-" in self.specification


def get_offset_of_line(c_file, line):
    with open(c_file, "r") as f:
        for i in range(1, line):
            f.readline()
        return f.tell()


def get_line_of_offset(c_file, offset):
    with open(c_file, "r") as f:
        i = 0
        line = ""
        while f.tell() <= offset:
            line = f.readline()
            i = i + 1
        return i, len(line) - (f.tell() - offset)


def get_coords(c_file, startline=None, endline=None, startoffset=None, endoffset=None):
    if not endline and startline:
        endline = startline

    if not startoffset and startline:
        startoffset = get_offset_of_line(c_file, int(startline))

    if not endoffset and endline:
        endoffset = get_offset_of_line(c_file, int(endline) + 1)

    if endoffset:
        with open(c_file, "r") as f:
            f.seek(int(startoffset))
            content = f.read(int(endoffset) - int(startoffset) - 1)
            startline, column = get_line_of_offset(c_file, int(startoffset))
            return {
                "startline": int(startline),
                "column": int(column),
                "endline": int(endline),
                "length": int(endoffset) - int(startoffset) + 1,
                "content": content,
            }
    return None


def detect_format(witnessfile):
    """Decide whether a witness file is GraphML or YAML.

    The file extension is authoritative; for unknown extensions the content
    is sniffed (GraphML witnesses are XML documents starting with '<').
    """
    lower = witnessfile.lower()
    if lower.endswith(".graphml") or lower.endswith(".xml"):
        return FORMAT_GRAPHML
    if lower.endswith(".yml") or lower.endswith(".yaml"):
        return FORMAT_YAML
    with open(witnessfile, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                return FORMAT_GRAPHML if stripped.startswith("<") else FORMAT_YAML
    raise KnownErrorVerdict("Empty witness")


def parse_witness(witnessfile, c_file):
    """Parse a witness of either format into a ParsedWitness."""
    if detect_format(witnessfile) == FORMAT_GRAPHML:
        return parse_graphml_witness(witnessfile, c_file)
    return parse_yaml_witness(witnessfile, c_file)


def parse_graphml_witness(witnessfile, c_file):
    witness = nx.read_graphml(witnessfile)
    if witness.graph["witness-type"] != "violation_witness":
        raise KnownErrorVerdict("Correctness witness")
    steps = []

    keys = {k for node in witness.nodes for k in witness.nodes[node].keys()}
    entry_key = "entry" if "entry" in keys else "isEntryNode"
    sink_key = "sink" if "sink" in keys else "isSinkNode"

    entry_nodes = list(nx.get_node_attributes(witness, entry_key).keys())
    if len(entry_nodes) == 0:
        entry_nodes = list(
            set([u for u, deg in witness.in_degree() if not deg])
            - set([u for u, deg in witness.out_degree() if not deg])
        )
        if len(entry_nodes) == 0:
            raise KnownErrorVerdict("No entry node")

    if len(entry_nodes) > 1:
        raise KnownErrorVerdict("Multiple entry nodes")

    node = entry_nodes[0]

    sink_nodes = set(nx.get_node_attributes(witness, sink_key).keys())

    while len(witness.out_edges(node)) > 0:
        out_edges = list(
            filter(lambda x: x[1] not in sink_nodes, witness.out_edges(node))
        )
        if len(out_edges) > 1:
            raise KnownErrorVerdict("Has branching")
        edge = list(out_edges)[0]
        attrs = witness.get_edge_data(edge[0], edge[1])

        startline = attrs["startline"] if "startline" in attrs else None
        endline = attrs["endline"] if "endline" in attrs else None
        startoffset = attrs["startoffset"] if "startoffset" in attrs else None
        endoffset = attrs["endoffset"] if "endoffset" in attrs else None

        coords = get_coords(c_file, startline, endline, startoffset, endoffset)
        metadata = {
            key: attrs[key]
            for key in ["assumption", "control", "threadId", "createThread"]
            if key in attrs
        }
        steps.append((coords, metadata))
        node = edge[1]

    specification = witness.graph.get("specification", "")
    return ParsedWitness(steps, specification, FORMAT_GRAPHML)


def _extract_constraint(waypoint):
    """Extract the assumption/constraint value from a YAML waypoint, or None.

    ``assumption`` constraints use ``c_expression``; ``function_return``
    constraints use ``ext_c_expression`` (the function-context grammar that
    ``\\result`` belongs to); ``branching`` waypoints omit ``format``
    entirely and carry a YAML bool (or, for ``switch``, an integer/
    ``default``) rather than a C expression string. Normalize all of these
    to plain strings so callers don't need to care which waypoint type they
    came from.
    """
    constraint = waypoint.get("constraint", {})
    if constraint.get("format", "c_expression") not in (
        "c_expression",
        "ext_c_expression",
    ):
        return None
    value = constraint.get("value")
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def parse_yaml_witness(witnessfile, c_file):
    with open(witnessfile, "r") as f:
        entries = yaml.safe_load(f)

    if not isinstance(entries, list):
        raise KnownErrorVerdict("Malformed witness")

    sequence = None
    for entry in entries:
        entry_type = entry.get("entry_type") if isinstance(entry, dict) else None
        if entry_type == "violation_sequence":
            sequence = entry
            break
        if entry_type == "invariant_set":
            raise KnownErrorVerdict("Correctness witness")
    if sequence is None:
        raise KnownErrorVerdict("No violation sequence")

    specification = (
        sequence.get("metadata", {}).get("task", {}).get("specification", "")
    )

    steps = []
    for segment_entry in sequence.get("content", []):
        for waypoint_entry in segment_entry.get("segment", []):
            waypoint = waypoint_entry.get("waypoint", {})
            if waypoint.get("action") != "follow":
                # 'avoid' waypoints restrict the matching of the witness
                # automaton; a concrete test execution cannot make use of
                # them, so they are skipped.
                continue

            waypoint_type = waypoint.get("type")
            location = waypoint.get("location", {})
            line = location.get("line")
            coords = get_coords(c_file, startline=line) if line else None

            metadata = {
                "type": waypoint_type,
                # thread_id is the format-2.2 concurrency extension; its
                # absence means the main thread (thread 0).
                "threadId": int(waypoint.get("thread_id", 0)),
            }

            # assumption/function_return constraints can pin a nondet call
            # to a specific value; branching constraints record which way
            # a branch was taken. All three are stored under the same
            # "assumption" key since witness2ast dispatches on "type".
            if waypoint_type in ("assumption", "function_return", "branching"):
                value = _extract_constraint(waypoint)
                if value is not None:
                    metadata["assumption"] = value

            steps.append((coords, metadata))

    return ParsedWitness(steps, specification, FORMAT_YAML)
