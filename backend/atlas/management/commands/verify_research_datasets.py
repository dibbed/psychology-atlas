import hashlib
import json

from django.core.management.base import BaseCommand, CommandError

from atlas.models import ResearchDataset, ResearchRecord


class Command(BaseCommand):
    help = "Verify archived research datasets without requiring the original JSON source files."

    def handle(self, *args, **options):
        datasets = list(ResearchDataset.objects.filter(is_active=True).order_by("id"))
        if not datasets:
            raise CommandError("No active ResearchDataset rows are available to verify.")

        failures = []
        total_records = 0
        for dataset in datasets:
            prefix = f"ResearchDataset {dataset.pk} ({dataset.source_filename})"
            if not dataset.raw_text:
                failures.append(f"{prefix}: raw_text is empty")
                continue

            raw_bytes = dataset.raw_text.encode("utf-8")
            digest = hashlib.sha256(raw_bytes).hexdigest()
            if digest != dataset.source_sha256:
                failures.append(
                    f"{prefix}: SHA-256 mismatch; expected {dataset.source_sha256}, got {digest}"
                )

            try:
                parsed = json.loads(dataset.raw_text)
            except json.JSONDecodeError as exc:
                failures.append(f"{prefix}: raw_text is not valid JSON: {exc}")
                parsed = None
            if parsed is not None and parsed != dataset.raw_document:
                failures.append(f"{prefix}: raw_text JSON and raw_document differ")

            audit = dataset.ingestion_audit or {}
            expected_records = audit.get("list_record_total")
            actual_records = dataset.records.count()
            total_records += actual_records
            if expected_records != actual_records:
                failures.append(
                    f"{prefix}: record count mismatch; audit={expected_records}, db={actual_records}"
                )

            bilingual_sections = audit.get("bilingual_educational_sections") or {}
            for section, section_audit in bilingual_sections.items():
                expected = int(section_audit.get("records") or 0)
                bilingual_names = int(section_audit.get("bilingual_name_records") or 0)
                if bilingual_names != expected:
                    failures.append(
                        f"{prefix}: {section} bilingual names {bilingual_names}/{expected}"
                    )
                if section_audit.get("content_pair_applicable"):
                    bilingual_content = int(section_audit.get("bilingual_content_records") or 0)
                    if bilingual_content != expected:
                        failures.append(
                            f"{prefix}: {section} bilingual content {bilingual_content}/{expected}"
                        )
                indexed = ResearchRecord.objects.filter(dataset=dataset, section=section)
                if indexed.count() != expected:
                    failures.append(
                        f"{prefix}: {section} indexed rows {indexed.count()}/{expected}"
                    )
                missing_en = indexed.filter(name_en="").count()
                missing_fa = indexed.filter(name_fa="").count()
                if missing_en or missing_fa:
                    failures.append(
                        f"{prefix}: {section} normalized names missing en={missing_en}, fa={missing_fa}"
                    )

            self.stdout.write(
                f"PASS {dataset.source_filename} · {actual_records} records · "
                f"{len(raw_bytes)} bytes · sha256={digest}"
            )

        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(f"FAIL {failure}"))
            raise CommandError(f"Research dataset verification failed with {len(failures)} issue(s).")

        self.stdout.write(
            self.style.SUCCESS(
                f"Research dataset verification PASS · {len(datasets)} datasets · {total_records} records"
            )
        )
