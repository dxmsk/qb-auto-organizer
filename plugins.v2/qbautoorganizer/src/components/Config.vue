<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['save', 'close'])

const defaults = {
  qb_url: 'http://127.0.0.1:8080', username: 'admin', password: '', interval: 30,
  tag_filter: '', log_level: 'INFO', enabled: false,
}
const config = ref({ ...defaults })
const testing = ref(false)
const snackbar = ref(false)
const testSuccess = ref(false)
const testMessage = ref('')
const logLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']

function save() {
  config.value.interval = Math.max(10, Number(config.value.interval || 30))
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
          <VCol cols="12" md="8"><VTextField v-model="config.tag_filter" label="标签过滤" placeholder="movie,tv" hint="逗号分隔，命中任一标签；留空处理全部" persistent-hint /></VCol>
        </VRow>
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
        <VAlert type="info" variant="tonal">启用时会把 qB 中所有现有种子作为启动基线，之后只整理新添加且下载完成的种子。</VAlert>
      </VCardText>
    </VCard>

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
