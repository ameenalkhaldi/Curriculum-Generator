export type BlockType = "text" | "audio" | "image" | "question";

export interface TextBlock {
  id: string;       // UUID
  slug: string;     // e.g. "b1"
  type: "text";
  data: string;
}

export interface AudioBlock {
  id: string;       // UUID
  slug: string;
  type: "audio";
  data: {
    src: string;
    caption?: string;
  };
}

export interface ImageBlock {
  id: string;       // UUID
  slug: string;
  type: "image";
  data: {
    src: string;
    alt?: string;
  };
}

export interface MCQuestionBlockType {
  id: string;
  slug: string;
  type: "mc";
  tags?: string[];
  data: {
    question: string;
    options: string[];
    answer: string;
  };
}

export interface FreeTextQuestionBlockType {
  id: string;
  slug: string;
  type: "free-text";
  tags?: string[];
  data: {
    question: string;
    answer: string;
  };
}

//future types could include drag/drop match, fill-in-the-blank, etc.
export type QuestionBlock = MCQuestionBlockType | FreeTextQuestionBlockType;

export type LessonBlock =
  | TextBlock
  | AudioBlock
  | ImageBlock
  | QuestionBlock;

// Each Lesson has a quiz at the end for that specific Lesson  
export interface LessonQuiz {
  questions: QuestionBlock[];
}

// Lessons within Modules. e.g: Module 'Verbs' has lessons such as 'Past Tense Verbs'
export interface Lesson {
  id: string;       // UUID
  slug: string;     // e.g. "1.1.3"
  title: string;
  blocks: LessonBlock[];
  quiz?: LessonQuiz;
}

// Each Module will have an exam covering content from all the lessons.
export interface ModuleExam {
  questions: QuestionBlock[];
}

// Modules such as 'Verbs', 'Types of Sentences', 'Advanced Particles'
export interface Module {
  id: string;       // UUID
  slug: string;     // e.g. "1.1"
  title: string;
  lessons: Lesson[];
  exam?: ModuleExam;
}

// Levels such as beginner grammar, intermediate, mastery level
export interface Level {
  id: string;       // UUID
  slug: string;     // e.g. "1"
  title: string;
  modules: Module[];
}

// For each language e.g: curriculum EN-AR (arabic for english speakers) or AR-AR
export interface Curriculum {
  levels: Level[];
}
