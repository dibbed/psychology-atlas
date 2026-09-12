export type Disorder = {
  id: number;
  slug: string;
  name_en: string;
  name_fa: string;
  short_description: string;
  category: string;
  category_slug: string;
  data_origin: "curated" | "dsm_master";
};

export type ConceptAlias = {
  text: string;
  language: "fa" | "en" | "other";
  alias_type: "alternative" | "abbreviation" | "historical";
};

export type Concept = {
  id: number;
  slug: string;
  name_en: string;
  name_fa: string;
  kind: string;
  kind_label?: string;
  domain: string;
  domain_label?: string;
  subtype: string;
  subtype_label?: string;
  simple_definition: string;
  aliases: ConceptAlias[];
  disorder_count?: number;
  flashcard_count?: number;
  relationship_count?: number;
};

export type ConceptDetail = Concept & {
  academic_definition: string;
  example: string;
  counterexample: string;
  recognition_cues: string;
  common_confusions: string;
  relationships: {
    slug: string;
    name_en: string;
    name_fa: string;
    relationship_type: string;
    direction: "incoming" | "outgoing";
    explanation: string;
    sources: {
      id: number;
      title: string;
      organization: string;
      citation?: string;
      url: string;
      publication_year?: number | null;
      source_type?: string;
    }[];
  }[];
  disorders: {
    role: string;
    explanation: string;
    disorder: Disorder;
  }[];
  symptoms: {
    slug: string;
    name_en: string;
    name_fa: string;
    domain: string;
    relationship_type: string;
    explanation: string;
  }[];
  therapies: {
    relationship_type: string;
    explanation: string;
    therapy: {
      slug: string;
      name_en: string;
      name_fa: string;
      summary: string;
      family: { slug: string; name_en: string; name_fa: string };
    };
    sources: SourceReference[];
  }[];
  techniques: {
    relationship_type: string;
    explanation: string;
    technique: { slug: string; name_en: string; name_fa: string; summary: string };
    sources: SourceReference[];
  }[];
  sources: {
    id: number;
    title: string;
    organization: string;
    citation?: string;
    url: string;
    publication_year?: number | null;
    source_type?: string;
  }[];
  flashcard_count: number;
};

export type DisorderDetail = Disorder & {
  overview: string;
  clinical_features: string;
  risk_factors: string;
  treatment_overview: string;
  assessment_overview: string;
  typical_onset: string;
  course_note: string;
  symptoms: {
    slug: string;
    name_en: string;
    name_fa: string;
    description: string;
    domain: string;
    prominence: string;
    note: string;
  }[];
  related: {
    slug: string;
    name_en: string;
    name_fa: string;
    relationship_type: string;
    explanation: string;
  }[];
  concepts: {
    slug: string;
    name_en: string;
    name_fa: string;
    kind: string;
    role: string;
    explanation: string;
  }[];
  sources: {
    id: number;
    title: string;
    organization: string;
    url: string;
  }[];
  study_resources: {
    quizzes: { slug: string; title: string }[];
    cases: { slug: string; title: string; difficulty: string }[];
  };
  therapies: {
    slug: string;
    name_en: string;
    name_fa: string;
    summary: string;
    family: { slug: string; name_en: string; name_fa: string };
    clinical_role: string;
    clinical_role_label: string;
    evidence_basis: string;
    evidence_basis_label: string;
    explanation: string;
    evidence_note: string;
    sources: SourceReference[];
  }[];
};

export type Quiz = {
  id: number;
  slug: string;
  title: string;
  description: string;
  disorder: Disorder | null;
  question_count?: number;
  questions?: {
    id: number;
    prompt: string;
    sort_order: number;
    choices: { id: number; text: string }[];
  }[];
};

export type ClinicalCase = {
  id: number;
  slug: string;
  title: string;
  patient_summary: string;
  difficulty: string;
  step_count?: number;
  educational_objective?: string;
  primary_disorder: Disorder | null;
  steps?: {
    id: number;
    title: string;
    narrative: string;
    sort_order: number;
    questions: {
      id: number;
      prompt: string;
      sort_order: number;
      choices: { id: number; text: string }[];
    }[];
  }[];
};

export type Category = {
  slug: string;
  name_en: string;
  name_fa: string;
  description: string;
  disorder_count: number;
};

export type UserNote = {
  id?: number;
  body: string;
  exists?: boolean;
  updated_at?: string;
  disorder?: Disorder;
};

export type ConceptNote = {
  id?: number;
  body: string;
  exists?: boolean;
  updated_at?: string;
  concept?: Concept;
};

export type Flashcard = {
  id: number;
  slug: string;
  front: string;
  back: string;
  hint: string;
  difficulty: string;
  concept: Concept | null;
  disorder: Disorder | null;
};

export type FlashcardProgress = {
  flashcard: Flashcard;
  state: string;
  due_at: string;
  interval_days: number;
  ease_factor: number;
  repetitions: number;
  lapses: number;
  last_rating: string;
  last_reviewed_at: string | null;
};

export type ReviewQueueItem = {
  is_new: boolean;
  flashcard: Flashcard;
  progress: FlashcardProgress | null;
};

export type DailyChallenge = {
  id: number;
  prompt: string;
  date: string;
  choices: { id: number; text: string }[];
  concept: Concept | null;
  disorder: Disorder | null;
  attempt: null | {
    selected_choice_id: number;
    correct: boolean;
    explanation: string;
  };
};

export type SearchResults = {
  query: string;
  disorders: Disorder[];
  concepts: Concept[];
  therapies: Therapy[];
  techniques: Technique[];
  psychologists: Psychologist[];
  theories: Theory[];
  timeline_events: TimelineEvent[];
  symptoms: {
    slug: string;
    name_en: string;
    name_fa: string;
    description: string;
    domain: string;
    disorders: Disorder[];
  }[];
};

export type AtlasOverview = {
  counts: {
    categories: number;
    disorders: number;
    concepts: number;
    symptoms: number;
    therapies: number;
    techniques: number;
    psychologists: number;
    theories: number;
    timeline_events: number;
    flashcards: number;
    daily_challenges: number;
    quizzes: number;
    clinical_cases: number;
  };
  graph: { nodes: number; edges: number };
  categories: { slug: string; name_en: string; name_fa: string; count: number }[];
  concept_kinds: { kind: string; label: string; count: number }[];
  concept_domains: { domain: string; label: string; count: number }[];
  concept_subtypes: { subtype: string; label: string; count: number }[];
};

export type KnowledgeGraphNode = {
  id: string;
  type: "concept" | "disorder" | "symptom" | "therapy" | "technique" | "psychologist" | "theory" | "timeline";
  slug: string;
  label: string;
  name_en: string;
  name_fa: string;
  kind: string;
  group: string;
  domain?: string;
  domain_label?: string;
  subtype?: string;
  summary: string;
  href: string;
  degree: number;
  dsm_master_id?: string;
  dsm_chapter_number?: number | null;
  dsm_chapter_name_fa?: string;
  category?: string;
  family?: string;
  classifications?: string[];
  review_status?: string;
  role?: string;
  nationality?: string;
  birth_year?: number | null;
  death_year?: number | null;
  period_text?: string;
  modern_status?: string;
  event_type?: string;
  date_precision?: string;
  date_text?: string;
  year_start?: number | null;
  year_end?: number | null;
  exact_date?: string | null;
  distance?: number;
  filtered_degree?: number;
};

export type KnowledgeGraphEdge = {
  source: string;
  target: string;
  kind: string;
  explanation: string;
  traversal_direction?: "forward" | "reverse";
  traversed_from?: string;
  traversed_to?: string;
  review_status?: string;
  sources?: {
    id?: number;
    title: string;
    organization: string;
    citation?: string;
    url: string;
    publication_year?: number | null;
    source_type?: string;
    verification_status?: string;
    doi?: string;
    pmid?: string;
  }[];
};

export type ConceptNeighborhood = {
  center: string;
  depth: 1 | 2;
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
};

export type GraphPathResult = {
  from: string;
  to: string;
  found: boolean;
  hops: number | null;
  structural_edges_included?: boolean;
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
};

export type CognitiveDistortionsOverview = {
  count: number;
  practice_count: number;
  items: Concept[];
};

export type DistortionPracticeChoice = {
  id: number;
  text: string;
  concept: { slug: string; name_en: string; name_fa: string };
};

export type DistortionPracticeItem = {
  slug: string;
  prompt: string;
  difficulty: "basic" | "intermediate" | "advanced";
  choices: DistortionPracticeChoice[];
};

export type DistortionPracticeQueue = {
  count: number;
  items: DistortionPracticeItem[];
};

export type DistortionPracticeResult = {
  attempt_id: number;
  correct: boolean;
  selected_choice_id: number;
  correct_choice_id: number;
  correct_concept: Concept;
  explanation: string;
  progress_percent: number;
};

export type KnowledgeGraphData = {
  meta: {
    node_count: number;
    edge_count: number;
    node_types: {
      concept: number;
      disorder: number;
      symptom: number;
      therapy: number;
      technique: number;
      psychologist: number;
      theory: number;
      timeline: number;
    };
    edge_kinds: Record<string, number>;
    available_edge_kinds?: Record<string, number>;
  };
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
};

export type SourceReference = {
  id: number;
  title: string;
  organization: string;
  citation?: string;
  url: string;
  publication_year?: number | null;
  source_type?: string;
  authors?: string[];
  doi?: string;
  pmid?: string;
  verification_status?: string;
};

export type TherapyFamily = {
  slug: string;
  name_en: string;
  name_fa: string;
  description: string;
};

export type TherapyClassification = {
  slug: string;
  name_en: string;
  name_fa: string;
  kind: "focus" | "method" | "delivery" | "population" | "other" | string;
  kind_label: string;
  description: string;
};

export type TherapyAlias = {
  text: string;
  language: "fa" | "en" | "other";
  alias_type: "alternative" | "abbreviation" | "historical";
};

export type Technique = {
  id: number;
  slug: string;
  name_en: string;
  name_fa: string;
  summary: string;
  review_status: "unreviewed" | "source_checked" | "reviewed" | string;
  aliases: TherapyAlias[];
  therapy_count: number;
  concept_count: number;
};

export type Therapy = {
  id: number;
  slug: string;
  name_en: string;
  name_fa: string;
  summary: string;
  family: TherapyFamily;
  aliases: TherapyAlias[];
  classifications: TherapyClassification[];
  review_status: "unreviewed" | "source_checked" | "reviewed" | string;
  technique_count: number;
  disorder_count: number;
  concept_count: number;
};

export type TherapyBookmark = {
  id: number;
  therapy: Therapy;
  created_at: string;
};

export type TherapyNote = {
  id?: number;
  therapy?: Therapy;
  therapy_slug?: string;
  body: string;
  exists?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type TherapyCompareResponse = {
  items: TherapyDetail[];
  note: string;
};

export type TherapyDetail = Therapy & {
  academic_definition: string;
  historical_context: string;
  core_principles: string;
  typical_structure: string;
  appropriate_contexts: string;
  limitations: string;
  safety_notes: string;
  evidence_note: string;
  sources: SourceReference[];
  techniques: {
    role: string;
    explanation: string;
    technique: Technique;
    sources: SourceReference[];
  }[];
  disorders: {
    clinical_role: string;
    clinical_role_label: string;
    evidence_basis: string;
    evidence_basis_label: string;
    explanation: string;
    evidence_note: string;
    disorder: Disorder;
    sources: SourceReference[];
  }[];
  concepts: {
    relationship_type: string;
    explanation: string;
    concept: Concept;
    sources: SourceReference[];
  }[];
};

export type TechniqueDetail = Technique & {
  academic_definition: string;
  application_notes: string;
  limitations: string;
  safety_notes: string;
  sources: SourceReference[];
  therapies: {
    role: string;
    explanation: string;
    therapy: {
      slug: string;
      name_en: string;
      name_fa: string;
      family: TherapyFamily;
    };
    sources: SourceReference[];
  }[];
  concepts: {
    relationship_type: string;
    explanation: string;
    concept: Concept;
    sources: SourceReference[];
  }[];
};

export type TherapyTaxonomy = {
  families: TherapyFamily[];
  classifications: TherapyClassification[];
  clinical_roles: { value: string; label: string }[];
  evidence_bases: { value: string; label: string }[];
  note: string;
};

export type ScientificReviewStatus = "unreviewed" | "source_checked" | "reviewed" | string;

export type ScientificEntitySourceLink = {
  role: string;
  role_label: string;
  note: string;
  source: SourceReference;
};

export type PsychologistAlias = {
  text: string;
  language: "fa" | "en" | "other";
  alias_type: "alternative" | "initials" | "transliteration" | "historical" | string;
};

export type TheoryAlias = {
  text: string;
  language: "fa" | "en" | "other";
  alias_type: "alternative" | "abbreviation" | "historical" | "transliteration" | string;
};

export type PsychologistBrief = {
  slug: string;
  name_en: string;
  name_fa: string;
  role_en: string;
  role_fa: string;
  review_status: ScientificReviewStatus;
};

export type TheoryBrief = {
  slug: string;
  name_en: string;
  name_fa: string;
  domain: string;
  modern_status: string;
  review_status: ScientificReviewStatus;
};

export type V6ConceptBrief = {
  slug: string;
  name_en: string;
  name_fa: string;
  kind: string;
  domain: string;
};

export type V6TherapyBrief = {
  slug: string;
  name_en: string;
  name_fa: string;
  family: null | { slug: string; name_en: string; name_fa: string };
  review_status: ScientificReviewStatus;
};

export type V6TechniqueBrief = {
  slug: string;
  name_en: string;
  name_fa: string;
  review_status: ScientificReviewStatus;
};

export type TimelineEventBrief = {
  slug: string;
  title_en: string;
  title_fa: string;
  event_type: string;
  date_precision: "exact_date" | "year" | "year_range" | "approximate_year" | "unknown" | string;
  date_text: string;
  year_start: number | null;
  year_end: number | null;
  exact_date: string | null;
  review_status: ScientificReviewStatus;
};

export type Psychologist = {
  id: number;
  slug: string;
  name_en: string;
  name_fa: string;
  summary_en: string;
  summary_fa: string;
  role_en: string;
  role_fa: string;
  nationality_en: string;
  nationality_fa: string;
  birth_year: number | null;
  death_year: number | null;
  review_status: ScientificReviewStatus;
  aliases: PsychologistAlias[];
  theory_count: number;
  concept_count: number;
  therapy_count: number;
  timeline_event_count: number;
};

export type PsychologistDetail = Psychologist & {
  academic_disciplines: string[];
  contributions_en: string[];
  contributions_fa: string[];
  affiliations: string[];
  historical_context_en: string;
  historical_context_fa: string;
  sources: ScientificEntitySourceLink[];
  theories: {
    relationship_type: string;
    relationship_label: string;
    explanation_en: string;
    explanation_fa: string;
    review_status: ScientificReviewStatus;
    theory: TheoryBrief;
    sources: SourceReference[];
  }[];
  concepts: {
    relationship_type: string;
    relationship_label: string;
    explanation_en: string;
    explanation_fa: string;
    review_status: ScientificReviewStatus;
    concept: V6ConceptBrief;
    sources: SourceReference[];
  }[];
  therapies: {
    relationship_type: string;
    relationship_label: string;
    explanation_en: string;
    explanation_fa: string;
    review_status: ScientificReviewStatus;
    therapy: V6TherapyBrief;
    sources: SourceReference[];
  }[];
  related_psychologists: {
    direction: "incoming" | "outgoing";
    relationship_type: string;
    relationship_label: string;
    explanation_en: string;
    explanation_fa: string;
    review_status: ScientificReviewStatus;
    psychologist: PsychologistBrief;
    sources: SourceReference[];
  }[];
  timeline_events: {
    role: string;
    role_label: string;
    review_status: ScientificReviewStatus;
    event: TimelineEventBrief;
    sources: SourceReference[];
  }[];
};

export type Theory = {
  id: number;
  slug: string;
  name_en: string;
  name_fa: string;
  domain: string;
  period_text: string;
  summary_en: string;
  summary_fa: string;
  modern_status: string;
  review_status: ScientificReviewStatus;
  aliases: TheoryAlias[];
  psychologist_count: number;
  concept_count: number;
  therapy_count: number;
  technique_count: number;
  timeline_event_count: number;
};

export type TheoryDetail = Theory & {
  core_proposition_en: string;
  core_proposition_fa: string;
  historical_context_en: string;
  historical_context_fa: string;
  key_propositions_en: string[];
  key_propositions_fa: string[];
  applications_en: string[];
  applications_fa: string[];
  criticisms_en: string[];
  criticisms_fa: string[];
  limitations_en: string[];
  limitations_fa: string[];
  historical_importance_en: string;
  historical_importance_fa: string;
  sources: ScientificEntitySourceLink[];
  psychologists: {
    relationship_type: string;
    relationship_label: string;
    explanation_en: string;
    explanation_fa: string;
    review_status: ScientificReviewStatus;
    psychologist: PsychologistBrief;
    sources: SourceReference[];
  }[];
  concepts: {
    relationship_type: string;
    relationship_label: string;
    explanation_en: string;
    explanation_fa: string;
    review_status: ScientificReviewStatus;
    concept: V6ConceptBrief;
    sources: SourceReference[];
  }[];
  therapies: {
    relationship_type: string;
    relationship_label: string;
    explanation_en: string;
    explanation_fa: string;
    review_status: ScientificReviewStatus;
    therapy: V6TherapyBrief;
    sources: SourceReference[];
  }[];
  techniques: {
    relationship_type: string;
    relationship_label: string;
    explanation_en: string;
    explanation_fa: string;
    review_status: ScientificReviewStatus;
    technique: V6TechniqueBrief;
    sources: SourceReference[];
  }[];
  related_theories: {
    direction: "incoming" | "outgoing";
    relationship_type: string;
    relationship_label: string;
    explanation_en: string;
    explanation_fa: string;
    review_status: ScientificReviewStatus;
    theory: TheoryBrief;
    sources: SourceReference[];
  }[];
  timeline_events: {
    role: string;
    role_label: string;
    review_status: ScientificReviewStatus;
    event: TimelineEventBrief;
    sources: SourceReference[];
  }[];
};

export type TimelineEvent = TimelineEventBrief & {
  id: number;
  event_type_label: string;
  category: string;
  date_precision_label: string;
  psychologist_count: number;
  theory_count: number;
  therapy_count: number;
  technique_count: number;
  concept_count: number;
};

export type TimelineEventDetail = TimelineEvent & {
  description_en: string;
  description_fa: string;
  historical_importance_en: string;
  historical_importance_fa: string;
  sources: ScientificEntitySourceLink[];
  psychologists: {
    role: string;
    role_label: string;
    review_status: ScientificReviewStatus;
    psychologist: PsychologistBrief;
    sources: SourceReference[];
  }[];
  theories: {
    role: string;
    role_label: string;
    review_status: ScientificReviewStatus;
    theory: TheoryBrief;
    sources: SourceReference[];
  }[];
  therapies: {
    role: string;
    role_label: string;
    review_status: ScientificReviewStatus;
    therapy: V6TherapyBrief;
    sources: SourceReference[];
  }[];
  techniques: {
    role: string;
    role_label: string;
    review_status: ScientificReviewStatus;
    technique: V6TechniqueBrief;
    sources: SourceReference[];
  }[];
  concepts: {
    role: string;
    role_label: string;
    review_status: ScientificReviewStatus;
    concept: V6ConceptBrief;
    sources: SourceReference[];
  }[];
};

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type DSMDisplayType =
  | "diagnosis"
  | "structural"
  | "clinical_attention"
  | "research"
  | "alternative_model"
  | "specifier"
  | "reference"
  | "code"
  | "other";

export type DSMRecordBrief = {
  master_id: string;
  name_fa: string;
  name_en: string;
  display_type: DSMDisplayType;
  classification_status: string;
  specialization_level: string;
  root_section: string;
  chapter_number: number | null;
  chapter_name_fa: string;
  chapter_name_en: string;
  group_name: string;
  summary: string;
  linked_disorder: Disorder | null;
};

export type DSMSource = {
  key: string;
  عنوان?: string;
  نشانی?: string;
  کاربرد?: string;
};

export type DSMRecordDetail = DSMRecordBrief & {
  source_type: string;
  key_features: unknown[];
  assessment: unknown[];
  differential: unknown[];
  comorbidity: string;
  course: string;
  management: unknown[];
  assessment_tools: unknown[];
  context_considerations: string;
  red_flags: string;
  pitfalls: unknown[];
  nearby_titles: unknown[];
  official_updates: unknown[];
  homonym_info: Record<string, unknown>;
  prevalence_numeric: unknown;
  prevalence_policy: string;
  coding: string;
  source_keys: string[];
  sources: DSMSource[];
  quality: Record<string, unknown>;
  exam_tip: string;
  self_test: unknown[];
  structural_path: Record<string, unknown>;
  parent: DSMRecordBrief | null;
  children: DSMRecordBrief[];
  relations: {
    direction: "in" | "out";
    relationship_type: "nearby" | "differential";
    explanation: string;
    record: DSMRecordBrief;
  }[];
  source_payload: Record<string, unknown>;
};

export type DSMStudyKit = {
  glossary: Record<string, string>;
  study_guide: string[];
  cultural_note: string;
  urgent_warnings: Record<string, unknown>;
  stats: {
    records: number;
    diagnoses: number;
    self_test_questions: number;
    exam_tips: number;
    glossary_terms: number;
  };
};

export type DSMGraphNode = {
  id: string;
  label: string;
  name_en: string;
  display_type: DSMDisplayType;
  classification_status: string;
  chapter_number: number | null;
  chapter_name_fa: string;
  group_name: string;
  summary: string;
  degree: number;
  href: string;
  linked_disorder_slug: string | null;
};

export type DSMGraphData = {
  meta: {
    node_count: number;
    edge_count: number;
    relation_counts: { hierarchy: number; nearby: number; differential: number };
  };
  nodes: DSMGraphNode[];
  edges: { source: string; target: string; kind: "hierarchy" | "nearby" | "differential"; explanation: string }[];
};

export type DSMPaginatedRecords = {
  count: number;
  next: string | null;
  previous: string | null;
  results: DSMRecordBrief[];
};

export type DSMOverview = {
  corpus: {
    key: string;
    title: string;
    version_name: string;
    version_date: string;
    language: string;
    purpose: string;
    copyright_note: string;
    clinical_note: string;
    source_filename: string;
    source_sha256: string;
  };
  counts: {
    records: number;
    linked_atlas_disorders: number;
    types: Partial<Record<DSMDisplayType, number>>;
    roots: Record<string, number>;
  };
  chapters: {
    chapter_number: number;
    chapter_name_fa: string;
    chapter_name_en: string;
    record_count: number;
    diagnosis_count: number;
  }[];
  stats: Record<string, unknown>;
  official_status: Record<string, unknown>;
  source_registry: Record<string, Omit<DSMSource, "key">>;
  quality_audit: Record<string, unknown>;
  study_guide: string[];
  urgent_warnings: Record<string, unknown>;
  cultural_note: string;
  periodic_review: Record<string, unknown>[];
  release_updates: Record<string, unknown>;
  health_check: Record<string, unknown>;
};
