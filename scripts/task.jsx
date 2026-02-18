// task.jsx — Photoshop ExtendScript
// Executed by orchestrator.py via COM DoJavaScript()
//
// IMPORTANT: This Photoshop build can ONLY write files to C:\Users\Public\...
// All logs and output files MUST go there. Writing anywhere else silently fails.
//
// Input files (base.png, asset_01.png) are read from __jobRoot__ (injected by Python).
// Output PNG goes to the path from config (export.png.path), which MUST be in C:\Users\Public\...
//
// Debug logs:
//   C:\Users\Public\ps_agent_jsx_debug.txt    — step-by-step progress log
//   C:\Users\Public\ps_agent_bootstrap.log    — detailed bootstrap log

#target photoshop
app.displayDialogs = DialogModes.NO;

(function () {

  // ══════════════════════════════════════════════════════════════════════════
  // CONFIGURATION — all writable paths are in C:\Users\Public\...
  // ══════════════════════════════════════════════════════════════════════════

  // These are the ONLY paths where this Photoshop build can write files.
  // DO NOT change these to any other location — they will silently fail.
  var PUBLIC_DIR       = "C:/Users/Public";
  var DEBUG_LOG_PATH   = "C:/Users/Public/ps_agent_jsx_debug.txt";
  var BOOTSTRAP_LOG    = "C:/Users/Public/ps_agent_bootstrap.log";

  // ══════════════════════════════════════════════════════════════════════════
  // UTILITIES
  // ══════════════════════════════════════════════════════════════════════════

  function nowStr() {
    var d = new Date();
    function z(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-" + z(d.getMonth() + 1) + "-" + z(d.getDate()) +
           " " + z(d.getHours()) + ":" + z(d.getMinutes()) + ":" + z(d.getSeconds());
  }

  function norm(p) { return p.replace(/\\/g, "/"); }

  function joinPath(a, b) {
    if (!a) return b;
    var sep = (a.charAt(a.length - 1) === "/" || a.charAt(a.length - 1) === "\\") ? "" : "/";
    return a + sep + b;
  }

  // Write to a log file (append mode). ONLY use paths in C:\Users\Public\...
  function writeLog(logPath, msg) {
    try {
      var f = new File(logPath);
      f.encoding = "UTF-8";
      f.open("a");
      f.writeln(nowStr() + " | " + msg);
      f.close();
    } catch (e) {
      // If even C:\Users\Public fails, there's nothing we can do
    }
  }

  // Write to the debug log (convenience function)
  function debug(msg) {
    writeLog(DEBUG_LOG_PATH, msg);
  }

  function readText(path) {
    var f = new File(path);
    if (!f.exists) throw new Error("File not found: " + path);
    f.encoding = "UTF-8";
    f.open("r");
    var s = f.read();
    f.close();
    return s;
  }

  function parseJson(s) {
    if (s.charCodeAt(0) === 0xFEFF) s = s.slice(1);  // Strip BOM
    if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(s);
    return eval("(" + s + ")");
  }

  function getBoundsPx(layer) {
    var b = layer.bounds;
    return { l: b[0].as("px"), t: b[1].as("px"), r: b[2].as("px"), b: b[3].as("px") };
  }

  function moveCenterTo(layer, x, y) {
    var bb = getBoundsPx(layer);
    var cx = (bb.l + bb.r) / 2.0;
    var cy = (bb.t + bb.b) / 2.0;
    layer.translate(x - cx, y - cy);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // MAIN
  // ══════════════════════════════════════════════════════════════════════════

  // Clear debug log at start (overwrite with fresh run info)
  try {
    var _df = new File(DEBUG_LOG_PATH);
    _df.encoding = "UTF-8";
    _df.open("w");
    _df.writeln(nowStr() + " | === JSX START ===");
    _df.close();
  } catch (e) {}

  debug("step: init");
  writeLog(BOOTSTRAP_LOG, "=== JSX START ===");

  try {

    // ── 1. Resolve jobRoot (injected by Python) ──────────────────────────────
    debug("step: resolve jobRoot");

    var jobRoot;
    if (typeof __jobRoot__ !== "undefined" && __jobRoot__) {
      jobRoot = norm(__jobRoot__);
      debug("jobRoot source: __jobRoot__");
      debug("jobRoot: " + jobRoot);
    } else {
      debug("ERROR: __jobRoot__ not injected by orchestrator");
      writeLog(BOOTSTRAP_LOG, "ERROR: __jobRoot__ not injected");
      return;  // Cannot proceed
    }

    writeLog(BOOTSTRAP_LOG, "jobRoot: " + jobRoot);

    // ── 2. Read config ───────────────────────────────────────────────────────
    debug("step: read config");

    var configPath = norm(joinPath(jobRoot, "config.json"));
    debug("configPath: " + configPath);

    var configFile = new File(configPath);
    if (!configFile.exists) {
      debug("ERROR: config.json not found");
      writeLog(BOOTSTRAP_LOG, "ERROR: config.json not found at " + configPath);
      return;
    }
    debug("config exists: true");

    var cfg = parseJson(readText(configPath));
    debug("config loaded: true");
    debug("job_id: " + (cfg.job_id || "(none)"));
    writeLog(BOOTSTRAP_LOG, "config loaded OK. job_id=" + (cfg.job_id || "(none)"));

    // ── 3. Resolve output PNG path ───────────────────────────────────────────
    debug("step: resolve output path");

    var outPath = (cfg.export && cfg.export.png && cfg.export.png.path)
                  ? norm(cfg.export.png.path)
                  : null;

    if (!outPath) {
      debug("ERROR: export.png.path not set in config");
      writeLog(BOOTSTRAP_LOG, "ERROR: export.png.path not set");
      return;
    }

    // Verify output path is in C:\Users\Public\... (our only writable location)
    if (outPath.toLowerCase().indexOf("c:/users/public") !== 0) {
      debug("WARNING: output path NOT in C:/Users/Public - may fail: " + outPath);
      writeLog(BOOTSTRAP_LOG, "WARNING: output path not in C:/Users/Public: " + outPath);
    }

    debug("output PNG: " + outPath);
    writeLog(BOOTSTRAP_LOG, "output PNG: " + outPath);

    // ── 4. Check input files ─────────────────────────────────────────────────
    debug("step: check input files");

    var baseRel  = (cfg.base && cfg.base.path) ? cfg.base.path : "input/base.png";
    var basePath = norm(joinPath(jobRoot, baseRel));
    debug("basePath: " + basePath);

    var baseFile = new File(basePath);
    if (!baseFile.exists) {
      debug("ERROR: base image not found: " + basePath);
      writeLog(BOOTSTRAP_LOG, "ERROR: base image not found: " + basePath);
      return;
    }
    debug("base exists: true");

    // Check assets
    var layers = cfg.layers || [];
    debug("layers count: " + layers.length);

    for (var i = 0; i < layers.length; i++) {
      var L = layers[i];
      if (!L || L.type !== "image") continue;

      var assetPath = norm(joinPath(jobRoot, L.path));
      var assetFile = new File(assetPath);
      debug("asset[" + i + "] " + L.name + " exists: " + assetFile.exists);

      if (!assetFile.exists) {
        debug("WARNING: asset missing: " + assetPath);
        writeLog(BOOTSTRAP_LOG, "WARNING: asset missing: " + assetPath);
      }
    }

    // ── 5. Open base image ───────────────────────────────────────────────────
    debug("step: open base image");

    var doc = app.open(baseFile);
    debug("base opened: " + doc.width.as("px") + "x" + doc.height.as("px") + "px");
    writeLog(BOOTSTRAP_LOG, "base opened: " + basePath);

    // ── 6. Place layers ──────────────────────────────────────────────────────
    debug("step: place layers");

    for (var i = 0; i < layers.length; i++) {
      var L = layers[i];
      if (!L || L.type !== "image") continue;

      var assetPath = norm(joinPath(jobRoot, L.path));
      var af = new File(assetPath);
      if (!af.exists) {
        debug("skip asset[" + i + "]: not found");
        continue;
      }

      debug("placing asset[" + i + "]: " + L.name);

      var assetDoc = app.open(af);
      assetDoc.activeLayer.name = L.name ? L.name : ("asset_" + (i + 1));
      assetDoc.activeLayer.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
      assetDoc.close(SaveOptions.DONOTSAVECHANGES);

      doc.activeLayer = doc.layers[0];

      var t      = L.transform || {};
      var scale  = (typeof t.scale  === "number") ? t.scale  : 100;
      var rotate = (typeof t.rotate === "number") ? t.rotate : 0;
      var x      = (typeof t.x      === "number") ? t.x      : (doc.width.as("px")  / 2.0);
      var y      = (typeof t.y      === "number") ? t.y      : (doc.height.as("px") / 2.0);

      if (scale  !== 100) doc.activeLayer.resize(scale, scale, AnchorPosition.MIDDLECENTER);
      if (rotate !== 0)   doc.activeLayer.rotate(rotate, AnchorPosition.MIDDLECENTER);
      moveCenterTo(doc.activeLayer, x, y);

      debug("placed: " + L.name + " at (" + x + "," + y + ") scale=" + scale);
    }

    // ── 7. Export PNG ────────────────────────────────────────────────────────
    debug("step: export PNG");

    var outFile = new File(outPath);

    // Try modern exportDocument first, fall back to saveAs
    try {
      var sfwOpts = new ExportOptionsSaveForWeb();
      sfwOpts.format       = SaveDocumentType.PNG;
      sfwOpts.PNG8         = false;  // PNG-24
      sfwOpts.transparency = true;
      sfwOpts.interlaced   = false;
      sfwOpts.quality      = 100;
      doc.exportDocument(outFile, ExportType.SAVEFORWEB, sfwOpts);
      debug("export method: exportDocument/SaveForWeb");
    } catch (exportErr) {
      debug("exportDocument failed, trying saveAs: " + exportErr.message);
      var pngOpts = new PNGSaveOptions();
      pngOpts.compression = 6;
      doc.saveAs(outFile, pngOpts, true, Extension.LOWERCASE);
      debug("export method: saveAs fallback");
    }

    // Verify output
    var verifyFile = new File(outPath);
    if (verifyFile.exists && verifyFile.length > 0) {
      var sizeKB = Math.round(verifyFile.length / 1024);
      debug("export ok: " + outPath + " (" + sizeKB + " KB)");
      writeLog(BOOTSTRAP_LOG, "EXPORT OK: " + outPath + " (" + sizeKB + " KB)");
    } else {
      debug("export failed: file not created or empty");
      writeLog(BOOTSTRAP_LOG, "EXPORT FAILED: " + outPath);
    }

    // ── 8. Close document ────────────────────────────────────────────────────
    doc.close(SaveOptions.DONOTSAVECHANGES);
    debug("document closed");

    // ── 9. Done ──────────────────────────────────────────────────────────────
    debug("step: done");
    debug("=== JSX END OK ===");
    writeLog(BOOTSTRAP_LOG, "=== JSX END OK ===");

  } catch (err) {
    var errMsg = "ERROR: " + err.message + " (line " + err.line + ")";
    debug("exception: " + errMsg);
    writeLog(BOOTSTRAP_LOG, errMsg);
  }

})();
