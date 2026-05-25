#!/usr/bin/env python3
"""
Terraform → Cisco Network as Code XML Mapper
Core conversion engine: parses .tf files and generates XML using mapping templates.
"""

import json
import os
import re
import sys
from pathlib import Path
from xml.dom import minidom
from typing import Any, Optional


# ── Mapping loader ────────────────────────────────────────────────────

def load_mappings(mapping_dir: str = None) -> dict:
    """Load all mapping JSON files from the mappings directory."""
    if mapping_dir is None:
        mapping_dir = Path(__file__).parent / "mappings"
    else:
        mapping_dir = Path(mapping_dir)

    all_mappings = {}
    for f in sorted(mapping_dir.glob("*.json")):
        with open(f) as fh:
            data = json.load(fh)
            provider = data.get("provider", f.stem)
            all_mappings[provider] = data
    return all_mappings


def get_resource_mapping(mappings: dict, resource_type: str) -> Optional[dict]:
    """Find the mapping definition for a given Terraform resource type."""
    for provider_data in mappings.values():
        resources = provider_data.get("resources", {})
        if resource_type in resources:
            return resources[resource_type]
    return None


# ── HCL / Terraform parser ────────────────────────────────────────────

def parse_tf(text: str) -> list[dict]:
    """
    Parse Terraform HCL text and extract resource blocks.
    Returns a list of {type, name, attributes} dicts.
    Supports: simple values, booleans, numbers, lists, lists of objects.
    """
    resources = []
    # Pattern: resource "type" "name" { ... }
    resource_pattern = re.compile(
        r'resource\s+"(\w+(?::\w+)?)"\s+"(\w+)"\s*\{',
        re.DOTALL
    )

    pos = 0
    while True:
        m = resource_pattern.search(text, pos)
        if not m:
            break

        resource_type = m.group(1)
        resource_name = m.group(2)
        block_start = m.end()

        # Find matching closing brace, accounting for nesting
        brace_depth = 1
        block_end = block_start
        in_string = False
        string_char = None

        while brace_depth > 0 and block_end < len(text):
            ch = text[block_end]

            if in_string:
                if ch == '\\':
                    block_end += 2
                    continue
                elif ch == string_char:
                    in_string = False
            else:
                if ch in ('"', "'"):
                    in_string = True
                    string_char = ch
                elif ch == '{':
                    brace_depth += 1
                elif ch == '}':
                    brace_depth -= 1

            block_end += 1

        if brace_depth != 0:
            break  # malformed block

        body = text[block_start:block_end - 1]
        attrs = _parse_block_body(body)

        resources.append({
            "type": resource_type,
            "name": resource_name,
            "attributes": attrs
        })

        pos = block_end

    return resources


def _parse_block_body(body: str) -> dict:
    """Parse the body of a Terraform block into a nested dict."""
    result = {}
    lines = body.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty/comment lines
        if not stripped or stripped.startswith('#') or stripped.startswith('//'):
            i += 1
            continue

        # Multi-line list: attr = [ ... ]
        if '=' in stripped and '[' in stripped and ']' not in stripped.split('=')[1]:
            key = stripped.split('=')[0].strip()
            list_items = []
            i += 1
            # Collect list until matching ]
            brace_depth = 1  # the opening [
            list_body = ""
            while i < len(lines) and brace_depth > 0:
                l = lines[i]
                for ch in l:
                    if ch == '[':
                        brace_depth += 1
                    elif ch == ']':
                        brace_depth -= 1
                        if brace_depth == 0:
                            break
                if brace_depth > 0:
                    list_body += l + "\n"
                i += 1

            # Now parse the list body
            result[key] = _parse_list_body(list_body)

        # Simple key = value
        elif '=' in stripped:
            key = stripped.split('=')[0].strip()
            value_part = '='.join(stripped.split('=')[1:]).strip()

            # Remove trailing comma
            if value_part.endswith(','):
                value_part = value_part[:-1].strip()

            result[key] = _parse_value(value_part)
            i += 1
        else:
            i += 1

    return result


def _parse_value(value: str) -> Any:
    """Parse a single Terraform value (string, bool, number, list, object)."""
    value = value.strip()

    if not value:
        return None

    # Boolean
    if value == 'true':
        return True
    if value == 'false':
        return False

    # Null
    if value == 'null':
        return None

    # Quoted string
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]

    # Number
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    # Inline list [a, b, c]
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items = []
        # Simple comma split for flat lists
        for item in re.findall(r'"[^"]*"|\'[^\']*\'|\S+', inner):
            items.append(_parse_value(item))
        return items

    # Reference (var.xxx, data.xxx, resource.xxx)
    if re.match(r'^[\w.()\[\]"\'-]+$', value) and not value.startswith('"'):
        return value

    return value


def _parse_list_body(body: str) -> list:
    """Parse the content inside a list [ ... ] into items."""
    items = []
    # Check if items are objects: { key = value }
    obj_pattern = re.compile(r'\{([^}]+)\}', re.DOTALL)

    for m in obj_pattern.finditer(body):
        obj_body = m.group(1)
        obj = _parse_block_body(obj_body)
        items.append(obj)

    if not items:
        # Flat list: "item1", "item2"
        flat_items = re.findall(r'"([^"]*)"', body)
        items = flat_items

    return items


# ── XML Generator (minidom-based) ─────────────────────────────────────

def tf_to_xml(resource_type: str, attributes: dict, mappings: dict) -> Optional[str]:
    """
    Convert Terraform resource attributes to XML using mapping template.
    Returns formatted XML string or None if no mapping found.
    """
    mapping = get_resource_mapping(mappings, resource_type)
    if not mapping:
        return None

    doc = minidom.Document()
    root_tag = mapping["xml_root"]
    root = doc.createElement(root_tag)
    doc.appendChild(root)

    # Comment with metadata
    comment = doc.createComment(f" Generated from Terraform: {resource_type} ")
    root.appendChild(comment)

    _build_xml_children(doc, root, mapping.get("attributes", []), attributes)

    return doc.toprettyxml(indent="  ")


def _build_xml_children(doc: minidom.Document, parent: minidom.Element,
                        attr_defs: list, attrs: dict):
    """Recursively build XML children from attribute definitions and values."""
    for attr_def in attr_defs:
        tf_name = attr_def["tf_name"]
        xml_tag = attr_def["xml_tag"]
        value = attrs.get(tf_name)

        attr_type = attr_def.get("type", "string")

        if value is None:
            continue  # skip empty attributes

        if attr_type == "list_object":
            # List of objects - each item's fields as children of the parent
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        for obj_attr in attr_def.get("object_attributes", []):
                            obj_val = item.get(obj_attr["tf_name"])
                            if obj_val is not None:
                                el = doc.createElement(obj_attr["xml_tag"])
                                el.appendChild(doc.createTextNode(
                                    _format_xml_value(obj_val, obj_attr.get("type", "string"))
                                ))
                                parent.appendChild(el)

        elif attr_type == "list":
            # Simple list - each item as a sub-element
            if isinstance(value, list):
                item_tag = attr_def.get("list_item_tag", "item")
                for item in value:
                    if item:
                        el = doc.createElement(item_tag)
                        el.appendChild(doc.createTextNode(_format_xml_value(item, "string")))
                        parent.appendChild(el)
            else:
                el = doc.createElement(xml_tag)
                el.appendChild(doc.createTextNode(_format_xml_value(value, attr_type)))
                parent.appendChild(el)

        else:
            el = doc.createElement(xml_tag)
            el.appendChild(doc.createTextNode(_format_xml_value(value, attr_type)))
            parent.appendChild(el)


def _format_xml_value(value: Any, value_type: str = "string") -> str:
    """Format a value for XML text content."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


# ── Main CLI ──────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Terraform → Cisco Network as Code XML Mapper")
    parser.add_argument("files", nargs="+", help="Terraform .tf files to convert")
    parser.add_argument("-m", "--mappings", help="Mapping directory (default: ./mappings)")
    parser.add_argument("-o", "--output-dir", help="Output directory for XML files")
    parser.add_argument("--pretty", action="store_true", default=True, help="Pretty-print XML")

    args = parser.parse_args()

    # Load mappings
    mappings = load_mappings(args.mappings)

    for filepath in args.files:
        path = Path(filepath)
        if not path.exists():
            print(f"❌ File not found: {filepath}", file=sys.stderr)
            continue

        text = path.read_text()
        resources = parse_tf(text)

        for res in resources:
            xml = tf_to_xml(res["type"], res["attributes"], mappings)
            if xml is None:
                print(f"⚠️  No mapping found for {res['type']} (file: {filepath})")
                continue

            if args.output_dir:
                out_dir = Path(args.output_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
                # Name: resource_name.xml or type_name.xml
                out_file = out_dir / f"{res['name']}_{res['type'].split('_')[-1]}.xml"
                out_file.write_text(xml)
                print(f"✅ {res['type']} ({res['name']}) → {out_file}")
            else:
                print(f"─── {res['type']} ({res['name']}) ───")
                print(xml)


if __name__ == "__main__":
    main()
