# Stubbed for the browser/Pyodide build: no libclang is available in-wasm.
# witnesslint/yaml_linter/yaml_linter.py already wraps the one call site
# (get_stmt_locations_from_source, used only by --strictChecking) in a
# try/except that logs a warning and continues with ast_nodes=None, so this
# stub simply needs to fail loudly without an import-time crash. Installed
# over the real witnesslint/clang_ast.py at Docker build time.
def get_stmt_locations_from_source(program):
    raise NotImplementedError(
        "clang AST cross-checking (--strictChecking) is not available "
        "in the browser build of witnesslint."
    )
