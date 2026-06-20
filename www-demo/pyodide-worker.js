// Web Worker owning the Pyodide runtime. Both the live linter and the
// instrumenter run here so the UI thread (and Monaco) never blocks.
//
// Pyodide itself is loaded from the jsdelivr CDN at runtime rather than
// vendored: the site already depends on network access for the live
// sv-benchmarks browser (GitLab API), and the full Pyodide distribution
// (~400MB) is impractical to vendor, while pyodide-core lacks the
// pyyaml/lxml/jsonschema builds we need. Monaco is vendored locally since
// it is the primary UI and reasonably sized.
const PYODIDE_VERSION = "0.29.4";
const PYODIDE_INDEX_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

importScripts(PYODIDE_INDEX_URL + "pyodide.js");

let pyodideReadyPromise = null;

async function initPyodide() {
  const pyodide = await loadPyodide({ indexURL: PYODIDE_INDEX_URL });
  await pyodide.loadPackage([
    "pyyaml",
    "lxml",
    "jsonschema",
    "pycparser",
    "networkx",
    "micropip",
  ]);

  const micropip = pyodide.pyimport("micropip");
  const wheelUrl = new URL(
    "vendor/pypi/pcpp-1.30-py2.py3-none-any.whl",
    self.location.href
  ).toString();
  await micropip.install(wheelUrl);

  const zipResp = await fetch(new URL("py.zip", self.location.href));
  const zipBuf = await zipResp.arrayBuffer();
  pyodide.unpackArchive(zipBuf, "zip", { extractDir: "/" });

  pyodide.FS.mkdirTree("/work");
  await pyodide.runPythonAsync(`
import sys
for p in ("/py", "/py/cwt"):
    if p not in sys.path:
        sys.path.insert(0, p)
import shim  # noqa: F401  (import once now so later calls are fast)
`);

  return pyodide;
}

function getPyodide() {
  if (!pyodideReadyPromise) {
    pyodideReadyPromise = initPyodide();
  }
  return pyodideReadyPromise;
}

// Kick off loading immediately so it's ready by the time the user acts.
getPyodide().then(
  () => postMessage({ cmd: "ready" }),
  (err) => postMessage({ cmd: "error", error: String(err) })
);

self.onmessage = async (event) => {
  const { id, cmd } = event.data;
  try {
    const pyodide = await getPyodide();
    const shim = pyodide.pyimport("shim");

    if (cmd === "lint") {
      const { yaml, c, strict } = event.data;
      pyodide.FS.writeFile("/work/witness.yml", yaml);
      let programPath = null;
      if (c !== null && c !== undefined) {
        pyodide.FS.writeFile("/work/program.c", c);
        programPath = "/work/program.c";
      }
      const result = shim.lint("/work/witness.yml", programPath, !!strict).toJs({
        dict_converter: Object.fromEntries,
      });
      postMessage({ id, cmd, ok: true, result });
    } else if (cmd === "instrument") {
      const { c, yaml } = event.data;
      pyodide.FS.writeFile("/work/input.c", c);
      pyodide.FS.writeFile("/work/witness.yml", yaml);
      const result = shim.instrument("/work/input.c", "/work/witness.yml").toJs({
        dict_converter: Object.fromEntries,
      });
      postMessage({ id, cmd, ok: true, result });
    } else {
      postMessage({ id, cmd, ok: false, error: `Unknown command: ${cmd}` });
    }
  } catch (err) {
    postMessage({ id, cmd, ok: false, error: String(err && err.message ? err.message : err) });
  }
};
