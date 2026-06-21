// Wires the two Monaco editors, the live example sidebar (sv-witnesses
// examples + sv-benchmarks, both via the GitLab API) and the Pyodide
// worker (live linting, one-shot instrumentation).

const GITLAB_PROJECT = "sosy-lab%2Fbenchmarking%2Fsv-benchmarks";
const GITLAB_API = `https://gitlab.com/api/v4/projects/${GITLAB_PROJECT}`;

const SV_WITNESSES_PROJECT = "sosy-lab%2Fbenchmarking%2Fsv-witnesses";
const SV_WITNESSES_API = `https://gitlab.com/api/v4/projects/${SV_WITNESSES_PROJECT}`;

// Both refs are user-editable via the sidebar's "Branch/tag" inputs --
// "concurrent-sc-violation-witnesses" is just the default, since examples/
// on sv-witnesses' main only has format-2.1-and-earlier witnesses.
function getSvBenchmarksRef() {
  const input = document.getElementById("sv-benchmarks-ref");
  return (input && input.value.trim()) || "main";
}

function getSvWitnessesRef() {
  const input = document.getElementById("sv-witnesses-ref");
  return (input && input.value.trim()) || "concurrent-sc-violation-witnesses";
}

// Fallback text if the live fetch from sv-benchmarks' c/properties/*.prp
// fails (offline, rate-limited, etc.) -- kept in sync with the real files.
const SPEC_FALLBACK = {
  "unreach-call": "CHECK( init(main()), LTL(G ! call(reach_error())) )",
  "no-data-race": "CHECK( init(main()), LTL(G ! data-race) )",
  "no-overflow": "CHECK( init(main()), LTL(G ! overflow) )",
};
const specTextCache = new Map();

async function getSpecificationText(property) {
  if (specTextCache.has(property)) return specTextCache.get(property);
  try {
    const url = `${GITLAB_API}/repository/files/${encodeURIComponent(
      `c/properties/${property}.prp`
    )}/raw?ref=${getSvBenchmarksRef()}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const text = (await resp.text()).trim();
    specTextCache.set(property, text);
    return text;
  } catch (err) {
    return SPEC_FALLBACK[property] || property;
  }
}

// ---------------------------------------------------------------------------
// Local examples: bundled with ConcurrentWitness2Test (the example/
// directory, copied verbatim into the image by the Dockerfile), fetched
// from the same origin -- no network round-trip to GitLab, and no
// duplication of the actual files into this script.  Each manifest entry
// just names which example/ files to fetch and which spec property to
// preselect.
// ---------------------------------------------------------------------------

const LOCAL_EXAMPLES = [
  {
    label: "concurrent-unreach (unreach-call, thread ordering)",
    property: "unreach-call",
    base: "concurrent-unreach",
  },
  {
    label: "concurrent-data-race (no-data-race, racing writes)",
    property: "no-data-race",
    base: "concurrent-data-race",
  },
  {
    label: "concurrent-nondet (unreach-call, nondet + thread-ID guard)",
    property: "unreach-call",
    base: "concurrent-nondet",
  },
  {
    label: "function-return (unreach-call, function_return waypoint)",
    property: "unreach-call",
    base: "function-return",
  },
  {
    label: "no-overflow (no-overflow, UBSan integer overflow)",
    property: "no-overflow",
    base: "no-overflow",
  },
];

async function fetchExampleFile(name) {
  const resp = await fetch(`example/${name}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching example/${name}`);
  return await resp.text();
}

function renderLocalExamples() {
  const list = document.getElementById("local-examples");
  list.innerHTML = "";
  for (const ex of LOCAL_EXAMPLES) {
    const li = document.createElement("li");
    li.className = "file";
    li.textContent = ex.label;
    li.addEventListener("click", async () => {
      if (!cEditor || !yamlEditor) return;
      const filename = `${ex.base}.i`;
      let c, witness;
      try {
        [c, witness] = await Promise.all([
          fetchExampleFile(filename),
          fetchExampleFile(`${ex.base}.witness-2.2.yml`),
        ]);
      } catch (err) {
        logOutput("instrument", `Failed to load example "${ex.label}":\n${err}`);
        return;
      }
      cEditor.setValue(c);
      cFilename.textContent = filename;
      // Set the spec selector to match the example's property
      if (specSelect && ex.property) {
        const option = Array.from(specSelect.options).find(
          (o) => o.value === ex.property
        );
        if (option) {
          specSelect.value = ex.property;
          specSelect.dispatchEvent(new Event("change"));
        }
      }
      yamlEditor.setValue(witness);
    });
    list.appendChild(li);
  }
}

const outputPanels = {
  linter: document.getElementById("output-linter"),
  instrument: document.getElementById("output-instrument"),
  clang: document.getElementById("output-clang"),
};
const outputPanel = document.getElementById("output-panel");
const outputResizer = document.getElementById("output-resizer");
const outputToggleBtn = document.getElementById("output-toggle");
const lintStatus = document.getElementById("lint-status");
const pyodideStatus = document.getElementById("pyodide-status");
const instrumentBtn = document.getElementById("instrument-btn");
const instrumentCaret = document.getElementById("instrument-caret");
const instrumentMenu = document.getElementById("instrument-menu");
const cFilename = document.getElementById("c-filename");
const cursorPos = document.getElementById("cursor-pos");
const specSelect = document.getElementById("spec-select");
const addWaypointBtn = document.getElementById("add-waypoint-btn");
const compileRunBtn = document.getElementById("compile-run-btn");

function setStatus(el, cls, text) {
  el.className = `status status-${cls}`;
  el.textContent = text;
}

// Output panel: only auto-opens on its own; once the user explicitly hides
// it, it stays hidden even as new output comes in (they can still re-open).
let outputHiddenByUser = false;

// panel is one of "linter" | "instrument" | "clang", matching the three
// output sources (the linter, ConcurrentWitness2Test's instrumentation
// pipeline, and clang/Compile & Run).
function logOutput(panel, text) {
  outputPanels[panel].textContent = text;
  if (!outputHiddenByUser) {
    outputPanel.classList.remove("collapsed");
    outputResizer.classList.remove("collapsed");
  }
}

function setOutputCollapsed(collapsed) {
  outputHiddenByUser = collapsed;
  outputPanel.classList.toggle("collapsed", collapsed);
  outputResizer.classList.toggle("collapsed", collapsed);
  outputToggleBtn.textContent = collapsed ? "Show" : "Hide";
}

outputToggleBtn.addEventListener("click", () => {
  setOutputCollapsed(!outputPanel.classList.contains("collapsed"));
});
for (const btn of document.querySelectorAll(".output-clear-btn")) {
  btn.addEventListener("click", () => {
    outputPanels[btn.dataset.target].textContent = "";
  });
}

// ---------------------------------------------------------------------------
// Resizable panels
// ---------------------------------------------------------------------------

function makeResizer(resizerEl, { axis, min, max, getSize, setSize, invert = false }) {
  resizerEl.addEventListener("mousedown", (downEvent) => {
    downEvent.preventDefault();
    const start = axis === "x" ? downEvent.clientX : downEvent.clientY;
    const startSize = getSize();
    document.body.classList.add(axis === "x" ? "resizing-h" : "resizing-v");

    function onMove(moveEvent) {
      const cur = axis === "x" ? moveEvent.clientX : moveEvent.clientY;
      const delta = invert ? start - cur : cur - start;
      const next = Math.min(max(), Math.max(min(), startSize + delta));
      setSize(next);
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.classList.remove("resizing-h", "resizing-v");
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });
}

const sidebarEl = document.getElementById("sidebar");
const editorsEl = document.getElementById("editors");
const cPaneEl = document.getElementById("c-pane");

makeResizer(document.getElementById("sidebar-resizer"), {
  axis: "x",
  min: () => 160,
  max: () => 600,
  getSize: () => sidebarEl.getBoundingClientRect().width,
  setSize: (w) => {
    sidebarEl.style.width = `${w}px`;
  },
});

makeResizer(document.getElementById("pane-resizer"), {
  axis: "x",
  min: () => 240,
  max: () => editorsEl.getBoundingClientRect().width - 240,
  getSize: () => cPaneEl.getBoundingClientRect().width,
  setSize: (w) => {
    cPaneEl.style.flex = `0 0 ${w}px`;
  },
});

makeResizer(outputResizer, {
  axis: "y",
  invert: true, // the resizer sits above the panel, so dragging up (cursor
  // moving to smaller clientY) must grow it, not shrink it
  min: () => 80,
  max: () => window.innerHeight - 160,
  getSize: () => outputPanel.getBoundingClientRect().height,
  setSize: (h) => {
    outputPanel.style.height = `${h}px`;
  },
});

// ---------------------------------------------------------------------------
// Sidebar collapse (hamburger toggle in the top bar)
// ---------------------------------------------------------------------------

const sidebarHamburgerBtn = document.getElementById("sidebar-hamburger");

// The collapsed flag lives on <body> (not #layout) so the hamburger icon
// itself -- which sits in the topbar, a sibling of #layout -- can also be
// styled off it with a plain CSS selector.
sidebarHamburgerBtn.addEventListener("click", () => {
  document.body.classList.toggle("sidebar-collapsed");
});

// ---------------------------------------------------------------------------
// Dark/light theme toggle
// ---------------------------------------------------------------------------

const themeToggleBtn = document.getElementById("theme-toggle");

function getTheme() {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function getMonacoTheme() {
  return getTheme() === "light" ? "vs" : "vs-dark";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("cwt-theme", theme);
  themeToggleBtn.textContent = theme === "light" ? "☼" : "☽"; // sun / moon-ish glyph
  if (window.monaco) monaco.editor.setTheme(getMonacoTheme());
}

themeToggleBtn.addEventListener("click", () => {
  applyTheme(getTheme() === "light" ? "dark" : "light");
});

applyTheme(getTheme()); // sync the button glyph with the theme set by index.html's inline script

// ---------------------------------------------------------------------------
// Monaco setup
// ---------------------------------------------------------------------------

let cEditor, yamlEditor;
let editorsReady = false;
let pyodideReady = false;

function updateInstrumentButton() {
  const ready = editorsReady && pyodideReady;
  instrumentBtn.disabled = !ready;
  instrumentCaret.disabled = !ready;
}

// Compile & Run doesn't need Pyodide at all (it's a real clang/WASIX
// pipeline, independent of the linting/instrumentation worker) -- only
// gated on the editors existing and unreach-call being selected, since
// that's the only property whose violation a plain compile+run (exit code
// 74 from reach_error()) can confirm; no-data-race needs ThreadSanitizer
// and no-overflow needs UBSan, neither of which is wired in here.
function updateCompileRunButton() {
  compileRunBtn.disabled = !editorsReady || specSelect.value !== "unreach-call";
}

const monacoReady = new Promise((resolve) => {
  require.config({ paths: { vs: "vendor/monaco/vs" } });
  require(["vs/editor/editor.main"], () => resolve());
});

// Before anything is picked from the sidebar, behave as if a fresh
// "temp.c" was opened: a minimal program in the C editor, and the witness
// editor pre-filled exactly as it would be for any other freshly loaded
// program (auto-filled metadata, empty content list).
const DEFAULT_C_FILENAME = "temp.c";
const DEFAULT_C_CONTENT = `int main(void) {
    return 0;
}
`;

async function initEditors() {
  await monacoReady;
  cEditor = monaco.editor.create(document.getElementById("c-editor"), {
    language: "c",
    theme: getMonacoTheme(),
    automaticLayout: true,
    value: DEFAULT_C_CONTENT,
    minimap: { enabled: false },
  });
  cFilename.textContent = DEFAULT_C_FILENAME;
  yamlEditor = monaco.editor.create(document.getElementById("yaml-editor"), {
    language: "yaml",
    theme: getMonacoTheme(),
    automaticLayout: true,
    value: "",
    minimap: { enabled: false },
  });

  cEditor.onDidChangeCursorPosition((e) => {
    cursorPos.textContent = `Ln ${e.position.lineNumber}, Col ${e.position.column}`;
  });
  cEditor.onDidChangeModelContent(debounce(updateScheduleDecorations, 200));

  cEditor.addAction({
    id: "cwt.addWaypointAtCursor",
    label: "Add witness waypoint at cursor",
    contextMenuGroupId: "navigation",
    contextMenuOrder: 1.5,
    run: () => addWaypointAtCursor(),
  });

  yamlEditor.onDidChangeModelContent(debounce(runLint, 400));
  yamlEditor.onDidChangeCursorPosition(() => highlightCLocationForYamlCursor());
  addWaypointBtn.addEventListener("click", () => addWaypointAtCursor());

  yamlEditor.setValue(
    await buildWitnessSkeleton(DEFAULT_C_FILENAME, DEFAULT_C_CONTENT, specSelect.value)
  );

  editorsReady = true;
  updateInstrumentButton();
  updateCompileRunButton();
}

function debounce(fn, ms) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// ---------------------------------------------------------------------------
// __concurrentwit2test_yield()/__concurrentwit2test_release() decorations
// ---------------------------------------------------------------------------

let scheduleDecorations = [];

function updateScheduleDecorations() {
  if (!cEditor) return;
  const model = cEditor.getModel();
  const decorations = [];
  const lineCount = model.getLineCount();
  for (let line = 1; line <= lineCount; line++) {
    const text = model.getLineContent(line);
    const re = /\b(__concurrentwit2test_yield|__concurrentwit2test_release)\s*\([^)]*\)/g;
    let match;
    while ((match = re.exec(text))) {
      decorations.push({
        range: new monaco.Range(line, match.index + 1, line, match.index + 1 + match[0].length),
        options: {
          inlineClassName: match[1] === "__concurrentwit2test_yield" ? "cwt-yield-call" : "cwt-release-call",
        },
      });
    }
  }
  scheduleDecorations = model.deltaDecorations(scheduleDecorations, decorations);
}

// ---------------------------------------------------------------------------
// YAML cursor -> C location highlight: clicking (or moving the cursor) into
// a waypoint's body in the YAML editor highlights the C source location its
// `location:` block points at.
// ---------------------------------------------------------------------------

// A line-based scan, not a real YAML parse (no YAML library is vendored,
// and the witness schema's shape is fixed enough that this is reliable):
// each `- waypoint:` line starts a new waypoint, owning every line up to
// (not including) the next one, anywhere in the document.
function parseWaypointLocations(yamlText) {
  const lines = yamlText.split("\n");
  const starts = [];
  for (let i = 0; i < lines.length; i++) {
    if (/^\s*-\s*waypoint:\s*$/.test(lines[i])) starts.push(i + 1); // 1-indexed
  }
  return starts.map((startLine, idx) => {
    const endLine = idx + 1 < starts.length ? starts[idx + 1] - 1 : lines.length;
    const block = lines.slice(startLine - 1, endLine).join("\n");
    const lineMatch = block.match(/\bline:\s*(\d+)/);
    const colMatch = block.match(/\bcolumn:\s*(\d+)/);
    return {
      startLine,
      endLine,
      cLine: lineMatch ? parseInt(lineMatch[1], 10) : null,
      cColumn: colMatch ? parseInt(colMatch[1], 10) : 1,
    };
  });
}

// After "Instrument" the C editor shows LineDirectiveCGenerator's output
// (see tweaks.py): the original source reformatted, with instrumentation
// inserted, and `#line N "file"` comments ahead of each original-source
// chunk so the *line numbers* survive the reformatting. A waypoint's
// `location.line` is always in original-source terms, so it has to be
// resolved through those directives to find the right physical Monaco
// line -- forward-simulating the same line count gcc/UBSan/TSan would.
//
// The directives say nothing about *columns*: CGenerator's own
// indentation/formatting means an original column number is meaningless
// on the regenerated physical line, so column-precision highlighting is
// only valid when there are no directives at all (untouched source, where
// physical and original line numbers already coincide).
function resolvePhysicalLine(model, originalLine) {
  let curLine = null;
  let sawDirective = false;
  // A line reached by counting forward from the last directive (no fresh
  // directive of its own) is only a best-effort guess -- synthetic
  // instrumentation lines with no original-source line of their own can
  // coincidentally drift onto the same number. A directive that names
  // `originalLine` explicitly is always ground truth and wins outright;
  // the counted-forward guess is kept only as a fallback for when no
  // directive ever claims that line (e.g. a line whose statement never
  // needed its own re-anchoring).
  let fallback = null;
  const lineCount = model.getLineCount();
  for (let physicalLine = 1; physicalLine <= lineCount; physicalLine++) {
    const m = /^\s*#line\s+(\d+)\s+"[^"]*"\s*$/.exec(model.getLineContent(physicalLine));
    if (m) {
      sawDirective = true;
      curLine = parseInt(m[1], 10);
      if (curLine === originalLine) {
        return { line: physicalLine + 1, columnReliable: false };
      }
      continue;
    }
    if (curLine !== null) {
      if (curLine === originalLine && fallback === null) {
        fallback = { line: physicalLine, columnReliable: false };
      }
      curLine++;
    }
  }
  if (sawDirective) return fallback;
  return { line: originalLine, columnReliable: true };
}

let yamlCursorDecorations = [];

function highlightCLocationForYamlCursor() {
  if (!yamlEditor || !cEditor) return;
  const model = cEditor.getModel();
  if (!model) return;

  const pos = yamlEditor.getPosition();
  const waypoint = pos
    ? parseWaypointLocations(yamlEditor.getValue()).find(
        (wp) => pos.lineNumber >= wp.startLine && pos.lineNumber <= wp.endLine
      )
    : null;

  const resolved = waypoint && waypoint.cLine ? resolvePhysicalLine(model, waypoint.cLine) : null;
  if (!resolved || resolved.line > model.getLineCount()) {
    yamlCursorDecorations = model.deltaDecorations(yamlCursorDecorations, []);
    return;
  }

  const { line, columnReliable } = resolved;
  cEditor.revealLineInCenterIfOutsideViewport(line);
  const decorations = [
    {
      range: new monaco.Range(line, 1, line, 1),
      options: { isWholeLine: true, className: "cwt-waypoint-location-line" },
    },
  ];
  if (columnReliable) {
    const column = Math.min(waypoint.cColumn, model.getLineMaxColumn(line));
    decorations.push({
      range: new monaco.Range(line, column, line, column + 1),
      options: { inlineClassName: "cwt-waypoint-location-col" },
    });
  }
  yamlCursorDecorations = model.deltaDecorations(yamlCursorDecorations, decorations);
}

// ---------------------------------------------------------------------------
// Witness metadata skeleton
// ---------------------------------------------------------------------------

async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function buildWitnessSkeleton(filename, programText, property) {
  const hash = await sha256Hex(programText);
  const uuid = crypto.randomUUID();
  const creationTime = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const specification = await getSpecificationText(property);
  return `# Auto-filled metadata (format 2.2). Please edit as needed.
- entry_type: violation_sequence
  metadata:
    format_version: "2.2"
    uuid: "${uuid}"
    creation_time: "${creationTime}"
    producer:
      name: "www-demo playground"
      version: "1.0"
    task:
      input_files:
        - "${filename}"
      input_file_hashes:
        "${filename}": "${hash}"
      specification: "${specification}"
      data_model: "ILP32"
      language: "C"
  content: []
`;
}

specSelect.addEventListener("change", async () => {
  updateCompileRunButton();
  if (!yamlEditor) return;
  const specification = await getSpecificationText(specSelect.value);
  const yaml = yamlEditor.getValue();
  const updated = yaml.replace(
    /specification:\s*".*"/,
    `specification: "${specification.replace(/"/g, '\\"')}"`
  );
  if (updated !== yaml) yamlEditor.setValue(updated);
});

// ---------------------------------------------------------------------------
// Add witness waypoint at cursor (placeholder scaffold)
// ---------------------------------------------------------------------------

function addWaypointAtCursor() {
  if (!cEditor || !yamlEditor) return;
  const pos = cEditor.getPosition();
  if (!pos) return;
  const filename = cFilename.textContent || "input.c";
  const block = `  - segment:
    - waypoint:
        type: assumption # TODO: assumption | target | function_enter | function_return | branching
        action: follow
        thread_id: 0 # TODO: 0 = main thread, k = k-th spawned thread
        constraint: # TODO: only valid for assumption/function_return waypoints
          value: "TODO" # e.g. "x == 1"
          format: c_expression
        location:
          file_name: "${filename}"
          line: ${pos.lineNumber}
          column: ${pos.column}
          function: "TODO"
`;
  let yaml = yamlEditor.getValue();
  yaml = yaml.replace(/content:\s*\[\]\s*$/m, "content:");
  if (!yaml.endsWith("\n")) yaml += "\n";
  const insertLine = yaml.split("\n").length; // 1-indexed line the block will start on
  yaml += block;
  yamlEditor.setValue(yaml);
  yamlEditor.revealLineInCenter(insertLine);
  yamlEditor.setPosition({ lineNumber: insertLine, column: 1 });
  yamlEditor.focus();
}

// ---------------------------------------------------------------------------
// Pyodide worker
// ---------------------------------------------------------------------------

const worker = new Worker("pyodide-worker.js");
let workerReady = false;
let nextRequestId = 1;
const pending = new Map();

// Without this, a worker-startup failure (e.g. a blocked cross-origin
// subresource) shows up only as the page silently never leaving "Loading
// Python runtime..." -- no console output, since errors *inside* a worker
// don't otherwise surface on the main thread.
worker.onerror = (event) => {
  setStatus(pyodideStatus, "err", "Python runtime failed to load");
  const msg = `Pyodide worker failed to start:\n${event.message || event}`;
  logOutput("linter", msg);
  logOutput("instrument", msg);
};

worker.onmessage = (event) => {
  const data = event.data;
  if (data.cmd === "ready") {
    workerReady = true;
    pyodideReady = true;
    setStatus(pyodideStatus, "ok", "Python runtime ready");
    updateInstrumentButton();
    runLint();
    return;
  }
  if (data.cmd === "error" && data.id === undefined) {
    setStatus(pyodideStatus, "err", "Python runtime failed to load");
    const msg = `Pyodide failed to initialize:\n${data.error}`;
    logOutput("linter", msg);
    logOutput("instrument", msg);
    return;
  }
  const resolver = pending.get(data.id);
  if (resolver) {
    pending.delete(data.id);
    resolver(data);
  }
};

function callWorker(cmd, payload) {
  const id = nextRequestId++;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    worker.postMessage({ id, cmd, ...payload });
  });
}

async function runLint() {
  if (!workerReady || !yamlEditor) return;
  setStatus(lintStatus, "loading", "Lint: running…");
  const yaml = yamlEditor.getValue();
  const c = cEditor ? cEditor.getValue() : null;
  const response = await callWorker("lint", { yaml, c });
  if (!response.ok) {
    setStatus(lintStatus, "err", "Lint: error");
    logOutput("linter", `Linter failed to run:\n${response.error}`);
    return;
  }
  const { exit_code, output } = response.result;
  if (exit_code === 0) {
    setStatus(lintStatus, "ok", "Lint: valid");
  } else {
    setStatus(lintStatus, "warn", `Lint: exit ${exit_code}`);
  }
  logOutput("linter", output);
}

async function runInstrumentPipeline() {
  const c = cEditor.getValue();
  const yaml = yamlEditor.getValue();
  const response = await callWorker("instrument", { c, yaml });
  if (!response.ok) {
    logOutput("instrument", `Instrumentation failed to run:\n${response.error}`);
    return null;
  }
  const { ok, source, error, log, data_race, no_overflow } = response.result;
  if (!ok) {
    logOutput("instrument", `Instrumentation failed:\n${error}\n${log || ""}`);
    return null;
  }
  const notes = [];
  if (data_race) notes.push("data-race witness: compile with -fsanitize=thread");
  if (no_overflow) notes.push("overflow witness: compile with -fsanitize=undefined -fno-sanitize-recover=all");
  logOutput(
    "instrument",
    `Instrumented successfully${notes.length ? " (" + notes.join("; ") + ")" : ""}.`
  );
  return { source, dataRace: !!data_race, noOverflow: !!no_overflow };
}

// ---------------------------------------------------------------------------
// "Download instrumented program": bundles instrumented.c + the project's
// svcomp.c scheduler/stub harness + a Makefile into a .zip (hand-rolled,
// store-only -- no compression library needed for source-sized files).
// ---------------------------------------------------------------------------

let svcompSourceCache = null;

async function getSvcompSource() {
  if (svcompSourceCache === null) {
    const resp = await fetch("svcomp.c");
    svcompSourceCache = await resp.text();
  }
  return svcompSourceCache;
}

function buildMakefile(dataRace, noOverflow) {
  let extraFlags = "";
  let runCmd = "./$(TARGET)";
  if (dataRace) {
    extraFlags += " -fsanitize=thread -g";
    runCmd = 'TSAN_OPTIONS="halt_on_error=1 exitcode=74" ./$(TARGET)';
  }
  if (noOverflow) {
    extraFlags += " -fsanitize=undefined -fno-sanitize-recover=all -g";
    runCmd = 'UBSAN_OPTIONS="halt_on_error=1:exitcode=74:print_stacktrace=1" ./$(TARGET)';
  }
  return `CC ?= gcc
CFLAGS ?= -w -Wno-implicit-function-declaration -pthread${extraFlags}
TARGET ?= a.out
SRCS = instrumented.c svcomp.c

.PHONY: all run clean

all: $(TARGET)

$(TARGET): $(SRCS)
	$(CC) $(CFLAGS) $(SRCS) -o $(TARGET)

run: $(TARGET)
	${runCmd}

clean:
	rm -f $(TARGET)
`;
}

function crc32(bytes) {
  let crc = ~0;
  for (let i = 0; i < bytes.length; i++) {
    crc ^= bytes[i];
    for (let j = 0; j < 8; j++) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return ~crc >>> 0;
}

// Minimal store-only (uncompressed) ZIP writer: local file headers + central
// directory + end record, per the ZIP spec. Verified against `unzip` while
// building this.
function makeZip(files) {
  const localParts = [];
  const centralParts = [];
  const records = [];
  let offset = 0;

  for (const f of files) {
    const nameBytes = f.nameBytes;
    const data = f.data;
    const crc = crc32(data);
    const size = data.length;

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    local.setUint16(6, 0, true);
    local.setUint16(8, 0, true);
    local.setUint16(10, 0, true);
    local.setUint16(12, 0x21, true); // DOS date 1980-01-01; time unused
    local.setUint32(14, crc, true);
    local.setUint32(18, size, true);
    local.setUint32(22, size, true);
    local.setUint16(26, nameBytes.length, true);
    local.setUint16(28, 0, true);
    const localBytes = new Uint8Array(local.buffer);

    localParts.push(localBytes, nameBytes, data);
    records.push({ nameBytes, crc, size, offset });
    offset += localBytes.length + nameBytes.length + data.length;
  }

  const centralOffset = offset;
  for (const rec of records) {
    const central = new DataView(new ArrayBuffer(46));
    central.setUint32(0, 0x02014b50, true);
    central.setUint16(4, 20, true);
    central.setUint16(6, 20, true);
    central.setUint16(8, 0, true);
    central.setUint16(10, 0, true);
    central.setUint16(12, 0, true);
    central.setUint16(14, 0x21, true);
    central.setUint32(16, rec.crc, true);
    central.setUint32(20, rec.size, true);
    central.setUint32(24, rec.size, true);
    central.setUint16(28, rec.nameBytes.length, true);
    central.setUint16(30, 0, true);
    central.setUint16(32, 0, true);
    central.setUint16(34, 0, true);
    central.setUint16(36, 0, true);
    central.setUint32(38, 0, true);
    central.setUint32(42, rec.offset, true);
    centralParts.push(new Uint8Array(central.buffer), rec.nameBytes);
    offset += 46 + rec.nameBytes.length;
  }
  const centralSize = offset - centralOffset;

  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(4, 0, true);
  end.setUint16(6, 0, true);
  end.setUint16(8, records.length, true);
  end.setUint16(10, records.length, true);
  end.setUint32(12, centralSize, true);
  end.setUint32(16, centralOffset, true);
  end.setUint16(20, 0, true);

  return new Blob([...localParts, ...centralParts, new Uint8Array(end.buffer)], {
    type: "application/zip",
  });
}

function makeZipFromTexts(textFiles) {
  const encoder = new TextEncoder();
  return makeZip(
    textFiles.map((f) => ({ nameBytes: encoder.encode(f.name), data: encoder.encode(f.content) }))
  );
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

let instrumentMode = "inplace";

async function runInstrument(mode) {
  if (!workerReady || !cEditor || !yamlEditor) return;
  instrumentBtn.disabled = true;
  instrumentCaret.disabled = true;
  const originalLabel = instrumentBtn.textContent;
  instrumentBtn.textContent = "Instrumenting…";
  try {
    const result = await runInstrumentPipeline();
    if (result === null) return;
    const { source, dataRace } = result;
    if (mode === "download") {
      const svcompSource = await getSvcompSource();
      const zipBlob = makeZipFromTexts([
        { name: "instrumented.c", content: source },
        { name: "svcomp.c", content: svcompSource },
        { name: "Makefile", content: buildMakefile(dataRace, noOverflow) },
      ]);
      const name = (cFilename.textContent || "instrumented").replace(/\.[ci]$/, "") + "-bundle.zip";
      downloadBlob(name, zipBlob);
    } else {
      cEditor.setValue(source);
    }
  } finally {
    instrumentBtn.disabled = false;
    instrumentCaret.disabled = false;
    instrumentBtn.textContent = originalLabel;
  }
}

instrumentBtn.addEventListener("click", () => runInstrument(instrumentMode));
instrumentCaret.addEventListener("click", (e) => {
  e.stopPropagation();
  instrumentMenu.hidden = !instrumentMenu.hidden;
});
document.addEventListener("click", (e) => {
  if (!instrumentMenu.hidden && !e.target.closest("#instrument-split")) {
    instrumentMenu.hidden = true;
  }
});
for (const item of instrumentMenu.querySelectorAll("button[data-mode]")) {
  item.addEventListener("click", () => {
    instrumentMode = item.dataset.mode;
    instrumentBtn.textContent = item.dataset.mode === "download" ? "Download instrumented program" : "Instrument in-place";
    instrumentMenu.hidden = true;
  });
}

// ---------------------------------------------------------------------------
// Compile & Run: takes the C editor's *current* contents verbatim (no
// re-instrumentation -- whatever's in the editor, instrumented or not, is
// what gets compiled) and runs it for real via clang/WASIX, with actual
// multithreading (Web Workers + SharedArrayBuffer), not a simulation.
// ---------------------------------------------------------------------------

compileRunBtn.addEventListener("click", async () => {
  if (compileRunBtn.disabled || !cEditor) return;
  const originalLabel = compileRunBtn.textContent;
  compileRunBtn.disabled = true;
  try {
    const { compileAndRun } = await import("./wasmer-run.js");
    const cSource = cEditor.getValue();
    const svcompSource = await getSvcompSource();
    const result = await compileAndRun(cSource, svcompSource, (status) => {
      compileRunBtn.textContent = status;
      logOutput("clang", status);
    });

    if (result.stage === "compile") {
      logOutput(
        "clang",
        `Compilation failed (exit code ${result.code}):\n\n${result.stderr || result.stdout || "(no output)"}`
      );
      return;
    }

    let verdict;
    if (result.code === 74) {
      verdict = "Property VIOLATED: reach_error() was called (exit code 74) -- the witness's execution was reproduced.";
    } else {
      verdict = `Program exited with code ${result.code} without calling reach_error() -- this run did not reproduce the witness's violation.`;
    }
    logOutput(
      "clang",
      `${verdict}\n\n--- stdout ---\n${result.stdout || "(empty)"}\n--- stderr ---\n${result.stderr || "(empty)"}`
    );
  } catch (err) {
    logOutput("clang", `Compile & Run failed:\n${err && err.stack ? err.stack : err}`);
  } finally {
    compileRunBtn.textContent = originalLabel;
    updateCompileRunButton();
  }
});

// ---------------------------------------------------------------------------
// Sidebar: live sv-benchmarks browser (GitLab API)
// ---------------------------------------------------------------------------

async function fetchCategoryEntries(category) {
  const path = encodeURIComponent(`c/${category}`);
  const url = `${GITLAB_API}/repository/tree?path=${path}&ref=${getSvBenchmarksRef()}&per_page=100`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`GitLab API returned ${resp.status}`);
  const entries = await resp.json();
  return entries
    .filter((e) => e.type === "blob" && e.name.endsWith(".yml"))
    .sort((a, b) => a.name.localeCompare(b.name));
}

async function fetchRawFile(category, filename) {
  const encodedPath = encodeURIComponent(`c/${category}/${filename}`);
  const url = `${GITLAB_API}/repository/files/${encodedPath}/raw?ref=${getSvBenchmarksRef()}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`GitLab API returned ${resp.status}`);
  return resp.text();
}

// SV-COMP task .yml files declare their program(s) as a scalar
// (`input_files: 'foo.c'`), a flow sequence (`input_files: [foo.c]`), or a
// block sequence (`input_files:\n  - foo.c`). We only need the first.
function extractFirstInputFile(taskYaml) {
  // Scalar or flow-sequence form, kept on input_files:'s own line.
  let m = taskYaml.match(/input_files:[ \t]*\[?[ \t]*['"]?([^'",\]\s][^'",\]\n]*)/);
  if (m) return m[1].trim();
  // Block-sequence form: the value is on the following line(s).
  m = taskYaml.match(/input_files:\s*\n\s*-\s*['"]?([^'",\]\s]+)/);
  return m ? m[1] : null;
}

async function loadSvBenchmarkEntry(category, entry) {
  const taskYaml = await fetchRawFile(category, entry.name);
  const programName = extractFirstInputFile(taskYaml);
  if (!programName) {
    throw new Error(`Could not find input_files in ${entry.name}`);
  }
  const text = await fetchRawFile(category, programName);
  cEditor.setValue(text);
  cFilename.textContent = programName;
  yamlEditor.setValue(await buildWitnessSkeleton(programName, text, specSelect.value));
}

async function fetchAllSvBenchmarksCategories() {
  const categories = [];
  let page = 1;
  for (;;) {
    const url = `${GITLAB_API}/repository/tree?path=c&ref=${getSvBenchmarksRef()}&per_page=100&page=${page}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`GitLab API returned ${resp.status}`);
    const entries = await resp.json();
    categories.push(...entries.filter((e) => e.type === "tree").map((e) => e.name));
    const totalPages = parseInt(resp.headers.get("x-total-pages") || "1", 10);
    if (entries.length === 0 || page >= totalPages) break;
    page++;
  }
  return categories.sort((a, b) => a.localeCompare(b));
}

async function renderSvBenchmarksCategories() {
  const list = document.getElementById("sv-benchmarks-categories");
  list.innerHTML = '<li class="loading">Loading categories&hellip;</li>';
  let categories;
  try {
    categories = await fetchAllSvBenchmarksCategories();
  } catch (err) {
    list.innerHTML = "";
    const errLi = document.createElement("li");
    errLi.className = "empty";
    errLi.textContent = `Failed to list categories: ${err.message}`;
    list.appendChild(errLi);
    return;
  }
  list.innerHTML = "";
  for (const category of categories) {
    const li = document.createElement("li");
    li.className = "category";
    li.textContent = `c/${category}`;
    let expanded = false;
    let entriesList = null;
    li.addEventListener("click", async () => {
      expanded = !expanded;
      li.classList.toggle("open", expanded);
      if (!expanded) {
        if (entriesList) entriesList.remove();
        entriesList = null;
        return;
      }
      entriesList = document.createElement("ul");
      entriesList.className = "example-list";
      const loadingLi = document.createElement("li");
      loadingLi.className = "loading";
      loadingLi.textContent = "Loading…";
      entriesList.appendChild(loadingLi);
      li.after(entriesList);
      try {
        const entries = await fetchCategoryEntries(category);
        entriesList.innerHTML = "";
        if (entries.length === 0) {
          const emptyLi = document.createElement("li");
          emptyLi.className = "empty";
          emptyLi.textContent = "(no .yml task files)";
          entriesList.appendChild(emptyLi);
        }
        for (const entry of entries) {
          const fileLi = document.createElement("li");
          fileLi.className = "file";
          fileLi.textContent = entry.name;
          fileLi.addEventListener("click", (ev) => {
            ev.stopPropagation();
            loadSvBenchmarkEntry(category, entry).catch((err) =>
              logOutput("linter", `Failed to load ${entry.name}:\n${err}`)
            );
          });
          entriesList.appendChild(fileLi);
        }
      } catch (err) {
        entriesList.innerHTML = "";
        const errLi = document.createElement("li");
        errLi.className = "empty";
        errLi.textContent = `Failed to list: ${err.message}`;
        entriesList.appendChild(errLi);
      }
    });
    list.appendChild(li);
  }
}

// ---------------------------------------------------------------------------
// Sidebar: live sv-witnesses examples browser (GitLab API)
// ---------------------------------------------------------------------------

async function fetchSvWitnessesExamples() {
  const url = `${SV_WITNESSES_API}/repository/tree?path=examples&ref=${getSvWitnessesRef()}&per_page=100`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`GitLab API returned ${resp.status}`);
  const entries = await resp.json();
  return entries
    .filter((e) => e.type === "blob" && e.name.endsWith(".yml"))
    .sort((a, b) => a.name.localeCompare(b.name));
}

async function fetchSvWitnessesRawFile(filename) {
  const encodedPath = encodeURIComponent(`examples/${filename}`);
  const url = `${SV_WITNESSES_API}/repository/files/${encodedPath}/raw?ref=${getSvWitnessesRef()}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`GitLab API returned ${resp.status}`);
  return resp.text();
}

async function loadSvWitnessExample(entry) {
  const witnessYaml = await fetchSvWitnessesRawFile(entry.name);
  const programRef = extractFirstInputFile(witnessYaml);
  if (!programRef) {
    throw new Error(`Could not find task.input_files in ${entry.name}`);
  }
  // These examples reference siblings within the same examples/ directory,
  // sometimes as "./foo.c" -- only the basename is ever needed.
  const programName = programRef.replace(/^\.\//, "").split("/").pop();
  const programText = await fetchSvWitnessesRawFile(programName);
  cEditor.setValue(programText);
  cFilename.textContent = programName;
  yamlEditor.setValue(witnessYaml);
}

async function renderSvWitnessesExamples() {
  const list = document.getElementById("sv-witnesses-examples");
  list.innerHTML = '<li class="loading">Loading examples&hellip;</li>';
  let entries;
  try {
    entries = await fetchSvWitnessesExamples();
  } catch (err) {
    list.innerHTML = "";
    const errLi = document.createElement("li");
    errLi.className = "empty";
    errLi.textContent = `Failed to list examples: ${err.message}`;
    list.appendChild(errLi);
    return;
  }
  list.innerHTML = "";
  for (const entry of entries) {
    const li = document.createElement("li");
    li.className = "file";
    li.textContent = entry.name;
    li.addEventListener("click", () => {
      loadSvWitnessExample(entry).catch((err) =>
        logOutput("linter", `Failed to load ${entry.name}:\n${err}`)
      );
    });
    list.appendChild(li);
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

function wireRefPicker(inputId, onChange) {
  const input = document.getElementById(inputId);
  input.addEventListener("change", onChange);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") input.blur(); // triggers the change listener above
  });
}

wireRefPicker("sv-witnesses-ref", () => renderSvWitnessesExamples());
wireRefPicker("sv-benchmarks-ref", () => renderSvBenchmarksCategories());

renderLocalExamples();
renderSvWitnessesExamples();
renderSvBenchmarksCategories();
initEditors();
