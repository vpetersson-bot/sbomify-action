#!/usr/bin/env python3
"""Score one SBOM and emit a flat JSON record.

Reads a CycloneDX or SPDX JSON document and reports, per document:
  * what produced it and in what shape (spec version, generator tools)
  * per-component field coverage -- the fields a consumer actually needs
    (licence, purl, version, supplier, hashes, external refs)
  * NTIA minimum-element coverage, which is what a compliance user is
    ultimately buying
  * enrichment attribution, taken from the ``sbomify:enrichment:source``
    property the enricher stamps on every field it fills

Coverage is reported over *dependency* components: the root component
describes the project itself and is populated by augmentation rather than
enrichment, so folding it in would flatter every percentage by one row.
"""

import json
import sys
from collections import Counter


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def _licence_of(c):
    """Return a licence string for a CycloneDX component, or None.

    Handles all three shapes: an SPDX ``expression``, a licence ``id``, and
    a free-text ``name``. A ``name`` counts as present but is tracked
    separately -- "BSD-ish" is a licence field that no policy engine can act
    on, and conflating it with a real SPDX id would overstate quality.
    """
    lics = c.get("licenses") or []
    for entry in lics:
        if not isinstance(entry, dict):
            continue
        if expr := entry.get("expression"):
            return expr, "expression"
        lic = entry.get("license") or {}
        if lid := lic.get("id"):
            return lid, "id"
        if lname := lic.get("name"):
            return lname, "name"
    return None, None


def inspect_cyclonedx(doc):
    all_comps = doc.get("components") or []
    meta = doc.get("metadata") or {}
    root = meta.get("component") or {}

    # Syft's file cataloguer emits one component per file in a container
    # image -- 6,847 of eclipse-temurin's 7,003 entries are `type: file`
    # with nothing but a path. They are not packages, they cannot carry a
    # purl, and averaging them into field coverage buries the ~150 real
    # packages that do. Coverage below is computed over packages only;
    # the file count is reported separately.
    type_counts = Counter(c.get("type") for c in all_comps)
    comps = [c for c in all_comps if c.get("type") != "file"]

    tools = meta.get("tools") or {}
    tool_names = []
    if isinstance(tools, dict):
        for t in tools.get("components") or []:
            tool_names.append(f"{t.get('name')}@{t.get('version')}")
    elif isinstance(tools, list):
        for t in tools:
            tool_names.append(f"{t.get('name')}@{t.get('version')}")

    n = len(comps)
    have = Counter()
    lic_kinds = Counter()
    enrich_src = Counter()
    purl_types = Counter()
    bad_version = 0

    for c in comps:
        lic, kind = _licence_of(c)
        if lic:
            have["license"] += 1
            lic_kinds[kind] += 1
        if c.get("purl"):
            have["purl"] += 1
            try:
                purl_types[c["purl"].split(":", 1)[1].split("/", 1)[0]] += 1
            except (IndexError, KeyError):
                pass
        if c.get("cpe"):
            have["cpe"] += 1
        v = c.get("version")
        if v:
            have["version"] += 1
            # A pinned version is the point of a lockfile-derived SBOM.
            # These placeholders are what generators emit when they could
            # not resolve one, and they defeat vulnerability matching.
            if str(v).lower() in ("latest", "unknown", "*", "", "none"):
                bad_version += 1
        if c.get("description"):
            have["description"] += 1
        if c.get("supplier") or c.get("publisher"):
            have["supplier"] += 1
        if c.get("author") or c.get("authors") or c.get("manufacturer"):
            have["author"] += 1
        if c.get("hashes"):
            have["hashes"] += 1
        if c.get("externalReferences"):
            have["extrefs"] += 1
        for ref in c.get("externalReferences") or []:
            if ref.get("type") == "vcs":
                have["vcs"] += 1
                break
        for p in c.get("properties") or []:
            if p.get("name") == "sbomify:enrichment:source":
                enrich_src[p.get("value")] += 1

    deps = doc.get("dependencies") or []
    # A dependency array where every entry has an empty dependsOn is a flat
    # list wearing a graph's clothes -- it satisfies the schema but conveys
    # no relationships, which is an NTIA element.
    dep_edges = sum(len(d.get("dependsOn") or []) for d in deps)

    return {
        "format": "cyclonedx",
        "spec_version": doc.get("specVersion"),
        "serial_number": bool(doc.get("serialNumber")),
        "timestamp": bool(meta.get("timestamp")),
        "tools": tool_names,
        "components": n,
        "components_all": len(all_comps),
        "file_components": type_counts.get("file", 0),
        "component_types": dict(type_counts),
        "root_name": root.get("name"),
        "root_version": root.get("version"),
        "root_purl": root.get("purl"),
        "root_has_license": bool(root.get("licenses")),
        "root_version_placeholder": str(root.get("version", "")).lower()
        in ("latest", "unknown", "", "none"),
        "coverage": {k: pct(have[k], n) for k in
                     ("license", "purl", "version", "description", "supplier",
                      "author", "hashes", "extrefs", "vcs", "cpe")},
        "counts": dict(have),
        "license_kinds": dict(lic_kinds),
        "version_placeholder_count": bad_version,
        "purl_types": dict(purl_types),
        "enrichment_sources": dict(enrich_src),
        "enriched_components": sum(enrich_src.values()),
        "dependency_nodes": len(deps),
        "dependency_edges": dep_edges,
    }


def inspect_spdx(doc):
    pkgs = doc.get("packages") or []
    n = len(pkgs)
    have = Counter()
    for p in pkgs:
        lc = p.get("licenseConcluded") or p.get("licenseDeclared")
        if lc and lc not in ("NOASSERTION", "NONE"):
            have["license"] += 1
        if p.get("versionInfo"):
            have["version"] += 1
        supplier = p.get("supplier")
        if supplier and supplier != "NOASSERTION":
            have["supplier"] += 1
        if p.get("checksums"):
            have["hashes"] += 1
        for ref in p.get("externalRefs") or []:
            if ref.get("referenceType") == "purl":
                have["purl"] += 1
                break
    return {
        "format": "spdx",
        "spec_version": doc.get("spdxVersion"),
        "components": n,
        "coverage": {k: pct(have[k], n) for k in
                     ("license", "purl", "version", "supplier", "hashes")},
        "counts": dict(have),
        "dependency_nodes": len(doc.get("relationships") or []),
    }


def main():
    path = sys.argv[1]
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except Exception as e:
        print(json.dumps({"error": f"unreadable: {e}"}))
        return
    try:
        if doc.get("bomFormat") == "CycloneDX" or "specVersion" in doc:
            out = inspect_cyclonedx(doc)
        elif "spdxVersion" in doc:
            out = inspect_spdx(doc)
        else:
            out = {"error": "unrecognised document"}
    except Exception as e:
        out = {"error": f"inspect failed: {type(e).__name__}: {e}"}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
