#target photoshop
app.displayDialogs = DialogModes.NO;

(function () {

  function nowStr() {
    var d = new Date();
    function z(n){ return (n<10?'0':'')+n; }
    return d.getFullYear()+"-"+z(d.getMonth()+1)+"-"+z(d.getDate())+" "+z(d.getHours())+":"+z(d.getMinutes())+":"+z(d.getSeconds());
  }

  function joinPath(a, b) {
    if (!a) return b;
    if (a.charAt(a.length-1) === "/" || a.charAt(a.length-1) === "\\") return a + b;
    return a + "/" + b;
  }

  function norm(p){ return p.replace(/\\/g, "/"); }

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
    } catch (e) {}
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
    if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(s);
    return eval("(" + s + ")");
  }

  function getBoundsPx(layer) {
    var b = layer.bounds;
    return { l:b[0].as("px"), t:b[1].as("px"), r:b[2].as("px"), b:b[3].as("px") };
  }

  function moveCenterTo(layer, x, y) {
    var bb = getBoundsPx(layer);
    var cx = (bb.l + bb.r) / 2.0;
    var cy = (bb.t + bb.b) / 2.0;
    layer.translate(x - cx, y - cy);
  }

  // jobRoot = папка на уровень выше scripts
  var scriptFile = new File($.fileName);
  var jobRoot = scriptFile.parent.parent;

  var configPath = norm(joinPath(jobRoot.fsName, "config.json"));
  var outputDir = norm(joinPath(jobRoot.fsName, "output"));
  ensureFolder(outputDir);

  var logPath = norm(joinPath(outputDir, "run.log"));
  writeLog(logPath, "JSX start. config=" + configPath);

  try {
    var cfg = parseJson(readText(configPath));

    var baseRel = (cfg.base && cfg.base.path) ? cfg.base.path : "input/base.png";
    var basePath = norm(joinPath(jobRoot.fsName, baseRel));
    if (!(new File(basePath)).exists) throw new Error("Base missing: " + basePath);

    var doc = app.open(new File(basePath));
    writeLog(logPath, "Opened base: " + basePath);

    var layers = cfg.layers || [];
    for (var i=0; i<layers.length; i++) {
      var L = layers[i];
      if (!L || L.type !== "image") continue;

      var assetPath = norm(joinPath(jobRoot.fsName, L.path));
      var af = new File(assetPath);
      if (!af.exists) { writeLog(logPath, "WARN missing asset: " + assetPath); continue; }

      var assetDoc = app.open(af);
      assetDoc.activeLayer.name = L.name ? L.name : ("asset_" + (i+1));
      assetDoc.activeLayer.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
      assetDoc.close(SaveOptions.DONOTSAVECHANGES);

      doc.activeLayer = doc.layers[0];

      var t = L.transform || {};
      var scale = (typeof t.scale === "number") ? t.scale : 100;
      var rotate = (typeof t.rotate === "number") ? t.rotate : 0;
      var x = (typeof t.x === "number") ? t.x : (doc.width.as("px")/2.0);
      var y = (typeof t.y === "number") ? t.y : (doc.height.as("px")/2.0);

      if (scale !== 100) doc.activeLayer.resize(scale, scale, AnchorPosition.MIDDLECENTER);
      if (rotate !== 0) doc.activeLayer.rotate(rotate, AnchorPosition.MIDDLECENTER);
      moveCenterTo(doc.activeLayer, x, y);

      writeLog(logPath, "Placed " + doc.activeLayer.name + " at ("+x+","+y+") scale="+scale+" rot="+rotate);
    }

    var outRel = (cfg.export && cfg.export.png && cfg.export.png.path) ? cfg.export.png.path : "output/final.png";
    var outPath = norm(joinPath(jobRoot.fsName, outRel));
    var outFile = new File(outPath);

    var pngOpts = new PNGSaveOptions();
    doc.saveAs(outFile, pngOpts, true, Extension.LOWERCASE);
    writeLog(logPath, "Saved PNG: " + outPath);

    doc.close(SaveOptions.DONOTSAVECHANGES);
    writeLog(logPath, "JSX done OK");

  } catch (err) {
    writeLog(logPath, "ERROR: " + err.message);
  }

})();
