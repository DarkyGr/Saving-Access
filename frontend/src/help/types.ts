/** A paragraph, or a bulleted list. */
export type HelpBlock = string | string[];

export interface HelpSection {
  /** Stable anchor used in links (#id). */
  id: string;
  title: string;
  blocks: HelpBlock[];
}

export type Guide = Record<"en" | "es", HelpSection[]>;
