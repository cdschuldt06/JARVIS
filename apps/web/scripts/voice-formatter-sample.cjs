const fs = require("fs");
const path = require("path");
const ts = require("typescript");
const vm = require("vm");

const voicePath = path.join(__dirname, "..", "lib", "voice.ts");
const source = fs.readFileSync(voicePath, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const sandbox = { exports: {}, window: undefined, SpeechSynthesisUtterance: function SpeechSynthesisUtterance() {} };
vm.runInNewContext(compiled, sandbox);

const examples = [
  {
    name: "news",
    input: `## Concise summary - Today's headlines
Today's biggest headlines are U.S.-Iran tensions, inflation rising, World Cup opening, and Honda recall.

## Key findings
- **U.S.-Iran tensions escalated.** Reports said the conflict intensified after new strikes and diplomatic warnings. ([apnews.com](https://example.com/iran))
- **Inflation rose to 4.2 percent.** The latest inflation print renewed pressure on household budgets. ([bls.gov](https://example.com/inflation))
- **The World Cup opened today.** Mexico City hosted the opening ceremony and first match. ([fifa.com](https://example.com/world-cup))
- **Honda announced a major recall.** The company recalled 880,514 vehicles over a safety defect. ([nhtsa.gov](https://example.com/honda))

## Sources
- https://example.com/source-one`,
    required: [
      "Here are the main headlines.",
      "U.S.-Iran tensions escalated.",
      "Inflation rose to 4.2 percent.",
      "The World Cup opened today.",
      "Honda announced a major recall.",
      "I put the full sources and details on screen.",
    ],
  },
  {
    name: "markets",
    input: `## Market summary
Stocks sold off today as the Nasdaq led losses and oil prices rose.

## Major drivers
- **Tech shares pulled indexes lower.** AI-linked names saw broad selling.
- **Oil prices rose.** Traders reacted to renewed geopolitical risk.
- **Bond yields climbed.** Investors priced in a tighter Fed path.

## Sources
- https://example.com/markets`,
    required: [
      "Stocks sold off today",
      "Tech shares pulled indexes lower.",
      "Oil prices rose.",
      "Bond yields climbed.",
      "I put the full market details on screen.",
    ],
  },
  {
    name: "research",
    input: `## Research summary
Browser speech APIs are useful for a prototype, but production voice should keep fallbacks.

## Key findings
- **SpeechSynthesis is good enough for browser text-to-speech.** It needs user controls for rate and stopping.
- **SpeechRecognition should be feature detected.** Browser support is inconsistent.
- **MediaRecorder is the better fallback path.** It can support backend transcription later.

## Sources
- https://example.com/speech`,
    required: [
      "Browser speech APIs are useful for a prototype",
      "SpeechSynthesis is good enough for browser text-to-speech.",
      "SpeechRecognition should be feature detected.",
      "MediaRecorder is the better fallback path.",
      "I put the full research and sources on screen.",
    ],
  },
  {
    name: "repository",
    input: `## Repository risks
- **Usage logging has no automated tests yet.** The formatter and backend logging rely on manual checks.
- **SQLite migrations are local-development only.** Production migration strategy is still light.
- **Repository indexing is heuristic.** It summarizes important files but does not parse every module.

Repository Context Used:
8 files`,
    required: [
      "Here is what stands out in the repository.",
      "Usage logging has no automated tests yet.",
      "SQLite migrations are local-development only.",
      "Repository indexing is heuristic.",
      "I put the full repository details on screen.",
    ],
  },
  {
    name: "codex_handoff",
    input: `## Project
Jarvis

## Goal
Add repository-aware usage tracking to Jarvis.

## Constraints
- Keep repository access read-only.
- Do not change handoff storage.`,
    required: [
      "The Codex brief is ready.",
      "The goal is: Add repository-aware usage tracking to Jarvis.",
      "I put the full brief on screen.",
    ],
  },
];

let failed = false;
for (const example of examples) {
  const spoken = sandbox.exports.formatAssistantResponseForSpeech(example.input);
  const missing = example.required.filter((phrase) => !spoken.includes(phrase));
  const hasUrl = /https?:\/\//.test(spoken);
  if (missing.length > 0 || hasUrl || /[#*_`|]/.test(spoken)) {
    failed = true;
    console.error(`Voice formatter sample failed: ${example.name}`);
    console.error("Spoken output:");
    console.error(spoken);
    console.error("Missing:");
    console.error(missing.join("\n"));
    if (hasUrl) console.error("Output still contains a URL.");
  } else {
    console.log(`${example.name}: ${spoken}`);
  }
}

if (failed) process.exit(1);
