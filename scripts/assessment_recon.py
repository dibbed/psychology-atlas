"""Read-only corpus classification; labels are leads, never publication decisions."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3

TERMS = re.compile(r"\b(?:assessment|scale|inventory|questionnaire|screening|measure|instrument|test|psychometric|reliability|validity|sensitivity|specificity|cutoff|norm|translation|licensing|copyright)s?\b|persian validation", re.I)


def inspect(database):
    with sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True) as connection:
        datasets = connection.execute("SELECT id,key,source_sha256,is_active FROM atlas_researchdataset ORDER BY id").fetchall()
        rows = connection.execute("SELECT id,dataset_id,section,external_id,name_en,payload FROM atlas_researchrecord ORDER BY id").fetchall()
        matches = []
        for pk, dataset, section, external_id, name, raw in rows:
            terms = sorted({match.group().lower() for match in TERMS.finditer(raw)})
            if not terms:
                continue
            payload = json.loads(raw)
            labels = []
            if section == "research_gaps":
                labels.append("G")
            elif section in {"sources", "source", "brain_source"}:
                labels.append("D")
            elif section == "symptoms" and payload.get("measures"):
                labels.extend(["A", "H"])
            elif section in {"claims", "relationships"} and set(terms) & {"psychometric", "reliability", "validity"}:
                labels.extend(["C", "H"])
            else:
                labels.append("E")
            if set(terms) & {"copyright", "licensing", "questionnaire", "inventory"}:
                labels.append("F")
            measure_names = [value for value in payload.get("measures", []) if isinstance(value, str)] if isinstance(payload, dict) else []
            matches.append(dict(record_id=pk, dataset_id=dataset, section=section, external_id=external_id,
                                name=name, terms=terms, classifications=labels, instrument_name_leads=measure_names))
        return dict(datasets=[dict(id=pk, key=key, sha256=digest, active=bool(active)) for pk,key,digest,active in datasets],
                    record_count=len(rows), matched_record_count=len(matches),
                    classification_counts=dict(sorted(Counter(label for row in matches for label in row["classifications"]).items())),
                    labels={"A": "Instrument-name lead only; no canonical promotion", "B": "Exact version/form lead",
                            "C": "Measurement-evidence lead; context still unverified", "D": "Bibliographic/source record",
                            "E": "Incidental mention", "F": "Rights-sensitive lead", "G": "Explicit research gap",
                            "H": "Unsupported/weak lead"},
                    distinct_measure_names=sorted({value for row in matches for value in row["instrument_name_leads"]}),
                    canonical_promotions=0, matches=matches)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("output")
    args = parser.parse_args()
    report = inspect(args.database)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key,value in report.items() if key not in {"matches", "datasets", "labels", "distinct_measure_names"}}))
