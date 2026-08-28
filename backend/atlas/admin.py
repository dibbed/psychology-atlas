from django.contrib import admin
from .models import (
    Bookmark, CaseAttempt, CaseChoice, CaseQuestion, CaseStep, Category,
    ClinicalCase, DifferentialRelationship, Disorder, DisorderSource,
    DisorderSymptom, Quiz, QuizAttempt, QuizChoice, QuizQuestion,
    SourceReference, Symptom, UserProgress,
)

for model in [
    Bookmark, CaseAttempt, CaseChoice, CaseQuestion, CaseStep, Category,
    ClinicalCase, DifferentialRelationship, Disorder, DisorderSource,
    DisorderSymptom, Quiz, QuizAttempt, QuizChoice, QuizQuestion,
    SourceReference, Symptom, UserProgress,
]:
    admin.site.register(model)
