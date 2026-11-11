"""P20 collection-route authorization sweep; synthetic sessions and empty test DB only."""
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings

from .cms_content import REGISTRY, capability
from .cms_governance import REGISTRY as GOVERNANCE_REGISTRY
from .cms_content_models import ContentState
from .cms_domains import domain_for
from .tests_v100_p01 import SecurityFixture

BASE = "/api/admin/"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RegistryRouteAuthorizationTests(SecurityFixture, TestCase):
    def test_owner_collections_are_routed_and_viewed_for_every_registered_kind(self):
        owner_client = self.sign_in(self.owner)
        schema = owner_client.get(BASE + "content/schema/")
        self.assertEqual(schema.status_code, 200, schema.content[:450])
        kinds = {item["kind"] for item in schema.json()["kinds"]}
        self.assertEqual(kinds, set(REGISTRY))
        self.assertEqual(len(kinds), 90)
        for kind in sorted(REGISTRY):
            with self.subTest(kind=kind):
                response = owner_client.get(BASE + f"content/{kind}/")
                self.assertEqual(response.status_code, 200, response.content[:320])
                self.assertIn("results", response.json())

    def test_unprivileged_cms_session_cannot_enumerate_any_of_the_90_collections(self):
        actor = self.user("p20-no-domain-view", staff=True, caps=("cms_enter", "cms_catalog"))
        client = self.sign_in(actor)
        schema = client.get(BASE + "content/schema/")
        self.assertEqual(schema.status_code, 200, schema.content[:400])
        self.assertEqual(schema.json()["kinds"], [])
        for kind in sorted(REGISTRY):
            with self.subTest(kind=kind):
                response = client.get(BASE + f"content/{kind}/")
                self.assertEqual(response.status_code, 403, response.content[:400])
                self.assertEqual(response.json()["code"], "PERMISSION_DENIED")

    def test_domain_visibility_is_current_and_restricted_without_relogin(self):
        actor = self.user("p20-therapy-only", staff=True,
                          caps=("cms_enter", "cms_catalog", "cms_therapy_view"))
        client = self.sign_in(actor)
        schema = client.get(BASE + "content/schema/")
        self.assertEqual(schema.status_code, 200, schema.content[:400])
        kinds = {row["kind"] for row in schema.json()["kinds"]}
        expected = {kind for kind in REGISTRY if domain_for(kind) == "therapy"}
        self.assertTrue(expected)
        self.assertEqual(kinds, expected)
        for kind in sorted(REGISTRY):
            with self.subTest(kind=kind):
                result = client.get(BASE + f"content/{kind}/")
                self.assertEqual(result.status_code, 200 if kind in expected else 403,
                                 result.content[:400])
        Permission.objects.filter(
            content_type__app_label="atlas",
            content_type__model="rolepolicy",
            codename="cms_therapy_view",
        ).first().user_set.remove(actor)
        self.assertEqual(client.get(BASE + "content/schema/").json()["kinds"], [])
        denied = client.get(BASE + "content/therapy/")
        self.assertEqual(denied.status_code, 403, denied.content[:400])
        self.assertEqual(denied.json()["code"], "PERMISSION_DENIED")

    def test_all_governance_resource_selectors_respect_view_capability(self):
        self.assertEqual(len(GOVERNANCE_REGISTRY), 94)
        owner_client = self.sign_in(self.owner)
        no_domains = self.user("p20-governance-denied", staff=True,
                               caps=("cms_enter", "cms_catalog"))
        denied_client = self.sign_in(no_domains)
        for resource_type in sorted(GOVERNANCE_REGISTRY):
            with self.subTest(resource_type=resource_type):
                url = BASE + f"governance/resources/?resource_type={resource_type}"
                ok = owner_client.get(url)
                self.assertEqual(ok.status_code, 200, ok.content[:400])
                self.assertIn("results", ok.json())
                denied = denied_client.get(url)
                self.assertEqual(denied.status_code, 404, denied.content[:400])
                self.assertEqual(denied.json()["code"], "NOT_FOUND")

    def test_governance_resource_domain_scope_and_live_revocation(self):
        actor = self.user("p20-therapy-resource-only", staff=True,
                          caps=("cms_enter", "cms_catalog", "cms_therapy_view"))
        client = self.sign_in(actor)
        allowed_types = {resource_type for resource_type, spec in GOVERNANCE_REGISTRY.items()
                         if spec[1] == "therapy"}
        self.assertTrue(allowed_types)
        for resource_type in sorted(GOVERNANCE_REGISTRY):
            with self.subTest(resource_type=resource_type):
                url = BASE + f"governance/resources/?resource_type={resource_type}"
                response = client.get(url)
                self.assertEqual(response.status_code,
                                 200 if resource_type in allowed_types else 404,
                                 response.content[:320])
                if response.status_code == 200:
                    self.assertEqual(
                        {row["resource_type"] for row in response.json()["resource_types"]},
                        allowed_types,
                    )
        actor.user_permissions.remove(*actor.user_permissions.filter(
            codename="cms_therapy_view",
            content_type__app_label="atlas",
            content_type__model="rolepolicy",
        ))
        now_denied = client.get(BASE + "governance/resources/?resource_type=therapy")
        self.assertEqual(now_denied.status_code, 404, now_denied.content[:350])

    def test_owner_invalid_drafts_for_all_90_kinds_fail_before_database_mutation(self):
        # Route/capability READY must not silently accept unrecognized payloads
        # just because the caller is a CMS owner.
        from .cms_content_models import ContentRevision
        owner_client = self.sign_in(self.owner)
        self.assertEqual(len(REGISTRY), 90)
        for kind in sorted(REGISTRY):
            with self.subTest(kind=kind):
                response = self.post(owner_client, f"content/{kind}/", {
                    "payload": {"__p20_unknown_column__": "NEVER INSERT"},
                })
                self.assertEqual(response.status_code, 400, response.content[:450])
                self.assertEqual(response.json()["code"], "INVALID_FIELDS")
        self.assertEqual(ContentState.objects.count(), 0)
        self.assertEqual(ContentRevision.objects.count(), 0)

    def test_no_domain_create_grant_is_not_a_write_authorization(self):
        actor = self.user("p20-nonwriting", staff=True,
                          caps=("cms_enter", "cms_catalog", "cms_therapy_view"))
        client = self.sign_in(actor)
        for kind in sorted(REGISTRY):
            with self.subTest(kind=kind):
                # Even a malformed draft must be stopped at the permission boundary.
                response = self.post(client, f"content/{kind}/",
                                     {"payload": {"name_en": "NO INSERT"}},)
                self.assertEqual(response.status_code, 403, response.content[:400])
                self.assertEqual(response.json()["code"], "PERMISSION_DENIED")
        self.assertEqual(ContentState.objects.count(), 0)
