import re

from django.db.models import Case, Exists, IntegerField, OuterRef, Prefetch, Q, Value, When
from rest_framework import generics
from rest_framework.exceptions import ValidationError

from . import models
from .brain_publication import NESTED_LIMIT, NONBLANK_PATTERN, URL_PATTERN, public_anatomy, resolved_sources
from .brain_serializers import BrainAnatomyDetailSerializer, BrainAnatomyListSerializer
from .pagination import AtlasPagination
from .search_utils import icontains_any, search_variants


def anatomy_queryset():
    return public_anatomy().prefetch_related(
        Prefetch("aliases", queryset=valid_aliases().order_by("language", "text", "pk")[:NESTED_LIMIT + 1],
                 to_attr="public_aliases"),
        Prefetch("source_links", queryset=models.BrainAnatomicalEntitySource.objects.filter(
            source__in=resolved_sources(),
        ).select_related("source").order_by("source_id", "pk")[:NESTED_LIMIT + 1], to_attr="public_sources"),
    )


def valid_aliases():
    return models.BrainAnatomicalAlias.objects.filter(
        language__in=models.BrainAnatomicalAlias.Language.values,
        alias_type__in=models.BrainAnatomicalAlias.AliasType.values, text__regex=NONBLANK_PATTERN,
        review_status="reviewed", source__in=resolved_sources(), source_note__regex=NONBLANK_PATTERN,
    ).select_related("source")


class BrainAnatomyListView(generics.ListAPIView):
    serializer_class = BrainAnatomyListSerializer
    pagination_class = AtlasPagination

    def get_queryset(self):
        params = self.request.query_params
        allowed = {"q", "kind", "laterality", "parent", "page", "page_size", "format"}
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise ValidationError({key: "Unsupported Brain filter." for key in unknown})
        if any(len(params.getlist(key)) != 1 for key in params):
            raise ValidationError("Brain query parameters must have one value each.")
        qs = anatomy_queryset()
        for key, choices in (("kind", models.BrainAnatomicalEntity.Kind.values),
                             ("laterality", models.BrainAnatomicalEntity.Laterality.values)):
            value = params.get(key, "").strip()
            if key in params and value not in choices:
                raise ValidationError({key: "Invalid Brain filter value."})
            if value:
                qs = qs.filter(**{key: value})
        if "parent" in params:
            parent = params["parent"].strip()
            if not re.fullmatch(r"[a-z0-9_-]{1,180}", parent) or not public_anatomy().filter(slug=parent).exists():
                raise ValidationError({"parent": "Unknown public parent slug."})
            qs = qs.filter(parent_links__parent__slug=parent, parent_links__is_active=True,
                           parent_links__review_status=models.ScientificReviewStatus.REVIEWED)
        q = params.get("q", "").strip()
        if len(q) > 255:
            raise ValidationError({"q": "Search text must be at most 255 characters."})
        if q:
            aliases = valid_aliases().filter(entity_id=OuterRef("pk"))
            qs = qs.filter(icontains_any(("name_en", "name_fa", "slug"), q) | Exists(aliases.filter(icontains_any(("text",), q))))
            exact = Q()
            exact_alias = Q()
            for variant in search_variants(q):
                for field in ("name_en", "name_fa", "slug"):
                    exact |= Q(**{f"{field}__iexact": variant})
                exact_alias |= Q(text__iexact=variant)
            qs = qs.annotate(search_rank=Case(When(exact | Exists(aliases.filter(exact_alias)), then=Value(0)),
                                            default=Value(1), output_field=IntegerField()))
            return qs.distinct().order_by("search_rank", "name_en", "id")
        return qs.distinct().order_by("name_en", "id")


class BrainAnatomyDetailView(generics.RetrieveAPIView):
    serializer_class = BrainAnatomyDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        relation_sources = models.BrainHierarchyLinkSource.objects.filter(
            source__in=resolved_sources(), note__regex=NONBLANK_PATTERN,
        ).select_related("source").order_by("source_id", "pk")
        links = models.BrainHierarchyLink.objects.filter(
            is_active=True, review_status=models.ScientificReviewStatus.REVIEWED,
            child__in=public_anatomy(), parent__in=public_anatomy(),
        ).select_related("child", "parent").prefetch_related(
            Prefetch("source_links", queryset=relation_sources[:NESTED_LIMIT + 1], to_attr="public_sources"),
        )
        memberships = supported_relations(models.BrainNetworkMembership).filter(
            network__in=models.BrainNetwork.objects.filter(is_active=True, review_status="reviewed",
                                                          source_links__source__in=resolved_sources()),
        ).select_related("network")
        associations = supported_relations(models.BrainFunctionalAssociation).filter(
            network__isnull=True, concept__is_active=True,
        ).select_related("concept")
        return anatomy_queryset().prefetch_related(
            Prefetch("parent_links", queryset=links.order_by("pk")[:1], to_attr="public_parents"),
            Prefetch("child_links", queryset=links.order_by("child__name_en", "child_id", "pk")[:NESTED_LIMIT + 1], to_attr="public_children"),
            Prefetch("external_identifiers", queryset=models.BrainExternalIdentifier.objects.filter(
                review_status=models.ScientificReviewStatus.REVIEWED, source__in=resolved_sources(),
                source_note__regex=NONBLANK_PATTERN, namespace__regex=NONBLANK_PATTERN,
                identifier__regex=NONBLANK_PATTERN, source_version__regex=NONBLANK_PATTERN,
            ).filter(Q(url="") | Q(url__regex=URL_PATTERN)).select_related("source")
                     .order_by("namespace", "source_version", "identifier", "pk")[:NESTED_LIMIT + 1], to_attr="public_identifiers"),
            Prefetch("network_memberships", queryset=memberships[:NESTED_LIMIT + 1], to_attr="public_memberships"),
            Prefetch("functional_associations", queryset=associations[:NESTED_LIMIT + 1], to_attr="public_associations"),
        )


def supported_relations(model):
    source_model = model._meta.get_field("source_links").related_model
    qs = model.objects.filter(is_active=True, review_status="reviewed", evidence_key__regex=r"^[a-z0-9_-]+$").filter(
        Exists(source_model.objects.filter(relationship_id=OuterRef("pk"), source__in=resolved_sources(), note__regex=NONBLANK_PATTERN)),
    )
    for field in model.required_context:
        qs = qs.filter(**{f"{field}__regex": NONBLANK_PATTERN})
    return qs.order_by("sort_order", "evidence_key", "pk").prefetch_related(
        Prefetch("source_links", queryset=source_model.objects.filter(source__in=resolved_sources(), note__regex=NONBLANK_PATTERN)
                 .select_related("source").order_by("source_id", "pk")[:NESTED_LIMIT + 1], to_attr="public_sources"),
    )
