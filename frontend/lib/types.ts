export type Disorder = {
  id: number;
  slug: string;
  name_en: string;
  name_fa: string;
  short_description: string;
  category: string;
  category_slug: string;
};

export type Concept = {
  id: number;
  slug: string;
  name_en: string;
  name_fa: string;
  kind: string;
  kind_label?: string;
  simple_definition: string;
  disorder_count?: number;
  flashcard_count?: number;
  relationship_count?: number;
};

export type ConceptDetail = Concept & {
  academic_definition: string;
  example: string;
  relationships: {
    slug: string;
    name_en: string;
    name_fa: string;
    relationship_type: string;
    direction: "incoming" | "outgoing";
    explanation: string;
  }[];
  disorders: {
    role: string;
    explanation: string;
    disorder: Disorder;
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
    flashcards: number;
    daily_challenges: number;
    quizzes: number;
    clinical_cases: number;
  };
  graph: { nodes: number; edges: number };
  categories: { slug: string; name_en: string; name_fa: string; count: number }[];
  concept_kinds: { kind: string; label: string; count: number }[];
};

export type KnowledgeGraphNode = {
  id: string;
  type: "concept" | "disorder" | "symptom";
  slug: string;
  label: string;
  name_en: string;
  name_fa: string;
  kind: string;
  group: string;
  summary: string;
  href: string;
  degree: number;
};

export type KnowledgeGraphEdge = {
  source: string;
  target: string;
  kind: string;
  explanation: string;
};

export type KnowledgeGraphData = {
  meta: {
    node_count: number;
    edge_count: number;
    node_types: { concept: number; disorder: number; symptom: number };
    edge_kinds: Record<string, number>;
  };
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
};
