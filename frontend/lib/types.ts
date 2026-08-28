export type Disorder = {
  id: number;
  slug: string;
  name_en: string;
  name_fa: string;
  short_description: string;
  category: string;
  category_slug: string;
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
