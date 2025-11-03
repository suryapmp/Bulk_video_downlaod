<!-- templates/index.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Bulk Video Downloader</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { background: linear-gradient(135deg,#eef2ff,#f8fafc); font-family: Inter, sans-serif; }
    .card { background: white; border-radius: 1rem; box-shadow: 0 6px 20px rgba(2,6,23,0.06); }
    .progress-bar { transition: width 0.25s ease; }
  </style>
</head>
<body class="py-10 flex justify-center">
  <div class="max-w-6xl w-full px-6">
    <div class="text-center mb-6">
      <h1 class="text-3xl font-bold text-indigo-700">🎥 Bulk Video Downloader</h1>
      <p class="text-gray-600">Upload Excel → choose folder name → start or resume downloads. Preview appears as soon as a video starts.</p>
    </div>

    <!-- Upload card -->
    <div class="card p-6 mb-6">
      <form id="uploadForm" class="space-y-4" onsubmit="return false;">
        <div>
          <label class="font-semibold">Excel file (xlsx)</label>
          <input id="fileInput" type="file" accept=".xlsx" class="mt-2 block w-full" />
        </div>

        <div class="flex gap-3 items-center">
          <input id="folderInput" type="text" placeholder="Absolute folder path (e.g., D:\ve) - required" class="flex-1 p-2 border rounded" />
          <input id="concurrency" type="number" min="1" max="20" value="6" title="Parallel downloads" class="w-24 p-2 border rounded" />
          <button id="uploadBtn" type="button" class="bg-indigo-600 text-white px-4 py-2 rounded">Upload Excel</button>
          <button id="startBtn" type="button" class="bg-green-600 text-white px-4 py-2 rounded hidden">Start Downloads</button>
          <button id="resumeBtn" type="button" class="bg-amber-500 text-white px-4 py-2 rounded hidden">Resume</button>
        </div>
        <div id="info" class="text-sm text-gray-600"></div>
      </form>
    </div>

    <!-- Summary -->
    <div class="flex gap-4 mb-6">
      <div class="card p-4 flex-1 text-center">
        <p class="text-sm text-gray-600">Completed</p>
        <div id="completedCount" class="text-2xl font-bold text-green-600">0</div>
      </div>
      <div class="card p-4 flex-1 text-center">
        <p class="text-sm text-gray-600">In Progress</p>
        <div id="processingCount" class="text-2xl font-bold text-indigo-600">0</div>
      </div>
      <div class="card p-4 flex-1 text-center">
        <p class="text-sm text-gray-600">Total</p>
        <div id="totalCount" class="text-2xl font-bold text-slate-800">0</div>
      </div>
      <div class="card p-4 flex-1 text-center">
        <p class="text-sm text-gray-600">Total GB</p>
        <div id="totalGB" class="text-2xl font-bold text-amber-600">0.00</div>
      </div>
    </div>

    <!-- Table -->
    <div class="card p-6 mb-8">
      <h2 class="text-lg font-semibold mb-4">Download Progress</h2>
      <div class="overflow-auto max-h-96">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-slate-50">
            <tr>
              <th class="p-2 text-left">Roll No</th>
              <th class="p-2 text-left">Program</th>
              <th class="p-2 text-left">Course</th>
              <th class="p-2 text-left">Status</th>
              <th class="p-2 text-left">Speed</th>
              <th class="p-2 text-left">Size</th>
              <th class="p-2 text-left w-1/3">Progress</th>
              <th class="p-2 text-left">Preview</th>
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Preview modal -->
  <div id="previewModal" class="fixed inset-0 hidden items-center justify-center bg-black/60 z-50">
    <div class="bg-white rounded-lg w-11/12 md:w-3/4 max-h-[90vh] overflow-auto">
      <div class="p-3 border-b flex justify-between items-center">
        <h3 class="font-semibold">Video Preview</h3>
        <button id="closePreview" class="text-gray-600">✕</button>
      </div>
      <div class="p-4">
        <video id="previewPlayer" controls style="width:100%; height:auto;"></video>
      </div>
    </div>
  </div>

<script>
  // === WEBSOCKET ===
  let ws;
  function createWS() {
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws");
    ws.onopen = () => console.log("WS open");
    ws.onclose = () => { console.log("WS closed, reconnecting in 1s"); setTimeout(createWS, 1000); };
    ws.onerror = (e) => console.warn("WS error", e);
    ws.onmessage = handleMessage;
  }
  createWS();

  // === ELEMENTS ===
  const tbody = document.getElementById('tbody');
  const info = document.getElementById('info');
  const uploadBtn = document.getElementById('uploadBtn');
  const startBtn = document.getElementById('startBtn');
  const resumeBtn = document.getElementById('resumeBtn');
  const fileInput = document.getElementById('fileInput');
  const folderInput = document.getElementById('folderInput');
  const concurrencyInput = document.getElementById('concurrency');
  const completedCountEl = document.getElementById('completedCount');
  const processingCountEl = document.getElementById('processingCount');
  const totalCountEl = document.getElementById('totalCount');
  const totalGBEl = document.getElementById('totalGB');

  let rows = {};

  // === UPLOAD EXCEL ===
  uploadBtn.onclick = async () => {
    const file = fileInput.files[0];
    if (!file) { alert("Select Excel"); return; }
    const fd = new FormData(); fd.append('file', file);
    info.textContent = "Parsing Excel...";
    const res = await fetch('/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) { info.textContent = data.error; return; }
    info.textContent = `Parsed ${data.total} tasks. Ready to start.`;
    // populate table rows from returned tasks (if any)
    if (data.tasks && Array.isArray(data.tasks)) {
      data.tasks.forEach(t => addRow(t.roll, t.program, t.course));
    }
    totalCountEl.textContent = data.total;
    startBtn.classList.remove('hidden');
    resumeBtn.classList.remove('hidden');
  };

  // === START DOWNLOAD ===
  startBtn.onclick = async () => {
    const folder = folderInput.value.trim();
    if (!folder) { alert("Enter absolute folder path where files must be saved"); return; }
    const concurrency = concurrencyInput.value || 6;
    info.textContent = "🚀 Starting downloads...";
    await restoreCompleted(); // show existing files first
    const fd = new FormData(); fd.append('folder', folder); fd.append('concurrency', concurrency);
    const res = await fetch('/start_downloads', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) { info.textContent = data.error; return; }
    info.textContent = data.message || "Downloads started.";
  };

  // === RESUME DOWNLOAD ===
  resumeBtn.onclick = async () => {
    const folder = folderInput.value.trim();
    if (!folder) { alert("Enter absolute folder path where files were saved earlier"); return; }
    const concurrency = concurrencyInput.value || 6;
    info.textContent = "⏯️ Resuming downloads...";
    const fd = new FormData(); fd.append('folder', folder); fd.append('concurrency', concurrency);
    const res = await fetch('/start_downloads', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) { info.textContent = data.error; return; }
    info.textContent = data.message || "Resume started.";
  };

  // === ADD TABLE ROW ===
  function addRow(roll, program, course) {
    const key = `${roll}__${course}`;
    if (rows[key]) return;
    const tr = document.createElement('tr');
    tr.dataset.key = key;
    tr.innerHTML = `
      <td class="p-2 border-b roll">${roll}</td>
      <td class="p-2 border-b program">${program || '-'}</td>
      <td class="p-2 border-b course">${course || '-'}</td>
      <td class="p-2 border-b status">Queued</td>
      <td class="p-2 border-b speed">-</td>
      <td class="p-2 border-b size">-</td>
      <td class="p-2 border-b">
        <div class="w-full bg-slate-200 rounded h-3 overflow-hidden">
          <div class="progress-bar bg-indigo-500 h-3 rounded" style="width:0%"></div>
        </div>
        <div class="text-xs text-gray-600 mt-1 progress-text">0%</div>
      </td>
      <td class="p-2 border-b preview">-</td>
    `;
    tbody.appendChild(tr);
    rows[key] = tr;
  }

  // === HANDLE SERVER MESSAGES ===
  function handleMessage(evt) {
    try {
      const d = JSON.parse(evt.data);

      // final done
      if (d.type === "done" || d.status === "🎉 All downloads finished") {
        info.textContent = d.status || "All downloads finished";
        if (d.total_gb !== undefined) totalGBEl.textContent = Number(d.total_gb).toFixed(2);
        return;
      }

      // must have roll
      if (!d.roll) return;

      addRow(d.roll, d.program || '-', d.course || '-');
      const key = `${d.roll}__${d.course}`;
      const tr = rows[key]; if (!tr) return;

      // update fields
      tr.querySelector('.status').textContent = d.status || '-';
      tr.querySelector('.speed').textContent = d.speed || '-';
      if (d.size) tr.querySelector('.size').textContent = d.size;

      const bar = tr.querySelector('.progress-bar');
      const progressText = tr.querySelector('.progress-text');
      const progress = Number(d.progress || 0);
      bar.style.width = `${progress}%`;
      progressText.textContent = `${progress}%`;

      // show preview button (use server-provided preview URL)
      if (d.preview) {
        const previewCell = tr.querySelector('.preview');
        // keep only one button
        if (!previewCell.querySelector('button')) {
          previewCell.innerHTML = '';
          const btn = document.createElement('button');
          btn.textContent = 'Preview';
          btn.className = 'text-indigo-600 underline text-xs';
          btn.onclick = () => openPreview(d.preview);
          previewCell.appendChild(btn);
        }
      }

      // summary: total_gb, counts
      if (d.total_gb !== undefined) totalGBEl.textContent = Number(d.total_gb).toFixed(2);
      // compute completed count live
      const completed = Object.values(rows).filter(r => (r.querySelector('.status').textContent || '').toLowerCase().includes('completed')).length;
      completedCountEl.textContent = completed;

      // processing count = rows with status downloading or queued etc.
      const processing = Object.values(rows).filter(r => {
        const s = (r.querySelector('.status').textContent || '').toLowerCase();
        return s.includes('downloading') || s.includes('starting') || s.includes('resuming');
      }).length;
      processingCountEl.textContent = processing;

    } catch (err) {
      console.warn("WS parse error:", err);
    }
  }

  // === PREVIEW MODAL ===
  const previewModal = document.getElementById('previewModal');
  const previewPlayer = document.getElementById('previewPlayer');
  document.getElementById('closePreview').onclick = closePreview;
  function openPreview(url) {
    previewPlayer.src = url;
    previewModal.classList.remove('hidden'); previewModal.classList.add('flex');
    setTimeout(()=>previewPlayer.play().catch(()=>{}), 200);
  }
  function closePreview() {
    previewPlayer.pause(); previewPlayer.src = "";
    previewModal.classList.remove('flex'); previewModal.classList.add('hidden');
  }

  // === RESTORE COMPLETED FILES (on load & before start) ===
  async function restoreCompleted() {
    try {
      const res = await fetch('/status');
      const data = await res.json();
      if (!data || !data.completed) return;
      data.completed.forEach(item => {
        // try to infer roll from filename (filename is Roll.mp4)
        const fname = item.file || '';
        const roll = fname.replace('.mp4', '');
        // add if not exists
        addRow(roll, '-', '-');
        const key = `${roll}__-`;
        // best-effort find row matching roll (we store keyed by roll__course; course unknown -> '-')
        const found = Object.values(rows).find(r => r.querySelector('.roll').textContent.trim() === roll);
        if (found) {
          found.querySelector('.status').textContent = 'Completed';
          found.querySelector('.progress-bar').style.width = '100%';
          found.querySelector('.progress-text').textContent = '100%';
          if (item.size_bytes) {
            found.querySelector('.size').textContent = `${(item.size_bytes / (1024 ** 2)).toFixed(2)} MB`;
          }
          // preview button
          const previewCell = found.querySelector('.preview');
          previewCell.innerHTML = '';
          const btn = document.createElement('button');
          btn.textContent = 'Preview';
          btn.className = 'text-indigo-600 underline text-xs';
          btn.onclick = () => openPreview(item.preview);
          previewCell.appendChild(btn);
        }
      });

      if (data.total_gb !== undefined) totalGBEl.textContent = Number(data.total_gb).toFixed(2);
      if (data.count !== undefined) completedCountEl.textContent = data.count;
    } catch (e) {
      console.warn("restoreCompleted failed", e);
    }
  }

  // restore on load
  window.addEventListener('load', restoreCompleted);
</script>
</body>
</html>
