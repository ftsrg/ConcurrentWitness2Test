// Compiles and runs the C editor's *current* contents (verbatim -- the
// caller must not re-instrument it) together with svcomp.c, using the
// Wasmer JS SDK's WASIX runtime: real clang (the "clang/clang" Wasmer
// registry package) compiles to wasm32-wasix, and the resulting module
// runs with real multithreading (Web Workers + SharedArrayBuffer), not a
// single-threaded simulation. Both the SDK and clang's wasm itself are
// fetched lazily on first use -- clang in particular is ~100MB and comes
// straight from Wasmer's registry, not vendored, mirroring how Pyodide is
// loaded from a CDN at runtime elsewhere in this app.

let sdkModulePromise = null;
let clangPackagePromise = null;

async function getSdk() {
  if (!sdkModulePromise) {
    sdkModulePromise = (async () => {
      const mod = await import("./vendor/wasmer/index.mjs");
      // setWorkerUrl reaches into the wasm-bindgen exports object, which
      // only exists once init() has loaded and instantiated the wasm --
      // calling it first throws (exports object is still undefined).
      await mod.init();
      mod.setWorkerUrl(new URL("./vendor/wasmer/worker.mjs", import.meta.url).toString());
      return mod;
    })();
  }
  return sdkModulePromise;
}

async function getClang(mod) {
  if (!clangPackagePromise) {
    clangPackagePromise = mod.Wasmer.fromRegistry("clang/clang");
  }
  return clangPackagePromise;
}

// onStatus(text) is called with short progress updates as compilation
// proceeds through its stages (first run is slow: SDK init + ~100MB clang
// package fetch). Returns { stage: "compile"|"run", code, stdout, stderr }.
export async function compileAndRun(cSource, svcompSource, onStatus) {
  onStatus?.("Loading Wasmer SDK…");
  const mod = await getSdk();

  onStatus?.("Fetching clang (≈100MB on first run, cached after)…");
  const clang = await getClang(mod);

  const project = new mod.Directory();
  await project.writeFile("program.c", cSource);
  await project.writeFile("svcomp.c", svcompSource);

  onStatus?.("Compiling with clang (-pthread, wasm32-wasix)…");
  const compile = await clang.entrypoint.run({
    args: ["/project/program.c", "/project/svcomp.c", "-pthread", "-o", "/project/a.wasm"],
    mount: { "/project": project },
  });
  const compileResult = await compile.wait();
  if (compileResult.code !== 0) {
    return {
      stage: "compile",
      code: compileResult.code,
      stdout: compileResult.stdout,
      stderr: compileResult.stderr,
    };
  }

  onStatus?.("Running with real multithreading…");
  const wasmBytes = await project.readFile("a.wasm");
  const program = await mod.Wasmer.fromFile(wasmBytes);
  const instance = await program.entrypoint.run();
  const runResult = await instance.wait();
  return {
    stage: "run",
    code: runResult.code,
    stdout: runResult.stdout,
    stderr: runResult.stderr,
  };
}
