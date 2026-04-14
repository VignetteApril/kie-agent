<script setup>
import { computed, onBeforeUnmount, ref } from "vue";

const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001";

const words = ref([]);
const excel = ref(null);
const wordInput = ref(null);
const excelInput = ref(null);
const loadingPreview = ref(false);
const startingTask = ref(false);
const error = ref("");
const preview = ref(null);
const task = ref(null);
const selectedEvidence = ref({ header: "", value: "", evidence: "" });
let timer = null;

const canPreview = computed(() => words.value.length > 0 && excel.value && !loadingPreview.value);
const canStartTask = computed(() => preview.value && preview.value.mappings.some((item) => item.enabled) && !startingTask.value);
const hasSelectedFiles = computed(() => words.value.length > 0 || !!excel.value);
const taskStatusLabel = computed(() => ({ pending: "排队中", running: "处理中", completed: "已完成", failed: "失败" }[task.value?.status] || "未开始"));
const taskStatusClass = computed(() => `status-${task.value?.status || "idle"}`);
const wordCountLabel = computed(() => `${words.value.length} 份 Word 文档`);

function onWordsChange(event) {
  words.value = Array.from(event.target.files || []);
  resetFlow();
}

function onExcelChange(event) {
  excel.value = event.target.files?.[0] || null;
  resetFlow();
}

function resetFlow() {
  preview.value = null;
  task.value = null;
  selectedEvidence.value = { header: "", value: "", evidence: "" };
  error.value = "";
  stopPolling();
}

function clearFiles() {
  words.value = [];
  excel.value = null;
  if (wordInput.value) wordInput.value.value = "";
  if (excelInput.value) excelInput.value.value = "";
  resetFlow();
}

function formatSize(size) {
  if (!size && size !== 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(2)} MB`;
}

async function previewMappings() {
  if (!canPreview.value) return;
  error.value = "";
  loadingPreview.value = true;
  const formData = new FormData();
  words.value.forEach((file) => formData.append("words", file));
  formData.append("excel", excel.value);

  try {
    const response = await fetch(`${apiBase}/api/mappings/preview`, { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "表头识别失败");
    preview.value = data;
    task.value = null;
  } catch (err) {
    error.value = err.message;
  } finally {
    loadingPreview.value = false;
  }
}

async function startTask() {
  if (!canStartTask.value) return;
  error.value = "";
  startingTask.value = true;
  try {
    const response = await fetch(`${apiBase}/api/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: preview.value.upload_id, mappings: preview.value.mappings }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "任务创建失败");
    task.value = data;
    startPolling();
  } catch (err) {
    error.value = err.message;
  } finally {
    startingTask.value = false;
  }
}

async function fetchTask() {
  if (!task.value?.task_id) return;
  const response = await fetch(`${apiBase}/api/tasks/${task.value.task_id}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "获取任务状态失败");
  task.value = data;
  if (["completed", "failed"].includes(data.status)) stopPolling();
}

function startPolling() {
  stopPolling();
  timer = window.setInterval(async () => {
    try { await fetchTask(); } catch (err) { error.value = err.message; stopPolling(); }
  }, 2000);
}

function stopPolling() {
  if (timer) {
    window.clearInterval(timer);
    timer = null;
  }
}

function chooseEvidence(row, header) {
  selectedEvidence.value = {
    header,
    value: row.values?.[header] || "",
    evidence: row.evidence?.[header] || "暂无来源说明",
  };
}

onBeforeUnmount(() => stopPolling());
</script>

<template>
  <main class="page">
    <div class="hero-glow hero-glow-left"></div>
    <div class="hero-glow hero-glow-right"></div>

    <section class="hero card glass-card">
      <div class="hero-copy">
        <span class="eyebrow">泰山智能抽取辅助系统</span>
        <h1>泰山智能抽取辅助系统</h1>
        <p class="hero-text">自动识别 Excel 列名，再从 Word 中精准抽取关键信息；支持字段说明人工调整、任务异步处理与结果下载。</p>
      </div>
      <div class="hero-panel">
        <div class="preview-window"><div class="preview-topbar"><span></span><span></span><span></span></div><div class="preview-body"><div class="preview-sheet"></div><div class="preview-lines"><span></span><span></span><span></span><span></span></div></div></div>
      </div>
    </section>

    <section class="content-grid two-steps">
      <section class="card glass-card upload-card">
        <div class="section-head">
          <div><h2>步骤 1：上传文件</h2><p>上传多个 Word 与一个 Excel 模板，先识别表头。</p></div>
          <div class="section-actions">
            <div class="badge badge-soft">自动识别</div>
            <button class="ghost-btn" :disabled="!hasSelectedFiles" @click="clearFiles">清空文件</button>
          </div>
        </div>
        <div class="upload-grid">
          <label class="upload-box"><div class="upload-icon">W</div><div class="upload-copy"><strong>Word 文档</strong><span>支持多选，仅 .docx</span></div><input ref="wordInput" type="file" accept=".docx" multiple @change="onWordsChange" /></label>
          <label class="upload-box"><div class="upload-icon excel">X</div><div class="upload-copy"><strong>Excel 模板</strong><span>第一行作为目标表头</span></div><input ref="excelInput" type="file" accept=".xlsx" @change="onExcelChange" /></label>
        </div>
        <div class="selection-panels">
          <div class="selection-card"><div class="selection-title-row"><h3>{{ wordCountLabel }}</h3><span class="mini-tag">DOCX</span></div><div v-if="words.length" class="file-chips"><div v-for="file in words" :key="file.name" class="file-chip"><div><strong>{{ file.name }}</strong><span>{{ formatSize(file.size) }}</span></div></div></div><div v-else class="empty-state">尚未选择 Word 文件</div></div>
          <div class="selection-card"><div class="selection-title-row"><h3>Excel 模板</h3><span class="mini-tag excel">XLSX</span></div><div v-if="excel" class="file-chip single"><div><strong>{{ excel.name }}</strong><span>{{ formatSize(excel.size) }}</span></div></div><div v-else class="empty-state">尚未选择 Excel 文件</div></div>
        </div>
        <div class="action-row"><button class="primary-btn" :disabled="!canPreview" @click="previewMappings"><span class="btn-main">{{ loadingPreview ? '识别表头中...' : '识别表头并生成抽取规则' }}</span><span class="btn-sub">上传文件 → 自动生成默认抽取说明</span></button></div>
        <div v-if="error" class="error-banner"><strong>请求失败</strong><span>{{ error }}</span></div>
      </section>

      <section class="card glass-card status-card">
        <div class="section-head status-head"><div><h2>步骤 2：确认字段映射</h2><p>可逐列修改抽取说明，再开始任务。</p></div><div class="badge" :class="preview ? 'status-running' : 'status-idle'">{{ preview ? '可编辑' : '待识别' }}</div></div>
        <template v-if="preview">
          <div class="mapping-list">
            <div v-for="(item, index) in preview.mappings" :key="`${item.header_name}-${index}`" class="mapping-item">
              <div class="mapping-top"><strong>{{ item.header_name }}</strong><label class="toggle"><input v-model="item.enabled" type="checkbox" /><span>启用</span></label></div>
              <textarea v-model="item.extract_instruction" class="mapping-textarea" rows="3"></textarea>
            </div>
          </div>
          <button class="primary-btn" :disabled="!canStartTask" @click="startTask"><span class="btn-main">{{ startingTask ? '创建任务中...' : '确认映射并开始抽取' }}</span><span class="btn-sub">每个 Word 输出 1 行结果</span></button>
        </template>
        <div v-else class="status-empty"><div class="status-empty-icon">🧠</div><strong>等待识别 Excel 表头</strong><p>识别后这里会显示每个表头对应的默认抽取说明；如果你点击“清空文件”，这里也会同步清空。</p></div>
      </section>
    </section>

    <section class="content-grid results-grid">
      <section class="card glass-card status-card">
        <div class="section-head status-head"><div><h2>任务中心</h2><p>提交后自动轮询，完成后可下载结果。</p></div><div class="badge" :class="taskStatusClass">{{ taskStatusLabel }}</div></div>
        <template v-if="task">
          <div class="task-meta"><div class="meta-item"><span>任务 ID</span><strong>{{ task.task_id }}</strong></div><div class="meta-item"><span>当前状态</span><strong>{{ taskStatusLabel }}</strong></div><div class="meta-item"><span>当前进度</span><strong>{{ task.progress }}%</strong></div></div>
          <div class="progress-panel"><div class="progress-label-row"><span>处理进度</span><span>{{ task.progress }}%</span></div><div class="progress-track"><div class="progress-fill" :style="{ width: `${task.progress}%` }"></div></div><p class="progress-message">{{ task.message }}</p></div>
          <a v-if="task.download_url" class="download-btn" :href="`${apiBase}${task.download_url}`">下载结果 Excel</a>
        </template>
        <div v-else class="status-empty"><div class="status-empty-icon">⌛</div><strong>还没有任务</strong><p>完成表头识别并确认映射后，这里会显示任务进度。</p></div>
      </section>

      <section class="card glass-card status-card">
        <div class="section-head status-head"><div><h2>结果预览与来源</h2><p>点击某个结果值查看它的来源片段。</p></div><div class="badge badge-soft">Evidence</div></div>
        <template v-if="task?.preview_rows?.length">
          <div class="table-wrap"><table class="result-table"><thead><tr><th>文档</th><th v-for="item in preview?.mappings?.filter((m) => m.enabled) || []" :key="item.header_name">{{ item.header_name }}</th></tr></thead><tbody><tr v-for="row in task.preview_rows" :key="row.document_name"><td>{{ row.document_name }}</td><td v-for="item in preview?.mappings?.filter((m) => m.enabled) || []" :key="item.header_name"><button class="cell-btn" @click="chooseEvidence(row, item.header_name)">{{ row.values?.[item.header_name] || '-' }}</button></td></tr></tbody></table></div>
          <div class="evidence-panel" v-if="selectedEvidence.header"><h3>{{ selectedEvidence.header }}</h3><div class="evidence-value">结果：{{ selectedEvidence.value || '空' }}</div><p>{{ selectedEvidence.evidence }}</p></div>
        </template>
        <div v-else class="status-empty"><div class="status-empty-icon">📄</div><strong>暂无结果预览</strong><p>任务开始后，这里会显示每个文档每个表头的抽取结果，点击可查看来源说明。</p></div>
      </section>
    </section>
  </main>
</template>
