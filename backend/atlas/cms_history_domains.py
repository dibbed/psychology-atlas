"""P09 explicitly authorable historical/person/theory/timeline fields.

All history proposals are private. Attribution and scientific chronology can be
suggested but cannot rewrite canonical/public records before P16.
"""
from . import models as atlas

FIELDS = {
 "psychologist": (atlas.Psychologist, "روان‌شناس", ("slug","name_en","name_fa","summary_en","summary_fa","role_en","role_fa","nationality_en","nationality_fa","birth_year","death_year","academic_disciplines","contributions_en","contributions_fa","affiliations","historical_context_en","historical_context_fa")),
 "psychologist-alias": (atlas.PsychologistAlias, "نام جایگزین روان‌شناس", ("psychologist","text","language","alias_type")),
 "psychologist-source": (atlas.PsychologistSource, "منبع زندگی‌نامه", ("psychologist","source","role","note")),
 "psychologist-theory": (atlas.PsychologistTheory, "انتساب روان‌شناس به نظریه", ("psychologist","theory","relationship_type","explanation_en","explanation_fa","sort_order")),
 "psychologist-theory-source": (atlas.PsychologistTheorySource, "منبع انتساب نظریه", ("relationship","source","note")),
 "psychologist-concept": (atlas.PsychologistConcept, "انتساب روان‌شناس به مفهوم", ("psychologist","concept","relationship_type","explanation_en","explanation_fa","sort_order")),
 "psychologist-concept-source": (atlas.PsychologistConceptSource, "منبع انتساب مفهوم", ("relationship","source","note")),
 "psychologist-therapy": (atlas.PsychologistTherapy, "انتساب روان‌شناس به درمان", ("psychologist","therapy","relationship_type","explanation_en","explanation_fa","sort_order")),
 "psychologist-therapy-source": (atlas.PsychologistTherapySource, "منبع انتساب درمان", ("relationship","source","note")),
 "psychologist-psychologist": (atlas.PsychologistPsychologist, "رابطهٔ جهت‌دار روان‌شناسان", ("psychologist","related_psychologist","relationship_type","explanation_en","explanation_fa","sort_order")),
 "psychologist-psychologist-source": (atlas.PsychologistPsychologistSource, "منبع رابطهٔ روان‌شناسان", ("relationship","source","note")),
 "theory": (atlas.Theory, "نظریه", ("slug","name_en","name_fa","domain","period_text","summary_en","summary_fa","core_proposition_en","core_proposition_fa","historical_context_en","historical_context_fa","key_propositions_en","key_propositions_fa","applications_en","applications_fa","criticisms_en","criticisms_fa","limitations_en","limitations_fa","modern_status","historical_importance_en","historical_importance_fa")),
 "theory-alias": (atlas.TheoryAlias, "نام جایگزین نظریه", ("theory","text","language","alias_type")),
 "theory-source": (atlas.TheorySource, "منبع نظریه", ("theory","source","role","note")),
 "theory-concept": (atlas.TheoryConcept, "رابطهٔ نظریه و مفهوم", ("theory","concept","relationship_type","explanation_en","explanation_fa","sort_order")),
 "theory-concept-source": (atlas.TheoryConceptSource, "منبع رابطهٔ نظریه و مفهوم", ("relationship","source","note")),
 "theory-therapy": (atlas.TheoryTherapy, "رابطهٔ نظریه و درمان", ("theory","therapy","relationship_type","explanation_en","explanation_fa","sort_order")),
 "theory-therapy-source": (atlas.TheoryTherapySource, "منبع رابطهٔ نظریه و درمان", ("relationship","source","note")),
 "theory-technique": (atlas.TheoryTechnique, "رابطهٔ نظریه و تکنیک", ("theory","technique","relationship_type","explanation_en","explanation_fa","sort_order")),
 "theory-technique-source": (atlas.TheoryTechniqueSource, "منبع رابطهٔ نظریه و تکنیک", ("relationship","source","note")),
 "theory-theory": (atlas.TheoryTheory, "رابطهٔ جهت‌دار نظریه‌ها", ("theory","related_theory","relationship_type","explanation_en","explanation_fa","sort_order")),
 "theory-theory-source": (atlas.TheoryTheorySource, "منبع رابطهٔ نظریه‌ها", ("relationship","source","note")),
 "timeline-event": (atlas.TimelineEvent, "رویداد تاریخ روان‌شناسی", ("slug","title_en","title_fa","description_en","description_fa","historical_importance_en","historical_importance_fa","event_type","category","date_precision","date_text","year_start","year_end","exact_date")),
 "timeline-event-source": (atlas.TimelineEventSource, "منبع رویداد تاریخی", ("event","source","role","note")),
 "timeline-psychologist": (atlas.TimelinePsychologist, "رابطهٔ رویداد و روان‌شناس", ("event","psychologist","role","explanation_en","explanation_fa","sort_order")),
 "timeline-psychologist-source": (atlas.TimelinePsychologistSource, "منبع رابطهٔ رویداد و روان‌شناس", ("relationship","source","note")),
 "timeline-theory": (atlas.TimelineTheory, "رابطهٔ رویداد و نظریه", ("event","theory","role","explanation_en","explanation_fa","sort_order")),
 "timeline-theory-source": (atlas.TimelineTheorySource, "منبع رابطهٔ رویداد و نظریه", ("relationship","source","note")),
 "timeline-therapy": (atlas.TimelineTherapy, "رابطهٔ رویداد و درمان", ("event","therapy","role","explanation_en","explanation_fa","sort_order")),
 "timeline-therapy-source": (atlas.TimelineTherapySource, "منبع رابطهٔ رویداد و درمان", ("relationship","source","note")),
 "timeline-technique": (atlas.TimelineTechnique, "رابطهٔ رویداد و تکنیک", ("event","technique","role","explanation_en","explanation_fa","sort_order")),
 "timeline-technique-source": (atlas.TimelineTechniqueSource, "منبع رابطهٔ رویداد و تکنیک", ("relationship","source","note")),
 "timeline-concept": (atlas.TimelineConcept, "رابطهٔ رویداد و مفهوم", ("event","concept","role","explanation_en","explanation_fa","sort_order")),
 "timeline-concept-source": (atlas.TimelineConceptSource, "منبع رابطهٔ رویداد و مفهوم", ("relationship","source","note")),
}
SOURCE_LINKS = {
 atlas.Psychologist: ((atlas.PsychologistSource,"psychologist"),),
 atlas.Theory: ((atlas.TheorySource,"theory"),),
 atlas.TimelineEvent: ((atlas.TimelineEventSource,"event"),),
 atlas.PsychologistTheory: ((atlas.PsychologistTheorySource,"relationship"),),
 atlas.PsychologistConcept: ((atlas.PsychologistConceptSource,"relationship"),),
 atlas.PsychologistTherapy: ((atlas.PsychologistTherapySource,"relationship"),),
 atlas.PsychologistPsychologist: ((atlas.PsychologistPsychologistSource,"relationship"),),
 atlas.TheoryConcept: ((atlas.TheoryConceptSource,"relationship"),),
 atlas.TheoryTherapy: ((atlas.TheoryTherapySource,"relationship"),),
 atlas.TheoryTechnique: ((atlas.TheoryTechniqueSource,"relationship"),),
 atlas.TheoryTheory: ((atlas.TheoryTheorySource,"relationship"),),
 atlas.TimelinePsychologist: ((atlas.TimelinePsychologistSource,"relationship"),),
 atlas.TimelineTheory: ((atlas.TimelineTheorySource,"relationship"),),
 atlas.TimelineTherapy: ((atlas.TimelineTherapySource,"relationship"),),
 atlas.TimelineTechnique: ((atlas.TimelineTechniqueSource,"relationship"),),
 atlas.TimelineConcept: ((atlas.TimelineConceptSource,"relationship"),),
}

def build_specs():
    # Avoid a module-import cycle: cms_domains imports this module's spec builder.
    from .cms_domains import ProposalSerializer, _spec
    result={}
    for kind,(model,label,fields) in FIELDS.items():
        meta=type("Meta",(),{"model":model,"fields":fields})
        serializer=type(model.__name__+"CMSProposal",(ProposalSerializer,),{"Meta":meta})
        spec=_spec(serializer,label)
        spec["domain"]="history"
        result[kind]=spec
    return result
