import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock,renderList:_renderList,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1 = { class: "organizer-page" };
const _hoisted_2 = { class: "toolbar-copy" };
const _hoisted_3 = { class: "text-caption text-medium-emphasis" };
const _hoisted_4 = {
  key: 1,
  class: "loading-state"
};
const _hoisted_5 = {
  key: 2,
  class: "empty-state"
};
const _hoisted_6 = {
  key: 3,
  class: "record-list"
};
const _hoisted_7 = { class: "poster-shell" };
const _hoisted_8 = ["src", "alt", "onError"];
const _hoisted_9 = {
  key: 1,
  class: "poster-placeholder"
};
const _hoisted_10 = { class: "record-main" };
const _hoisted_11 = { class: "record-heading" };
const _hoisted_12 = ["title"];
const _hoisted_13 = { class: "record-time" };
const _hoisted_14 = ["title"];
const _hoisted_15 = {
  key: 4,
  class: "pagination-bar"
};
const _hoisted_16 = { class: "text-body-2" };

const {computed,onMounted,ref} = await importShared('vue');


const pageSize = 20;

const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
},
  emits: ['close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const loading = ref(false);
const error = ref('');
const records = ref([]);
const total = ref(0);
const page = ref(1);
const pages = ref(1);
const brokenPosters = ref({});

const pageText = computed(() => `${page.value} / ${pages.value}`);

function unwrap(response) {
  if (response?.success !== undefined) return response.data || {}
  if (response?.data?.success !== undefined) return response.data.data || {}
  return response?.data || response || {}
}

async function loadRecords(targetPage = page.value) {
  loading.value = true;
  error.value = '';
  try {
    const response = await props.api.get('plugin/QbAutoOrganizer/records', {
      params: { page: targetPage, page_size: pageSize },
    });
    const data = unwrap(response);
    records.value = Array.isArray(data.records) ? data.records : [];
    total.value = Number(data.total || 0);
    page.value = Number(data.page || 1);
    pages.value = Math.max(1, Number(data.pages || 1));
  } catch (err) {
    error.value = err?.message || '整理记录加载失败';
  } finally {
    loading.value = false;
  }
}

function previousPage() {
  if (page.value > 1) loadRecords(page.value - 1);
}

function nextPage() {
  if (page.value < pages.value) loadRecords(page.value + 1);
}

function markPosterBroken(hash) {
  brokenPosters.value = { ...brokenPosters.value, [hash]: true };
}

onMounted(() => loadRecords(1));

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VProgressCircular = _resolveComponent("VProgressCircular");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VSheet = _resolveComponent("VSheet");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      color: "transparent",
      density: "comfortable",
      class: "organizer-toolbar"
    }, {
      default: _withCtx(() => [
        _createElementVNode("div", _hoisted_2, [
          _cache[3] || (_cache[3] = _createElementVNode("div", { class: "text-h6 font-weight-bold" }, "qB自动整理助手", -1)),
          _createElementVNode("div", _hoisted_3, "已成功整理 " + _toDisplayString(total.value) + " 个下载任务", 1)
        ]),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VBtn, {
          icon: "mdi-refresh",
          variant: "text",
          loading: loading.value,
          title: "刷新",
          onClick: _cache[0] || (_cache[0] = $event => (loadRecords(page.value)))
        }, null, 8, ["loading"]),
        _createVNode(_component_VBtn, {
          icon: "mdi-close",
          variant: "text",
          title: "关闭",
          onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
        })
      ]),
      _: 1
    }),
    (error.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 0,
          type: "error",
          variant: "tonal",
          class: "mb-4",
          closable: "",
          "onClick:close": _cache[2] || (_cache[2] = $event => (error.value = ''))
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(error.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (loading.value && !records.value.length)
      ? (_openBlock(), _createElementBlock("div", _hoisted_4, [
          _createVNode(_component_VProgressCircular, {
            indeterminate: "",
            color: "primary"
          }),
          _cache[4] || (_cache[4] = _createElementVNode("span", { class: "text-body-2 text-medium-emphasis" }, "正在加载整理记录…", -1))
        ]))
      : (!records.value.length)
        ? (_openBlock(), _createElementBlock("div", _hoisted_5, [
            _createVNode(_component_VIcon, {
              icon: "mdi-movie-open-outline",
              size: "52",
              color: "medium-emphasis"
            }),
            _cache[5] || (_cache[5] = _createElementVNode("div", { class: "text-subtitle-1 mt-3" }, "暂无整理记录", -1)),
            _cache[6] || (_cache[6] = _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "启动后新增的种子整理成功后会显示在这里", -1))
          ]))
        : (_openBlock(), _createElementBlock("div", _hoisted_6, [
            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(records.value, (record) => {
              return (_openBlock(), _createBlock(_component_VSheet, {
                key: record.hash,
                border: "",
                rounded: "lg",
                class: "record-row"
              }, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_7, [
                    (record.poster_url && !brokenPosters.value[record.hash])
                      ? (_openBlock(), _createElementBlock("img", {
                          key: 0,
                          src: record.poster_url,
                          alt: record.media_name,
                          class: "poster-image",
                          loading: "lazy",
                          onError: $event => (markPosterBroken(record.hash))
                        }, null, 40, _hoisted_8))
                      : (_openBlock(), _createElementBlock("div", _hoisted_9, [
                          _createVNode(_component_VIcon, {
                            icon: "mdi-image-off-outline",
                            size: "30"
                          })
                        ]))
                  ]),
                  _createElementVNode("div", _hoisted_10, [
                    _createElementVNode("div", _hoisted_11, [
                      _createElementVNode("div", {
                        class: "record-title",
                        title: record.media_name
                      }, _toDisplayString(record.media_name || '未知媒体'), 9, _hoisted_12),
                      _createVNode(_component_VChip, {
                        size: "small",
                        variant: "tonal",
                        color: record.media_type === '电视剧' ? 'info' : 'primary'
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(record.media_type || '未知'), 1)
                        ]),
                        _: 2
                      }, 1032, ["color"])
                    ]),
                    _createElementVNode("div", _hoisted_13, [
                      _createVNode(_component_VIcon, {
                        icon: "mdi-clock-outline",
                        size: "15"
                      }),
                      _createElementVNode("span", null, _toDisplayString(record.organized_at), 1)
                    ]),
                    _createElementVNode("div", {
                      class: "record-path",
                      title: record.target_path
                    }, [
                      _createVNode(_component_VIcon, {
                        icon: "mdi-folder-arrow-right-outline",
                        size: "16"
                      }),
                      _createElementVNode("span", null, _toDisplayString(record.target_path || '目标路径未返回'), 1)
                    ], 8, _hoisted_14)
                  ])
                ]),
                _: 2
              }, 1024))
            }), 128))
          ])),
    (total.value > 0)
      ? (_openBlock(), _createElementBlock("div", _hoisted_15, [
          _createVNode(_component_VBtn, {
            icon: "mdi-chevron-left",
            size: "small",
            variant: "tonal",
            disabled: page.value <= 1 || loading.value,
            title: "上一页",
            onClick: previousPage
          }, null, 8, ["disabled"]),
          _createElementVNode("span", _hoisted_16, "第 " + _toDisplayString(pageText.value) + " 页", 1),
          _createVNode(_component_VBtn, {
            icon: "mdi-chevron-right",
            size: "small",
            variant: "tonal",
            disabled: page.value >= pages.value || loading.value,
            title: "下一页",
            onClick: nextPage
          }, null, 8, ["disabled"])
        ]))
      : _createCommentVNode("", true)
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-7016292e"]]);

export { Page as default };
