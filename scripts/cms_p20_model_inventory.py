"""P20 read-only live Django-to-CMS registry inventory, never an acceptance certificate.

Usage: python scripts/cms_p20_model_inventory.py --write
       python scripts/cms_p20_model_inventory.py --check
Only metadata from the Django application registry is inspected. No ORM query,
database mutation, public effect, private values or external service access.
"""
import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.apps import apps
from django.urls import resolve
from atlas.cms_capabilities import KNOWN_PERMISSIONS, READY_CAPABILITIES
from atlas.cms_content import REGISTRY as CONTENT_REGISTRY, capability
from atlas.cms_content_views import ContentCreateView
from atlas.cms_domains import domain_for
from atlas.cms_governance import REGISTRY as GOVERNANCE_REGISTRY
from atlas.cms_governance_views import GovernanceResourcesView

OUTPUT = ROOT / "docs" / "v1.0-p20-live-model-inventory.md"


def inspect():
    models = sorted(
        (model for model in apps.get_app_config("atlas").get_models()
         if not model._meta.abstract),
        key=lambda model: model._meta.label_lower,
    )
    model_set = set(models)
    content_types = defaultdict(list)
    governance_types = defaultdict(list)
    for kind, entry in CONTENT_REGISTRY.items():
        content_types[entry[0]].append(kind)
    for kind, entry in GOVERNANCE_REGISTRY.items():
        governance_types[entry[0]].append(kind)
    unknown = (set(content_types) | set(governance_types)) - model_set
    if unknown:
        raise RuntimeError("Unregistered Django model in CMS registry: "
                           + ", ".join(sorted(str(x) for x in unknown)))

    routes = []
    for kind, (model, _, _) in sorted(CONTENT_REGISTRY.items()):
        route = f"/api/admin/content/{kind}/"
        match = resolve(route)
        if match.func.view_class is not ContentCreateView or match.kwargs != {"kind": kind}:
            raise RuntimeError(f"Content route mismatch for {kind}: {route}")
        domain = domain_for(kind)
        view_cap = capability(kind, "view")
        create_cap = capability(kind, "create")
        if view_cap not in KNOWN_PERMISSIONS or create_cap not in KNOWN_PERMISSIONS:
            raise RuntimeError(f"Missing permission declaration for {kind}")
        routes.append((kind, model.__name__, domain, view_cap in READY_CAPABILITIES,
                       create_cap in READY_CAPABILITIES))
    governance_route = "/api/admin/governance/resources/"
    if resolve(governance_route).func.view_class is not GovernanceResourcesView:
        raise RuntimeError(f"Governance resource selector route mismatch: {governance_route}")
    governance_routes = []
    for resource_type, (model, domain, *_fields) in sorted(GOVERNANCE_REGISTRY.items()):
        view_cap = f"cms_{domain}_view"
        if view_cap not in KNOWN_PERMISSIONS:
            raise RuntimeError(f"Undeclared governance view permission: {resource_type}")
        governance_routes.append((resource_type, model.__name__, domain,
                                  view_cap in READY_CAPABILITIES))
    covered_content = set(content_types)
    covered_governance = set(governance_types)
    shared = covered_content & covered_governance
    neither = model_set - (covered_content | covered_governance)
    lines = [
        "# P20 | Current live Django-to-CMS declarative model inventory",
        "",
        "Generated deterministically from the **local** Django app and CMS registries.",
        "Reproduce using `python scripts/cms_p20_model_inventory.py --check`",
        "or update with `--write`. This inspects model metadata **only**, never records.",
        "",
        "**CRITICAL:** A model in a registry is not evidence of a working editor,",
        "an authorized API, scientific approval, legal rights, public eligibility,",
        "browser QA, or completed P20 acceptance. An infrastructure/user/runtime",
        "model outside both registries is **not automatically a missing feature**.",
        "",
        "## Observed registry counts",
        "",
        "| Metric | Current value |",
        "| --- | ---: |",
        f"| Concrete atlas models | {len(models)} |",
        f"| Content proposal keys / unique models | {len(CONTENT_REGISTRY)} / {len(covered_content)} |",
        f"| Governance resource keys / unique models | {len(GOVERNANCE_REGISTRY)} / {len(covered_governance)} |",
        f"| Models in both mappings | {len(shared)} |",
        f"| Models in neither mapping | {len(neither)} |",
        f"| READY capability names (declarative only) | {len(READY_CAPABILITIES)} |",
        "",
        "## Current per-model mapping (not action/UI acceptance)",
        "",
        "| Concrete atlas model | Content proposal kind(s) | Governance type(s) | Action/UI acceptance |",
        "| --- | --- | --- | --- |",
    ]
    for model in models:
        content = ", ".join(sorted(content_types[model])) or "none"
        governance = ", ".join(sorted(governance_types[model])) or "none"
        lines.append(f"| {model.__name__} | {content} | {governance} | **Unverified** |")
    lines.extend([
        "",
        "## Authenticated Content collection route matrix (synthetic checks only)",
        "",
        "The exact Django resolver maps every registered kind to the common",
        "`ContentCreateView` collection. Current view/create capability names are",
        "declared separately and readiness is checked against `READY_CAPABILITIES`.",
        "The synthetic P20 regression `atlas.tests_v100_p20_routes` checks owner GET",
        "and no-domain-permission GET/POST across all kinds, isolated therapist",
        "view rights and live removal of that view grant without relogin.",
        "**This does not test authorized POST/CRUD, immutable revision lifecycle,",
        "reference-level visibility, privacy of non-empty records or public impact.**",
        "",
        "| Kind | Model | Domain | View cap READY | Create cap READY | Collection route |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for kind, model_name, domain, view_ready, create_ready in routes:
        lines.append(f"| {kind} | {model_name} | {domain} | "
                     f"{'yes' if view_ready else 'no'} | {'yes' if create_ready else 'no'}"
                     f" | `/api/admin/content/{kind}/` |")
    lines.extend([
        "",
        "## Governance resource-selector matrix (synthetic checks only)",
        "",
        "The 94 allowlisted governance types use a shared server route and a",
        "domain-scoped resource_type selector. The P20 synthetic regression",
        "tests owner GET, 404 refusal without domain view permission,",
        "one-domain visibility and live permission revocation for every type.",
        "This does NOT test non-empty private resources, governance workflow",
        "decisions, conflicts, rights/science approvals or publication readiness.",
        "",
        "| Resource type | Model | Domain | View cap READY | Selector |",
        "| --- | --- | --- | --- | --- |",
    ])
    for resource_type, model_name, domain, view_ready in governance_routes:
        lines.append(f"| {resource_type} | {model_name} | {domain} "
                     f"| {'yes' if view_ready else 'no'} "
                     f"| `/api/admin/governance/resources/?resource_type={resource_type}` |")
    lines.extend([
        "",
        "## Untested operational dimensions",
        "",
        "Every model still needs its *appropriate* action-level assessment: owner/scoped",
        "permissions, URL/UI/service/DB flow, stale write/idempotency, negative tests,",
        "privacy/redaction, and any public effect. Only relevant business operations",
        "require a CMS editor. Absence from proposal/governance registries alone",
        "does not prove a model needs one.",
        "",
        "Do not mark P20 complete until the source-checked navigation -> UI -> API ->",
        "permission -> service -> DB -> public impact/test matrix is independently",
        "evaluated and the mandatory scientific/rights/owner gates are satisfied.",
        "",
    ])
    return "\n".join(lines), {
        "concrete_models": len(models),
        "content_kinds": len(CONTENT_REGISTRY),
        "governance_types": len(GOVERNANCE_REGISTRY),
        "both": len(shared),
        "neither": len(neither),
        "ready_caps": len(READY_CAPABILITIES),
        "resolved_content_routes": len(routes),
        "view_cap_ready": sum(1 for item in routes if item[3]),
        "create_cap_ready": sum(1 for item in routes if item[4]),
        "resolved_governance_resource_types": len(governance_routes),
        "governance_view_cap_ready": sum(1 for item in governance_routes if item[3]),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="compare current inventory to committed Markdown")
    mode.add_argument("--write", action="store_true", help="regenerate only the in-repo inventory Markdown")
    args = parser.parse_args()
    text, counts = inspect()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            print(f"STALE model inventory: {OUTPUT}", file=sys.stderr)
            raise SystemExit(1)
        print("PASS P20 inventory reflects live model metadata:", counts)
    else:
        OUTPUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"WROTE {OUTPUT}:", counts)
