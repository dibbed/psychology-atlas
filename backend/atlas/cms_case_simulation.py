"""Private, write-free CaseRevision path simulation.

Never constructs CaseAttempt, CaseAttemptEvent, CaseAttemptAnswer, StudyActivity
or any public mastery/progress record. The resulting feedback is educational.
"""
from rest_framework.response import Response

from .case_graph import validate_case_revision_graph
from .cms_policy import CMSFailure, policy_lock, require
from .cms_views import AdminAPIView, payload
from .models import CaseChoice, CaseQuestion, CaseRevision, CaseStep, CaseTransition


class CaseRevisionSimulationView(AdminAPIView):
    capability = "cms_cases_preview"

    def post(self, request, case_id, revision_id):
        data = payload(request, {"choice_ids"})
        choices = data.get("choice_ids")
        if type(choices) is not list or len(choices) > 200 or any(
            type(value) is not int or value <= 0 for value in choices
        ):
            raise CMSFailure("INVALID_SIMULATION", 400)
        with policy_lock():
            require(request.user, "cms_cases_view")
            revision = CaseRevision.objects.filter(
                case_id=case_id, pk=revision_id,
            ).first()
            if revision is None:
                raise CMSFailure("NOT_FOUND", 404)
            if (revision.steps.count() > 200 or revision.transitions.count() > 2000
                    or CaseQuestion.objects.filter(step__revision=revision).count() > 800
                    or CaseChoice.objects.filter(question__step__revision=revision).count() > 2000
                    or revision.scoring_dimensions.count() > 50):
                raise CMSFailure("PREVIEW_LIMIT", 400)
            if validate_case_revision_graph(revision):
                raise CMSFailure("INVALID_REVISION_GRAPH", 409)
            step_id = revision.entry_step_id
            trace = []
            consumed = 0
            score = 0
            max_score = 0
            completed = False
            for _ in range(201):
                step = CaseStep.objects.filter(
                    pk=step_id, case_id=case_id, revision=revision, is_active=True,
                ).first()
                if step is None:
                    raise CMSFailure("INVALID_REVISION_GRAPH", 409)
                event = {
                    "step_id": step.id, "title": step.title, "kind": step.node_kind,
                    "selected_choice_id": None, "feedback": "",
                    "awarded_score": 0, "max_score": 0,
                }
                if step.node_kind == CaseStep.NodeKind.TERMINAL:
                    event["outcome"] = "complete"
                    trace.append(event)
                    completed = True
                    break
                if step.node_kind == CaseStep.NodeKind.DECISION:
                    question = step.questions.filter(is_active=True).first()
                    if question is None or consumed >= len(choices):
                        raise CMSFailure("SIMULATION_CHOICE_REQUIRED", 400)
                    choice = question.choices.filter(pk=choices[consumed], is_active=True).first()
                    if choice is None:
                        raise CMSFailure("SIMULATION_INVALID_CHOICE", 400)
                    consumed += 1
                    transition = CaseTransition.objects.filter(
                        revision=revision, source_step=step,
                        choice=choice, is_active=True,
                    ).first()
                    event["selected_choice_id"] = choice.id
                    event["feedback"] = choice.feedback
                    event["awarded_score"] = choice.score_value
                    event["max_score"] = max(
                        question.choices.filter(is_active=True).values_list("score_value", flat=True),
                        default=0,
                    )
                    score += event["awarded_score"]
                    max_score += event["max_score"]
                else:
                    transition = CaseTransition.objects.filter(
                        revision=revision, source_step=step,
                        choice__isnull=True, is_active=True,
                    ).first()
                if transition is None:
                    raise CMSFailure("INVALID_REVISION_GRAPH", 409)
                event["outcome"] = transition.outcome
                trace.append(event)
                if transition.outcome == CaseTransition.Outcome.COMPLETE:
                    completed = True
                    break
                step_id = transition.target_step_id
            if not completed:
                raise CMSFailure("SIMULATION_LIMIT", 400)
            if consumed != len(choices):
                raise CMSFailure("SIMULATION_UNUSED_CHOICES", 400)
            return Response({
                "scope": "private_case_revision_simulation", "case_id": case_id,
                "revision_id": revision_id, "preview_only": True,
                "completed": True, "trace": trace,
                "awarded_score": score, "max_score": max_score,
                "learner_activity_created": False,
                "notice": "SYNTHETIC_PREVIEW_NOT_ASSESSMENT_OR_LEARNER_EVIDENCE",
            })
