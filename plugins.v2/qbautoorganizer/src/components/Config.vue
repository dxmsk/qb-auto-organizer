<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['save', 'close'])

const defaults = {
  qb_url: 'http://127.0.0.1:8080', username: 'admin', password: '', interval: 30,
  tag_filter: '', force_organize: false, rapid_priority: true, rapid_grace_seconds: 8,
  log_level: 'INFO', enabled: false,
}
const config = ref({ ...defaults })
const testing = ref(false)
const resetDialog = ref(false)
const resetting = ref(false)
const snackbar = ref(false)
const testSuccess = ref(false)
const testMessage = ref('')
const logLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']

function save() {
  config.value.interval = Math.max(10, Number(config.value.interval || 30))
  config.value.rapid_grace_seconds = Math.min(60, Math.max(1, Number(config.value.rapid_grace_seconds || 8)))
  emit('save', { ...config.value })
}

async function testConnection() {
  testing.value = true
  try {
    const response = await props.api.get('plugin/QbAutoOrganizer/test')
    const payload = response?.data?.success !== undefined ? response.data : response
    testSuccess.value = Boolean(payload?.success)
    testMessage.value = payload?.message || (testSuccess.value ? '连接成功' : '连接失败')
  } catch (err) {
    testSuccess.value = false
    testMessage.value = err?.message || '连接测试失败'
  } finally {
    testing.value = false
    snackbar.value = true
  }
}

async function resetBaseline() {
  resetting.value = true
  try {
    const response = await props.api.post('plugin/QbAutoOrganizer/baseline/reset', {})
    const payload = response?.data?.success !== undefined ? response.data : response
    testSuccess.value = Boolean(payload?.success)
    testMessage.value = payload?.message || (testSuccess.value ? '基线已重置' : '重置基线失败')
    if (testSuccess.value) resetDialog.value = false
  } catch (err) {
    testSuccess.value = false
    testMessage.value = err?.message || '重置基线失败'
  } finally {
    resetting.value = false
    snackbar.value = true
  }
}

onMounted(() => { config.value = { ...defaults, ...(props.initialConfig || {}) } })
</script>

<template>
  <div class="config-page">
    <VToolbar color="transparent" density="comfortable">
      <div class="text-h6 font-weight-bold ms-3">qB自动整理助手配置</div>
      <VSpacer />
      <VBtn icon="mdi-content-save" color="primary" variant="text" title="保存" @click="save" />
      <VBtn icon="mdi-close" variant="text" title="关闭" @click="emit('close')" />
    </VToolbar>

    <VCard variant="tonal" class="config-card">
      <VCardTitle><VIcon icon="mdi-server-network" color="primary" class="mr-2" />qBittorrent 连接</VCardTitle>
      <VDivider />
      <VCardText>
        <VRow>
          <VCol cols="12" md="6"><VTextField v-model="config.qb_url" label="服务器地址" prepend-inner-icon="mdi-web" /></VCol>
          <VCol cols="12" md="3"><VTextField v-model="config.username" label="用户名" prepend-inner-icon="mdi-account" /></VCol>
          <VCol cols="12" md="3"><VTextField v-model="config.password" label="密码" type="password" prepend-inner-icon="mdi-lock" /></VCol>
        </VRow>
        <div class="d-flex align-center ga-3">
          <VBtn color="primary" variant="elevated" prepend-icon="mdi-lan-connect" :loading="testing" @click="testConnection">立即检测</VBtn>
          <span class="text-caption text-medium-emphasis">检测使用已保存的连接配置</span>
        </div>
      </VCardText>
    </VCard>

    <VCard variant="tonal" class="config-card">
      <VCardTitle><VIcon icon="mdi-tune-variant" color="success" class="mr-2" />监控规则</VCardTitle>
      <VDivider />
      <VCardText>
        <VRow>
          <VCol cols="12" md="4"><VTextField v-model.number="config.interval" label="监控间隔（秒）" type="number" min="10" hint="最小 10 秒" persistent-hint /></VCol>
          <VCol cols="12" md="4"><VTextField v-model="config.tag_filter" label="标签过滤" placeholder="movie,tv" hint="逗号分隔，命中任一标签；留空处理全部" persistent-hint /></VCol>
          <VCol cols="12" md="4">
            <VSwitch
              v-model="config.force_organize"
              label="强制整理"
              color="warning"
              inset
              hint="传递 manual=True、force=True，忽略“已整理”标签和历史整理记录"
              persistent-hint
            />
          </VCol>
        </VRow>
        <VRow class="mt-2">
          <VCol cols="12" md="4">
            <VSwitch
              v-model="config.rapid_priority"
              label="115 秒传优先"
              color="success"
              inset
              hint="秒传处理中暂缓整理；秒传成功后跳过整理；失败或超时后恢复整理"
              persistent-hint
            />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField
              v-model.number="config.rapid_grace_seconds"
              label="秒传登记等待（秒）"
              type="number"
              min="1"
              max="60"
              hint="秒传插件尚未登记 qB 任务时的短暂等待窗口"
              persistent-hint
            />
          </VCol>
        </VRow>
        <div class="d-flex flex-wrap align-center ga-3 mt-2">
          <VBtn color="error" variant="tonal" prepend-icon="mdi-database-refresh-outline" @click="resetDialog = true">重置基线</VBtn>
          <span class="text-caption text-medium-emphasis">下次插件启动或配置重载时重新扫描当前种子</span>
        </div>
      </VCardText>
    </VCard>

    <VCard variant="tonal" class="config-card">
      <VCardTitle><VIcon icon="mdi-bug-outline" color="warning" class="mr-2" />调试设置</VCardTitle>
      <VDivider />
      <VCardText>
        <VRow>
          <VCol cols="12" md="4"><VSelect v-model="config.log_level" :items="logLevels" label="日志级别" /></VCol>
          <VCol cols="12" md="4"><VSwitch v-model="config.enabled" label="启用插件" color="primary" inset /></VCol>
        </VRow>
        <VAlert type="info" variant="tonal">首次启用时会持久化 qB 中全部现有种子。后续重启沿用固定基线，只整理基线之外且下载完成的新种子。</VAlert>
      </VCardText>
    </VCard>

    <VDialog v-model="resetDialog" max-width="520">
      <VCard>
        <VCardTitle class="d-flex align-center"><VIcon icon="mdi-alert-outline" color="error" class="mr-2" />确认重置基线</VCardTitle>
        <VCardText>确认删除固定基线？当前运行不会立即改变；下次插件启动或配置重载时，qBittorrent 中所有现有种子都会重新记为历史种子。</VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="resetting" @click="resetDialog = false">取消</VBtn>
          <VBtn color="error" variant="elevated" :loading="resetting" @click="resetBaseline">确认重置</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar" :color="testSuccess ? 'success' : 'error'" timeout="5000">
      {{ testMessage }}
      <template #actions><VBtn variant="text" @click="snackbar = false">关闭</VBtn></template>
    </VSnackbar>
  </div>
</template>

<style scoped>
.config-page { padding: 4px 4px 20px; color: rgb(var(--v-theme-on-surface)); }
.config-card { margin-top: 14px; border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
</style>
