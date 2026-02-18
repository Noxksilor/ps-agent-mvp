// task.jsx — Photoshop ExtendScript
// Executed by Photoshop via:  Photoshop.exe -r scripts\task.jsx
//
// Reads config.json from the repo root (two levels above this file),
// composites layers, and exports a PNG to the path specified in config.
//
// Logs are written to:
//   out/bootstrap.log          — very early errors (before config is read)
//   out/<job_id>/run.log       — full per-run log

#target photoshop
app.displayDialogs = DialogModes.NO;

(function () {

  // ── Utilities ────────────────────────────────────────────────────────────

  function nowStr() {
    var d = new Date();
    function z(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-" + z(d.getMonth() + 1) + "-" + z(d.getDate()) +
           " " + z(d.getHours()) + ":" + z(d.getMinutes()) + ":" + z(d.getSeconds());
  }

  // Normalise backslashes → forward slashes
  function norm(p) { return p.replace(/\\/g, "/"); }

  function joinPath(a, b) {
    if (!a) return b;
    var sep = (a.charAt(a.length - 1) === "/" || a.charAt(a.length - 1) === "\\") ? "" : "/";
    return a + sep + b;
  }

  function ensureFolder(path) {
    var f = new Folder(path);
    if (!f.exists) {
      var ok = f.create();
      if (!ok) throw new Error("Cannot create folder: " + path);
    }
  }

  function writeLog(logPath, msg) {
    try {
      var f = new File(logPath);
      f.encoding = "UTF-8";
      f.open("a");
      f.writeln(nowStr() + " | " + msg);
      f.close();
    } catch (e) { /* swallow — don't let logging kill the job */ }
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
    // Strip UTF-8 BOM if present
    if (s.charCodeAt(0) === 0xFEFF) s = s.slice(1);
    if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(s);
    return eval("(" + s + ")");   // fallback for older PS versions
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

  // ── Resolve repo root ────────────────────────────────────────────────────
  //
  // Priority order:
  //   1. __jobRoot__  — injected by orchestrator.py via COM preamble (most reliable)
  //   2. __jsxFile__  — injected by orchestrator.py (derive parent.parent)
  //   3. $.fileName   — set by PS when run via File > Scripts > Browse
  //
  // Using __jobRoot__ directly avoids all File API path resolution issues.

  var jobRoot;

  if (typeof __jobRoot__ !== "undefined" && __jobRoot__) {
    // Best case: Python injected the absolute repo root directly
    jobRoot = norm(__jobRoot__);
  } else {
    // Fallback: derive from script file path
    var _selfPath = (typeof __jsxFile__ !== "undefined" && __jsxFile__)
                    ? __jsxFile__
                    : $.fileName;
    var scriptFile     = new File(_selfPath);
    var scriptAbsolute = scriptFile.absoluteURI;
    var scriptsFolder  = new File(scriptAbsolute).parent;
    var repoFolder     = scriptsFolder.parent;
    jobRoot = norm(repoFolder.fsName);
  }

  var configPath   = norm(joinPath(jobRoot, "config.json"));
  var bootstrapLog = norm(joinPath(jobRoot, "out/bootstrap.log"));

  // Ensure out/ exists before we try to write bootstrap.log
  try { ensureFolder(norm(joinPath(jobRoot, "out"))); } catch (e) {}

  // ── Super-early debug write (hardcoded path from __jobRoot__) ────────────
  // This is the very first file write. If this fails, Photoshop has no
  // write access to the output directory at all.
  try {
    var _earlyDebug = norm(joinPath(jobRoot, "out/jsx_debug.txt"));
    var _df = new File(_earlyDebug);
    _df.encoding = "UTF-8";
    _df.open("a");
    _df.writeln(nowStr() + " | JSX reached early-debug checkpoint. jobRoot=" + jobRoot);
    _df.close();
  } catch (_de) { /* if even this fails, nothing can be done */ }

  writeLog(bootstrapLog, "=== JSX start ===");
  writeLog(bootstrapLog, "jobRoot source = " +
           (typeof __jobRoot__ !== "undefined" && __jobRoot__ ? "__jobRoot__" :
            (typeof __jsxFile__ !== "undefined" && __jsxFile__ ? "__jsxFile__" : "$.fileName")));
  writeLog(bootstrapLog, "jobRoot      = " + jobRoot);
  writeLog(bootstrapLog, "configPath   = " + configPath);
  writeLog(bootstrapLog, "config exists? " + (new File(configPath)).exists);

  // ── Main ─────────────────────────────────────────────────────────────────
  var logPath;   // declared here so the catch block can reach it

  try {

    // 1. Read config ─────────────────────────────────────────────────────────
    if (!(new File(configPath)).exists) {
      throw new Error("config.json not found at: " + configPath);
    }
    var cfg = parseJson(readText(configPath));
    writeLog(bootstrapLog, "Config parsed OK. job_id=" + (cfg.job_id || "(none)"));

    // 2. Resolve output PNG path ──────────────────────────────────────────────
    var outRel  = (cfg.export && cfg.export.png && cfg.export.png.path)
                  ? cfg.export.png.path
                  : "out/final.png";
    var outPath = norm(joinPath(jobRoot, outRel));
    var outDir  = norm(new File(outPath).parent.fsName);
    ensureFolder(outDir);

    logPath = norm(joinPath(outDir, "run.log"));
    writeLog(logPath, "=== JSX start ===");
    writeLog(logPath, "jobRoot    = " + jobRoot);
    writeLog(logPath, "configPath = " + configPath);
    writeLog(logPath, "outPath    = " + outPath);
    writeLog(logPath, "outDir     = " + outDir);

    // 3. Open base image ──────────────────────────────────────────────────────
    var baseRel  = (cfg.base && cfg.base.path) ? cfg.base.path : "input/base.png";
    var basePath = norm(joinPath(jobRoot, baseRel));
    writeLog(logPath, "basePath   = " + basePath);
    writeLog(logPath, "base exists? " + (new File(basePath)).exists);

    if (!(new File(basePath)).exists) {
      throw new Error("Base image missing: " + basePath);
    }

    var openOpts = new OpenOptions();
    var doc = app.open(new File(basePath), openOpts);
    writeLog(logPath, "Opened base: " + basePath +
             "  (" + doc.width.as("px") + "x" + doc.height.as("px") + "px)");

    // 4. Place layers ─────────────────────────────────────────────────────────
    var layers = cfg.layers || [];
    writeLog(logPath, "Layers to place: " + layers.length);

    for (var i = 0; i < layers.length; i++) {
      var L = layers[i];
      if (!L || L.type !== "image") {
        writeLog(logPath, "Skipping layer[" + i + "] (type=" + (L ? L.type : "null") + ")");
        continue;
      }

      var assetPath = norm(joinPath(jobRoot, L.path));
      writeLog(logPath, "Layer[" + i + "] assetPath=" + assetPath +
               "  exists=" + (new File(assetPath)).exists);

      var af = new File(assetPath);
      if (!af.exists) {
        writeLog(logPath, "WARN: asset missing, skipping: " + assetPath);
        continue;
      }

      var assetDoc = app.open(af);
      writeLog(logPath, "Opened asset: " + assetPath);

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

      writeLog(logPath, "Placed " + doc.activeLayer.name +
               " at (" + x + "," + y + ") scale=" + scale + " rot=" + rotate);
    }

    // 5. Export PNG ───────────────────────────────────────────────────────────
    //
    // doc.saveAs() with PNGSaveOptions is deprecated in Photoshop 2022+.
    // Use exportDocument() with ExportType.SAVEFORWEB for reliable PNG output
    // across all modern PS versions.  Fall back to saveAs if exportDocument
    // is not available (very old PS).

    writeLog(logPath, "Exporting PNG to: " + outPath);

    var outFile = new File(outPath);

    try {
      // Modern path: Save for Web (PNG-24, no lossy compression)
      var sfwOpts = new ExportOptionsSaveForWeb();
      sfwOpts.format        = SaveDocumentType.PNG;
      sfwOpts.PNG8          = false;   // PNG-24
      sfwOpts.transparency  = true;
      sfwOpts.interlaced    = false;
      sfwOpts.quality       = 100;
      doc.exportDocument(outFile, ExportType.SAVEFORWEB, sfwOpts);
      writeLog(logPath, "Saved PNG (exportDocument/SaveForWeb): " + outPath);
    } catch (exportErr) {
      // Fallback: classic saveAs with PNGSaveOptions
      writeLog(logPath, "exportDocument failed (" + exportErr.message + "), trying saveAs fallback");
      var pngOpts = new PNGSaveOptions();
      pngOpts.compression = 6;
      doc.saveAs(outFile, pngOpts, true, Extension.LOWERCASE);
      writeLog(logPath, "Saved PNG (saveAs fallback): " + outPath);
    }

    // Verify the file was actually written
    if ((new File(outPath)).exists) {
      writeLog(logPath, "Verified: output file exists (" +
               Math.round((new File(outPath)).length / 1024) + " KB)");
    } else {
      throw new Error("PNG was not created at: " + outPath);
    }

    // 6. Optionally export PSD ────────────────────────────────────────────────
    var psdCfg = (cfg.export && cfg.export.psd) ? cfg.export.psd : {};
    if (psdCfg.enabled) {
      var psdRel  = psdCfg.path || "out/final.psd";
      var psdPath = norm(joinPath(jobRoot, psdRel));
      var psdOpts = new PhotoshopSaveOptions();
      doc.saveAs(new File(psdPath), psdOpts, true, Extension.LOWERCASE);
      writeLog(logPath, "Saved PSD: " + psdPath);
    }

    doc.close(SaveOptions.DONOTSAVECHANGES);
    writeLog(logPath, "=== JSX done OK ===");
    writeLog(bootstrapLog, "JSX done OK. Output: " + outPath);

  } catch (err) {
    var errMsg = "ERROR: " + err.message + " (line " + err.line + ")";
    writeLog(bootstrapLog, errMsg);
    if (logPath) {
      try { writeLog(logPath, errMsg); } catch (e2) {}
    }
    // Re-throw so Photoshop's own error handler also records it
    // (comment out if you don't want a PS error dialog)
    // throw err;
  }

})();
