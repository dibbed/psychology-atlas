"""Reproduce the reviewed, bounded FMA publication selection from pinned OWL.

Download the official fma.owl separately; the 208 MB ontology is not vendored.
The reviewed selection below is deliberate, not an automatic ontology importer.
"""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_SHA = "738b3ce478b0dd9f9213f5d8b8aba002701972fc2ab39eaa9263a81ca5893213"
FMA_SHA = "beb3dc47979ad5434ef70fd02af4307f147f2023f7d8c2c57103b995191194c3"
COMMIT = "c6f70808ba2859b88cb0b8362c34fa9017c6f96a"
VERSION = "FMA 5.1.0; uw-sig/FMA " + COMMIT[:12]
SOURCE = "source-fma-510-official"
FMA = "http://purl.org/sig/ont/fma/"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
RDFS = "{http://www.w3.org/2000/01/rdf-schema#}"
OWL = "{http://www.w3.org/2002/07/owl#}"
EXCLUDED = {
    "gray-matter": "FMA gray matter of neuraxis includes spinal cord; the brain-only Allen identity is not equivalent.",
    "white-matter": "FMA white matter of neuraxis includes spinal cord; the brain-only Allen identity is not equivalent.",
    "cerebral-nuclei": "No verified exact FMA equivalent of this Allen annotation collection.",
    "telencephalic-white-matter": "No verified exact FMA equivalent of this Allen annotation collection.",
    "telencephalic-commissures": "No verified exact FMA equivalent of this Allen annotation collection.",
    "mesencephalon": "Developmental extent equivalence is unresolved; adult Midbrain is independently added.",
    "myelencephalon": "Developmental extent equivalence is unresolved; adult Medulla oblongata is independently added.",
}
MANUAL = {"genu-corpus-callosum": "61946", "body-corpus-callosum": "61947",
          "splenium-corpus-callosum": "61948", "rostrum-corpus-callosum": "61945",
          "subthalamic-nucleus-left": "73368", "subthalamic-nucleus-right": "73367"}
ADDED = {"forebrain": ("61992", "region"), "hindbrain": ("67687", "region"),
         "midbrain": ("61993", "region"), "medulla-oblongata": ("62004", "region"),
         "brainstem": ("79876", "region"), "cerebral-hemisphere": ("61817", "hemisphere"),
         "neocortex": ("62429", "cortical_region"), "archicortex": ("62424", "cortical_region"),
         "hippocampus": ("275020", "structure"), "hippocampus-proper": ("62493", "structure"),
         "subcortex-cerebral-hemisphere": ("242188", "region"),
         "lentiform-nucleus": ("77615", "subcortical_structure"),
         "subthalamic-nucleus": ("62035", "subcortical_structure"),
         "base-midbrain-peduncle": ("242166", "structure"),
         "brain-ventricular-system": ("242787", "structure"),
         "lateral-ventricle": ("78448", "structure"), "third-ventricle": ("78454", "structure"),
         "fourth-ventricle": ("78469", "structure"), "cerebral-aqueduct": ("78467", "structure")}
# Prefer regional educational parents to the simultaneously asserted cortical tissue parent.
PARENTS = {
    "telencephalon": "forebrain", "diencephalon": "forebrain", "metencephalon": "hindbrain",
    "cerebral-cortex": "cerebral-hemisphere", "hippocampal-formation": "archicortex",
    "dentate-gyrus": "hippocampus", "subiculum": "hippocampal-formation",
    "basal-ganglia": "subcortex-cerebral-hemisphere", "caudate-nucleus": "striatum",
    "putamen": "striatum", "nucleus-accumbens": "striatum", "globus-pallidus": "lentiform-nucleus",
    "cerebellum": "metencephalon", "pons": "metencephalon", "hippocampus": "limbic-lobe",
    "hippocampus-proper": "hippocampus", "fusiform-gyrus": "neocortex",
    "parahippocampal-gyrus": "limbic-lobe", "cingulate-gyrus": "limbic-lobe",
    "midbrain": "brain", "medulla-oblongata": "hindbrain", "substantia-nigra": "base-midbrain-peduncle",
    "subthalamic-nucleus-left": "subthalamus", "subthalamic-nucleus-right": "subthalamus",
    "subthalamic-nucleus": "subthalamus", "pineal-gland": "epithalamus",
    "cerebellar-cortex": "cerebellum", "pontine-tegmentum": "pons", "locus-ceruleus": "pontine-tegmentum",
    "red-nucleus": "midbrain-tegmentum", "midbrain-tectum": "midbrain", "midbrain-tegmentum": "midbrain",
    "hypothalamus": "diencephalon", "epithalamus": "diencephalon",
    "forebrain": "brain", "hindbrain": "brain", "anterior-commissure": "telencephalon",
    "corpus-callosum": "telencephalon",
    "brain-ventricular-system": "brain", "lateral-ventricle": "cerebral-hemisphere",
    "third-ventricle": "brain-ventricular-system", "fourth-ventricle": "brain-ventricular-system",
    "cerebral-aqueduct": "brain-ventricular-system",
}
for lobe in ("frontal", "parietal", "temporal", "occipital", "limbic"):
    PARENTS[lobe + "-lobe"] = "cerebral-hemisphere"
PARENTS["insula"] = "cerebral-hemisphere"
for gyrus in ("precentral", "middle-frontal", "inferior-frontal", "superior-frontal"):
    PARENTS[gyrus + "-gyrus"] = "frontal-lobe"
for name in ("postcentral-gyrus", "superior-parietal-lobule", "inferior-parietal-lobule", "precuneus"):
    PARENTS[name] = "parietal-lobe"
for name in ("supramarginal-gyrus", "angular-gyrus"):
    PARENTS[name] = "inferior-parietal-lobule"
for name in ("superior-temporal-gyrus", "middle-temporal-gyrus", "inferior-temporal-gyrus"):
    PARENTS[name] = "temporal-lobe"
PARENTS["superior-occipital-gyrus"] = "occipital-lobe"
for name in ("genu", "body", "splenium", "rostrum"):
    PARENTS[name + "-corpus-callosum"] = "corpus-callosum"
for name in ("ca1", "ca2", "ca3"):
    PARENTS[name + "-field"] = "hippocampus-proper"
# Exact native synonyms selected after rejecting historical, ambiguous and tissue/whole conflations.
ALIASES = {
    "cerebral-cortex": ["Cortex of cerebrum", "Cortex of cerebral hemisphere"],
    "precentral-gyrus": ["Prerolandic gyrus", "Precentral convolution"],
    "inferior-frontal-gyrus": ["Inferior frontal convolution"],
    "postcentral-gyrus": ["Postrolandic gyrus", "Postcentral convolution"],
    "angular-gyrus": ["AG"], "precuneus": ["Precuneate lobule", "Quadrate lobule"],
    "insula": ["Insular lobe"], "dentate-gyrus": ["Dentate gyrus", "Fascia dentata"],
    "basal-ganglia": ["Basal ganglia set", "Set of basal nuclei"],
    "caudate-nucleus": ["Caudatus"], "putamen": ["Nucleus putamen"],
    "nucleus-accumbens": ["Accumbens nucleus", "Nucleus accumbens septi"],
    "amygdala": ["Amygdaloid nucleus"], "thalamus": ["Dorsal thalamus"],
    "subthalamus": ["Subthalamus", "Subthalamic region"],
    "cerebellar-nuclei": ["Cerebellar nuclei", "Intrinsic nuclei of cerebellum"],
    "dentate-nucleus": ["Lateral nucleus of cerebellum"], "pineal-gland": ["Pineal gland"],
    "superior-frontal-gyrus": ["Superior frontal convolution"],
    "middle-temporal-gyrus": ["Intermediate temporal gyrus"],
    "parahippocampal-gyrus": ["Hippocampal gyrus"],
    "midbrain-tegmentum": ["Tegmentum of midbrain", "Mesencephalic tegmentum"],
    "pontine-tegmentum": ["Tegmentum of pons", "Dorsal portion of pons"],
    "locus-ceruleus": ["Locus coeruleus", "Caerulean nucleus"],
    "cerebellar-cortex": ["Cortex of cerebellum"], "lentiform-nucleus": ["Lenticular nucleus"],
    "hippocampus-proper": ["Ammon's horn"], "archicortex": ["Archipallium"],
    "cerebral-aqueduct": ["Aqueduct of midbrain", "Aqueduct of Sylvius"],
}


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_fma(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != FMA_SHA:
        raise ValueError("Official FMA bytes do not match the reviewed Git LFS digest.")
    nodes = {}
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != OWL + "Class" or RDF + "about" not in el.attrib:
            continue
        uri = el.attrib[RDF + "about"]
        labels = [x.text for x in el if x.text and (x.tag == RDFS + "label" or
                  any(s in x.tag.lower() for s in ("synonym", "preferred_name")))]
        relations = []
        for sub in el.findall(RDFS + "subClassOf"):
            if RDF + "resource" in sub.attrib:
                relations.append(["is_a", sub.attrib[RDF + "resource"]])
            for rest in sub.findall(OWL + "Restriction"):
                prop, target = rest.find(OWL + "onProperty"), rest.find(OWL + "someValuesFrom")
                if prop is not None and target is not None and RDF + "resource" in target.attrib:
                    relations.append([prop.get(RDF + "resource"), target.get(RDF + "resource")])
        nodes[uri] = dict(labels=labels, relations=relations)
        el.clear()
    return nodes


def part_proof(nodes, child, parent):
    queue = collections.deque([(child, False, [])])
    seen = {(child, False)}
    while queue:
        node, has_part, proof = queue.popleft()
        if node == parent and has_part:
            return proof
        if len(proof) > 12:
            continue
        for predicate, target in nodes.get(node, {}).get("relations", []):
            if predicate != "is_a" and predicate not in (FMA + "regional_part_of", FMA + "constitutional_part_of"):
                continue
            state = (target, has_part or predicate != "is_a")
            if state not in seen:
                seen.add(state)
                queue.append((target, state[1], proof + [[node, predicate, target]]))
    return None


def build(path):
    oldpath = ROOT / "docs/research/brain/v0.9.2b/psychology_atlas_brain_curated_dossier_v0.9.2b.json"
    raw = oldpath.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PREVIOUS_SHA
    old = json.loads(raw)
    nodes = parse_fma(path)
    index = collections.defaultdict(set)
    for uri, node in nodes.items():
        for label in node["labels"]:
            index[norm(label)].add(uri)
    rows, replacements, mapping, proofs = [], {}, {}, {}
    catalog = copy.deepcopy(old["dataset_metadata"]["verified_source_catalog"])
    catalog[SOURCE] = dict(source_id=SOURCE, title="Foundational Model of Anatomy Ontology (FMA), version 5.1.0",
        organization="University of Washington, Structural Informatics Group", authors=["Cornelius Rosse", "Jose Leonardo V. Mejino Jr.", "Landon T. Detwiler", "James F. Brinkley"],
        publication_year=2026, source_type="dataset", resource_version=VERSION,
        citation="University of Washington Structural Informatics Group. Foundational Model of Anatomy Ontology (FMA) 5.1.0. Official repository commit " + COMMIT + ". CC BY 4.0; selected labels and part relations adapted for Psychology Atlas.",
        url="https://github.com/uw-sig/FMA/tree/" + COMMIT, doi="", pmid="",
        bibliographic_verification="independently_verified", access_date="2026-10-01",
        verification_urls=["https://raw.githubusercontent.com/uw-sig/FMA/" + COMMIT + "/LICENSE", "https://raw.githubusercontent.com/uw-sig/FMA/" + COMMIT + "/Version.txt", "https://media.githubusercontent.com/media/uw-sig/FMA/" + COMMIT + "/fma.owl"],
        evidence_role="Selected human anatomical classes, native synonyms and exact part-of restrictions; primary publication authority.",
        license="CC BY 4.0", artifact_sha256=FMA_SHA,
        limitations="A structural ontology, not a coordinate atlas or functional parcellation. Generic classes do not specify left/right boundaries. Parent forest omits unverified generic containment.")
    for r in old["records"]:
        if r["category"] == "source" or r.get("owner_type") == "network" or r["category"] == "network":
            rows.append(copy.deepcopy(r))
        if r["category"] != "anatomy" or r["slug"] in EXCLUDED:
            continue
        row = copy.deepcopy(r)
        slug = row["slug"]
        hits = index[norm(row["name_en"])]
        uri = FMA + "fma" + MANUAL[slug] if slug in MANUAL else next(iter(hits)) if len(hits) == 1 else None
        assert uri in nodes, slug
        mapping[slug] = uri
        replacements[row["id"]] = dict(previous_source_ids=r["source_ids"], new_source_ids=[SOURCE], native_uri=uri,
            change="Recurated generic human structural identity; Allen annotation extent, acronyms and spatial identifiers are not carried over.")
        row.update(name_en=nodes[uri]["labels"][0], review_status="reviewed", source_version=VERSION,
                   spatial_scope="Human structural ontology class " + uri + "; " + ("explicit " + row["laterality"] + " side." if row["laterality"] in ("left", "right") else "generic/unlateralized class; no bilateral spatial mask is asserted."))
        row["source_ids"] = [SOURCE]
        row["source_notes"] = {SOURCE: "Exact native class " + uri + "; label '" + row["name_en"] + "'. Selected from official FMA 5.1.0 under CC BY 4.0. Identity recuration replaces Allen annotation-specific extent; no exact inter-atlas spatial equivalence."}
        if row["name_fa"]:
            terminology = [s for s in r["source_ids"] if s != "source-hbao-2025-02-10"]
            for source in terminology:
                row["source_ids"].append(source)
                row["source_notes"][source] = r["source_notes"][source]
        rows.append(row)
    for slug, (identifier, kind) in ADDED.items():
        uri = FMA + "fma" + identifier
        mapping[slug] = uri
        rows.append(dict(id="anatomy-" + slug, category="anatomy", slug=slug, name_en=nodes[uri]["labels"][0],
            name_fa="", kind=kind, laterality="not_established", description_en="", description_fa="",
            source_version=VERSION, spatial_scope="Human FMA generic/unlateralized structural class " + uri + "; no individual spatial mask.",
            persian_reviewed=False, review_status="reviewed", verification_status="source_checked", is_active=True,
            source_ids=[SOURCE], source_notes={SOURCE: "Exact native FMA class " + uri + "; independently added educational anatomy. CC BY 4.0."}))
    for row in rows:
        if row["category"] == "anatomy":
            row["description_en"] = "Human anatomical structure represented by " + mapping[row["slug"]] + " in " + VERSION + ". " + row["spatial_scope"] + " Selected labels/relations adapted from the University of Washington Structural Informatics Group FMA under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). No exclusive function, diagnosis or coordinate boundary is asserted. An absent parent means no approved containment in this partial source-based forest."
        elif row["category"] == "network":
            row["description_en"] += " " + row["definition"] + " " + row["method"]
    # Add the verified source after assigning a portable, never-DB placeholder.
    info = catalog[SOURCE]
    rows.append(dict(id=SOURCE, category="source", source_reference_id=-25, source_ids=[], source_notes={},
        review_status="reviewed", verification_status="source_checked", is_active=True,
        **{k: info[k] for k in ("title", "citation", "url", "doi", "pmid")}))
    for slug, uri in mapping.items():
        rows.append(dict(id="external-id-" + slug + "-fma", category="external_identifier", owner_type="anatomy",
            owner_slug=slug, namespace="FMA", identifier=uri.split("fma")[-1], source_version=VERSION, url=uri,
            review_status="reviewed", verification_status="source_checked", is_active=True,
            source_ids=[SOURCE], source_notes={SOURCE: "Native class identifier " + uri + "; no Allen/HBAO equivalence asserted. CC BY 4.0."}))
        for label in ALIASES.get(slug, []):
            assert label in nodes[uri]["labels"], (slug, label)
            assert norm(label) != norm(nodes[uri]["labels"][0]), (slug, label)
            rows.append(dict(id="alias-" + slug + "-fma-" + norm(label).replace(" ", "-"), category="alias", owner_type="anatomy",
                owner_slug=slug, text=label, language="en", alias_type="abbreviation" if label == "AG" else "alternative", persian_reviewed=False,
                review_status="reviewed", verification_status="source_checked", is_active=True,
                source_ids=[SOURCE], source_notes={SOURCE: "Exact FMA synonym annotation '" + label + "' on " + uri + "; independently selected; CC BY 4.0."}))
    # Persian attestation is carried separately; no invented translations.
    for row in old["records"]:
        if row["category"] == "alias" and row.get("language") == "fa" and row["owner_slug"] in mapping:
            rows.append(dict(copy.deepcopy(row), review_status="reviewed"))
    previous_edges = {x["record"]["child_slug"]: x["record"] for x in old["dataset_metadata"]["deferred_hierarchy_claims"]}
    for child, parent in PARENTS.items():
        trail = part_proof(nodes, mapping[child], mapping[parent])
        assert trail, (child, parent)
        rid = "hierarchy-" + child + "-part-of-" + parent
        proofs[rid] = trail
        note = "FMA 5.1.0 exact containment proof: " + "; ".join(a + " --" + p + "--> " + b for a, p, b in trail) + ". regional_part_of and constitutional_part_of specialize part_of. is_a steps only inherit/generalize a part restriction; an is_a-only path is never containment. This is a selected primary parent, not the complete FMA DAG. CC BY 4.0."
        rows.append(dict(id=rid, category="hierarchy", child_slug=child, parent_slug=parent, predicate="part_of", source_version=VERSION,
            explanation_en="Selected structural part_of in the FMA projection; " + ("direct source assertion." if len(trail) == 1 else "qualified transitive/inherited restriction; exact proof in source note."), explanation_fa="",
            review_status="reviewed", verification_status="source_checked", is_active=True, source_ids=[SOURCE], source_notes={SOURCE: note}))
    by_id = {r["id"]: r for r in rows}
    ledger = []
    for entry in old["dataset_metadata"]["publication_review_ledger"]:
        rid = entry["record_id"]
        approved = rid in by_id
        reason = "Independent FMA 5.1.0 structural recuration and official CC BY 4.0 grant." if rid in replacements or rid in proofs else "Retained verified bibliographic/network metadata within its reviewed reuse scope." if approved else "Allen-specific provenance, identifier or abbreviation remains rights-deferred; not transferred to the FMA class."
        if rid.startswith("anatomy-") and not approved:
            reason = EXCLUDED[rid.removeprefix("anatomy-")]
        if entry["category"] == "hierarchy" and not approved:
            oldrow = previous_edges.get(rid.removeprefix("hierarchy-").split("-part-of-")[0])
            reason = "No approved exact FMA proof for these endpoints in the selected primary forest; old Allen assertion remains historical research."
        ledger.append(dict(record_id=rid, category=entry["category"], classification="APPROVED_FOR_PUBLICATION" if approved else "DEFERRED",
            previous_classification=entry["classification"], rights_status="RIGHTS_REPLACED_WITH_CLEAR_SOURCE" if rid in replacements or rid in proofs else "RIGHTS_CLEARED" if approved else "RIGHTS_UNRESOLVED",
            scientific_status="VERIFIED" if approved else "SCOPE_OR_PROVENANCE_DEFERRED", reason=reason,
            location="records" if approved else "previous v0.9.2B dossier (preserved, not staged)"))
    oldids = {e["record_id"] for e in ledger}
    for row in rows:
        if row["id"] not in oldids:
            ledger.append(dict(record_id=row["id"], category=row["category"], classification="APPROVED_FOR_PUBLICATION",
                previous_classification="NEW", rights_status="RIGHTS_CLEARED", scientific_status="VERIFIED", location="records",
                reason="Independently selected native FMA 5.1.0 class/synonym/identifier or proved containment; official CC BY 4.0 source."))
    counts = dict(collections.Counter(r["category"] for r in rows))
    cleared = [e["record_id"] for e in ledger if e["previous_classification"] == "DEFERRED" and e["classification"] == "APPROVED_FOR_PUBLICATION"]
    metadata = dict(key="psychology-atlas-brain-publication-v092c", version="0.9.2c-fma510-2026-10-01", curated_at="2026-10-01",
        title="Rights-remediated human Brain publication selection", previous_dossier_filename=oldpath.name,
        previous_dossier_sha256=PREVIOUS_SHA, original_web_sha256=old["dataset_metadata"]["parent_sha256"],
        original_deferred_count=375, previously_deferred_cleared_count=len(cleared), previously_deferred_cleared=cleared,
        remaining_previous_deferred_count=375-len(cleared), rights_rejected_count=0,
        record_counts=counts, publication_review_counts=dict(collections.Counter(e["classification"] for e in ledger)),
        added_record_count=len(rows)-len(oldids & set(by_id)), source_replacements=replacements,
        source_reference_id_policy="Negative IDs are portable identity placeholders only. Derive positive IDs inside the locked target transaction; never use them as portable identity.",
        verified_source_catalog=catalog, publication_review_ledger=ledger,
        selected_authority=dict(source=SOURCE, version=VERSION, commit=COMMIT, artifact_sha256=FMA_SHA, hierarchy="FMA-only partial forest of explicit/inherited/transitive structural restrictions. No Allen or cross-ontology edges.",
            inheritance_policy="Only a path containing a regional_part_of or constitutional_part_of restriction can prove containment. No inversion of existential has_part; no is_a-only containment."),
        hierarchy_proofs=proofs, anatomy_native_classes=mapping,
        rights_review=dict(commercial_use="PERMITTED_FOR_APPROVED_SELECTION", license="CC BY 4.0", official_license_url="https://raw.githubusercontent.com/uw-sig/FMA/"+COMMIT+"/LICENSE",
            official_license_sha256="7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661",
            conflict_resolution="OBO Foundry still links a 2006 draft/custom license; current University of Washington official repository explicitly licenses FMA 5.1.0 under CC BY 4.0. HRA v5.1.0 raw-asset metadata independently agrees. The official upstream ontology, not a relabeled Allen graph, is the publication source.",
            metadata_reuse="Verified citation facts and identifiers only for unused sources; no article text/figures.", redistribution="Selected FMA labels/relations permitted with attribution and change notice; network short-label subset retains CBIG MIT notice.",
            derivative_use="CC BY 4.0 allows commercial adaptation; selected projection, aliases and descriptions are marked as adapted.",
            attribution="University of Washington Structural Informatics Group; FMA 5.1.0; source commit, CC BY URL, adaptation notice in every anatomical source note/description; public source metadata retains full attribution.",
            visual_rights="No visuals, meshes or publisher images published. Future assets require separate review.", unresolved="Allen/HBAO annotation-specific identifiers/aliases and unsupported parent claims remain deferred."),
        research_delta=["Replaced primary anatomical authority with independently parsed official FMA 5.1.0 (human-specific).", "Rejected exact spatial equivalence assumptions; original Allen/HBAO records remain in the immutable B dossier.", "Verified Uberon release v2026-06-23 contains ontology version IRI 2026-06-19; not combined with FMA hierarchy.", "Current FIPAT site lists CC BY-SA 4.0, not CC0/public-domain unrestricted reuse; not used to bypass hierarchy evidence.", "Official FMA source agrees with HRA raw-asset CC BY 4.0; OBO custom-license link is historical.", "Native synonym review excludes contradictory Genu/Rostrum Mai annotation, historical archistriatum/paleostriatum, tissue-versus-whole aliases, and source-specific acronyms."],
        persian_review=dict(previous_review=old["dataset_metadata"]["persian_review_summary"],
            reviewed_anatomy_names=4, reviewed_anatomy_aliases=1, unresolved_anatomy_names=83,
            unresolved_network_names=7, unresolved_identity_terms=90,
            policy="Retained independent academic/professional usage attestations; no invented translation or national nomenclature certification."),
        deferred_research_reference="Original Web and v0.9.2B research, including lesion/connectivity/functional/visual/rights leads, remain unchanged; none are canonical relation evidence.",
        limitations=["Partial FMA structural forest: generic containment lacking an exact approved restriction is absent, not inferred from common knowledge.", "Laterality remains not_established for generic classes; explicit left/right subthalamic nuclei are retained separately.", "No network memberships, functional associations, coordinates, diagnostic claims or visual assets.", "No reviewed Persian name invented; four retained attested names and one Persian alias are subject to the B dossier's terminology limitations."],
        evidence_snapshots={uri: nodes[uri] for uri in sorted(set(mapping.values()) | {u for proof in proofs.values() for a,p,b in proof for u in (a,b)})})
    document = dict(schema_version="brain-staging-v1", dataset_metadata=metadata, records=rows)
    target = ROOT / "docs/research/brain/v0.9.2c"
    target.mkdir(parents=True, exist_ok=True)
    dossier = target / "psychology_atlas_brain_publication_dossier_v0.9.2c.json"
    content = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    dossier.write_bytes(content)
    manifest = dict(schema_version="brain-publication-manifest-v1", dossier_filename=dossier.name,
        dossier_sha256=hashlib.sha256(content).hexdigest(), dossier_version=metadata["version"],
        previous_dossier_sha256=PREVIOUS_SHA, counts=counts, candidates=ledger,
        approval_scope="Only these pinned scientific/rights-reviewed records; no generic auto-promotion. Commercial use remains possible.")
    (target / "publication_manifest.json").write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(dict(sha256=manifest["dossier_sha256"], counts=counts, cleared=len(cleared), remaining=375-len(cleared), total_ledger=len(ledger))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fma-owl", type=Path, required=True)
    build(parser.parse_args().fma_owl)
