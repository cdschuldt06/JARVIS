export type ChatInputMode = "text" | "voice";

type BrowserSpeechRecognitionResult = {
  readonly isFinal: boolean;
  readonly 0: {
    readonly transcript: string;
  };
};

type BrowserSpeechRecognitionEvent = {
  readonly resultIndex: number;
  readonly results: {
    readonly length: number;
    readonly [index: number]: BrowserSpeechRecognitionResult;
  };
};

type BrowserSpeechRecognitionErrorEvent = {
  readonly error: string;
};

export type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: BrowserSpeechRecognitionErrorEvent) => void) | null;
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

type SpeechWindow = Window & {
  SpeechRecognition?: BrowserSpeechRecognitionConstructor;
  webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
};

export function getSpeechRecognitionConstructor(): BrowserSpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const speechWindow = window as SpeechWindow;
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

export function isSpeechRecognitionAvailable(): boolean {
  return getSpeechRecognitionConstructor() !== null;
}

export function isSpeechSynthesisAvailable(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

export function createSpeechRecognition({
  onResult,
  onStart,
  onEnd,
  onError,
}: {
  onResult: (transcript: string) => void;
  onStart: () => void;
  onEnd: () => void;
  onError: (message: string) => void;
}): BrowserSpeechRecognition | null {
  const Recognition = getSpeechRecognitionConstructor();
  if (!Recognition) return null;

  const recognition = new Recognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "en-US";
  recognition.onstart = onStart;
  recognition.onend = onEnd;
  recognition.onerror = (event) => onError(`Voice input error: ${event.error}`);
  recognition.onresult = (event) => {
    let transcript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      transcript += event.results[index][0].transcript;
    }
    const trimmed = transcript.trim();
    if (trimmed) onResult(trimmed);
  };
  return recognition;
}

export type VoiceSpeed = "slow" | "normal" | "fast";

export const VOICE_SPEED_RATES: Record<VoiceSpeed, number> = {
  slow: 0.85,
  normal: 1,
  fast: 1.2,
};

type SpokenResponseType = "news" | "markets" | "research" | "repository" | "codex_handoff" | "general";

export function formatAssistantResponseForSpeech(response: string): string {
  const withoutBlocks = nonSourceLines(response.replace(/```[\s\S]*?```/g, " ")).join("\n");
  const cleaned = cleanSpeechText(withoutBlocks);
  const summary = cleanSpeechText(extractSectionText(response, ["summary", "concise summary"]) || firstUsefulParagraph(withoutBlocks));
  const responseType = detectSpokenResponseType(response);

  if (responseType === "news") {
    const stories = extractNewsStorySummaries(response);
    const spokenStories = stories.length > 0 ? stories.slice(0, 5).join(" ") : firstSentences(summary, 3).join(" ");
    return `Here are the main headlines. ${spokenStories || "I found the headlines, but the written response has the useful detail."} I put the full sources and details on screen.`;
  }

  if (responseType === "markets") {
    const marketSummary = cleanSpeechText(extractSectionText(response, ["summary", "market summary"]) || firstUsefulParagraph(withoutBlocks));
    const drivers = extractBriefingPoints(response, ["key findings", "drivers", "major drivers", "market drivers", "what moved markets"], 3);
    return conciseJoin([marketSummary || "Here is the market read.", ...drivers], "I put the full market details on screen.");
  }

  if (responseType === "research") {
    const researchSummary = cleanSpeechText(extractSectionText(response, ["summary", "research summary", "concise summary"]) || firstUsefulParagraph(withoutBlocks));
    const findings = extractBriefingPoints(response, ["key findings", "findings", "recommendations", "implementation takeaways"], 3);
    return conciseJoin([researchSummary || "Here is the research summary.", ...findings], "I put the full research and sources on screen.");
  }

  if (responseType === "repository") {
    const findings = extractBriefingPoints(response, ["top findings", "findings", "risks", "repository risks", "current repository implementation", "architecture summary"], 3);
    return conciseJoin(["Here is what stands out in the repository.", ...findings], "I put the full repository details on screen.");
  }

  if (responseType === "codex_handoff") {
    const goal = cleanSpeechText(extractSectionText(response, ["goal"]) || firstUsefulParagraph(withoutBlocks));
    const goalSentence = firstSentences(goal, 1)[0] ?? goal;
    return `The Codex brief is ready.${goalSentence ? ` The goal is: ${goalSentence}` : ""} I put the full brief on screen.`;
  }

  if (isLongSpeechResponse(response)) {
    const keyPoints = extractBriefingPoints(response, ["key findings", "main points", "highlights"], 3);
    const parts = [summary, ...keyPoints.slice(0, 3)].filter(Boolean).slice(0, 4);
    const spoken = parts.join(" ");
    return `${spoken || "I have the answer ready."} I put the full details on screen.`;
  }

  return cleaned.slice(0, 900);
}

export function speakText(text: string, options: { rate?: number; onEnd?: () => void; onError?: () => void } = {}): void {
  if (!isSpeechSynthesisAvailable()) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = options.rate ?? 1;
  utterance.onend = options.onEnd ?? null;
  utterance.onerror = options.onError ?? null;
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (!isSpeechSynthesisAvailable()) return;
  window.speechSynthesis.cancel();
}

export function pauseSpeaking(): void {
  if (!isSpeechSynthesisAvailable()) return;
  window.speechSynthesis.pause();
}

export function resumeSpeaking(): void {
  if (!isSpeechSynthesisAvailable()) return;
  window.speechSynthesis.resume();
}

function isLongSpeechResponse(response: string): boolean {
  return response.length > 900 || response.split(/\r?\n/).filter((line) => line.trim()).length > 10;
}

function detectSpokenResponseType(response: string): SpokenResponseType {
  const text = response.toLowerCase();
  if (/\b(codex brief|implementation brief)\b/.test(text) || hasHeadings(response, ["project", "goal", "constraints"])) return "codex_handoff";
  if (/\b(markets?|stocks?|s&p|nasdaq|dow|yields?|oil prices?|crypto|earnings|selloff|rally)\b/.test(text)) return "markets";
  if (/\b(news|headlines|current events|top stories)\b/.test(text)) return "news";
  if (/\b(repository|repo|codebase|architecture|indexed files|repository context|current repository implementation)\b/.test(text)) return "repository";
  if (/\b(research|key findings|sources|recommendation|implementation takeaways)\b/.test(text)) return "research";
  return "general";
}

function hasHeadings(response: string, names: string[]): boolean {
  const headings = response
    .split(/\r?\n/)
    .filter((line) => /^#{1,6}\s+\S/.test(line))
    .map(normalizeHeading);
  return names.every((name) => headings.includes(name));
}

function isSkippedSpeechLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return false;
  if (/^\|.*\|$/.test(trimmed)) return true;
  if (/^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(trimmed)) return true;
  if (/^#{1,6}\s*(sources?|references?|tool activity|repository answer grounding|repository context used|knowledge items used|repository last indexed|confidence)\b/i.test(trimmed)) return true;
  if (/^(sources?|references?|tool activity|repository context used|knowledge items used|repository last indexed|confidence):/i.test(trimmed)) return true;
  if (/[A-Za-z]:\\[\w\s.-]+\\[\w\s./\\-]+/.test(trimmed)) return true;
  return false;
}

function cleanSpeechText(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/\s*\(\[[^\]]+\]\(https?:\/\/[^)]+\)\)/g, "")
    .replace(/\s*\([^)]*https?:\/\/[^)]*\)/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, "$1")
    .replace(/\s*\[[^\]]+\]\s*/g, " ")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[A-Za-z]:\\[\w\s.-]+\\[\w\s./\\-]+/g, "")
    .replace(/\/[\w.-]+\/[\w./-]+/g, "")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/[_>#|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function extractSectionText(response: string, names: string[]): string {
  const lines = response.split(/\r?\n/);
  const start = lines.findIndex((line) => {
    const normalized = normalizeHeading(line);
    return names.some((name) => normalized === name || normalized.startsWith(`${name} `));
  });
  if (start === -1) return "";

  const sectionLines: string[] = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    if (/^#{1,6}\s+\S/.test(lines[index]) || /^[A-Z][A-Za-z /-]+:\s*$/.test(lines[index].trim())) break;
    if (!isSkippedSpeechLine(lines[index])) sectionLines.push(lines[index]);
  }
  return sectionLines.join(" ");
}

function extractNewsStorySummaries(response: string): string[] {
  const candidates = [
    ...extractSectionLines(response, ["key findings", "main points", "highlights", "headlines", "top headlines", "summary"]),
    ...bulletLines(response),
  ];
  const cleaned = candidates
    .map(oneSentenceStory)
    .filter((item) => item.length > 0 && !isGenericNewsSpeech(item));
  return Array.from(new Set(cleaned));
}

function extractBriefingPoints(response: string, sectionNames: string[], limit: number): string[] {
  const candidates = [
    ...extractSectionLines(response, sectionNames),
    ...bulletLines(response),
  ];
  const cleaned = candidates
    .map(oneSentenceStory)
    .filter((item) => item.length > 0 && !isGenericNewsSpeech(item));
  return Array.from(new Set(cleaned)).slice(0, limit);
}

function conciseJoin(parts: string[], closing: string): string {
  const spoken = parts
    .map(cleanSpeechText)
    .filter(Boolean)
    .slice(0, 4)
    .join(" ");
  return `${spoken || "I have the answer ready."} ${closing}`;
}

function oneSentenceStory(line: string): string {
  const boldHeadline = line.match(/^\s*(?:[-*+]|\d+\.)\s+\*\*([^*]+)\*\*/);
  if (boldHeadline) return cleanSpeechText(boldHeadline[1]);

  const cleaned = cleanSpeechText(line)
    .replace(/^(breaking|update|headline|story)\s*:\s*/i, "")
    .replace(/^news\s*:\s*/i, "")
    .trim();
  const sentences = firstSentences(cleaned, 1);
  return sentences[0] ?? cleaned;
}

function firstSentences(text: string, count: number): string[] {
  return cleanSpeechText(text)
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean)
    .slice(0, count);
}

function isGenericNewsSpeech(text: string): boolean {
  return /^(here are|these are|today's main headlines|main headlines|summary|key findings|i put|full details|full sources)/i.test(text);
}

function extractSectionLines(response: string, names: string[]): string[] {
  const lines = response.split(/\r?\n/);
  const start = lines.findIndex((line) => {
    const normalized = normalizeHeading(line);
    return names.some((name) => normalized === name || normalized.startsWith(`${name} `));
  });
  if (start === -1) return [];

  const sectionLines: string[] = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^#{1,6}\s+\S/.test(line) || /^[A-Z][A-Za-z /-]+:\s*$/.test(line.trim())) break;
    if (!isSkippedSpeechLine(line) && /^\s*(?:[-*+]|\d+\.)\s+/.test(line)) sectionLines.push(line);
  }
  return sectionLines;
}

function bulletLines(response: string): string[] {
  return nonSourceLines(response.replace(/```[\s\S]*?```/g, " "))
    .filter((line) => /^\s*(?:[-*+]|\d+\.)\s+/.test(line) && !isSkippedSpeechLine(line));
}

function firstUsefulParagraph(response: string): string {
  const paragraphs = response
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.split(/\r?\n/).filter((line) => !/^#{1,6}\s+\S/.test(line.trim())).join(" "))
    .map(cleanSpeechText)
    .filter((paragraph) => paragraph.length > 0 && !/^(sources?|references?|tool activity)\b/i.test(paragraph));
  return paragraphs[0] ?? "";
}

function nonSourceLines(response: string): string[] {
  const result: string[] = [];
  let skippingSection = false;
  for (const line of response.split(/\r?\n/)) {
    const heading = normalizeHeading(line);
    if (/^(sources?|references?|tool activity|repository answer grounding)\b/.test(heading)) {
      skippingSection = true;
      continue;
    }
    if (skippingSection && /^#{1,6}\s+\S/.test(line)) {
      skippingSection = false;
    }
    if (!skippingSection && !isSkippedSpeechLine(line)) result.push(line);
  }
  return result;
}

function normalizeHeading(line: string): string {
  return line
    .replace(/^#{1,6}\s*/, "")
    .replace(/[:—-].*$/, "")
    .trim()
    .toLowerCase();
}
