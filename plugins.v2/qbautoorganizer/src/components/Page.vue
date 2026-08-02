<script setup>
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['close'])

const loading = ref(false)
const error = ref('')
const records = ref([])
const total = ref(0)
const page = ref(1)
const pages = ref(1)
const pageSize = 20
const brokenPosters = ref({})

const pageText = computed(() => `${page.value} / ${pages.value}`)

function unwrap(response) {
  if (response?.success !== undefined) return response.data || {}
  if (response?.data?.success !== undefined) return response.data.data || {}
  return response?.data || response || {}
}

async function loadRecords(targetPage = page.value) {
  loading.value = true
  error.value = ''
  try {
    const response = await props.api.get('plugin/QbAutoOrganizer/records', {
      params: { page: targetPage, page_size: pageSize },
    })
    const data = unwrap(response)
    records.value = Array.isArray(data.records) ? data.records : []
    total.value = Number(data.total || 0)
    page.value = Number(data.page || 1)
    pages.value = Math.max(1, Number(data.pages || 1))
  } catch (err) {
    error.value = err?.message || '整理记录加载失败'
  } finally {
    loading.value = false
  }
}

function previousPage() {
  if (page.value > 1) loadRecords(page.value - 1)
}

function nextPage() {
  if (page.value < pages.value) loadRecords(page.value + 1)
}

function markPosterBroken(hash) {
  brokenPosters.value = { ...brokenPosters.value, [hash]: true }
}

onMounted(() => loadRecords(1))
</script>

<template>
  <div class="organizer-page">
    <VToolbar color="transparent" density="comfortable" class="organizer-toolbar">
      <div class="toolbar-copy">
        <div class="text-h6 font-weight-bold">qB自动整理助手</div>
        <div class="text-caption text-medium-emphasis">已成功整理 {{ total }} 个下载任务</div>
      </div>
      <VSpacer />
      <VBtn icon="mdi-refresh" variant="text" :loading="loading" title="刷新" @click="loadRecords(page)" />
      <VBtn icon="mdi-close" variant="text" title="关闭" @click="emit('close')" />
    </VToolbar>

    <VAlert v-if="error" type="error" variant="tonal" class="mb-4" closable @click:close="error = ''">
      {{ error }}
    </VAlert>

    <div v-if="loading && !records.length" class="loading-state">
      <VProgressCircular indeterminate color="primary" />
      <span class="text-body-2 text-medium-emphasis">正在加载整理记录…</span>
    </div>

    <div v-else-if="!records.length" class="empty-state">
      <VIcon icon="mdi-movie-open-outline" size="52" color="medium-emphasis" />
      <div class="text-subtitle-1 mt-3">暂无整理记录</div>
      <div class="text-body-2 text-medium-emphasis">启动后新增的种子整理成功后会显示在这里</div>
    </div>

    <div v-else class="record-list">
      <VSheet v-for="record in records" :key="record.hash" border rounded="lg" class="record-row">
        <div class="poster-shell">
          <img
            v-if="record.poster_url && !brokenPosters[record.hash]"
            :src="record.poster_url"
            :alt="record.media_name"
            class="poster-image"
            loading="lazy"
            @error="markPosterBroken(record.hash)"
          >
          <div v-else class="poster-placeholder">
            <VIcon icon="mdi-image-off-outline" size="30" />
          </div>
        </div>

        <div class="record-main">
          <div class="record-heading">
            <div class="record-title" :title="record.media_name">{{ record.media_name || '未知媒体' }}</div>
            <VChip
              size="small"
              variant="tonal"
              :color="record.media_type === '电视剧' ? 'info' : 'primary'"
            >
              {{ record.media_type || '未知' }}
            </VChip>
          </div>
          <div class="record-time">
            <VIcon icon="mdi-clock-outline" size="15" />
            <span>{{ record.organized_at }}</span>
          </div>
          <div class="record-path" :title="record.target_path">
            <VIcon icon="mdi-folder-arrow-right-outline" size="16" />
            <span>{{ record.target_path || '目标路径未返回' }}</span>
          </div>
        </div>
      </VSheet>
    </div>

    <div v-if="total > 0" class="pagination-bar">
      <VBtn
        icon="mdi-chevron-left"
        size="small"
        variant="tonal"
        :disabled="page <= 1 || loading"
        title="上一页"
        @click="previousPage"
      />
      <span class="text-body-2">第 {{ pageText }} 页</span>
      <VBtn
        icon="mdi-chevron-right"
        size="small"
        variant="tonal"
        :disabled="page >= pages || loading"
        title="下一页"
        @click="nextPage"
      />
    </div>
  </div>
</template>

<style scoped>
.organizer-page { padding: 8px 4px 20px; color: rgb(var(--v-theme-on-surface)); }
.organizer-toolbar { position: sticky; top: 0; z-index: 5; margin-bottom: 16px; background: rgba(var(--v-theme-surface), .94) !important; backdrop-filter: blur(12px); }
.toolbar-copy { min-width: 0; padding-left: 12px; }
.record-list { display: grid; gap: 12px; }
.record-row { display: flex; min-width: 0; padding: 12px; background: rgb(var(--v-theme-surface)); box-shadow: 0 3px 14px rgba(0, 0, 0, .06); transition: border-color .18s ease, transform .18s ease; }
.record-row:hover { transform: translateY(-1px); border-color: rgba(var(--v-theme-primary), .45); }
.poster-shell { flex: 0 0 72px; width: 72px; height: 104px; overflow: hidden; border-radius: 8px; background: rgb(var(--v-theme-surface-variant)); }
.poster-image { width: 100%; height: 100%; display: block; object-fit: cover; }
.poster-placeholder { width: 100%; height: 100%; display: grid; place-items: center; color: rgb(var(--v-theme-on-surface-variant)); }
.record-main { display: flex; flex: 1; min-width: 0; flex-direction: column; justify-content: center; gap: 10px; padding: 2px 4px 2px 16px; }
.record-heading { display: flex; min-width: 0; align-items: center; gap: 10px; }
.record-title { min-width: 0; overflow: hidden; color: rgb(var(--v-theme-on-surface)); font-size: 1rem; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.record-time, .record-path { display: flex; min-width: 0; align-items: center; gap: 7px; color: rgba(var(--v-theme-on-surface), .68); font-size: .82rem; }
.record-path span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.loading-state, .empty-state { min-height: 280px; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 12px; border: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 14px; }
.pagination-bar { display: flex; align-items: center; justify-content: center; gap: 14px; padding-top: 18px; }
@media (max-width: 600px) { .organizer-page { padding-inline: 0; } .poster-shell { flex-basis: 60px; width: 60px; height: 88px; } .record-main { padding-left: 12px; } .record-heading { align-items: flex-start; flex-direction: column; gap: 6px; } }
</style>
