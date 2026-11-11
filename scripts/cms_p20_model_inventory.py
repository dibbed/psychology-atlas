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
from atlas.cms_capabilities import READY_CAPABILITIES
from atlas.cms_content import REGISTRY as CONTENT_REGISTRY
from atlas.cms_governance import REGISTRY as GOVERNANCE_REGISTRY

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
