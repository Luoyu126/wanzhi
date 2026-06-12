#!/usr/bin/env python3
from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


NAMESPACE = "http://openbox.org/3.4/rc"
ET.register_namespace("", NAMESPACE)


def _tag(name: str) -> str:
    return f"{{{NAMESPACE}}}{name}"


def configure(rc_path: Path, title: str) -> bool:
    if rc_path.exists():
        tree = ET.parse(rc_path)
        root = tree.getroot()
    else:
        root = ET.Element(_tag("openbox_config"))
        tree = ET.ElementTree(root)

    window_rules = root.find(_tag("windowRules"))
    if window_rules is None:
        window_rules = ET.SubElement(root, _tag("windowRules"))

    for rule in window_rules.findall(_tag("windowRule")):
        if rule.get("title") != title:
            continue
        if any(action.get("name") == "ToggleFullscreen" for action in rule.findall(_tag("action"))):
            return False
        ET.SubElement(rule, _tag("action"), {"name": "ToggleFullscreen"})
        tree.write(rc_path, encoding="unicode", xml_declaration=True)
        return True

    rule = ET.SubElement(window_rules, _tag("windowRule"), {"title": title})
    ET.SubElement(rule, _tag("action"), {"name": "ToggleFullscreen"})
    rc_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(rc_path, encoding="unicode", xml_declaration=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure labwc to open Wanzhi fullscreen.")
    parser.add_argument("--rc", type=Path, default=Path.home() / ".config/labwc/rc.xml")
    parser.add_argument("--title", default="Wanzhi")
    args = parser.parse_args()

    changed = configure(args.rc, args.title)
    status = "updated" if changed else "already configured"
    print(f"{args.rc}: {status}")


if __name__ == "__main__":
    main()
