// task_simple.jsx — minimal smoke-test for ExtendScript execution
// Run this first to verify that Photoshop can execute JSX at all.
//
// All it does:
//   1. Writes a line to out/bootstrap.log  (repo root / out / bootstrap.log)
//   2. Creates out/jsx_ok.txt              (presence = JSX ran successfully)
//
// Usage (manual):  File > Scripts > Browse > select this file
// Usage (auto):    python orchestrator.py configjson/example_job.json
//                  (orchestrator will run task.jsx; run this manually to test)

#target photoshop
app.displayDialogs = DialogModes.NO;

(function () {

  function nowStr() {
    var d = new Date();
    function z(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-" + z(d.getMonth() + 1) + "-" + z(d.getDate()) +
           " " + z(d.getHours()) + ":" + z(d.getMinutes()) + ":" + z(d.getSeconds());
  }

  function norm(p) { return p.replace(/\\/g, "/"); }

  function writeFile(path, content, append) {
    var f = new File(path);
    f.encoding = "UTF-8";
    f.open(append ? "a" : "w");
    f.writeln(content);
    f.close();
  }

  // Resolve repo root: scripts/ → parent → repo root
  var scriptFile    = new File($.fileName);
  var scriptAbsURI  = scriptFile.absoluteURI;
  var scriptsFolder = new File(scriptAbsURI).parent;
  var repoFolder    = scriptsFolder.parent;
  var jobRoot       = norm(repoFolder.fsName);

  // Ensure out/ exists
  var outFolder = new Folder(norm(jobRoot + "/out"));
  if (!outFolder.exists) outFolder.create();

  var bootstrapLog = norm(jobRoot + "/out/bootstrap.log");
  var okFile       = norm(jobRoot + "/out/jsx_ok.txt");

  writeFile(bootstrapLog,
    nowStr() + " | task_simple.jsx executed OK. jobRoot=" + jobRoot +
    "  PS version=" + app.version,
    true);   // append

  writeFile(okFile,
    nowStr() + " | JSX ran OK. jobRoot=" + jobRoot,
    false);  // overwrite

  alert("task_simple.jsx ran OK!\nCheck: " + bootstrapLog);

})();
