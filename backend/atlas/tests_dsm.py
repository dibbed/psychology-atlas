import json
import tempfile
from pathlib import Path

from django.test import TestCase

from .dsm_import import _link_existing_disorders, _rebuild_record_relations, import_master_json
from .models import Category, DSMCorpus, DSMRecord, Disorder, DisorderSource


def master_profile(master_id, name_fa, name_en, status, *, chapter=None, chapter_en=None):
    return {
        "شناسه": master_id,
        "نام_فارسی": name_fa,
        "نام_انگلیسی": name_en,
        "وضعیت_طبقه‌بندی": status,
        "مسیر_ساختاری": {
            "ریشه": "فصل‌های_اختلال",
            "فصل": chapter,
            "فصل_انگلیسی": chapter_en,
            "گروه": "گروه آزمایشی",
        },
        "سطح_اختصاصی‌سازی": "رکورد-اختصاصی",
        "خلاصه_مفهومی_بازبینی‌شده": f"خلاصه {name_fa}",
        "ویژگی‌های_کلیدی_آموزشی": ["ویژگی کلیدی"],
        "ارزیابی_هدفمند": ["ارزیابی هدفمند"],
        "افتراق_تشخیصی_هدفمند": [{"عنوان": "افتراق", "نقطه_افتراق": "توضیح"}],
        "همبودی_و_همپوشانی": "همپوشانی آموزشی",
        "سیر_و_پیش‌آگهی_آموزشی": "سیر آموزشی",
        "مدیریت_و_درمان_کلی_آموزشی": ["مدیریت کلی"],
        "ابزارهای_سنجش_نمونه": ["ابزار نمونه"],
        "ملاحظات_فرهنگی_رشدی_و_زمینه‌ای": "زمینه فرهنگی",
        "پرچم‌های_قرمز_و_ایمنی": "هشدار ایمنی",
        "دام‌های_رایج_در_مطالعه_یا_تشخیص": ["دام رایج"],
        "عناوین_نزدیک_یا_ارجاعات": ["عنوان نزدیک"],
        "به‌روزرسانی‌های_رسمی_مرتبط": [],
        "هم‌نامی_یا_تکرار_ساختاری": {"تکراری": False},
        "شیوع_عددی": None,
        "سیاست_شیوع": "فقط با منبع",
        "کدگذاری": "نیازمند منبع جاری",
        "منابع_پایه": ["APA_UPDATES"],
        "کیفیت_و_محدودیت": {"ماهیت": "آموزشی"},
        "نکته_امتحانی_کلیدی": "نکته امتحانی",
        "سؤال‌های_خودآزمایی_پیشرفته": ["سؤال خودآزمایی؟"],
    }


class DSMMasterImportTests(TestCase):
    def setUp(self):
        category = Category.objects.create(
            slug="test-chapter",
            name_en="Test Chapter",
            name_fa="فصل آزمایشی",
            is_active=True,
        )
        self.disorder = Disorder.objects.create(
            category=category,
            slug="test-disorder",
            name_en="Test Disorder",
            name_fa="اختلال آزمایشی",
            is_active=True,
        )
        chapter_id = "DSM5TR-FA-M0001"
        disorder_id = "DSM5TR-FA-M0002"
        document = {
            "عنوان": "MASTER آزمایشی",
            "زبان": "فارسی",
            "هدف": "آزمون import",
            "محدودیت_حق_نشر": "آموزشی",
            "نکته_بالینی": "ابزار تشخیص نیست",
            "نسخه_MASTER": {"نام": "MASTER test", "تاریخ_ساخت": "2026-08-29"},
            "وضعیت_رسمی_بررسی_شده_تا_2026_08_29": {"وضعیت": "test"},
            "ثبت_منابع_MASTER": {
                "APA_UPDATES": {
                    "عنوان": "APA Updates Test",
                    "نشانی": "https://example.com/apa",
                    "کاربرد": "منبع تست",
                }
            },
            "نمایه_MASTER": {"براساس_شناسه": {disorder_id: "اختلال آزمایشی"}},
            "آمار_MASTER": {"تعداد_گره‌های_آدرس‌پذیر_دارای_پروفایل_MASTER": 2},
            "ممیزی_کیفیت_MASTER": {"نتیجه": "test"},
            "راهنمای_مطالعه_مرحله‌ای": ["مرحله یک"],
            "راهنمای_هشدارهای_فوری": {"هدف": "آموزشی"},
            "یادداشت_فرهنگی_و_زمینه‌ای": "زمینه مهم است",
            "موارد_نیازمند_بازبینی_دوره‌ای_MASTER": [{"موضوع": "کدگذاری"}],
            "ثبت_به‌روزرسانی‌های_سپتامبر_2025_MASTER": {"منبع": "APA_UPDATES"},
            "تست_سلامت_MASTER": {"JSON_قابل_بارگذاری": True, "تعداد_پروفایل": 2, "نتیجه": "PASS"},
            "واژه‌نامه_مطالعاتی": {"نمونه": "این داده باید در raw document بماند"},
            "فصل‌های_اختلال": [
                {
                    "شماره": 1,
                    "نام_فارسی": "فصل آزمایشی",
                    "نام_انگلیسی": "Test Chapter",
                    "شناسه_MASTER": chapter_id,
                    "پروفایل_آموزشی_پیشرفته_MASTER": master_profile(
                        chapter_id,
                        "فصل آزمایشی",
                        "Test Chapter",
                        "عنوان/ساختار/رکورد تاریخی؛ تشخیص مستقل تلقی نشود",
                        chapter="فصل آزمایشی",
                        chapter_en="Test Chapter",
                    ),
                    "گروه‌ها": [
                        {
                            "نام": "گروه آزمایشی",
                            "موارد": [
                                {
                                    "نام_فارسی": "اختلال آزمایشی",
                                    "نام_انگلیسی": "Test Disorder",
                                    "نوع": "تشخیص رسمی",
                                    "یادداشت_اختصاصی": "این فیلد خام باید حفظ شود",
                                    "شناسه_MASTER": disorder_id,
                                    "پروفایل_آموزشی_پیشرفته_MASTER": master_profile(
                                        disorder_id,
                                        "اختلال آزمایشی",
                                        "Test Disorder",
                                        "تشخیص رسمی در بخش مربوط",
                                        chapter="فصل آزمایشی",
                                        chapter_en="Test Chapter",
                                    ),
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False)
        json.dump(document, handle, ensure_ascii=False)
        handle.close()
        self.json_path = Path(handle.name)
        self.addCleanup(lambda: self.json_path.unlink(missing_ok=True))

    def test_import_is_idempotent_preserves_raw_data_and_links_atlas(self):
        first = import_master_json(self.json_path)
        second = import_master_json(self.json_path)

        self.assertEqual(first["records"], 2)
        self.assertEqual(second["records"], 2)
        self.assertEqual(second["linked_disorders"], 1)
        self.assertEqual(DSMCorpus.objects.count(), 1)
        self.assertEqual(DSMRecord.objects.count(), 2)

        corpus = DSMCorpus.objects.get()
        self.assertEqual(
            corpus.raw_document["واژه‌نامه_مطالعاتی"]["نمونه"],
            "این داده باید در raw document بماند",
        )
        record = DSMRecord.objects.get(master_id="DSM5TR-FA-M0002")
        self.assertEqual(record.display_type, DSMRecord.DisplayType.DIAGNOSIS)
        self.assertEqual(record.parent.master_id, "DSM5TR-FA-M0001")
        self.assertEqual(record.linked_disorder, self.disorder)
        self.assertEqual(record.source_payload["یادداشت_اختصاصی"], "این فیلد خام باید حفظ شود")
        self.assertTrue(DisorderSource.objects.filter(disorder=self.disorder).exists())

    def test_dsm_api_exposes_overview_search_detail_and_disorder_link(self):
        import_master_json(self.json_path)

        overview = self.client.get("/api/dsm/overview/")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["counts"]["records"], 2)
        self.assertEqual(overview.json()["counts"]["types"]["diagnosis"], 1)

        search = self.client.get("/api/dsm/records/?q=اختلال آزمایشی&type=diagnosis&page_size=100")
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["count"], 1)
        self.assertEqual(search.json()["results"][0]["master_id"], "DSM5TR-FA-M0002")

        detail = self.client.get("/api/dsm/records/DSM5TR-FA-M0002/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["assessment"][0], "ارزیابی هدفمند")
        self.assertEqual(detail.json()["sources"][0]["key"], "APA_UPDATES")
        self.assertEqual(detail.json()["source_payload"]["یادداشت_اختصاصی"], "این فیلد خام باید حفظ شود")

        linked = self.client.get("/api/dsm/records/by-disorder/test-disorder/")
        self.assertEqual(linked.status_code, 200)
        self.assertEqual(linked.json()["master_id"], "DSM5TR-FA-M0002")

    def test_import_creates_missing_formal_diagnoses_as_canonical_atlas_pages(self):
        document = json.loads(self.json_path.read_text(encoding="utf-8"))
        chapter = document["فصل‌های_اختلال"][0]
        items = chapter["گروه‌ها"][0]["موارد"]
        for master_id in ("DSM5TR-FA-M0003", "DSM5TR-FA-M0004"):
            items.append({
                "نام_فارسی": "اختلال عصبی رشدی آزمایشی",
                "نام_انگلیسی": "Test Neurodevelopmental Disorder",
                "نوع": "تشخیص رسمی",
                "شناسه_MASTER": master_id,
                "پروفایل_آموزشی_پیشرفته_MASTER": master_profile(
                    master_id,
                    "اختلال عصبی رشدی آزمایشی",
                    "Test Neurodevelopmental Disorder",
                    "تشخیص رسمی در بخش مربوط",
                    chapter="فصل آزمایشی",
                    chapter_en="Test Chapter",
                ),
            })
        document["آمار_MASTER"]["تعداد_گره‌های_آدرس‌پذیر_دارای_پروفایل_MASTER"] = 4
        document["تست_سلامت_MASTER"]["تعداد_پروفایل"] = 4
        self.json_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

        result = import_master_json(self.json_path)

        self.assertEqual(result["diagnosis_catalog"]["diagnosis_records"], 3)
        self.assertEqual(result["diagnosis_catalog"]["disorders"], 2)
        self.assertEqual(result["diagnosis_catalog"]["duplicate_records_collapsed"], 1)
        generated = Disorder.objects.get(name_en="Test Neurodevelopmental Disorder")
        self.assertEqual(generated.data_origin, Disorder.Origin.DSM_MASTER)
        self.assertEqual(generated.category.slug, "dsm-chapter-01")
        self.assertTrue(generated.name_fa)
        self.assertTrue(generated.short_description)
        self.assertEqual(
            DSMRecord.objects.filter(
                corpus__is_active=True,
                name_en="Test Neurodevelopmental Disorder",
                linked_disorder=generated,
            ).count(),
            1,
        )

    def test_duplicate_name_link_prefers_matching_atlas_category_chapter(self):
        import_master_json(self.json_path)
        corpus = DSMCorpus.objects.get(is_active=True)
        self.disorder.refresh_from_db()
        self.disorder.category.name_en = "Personality Disorders - Cluster A"
        self.disorder.category.save(update_fields=["name_en", "updated_at"])
        original = DSMRecord.objects.get(master_id="DSM5TR-FA-M0002")
        original.chapter_name_en = "Schizophrenia Spectrum and Other Psychotic Disorders"
        original.save(update_fields=["chapter_name_en", "updated_at"])
        preferred = DSMRecord.objects.create(
            corpus=corpus,
            master_id="DSM5TR-FA-M0999",
            sort_index=999,
            root_section="فصل‌های_اختلال",
            chapter_number=18,
            chapter_name_fa="اختلالات شخصیت",
            chapter_name_en="Personality Disorders",
            group_name="خوشه A",
            name_fa=self.disorder.name_fa,
            name_en=self.disorder.name_en,
            classification_status="تشخیص رسمی در بخش مربوط",
            display_type=DSMRecord.DisplayType.DIAGNOSIS,
            summary="preferred chapter match",
        )

        linked_count = _link_existing_disorders(corpus, {})
        self.assertEqual(linked_count, 1)
        original.refresh_from_db()
        preferred.refresh_from_db()
        self.assertIsNone(original.linked_disorder_id)
        self.assertEqual(preferred.linked_disorder_id, self.disorder.id)

    def test_resolved_relations_graph_and_study_kit_are_source_grounded(self):
        import_master_json(self.json_path)
        corpus = DSMCorpus.objects.get(is_active=True)
        record = DSMRecord.objects.get(master_id="DSM5TR-FA-M0002")
        record.nearby_titles = ["فصل آزمایشی"]
        record.save(update_fields=["nearby_titles", "updated_at"])
        counts = _rebuild_record_relations(corpus)
        self.assertEqual(counts["nearby"], 1)

        detail = self.client.get("/api/dsm/records/DSM5TR-FA-M0002/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["relations"][0]["record"]["master_id"], "DSM5TR-FA-M0001")

        graph = self.client.get("/api/dsm/graph/")
        self.assertEqual(graph.status_code, 200)
        self.assertEqual(graph.json()["meta"]["node_count"], 2)
        self.assertGreaterEqual(graph.json()["meta"]["relation_counts"]["hierarchy"], 1)
        self.assertEqual(graph.json()["meta"]["relation_counts"]["nearby"], 1)

        study = self.client.get("/api/dsm/study-kit/")
        self.assertEqual(study.status_code, 200)
        self.assertEqual(study.json()["stats"]["glossary_terms"], 1)
        self.assertEqual(study.json()["stats"]["self_test_questions"], 2)
