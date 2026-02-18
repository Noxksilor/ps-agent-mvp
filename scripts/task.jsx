// task.jsx — Photoshop ExtendScript
// Executed by Photoshop via:  Photoshop.exe -r scripts\task.jsx
//
// Reads config.json from the repo root (two levels above this file),
// composites layers, and exports a PNG to the path specified in config.
//
// Log is written to the same directory as the output PNG (run.log).

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

  function norm(p) { return p.replace(/\\/g, "/"); }

  function joinPath(a, b) {
    if (!a) return b;
    var sep = (a.charAt(a.length - 1) === "/" || a.charAt(a.length - 1) === "\\") ? "" : "/";
    return a + sep + b;
  }

  function ensureFolder(path) {
    var f = new Folder(path);
    if (!f.exists) f.create();
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

  // ── Resolve paths ────────────────────────────────────────────────────────

  // jobRoot = repo root = parent of the "scripts" folder
  var scriptFile = new File($.fileName);
  var jobRoot    = norm(scriptFile.parent.parent.fsName);

  var configPath = norm(joinPath(jobRoot, "config.json"));

  // ── Bootstrap log (before we know the real log path) ────────────────────
  var bootstrapLog = norm(joinPath(jobRoot, "out/bootstrap.log"));
  ensureFolder(norm(joinPath(jobRoot, "out")));
  writeLog(bootstrapLog, "JSX start. jobRoot=" + jobRoot + "  config=" + configPath);

  // ── Main ─────────────────────────────────────────────────────────────────
  try {
    var cfg = parseJson(readText(configPath));

    // Resolve output PNG path
    var outRel  = (cfg.export && cfg.export.png && cfg.export.png.path)
                  ? cfg.export.png.path
                  : "out/final.png";
    var outPath = norm(joinPath(jobRoot, outRel));
    var outDir  = norm(new File(outPath).parent.fsName);
    ensureFolder(outDir);

    var logPath = norm(joinPath(outDir, "run.log"));
    writeLog(logPath, "JSX start. config=" + configPath);
    writeLog(logPath, "Output PNG: " + outPath);

    // Open base image
    var baseRel  = (cfg.base && cfg.base.path) ? cfg.base.path : "input/base.png";
    var basePath = norm(joinPath(jobRoot, baseRel));
    if (!(new File(basePath)).exists) throw new Error("Base image missing: " + basePath);

    var doc = app.open(new File(basePath));
    writeLog(logPath, "Opened base: " + basePath);

    // Place layers
    var layers = cfg.layers || [];
    for (var i = 0; i < layers.length; i++) {
      var L = layers[i];
      if (!L || L.type !== "image") continue;

      var assetPath = norm(joinPath(jobRoot, L.path));
      var af = new File(assetPath);
      if (!af.exists) {
        writeLog(logPath, "WARN: asset missing, skipping: " + assetPath);
        continue;
      }

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

      writeLog(logPath, "Placed " + doc.activeLayer.name +
               " at (" + x + "," + y + ") scale=" + scale + " rot=" + rotate);
    }

    // Export PNG
    var outFile  = new File(outPath);
    var pngOpts  = new PNGSaveOptions();
    pngOpts.compression = 6;
    doc.saveAs(outFile, pngOpts, true, Extension.LOWERCASE);
    writeLog(logPath, "Saved PNG: " + outPath);

    // Optionally export PSD
    var psdCfg = (cfg.export && cfg.export.psd) ? cfg.export.psd : {};
    if (psdCfg.enabled) {
      var psdRel  = psdCfg.path || "out/final.psd";
      var psdPath = norm(joinPath(jobRoot, psdRel));
      var psdOpts = new PhotoshopSaveOptions();
      doc.saveAs(new File(psdPath), psdOpts, true, Extension.LOWERCASE);
      writeLog(logPath, "Saved PSD: " + psdPath);
    }

    doc.close(SaveOptions.DONOTSAVECHANGES);
    writeLog(logPath, "JSX done OK");

  } catch (err) {
    // Write error to both bootstrap log and (if known) run.log
    writeLog(bootstrapLog, "ERROR: " + err.message + " (line " + err.line + ")");
    try { writeLog(logPath, "ERROR: " + err.message + " (line " + err.line + ")"); } catch (e2) {}
  }

})();
