#!/usr/bin/env python3
"""
Generate a dependency graph visualization for the incident-copilot codebase.

Usage:
    python scripts/dependency_graph.py
    python scripts/dependency_graph.py --output deps.png
    python scripts/dependency_graph.py --format dot > deps.dot
"""

import ast
import argparse
from pathlib import Path
from collections import defaultdict
import json


def extract_imports(file_path: Path) -> list[str]:
    """Extract import statements from a Python file."""
    imports = []

    try:
        with open(file_path) as f:
            tree = ast.parse(f.read())
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports


def get_module_name(file_path: Path, src_root: Path) -> str:
    """Convert file path to module name."""
    relative = file_path.relative_to(src_root)
    parts = list(relative.parts)

    # Remove .py extension
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]

    # Remove __init__
    if parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts)


def build_dependency_graph(src_root: Path) -> dict[str, set[str]]:
    """Build a dependency graph from source files."""
    graph = defaultdict(set)

    # Find all Python files
    for py_file in src_root.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        module_name = get_module_name(py_file, src_root)
        if not module_name:
            continue

        imports = extract_imports(py_file)

        for imp in imports:
            # Only track internal imports (src.*)
            if imp.startswith("src.") or imp.startswith("."):
                # Normalize import
                if imp.startswith("src."):
                    imp = imp[4:]  # Remove 'src.' prefix

                # Get top-level module
                top_module = imp.split(".")[0]
                source_module = module_name.split(".")[0]

                if top_module != source_module and top_module:
                    graph[source_module].add(top_module)

    return dict(graph)


def generate_mermaid(graph: dict[str, set[str]]) -> str:
    """Generate Mermaid diagram syntax."""
    lines = ["graph TD"]

    # Add nodes with styling
    modules = set(graph.keys())
    for deps in graph.values():
        modules.update(deps)

    # Style critical modules
    critical = {"orchestrator", "ai", "integrations", "models"}
    for module in sorted(modules):
        if module in critical:
            lines.append(f"    {module}[{module}]:::critical")
        else:
            lines.append(f"    {module}[{module}]")

    lines.append("")

    # Add edges
    for source, targets in sorted(graph.items()):
        for target in sorted(targets):
            lines.append(f"    {source} --> {target}")

    lines.append("")
    lines.append("    classDef critical fill:#f96,stroke:#333,stroke-width:2px")

    return "\n".join(lines)


def generate_dot(graph: dict[str, set[str]]) -> str:
    """Generate DOT format for Graphviz."""
    lines = [
        "digraph dependencies {",
        "    rankdir=TB;",
        "    node [shape=box, style=filled, fillcolor=lightblue];",
        "",
    ]

    # Style critical modules
    critical = {"orchestrator", "ai", "integrations", "models"}
    for module in critical:
        lines.append(f"    {module} [fillcolor=orange];")

    lines.append("")

    # Add edges
    for source, targets in sorted(graph.items()):
        for target in sorted(targets):
            lines.append(f"    {source} -> {target};")

    lines.append("}")

    return "\n".join(lines)


def generate_json(graph: dict[str, set[str]]) -> str:
    """Generate JSON format."""
    # Convert sets to lists for JSON
    json_graph = {k: sorted(v) for k, v in graph.items()}
    return json.dumps(json_graph, indent=2)


def analyze_graph(graph: dict[str, set[str]]) -> dict:
    """Analyze the dependency graph for issues."""
    issues = []
    stats = {
        "total_modules": 0,
        "total_dependencies": 0,
        "most_dependencies": [],
        "most_depended_on": [],
    }

    # Count dependencies
    all_modules = set(graph.keys())
    for deps in graph.values():
        all_modules.update(deps)

    stats["total_modules"] = len(all_modules)
    stats["total_dependencies"] = sum(len(deps) for deps in graph.values())

    # Find modules with most dependencies
    dep_counts = [(module, len(deps)) for module, deps in graph.items()]
    dep_counts.sort(key=lambda x: x[1], reverse=True)
    stats["most_dependencies"] = dep_counts[:5]

    # Find most depended-on modules
    depended_on = defaultdict(int)
    for deps in graph.values():
        for dep in deps:
            depended_on[dep] += 1

    dep_on_counts = sorted(depended_on.items(), key=lambda x: x[1], reverse=True)
    stats["most_depended_on"] = dep_on_counts[:5]

    # Check for forbidden dependencies
    forbidden = {
        ("integrations", "orchestrator"),
        ("ai", "integrations"),
        ("models", "orchestrator"),
    }

    for source, targets in graph.items():
        for target in targets:
            if (source, target) in forbidden:
                issues.append(f"FORBIDDEN: {source} -> {target}")

    return {"stats": stats, "issues": issues}


def main():
    parser = argparse.ArgumentParser(description="Generate dependency graph")
    parser.add_argument("--src", default="src", help="Source directory")
    parser.add_argument(
        "--format",
        choices=["mermaid", "dot", "json", "analyze"],
        default="mermaid",
        help="Output format",
    )
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    args = parser.parse_args()

    src_root = Path(args.src)
    if not src_root.exists():
        print(f"Error: {src_root} does not exist")
        return 1

    graph = build_dependency_graph(src_root)

    if args.format == "mermaid":
        output = generate_mermaid(graph)
    elif args.format == "dot":
        output = generate_dot(graph)
    elif args.format == "json":
        output = generate_json(graph)
    elif args.format == "analyze":
        analysis = analyze_graph(graph)
        output = json.dumps(analysis, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Written to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    exit(main())
