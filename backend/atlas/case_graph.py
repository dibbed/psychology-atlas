import hashlib
import json
from collections import defaultdict

from .models import CaseRevision, CaseStep, CaseTransition


def case_seed_hash(case_data):
    payload = {
        "title": case_data["title"],
        "summary": case_data["summary"],
        "objective": case_data["objective"],
        "disorder": case_data["disorder"],
        "difficulty": case_data["difficulty"],
        "rubric_version": case_data.get("rubric_version", 0),
        "dimensions": case_data.get("dimensions", []),
        "dimension_definitions": case_data.get("dimension_definitions", []),
        "step_dimensions": case_data.get("step_dimensions", []),
        "steps": case_data["steps"],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_case_revision_graph(revision: CaseRevision):
    issues = []
    steps = list(
        revision.steps.filter(is_active=True)
        .prefetch_related("questions__choices", "questions__scoring_dimension")
        .order_by("sort_order", "id")
    )
    step_by_id = {step.id: step for step in steps}
    if not steps:
        return ["revision_has_no_active_steps"]
    if not revision.entry_step_id:
        issues.append("entry_step_missing")
    elif revision.entry_step_id not in step_by_id:
        issues.append("entry_step_not_active_or_foreign")

    active_dimensions = list(revision.scoring_dimensions.filter(is_active=True).order_by("sort_order", "id"))
    active_dimension_ids = {dimension.id for dimension in active_dimensions}
    if revision.rubric_version >= 1 and not active_dimensions:
        issues.append("rubric_has_no_active_dimensions")
    if revision.rubric_version == 0 and active_dimensions:
        issues.append("legacy_rubric_has_active_dimensions")
    for dimension in active_dimensions:
        if not dimension.stable_key:
            issues.append(f"dimension:{dimension.id}:stable_key_missing")
        if not dimension.label.strip():
            issues.append(f"dimension:{dimension.id}:label_missing")

    used_dimension_ids = set()
    for step in steps:
        if step.case_id != revision.case_id:
            issues.append(f"step:{step.id}:case_mismatch")
        if step.revision_id != revision.id:
            issues.append(f"step:{step.id}:revision_mismatch")
        if not step.stable_key:
            issues.append(f"step:{step.id}:stable_key_missing")

    transitions = list(revision.transitions.filter(is_active=True).select_related("source_step", "target_step", "choice__question__step").order_by("source_step__sort_order", "sort_order", "id"))
    transitions_by_source = defaultdict(list)
    transitions_by_choice = defaultdict(list)
    adjacency = defaultdict(list)
    completion_edges = set()
    for transition in transitions:
        transitions_by_source[transition.source_step_id].append(transition)
        if transition.choice_id:
            transitions_by_choice[transition.choice_id].append(transition)
        if transition.source_step_id not in step_by_id:
            issues.append(f"transition:{transition.id}:source_not_active_or_foreign")
            continue
        if transition.choice_id:
            if transition.choice.question.step_id != transition.source_step_id:
                issues.append(f"transition:{transition.id}:choice_source_mismatch")
            if not transition.choice.is_active:
                issues.append(f"transition:{transition.id}:choice_inactive")
            if not transition.choice.question.is_active:
                issues.append(f"transition:{transition.id}:question_inactive")
        if transition.outcome == CaseTransition.Outcome.CONTINUE:
            if not transition.target_step_id:
                issues.append(f"transition:{transition.id}:continue_without_target")
            elif transition.target_step_id not in step_by_id:
                issues.append(f"transition:{transition.id}:target_not_active_or_foreign")
            else:
                adjacency[transition.source_step_id].append(transition.target_step_id)
        elif transition.outcome == CaseTransition.Outcome.COMPLETE:
            if transition.target_step_id:
                issues.append(f"transition:{transition.id}:complete_has_target")
            completion_edges.add(transition.source_step_id)
        else:
            issues.append(f"transition:{transition.id}:unknown_outcome")

    for step in steps:
        active_questions = [q for q in step.questions.all() if q.is_active]
        source_transitions = transitions_by_source.get(step.id, [])
        if step.node_kind == CaseStep.NodeKind.DECISION:
            if len(active_questions) != 1:
                issues.append(f"step:{step.id}:decision_requires_one_question")
                continue
            question = active_questions[0]
            if question.scoring_dimension_id:
                used_dimension_ids.add(question.scoring_dimension_id)
                if revision.rubric_version == 0:
                    issues.append(f"question:{question.id}:legacy_scoring_dimension_not_allowed")
                if question.scoring_dimension_id not in active_dimension_ids:
                    issues.append(f"question:{question.id}:scoring_dimension_inactive_or_foreign")
                elif question.scoring_dimension.revision_id != revision.id:
                    issues.append(f"question:{question.id}:scoring_dimension_revision_mismatch")
            elif revision.rubric_version >= 1:
                issues.append(f"question:{question.id}:scoring_dimension_missing")
            active_choices = [c for c in question.choices.all() if c.is_active]
            if not active_choices:
                issues.append(f"step:{step.id}:decision_has_no_choices")
            if any(t.choice_id is None for t in source_transitions):
                issues.append(f"step:{step.id}:decision_has_automatic_transition")
            for choice in active_choices:
                count = len(transitions_by_choice.get(choice.id, []))
                if count != 1:
                    issues.append(f"choice:{choice.id}:active_transition_count={count}")
        elif step.node_kind == CaseStep.NodeKind.INFORMATION:
            if active_questions:
                issues.append(f"step:{step.id}:information_has_questions")
            automatic = [t for t in source_transitions if t.choice_id is None]
            if len(automatic) != 1:
                issues.append(f"step:{step.id}:information_requires_one_automatic_transition")
        elif step.node_kind == CaseStep.NodeKind.TERMINAL:
            if active_questions:
                issues.append(f"step:{step.id}:terminal_has_questions")
            if source_transitions:
                issues.append(f"step:{step.id}:terminal_has_outgoing_transition")

    if revision.rubric_version >= 1:
        for dimension in active_dimensions:
            if dimension.id not in used_dimension_ids:
                issues.append(f"dimension:{dimension.id}:unused")

    if not revision.entry_step_id or revision.entry_step_id not in step_by_id:
        return issues
    visiting, visited = set(), set()
    cycle_found = False
    def walk(step_id):
        nonlocal cycle_found
        if step_id in visiting:
            cycle_found = True
            return
        if step_id in visited:
            return
        visiting.add(step_id)
        for target_id in adjacency.get(step_id, []):
            walk(target_id)
        visiting.remove(step_id)
        visited.add(step_id)
    walk(revision.entry_step_id)
    if cycle_found:
        issues.append("cycle_detected")
    for step_id in sorted(set(step_by_id) - visited):
        issues.append(f"step:{step_id}:unreachable")

    memo = {}
    def can_complete(step_id, stack):
        if step_id in memo:
            return memo[step_id]
        if step_id in stack:
            return False
        step = step_by_id[step_id]
        if step.node_kind == CaseStep.NodeKind.TERMINAL or step_id in completion_edges:
            memo[step_id] = True
            return True
        next_stack = stack | {step_id}
        result = any(can_complete(target_id, next_stack) for target_id in adjacency.get(step_id, []))
        memo[step_id] = result
        return result
    if not can_complete(revision.entry_step_id, set()):
        issues.append("entry_has_no_completion_path")
    return issues
