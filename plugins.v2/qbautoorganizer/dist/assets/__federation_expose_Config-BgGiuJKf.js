import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,createTextVNode:_createTextVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "config-page" };
const _hoisted_2 = { class: "d-flex align-center ga-3" };

const {onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({}) },
},
  emits: ['save', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const defaults = {
  qb_url: 'http://127.0.0.1:8080', username: 'admin', password: '', interval: 30,
  tag_filter: '', force_organize: false, log_level: 'INFO', enabled: false,
};
const config = ref({ ...defaults });
const testing = ref(false);
const snackbar = ref(false);
const testSuccess = ref(false);
const testMessage = ref('');
const logLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR'];

function save() {
  config.value.interval = Math.max(10, Number(config.value.interval || 30));
  emit('save', { ...config.value });
}

async function testConnection() {
  testing.value = true;
  try {
    const response = await props.api.get('plugin/QbAutoOrganizer/test');
    const payload = response?.data?.success !== undefined ? response.data : response;
    testSuccess.value = Boolean(payload?.success);
    testMessage.value = payload?.message || (testSuccess.value ? '连接成功' : '连接失败');
  } catch (err) {
    testSuccess.value = false;
    testMessage.value = err?.message || '连接测试失败';
  } finally {
    testing.value = false;
    snackbar.value = true;
  }
}

onMounted(() => { config.value = { ...defaults, ...(props.initialConfig || {}) }; });

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VSelect = _resolveComponent("VSelect");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VSnackbar = _resolveComponent("VSnackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      color: "transparent",
      density: "comfortable"
    }, {
      default: _withCtx(() => [
        _cache[11] || (_cache[11] = _createElementVNode("div", { class: "text-h6 font-weight-bold ms-3" }, "qB自动整理助手配置", -1)),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VBtn, {
          icon: "mdi-content-save",
          color: "primary",
          variant: "text",
          title: "保存",
          onClick: save
        }),
        _createVNode(_component_VBtn, {
          icon: "mdi-close",
          variant: "text",
          title: "关闭",
          onClick: _cache[0] || (_cache[0] = $event => (emit('close')))
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VCard, {
      variant: "tonal",
      class: "config-card"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCardTitle, null, {
          default: _withCtx(() => [
            _createVNode(_component_VIcon, {
              icon: "mdi-server-network",
              color: "primary",
              class: "mr-2"
            }),
            _cache[12] || (_cache[12] = _createTextVNode("qBittorrent 连接", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_VDivider),
        _createVNode(_component_VCardText, null, {
          default: _withCtx(() => [
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.qb_url,
                      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.value.qb_url) = $event)),
                      label: "服务器地址",
                      "prepend-inner-icon": "mdi-web"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.username,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.username) = $event)),
                      label: "用户名",
                      "prepend-inner-icon": "mdi-account"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.password,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.password) = $event)),
                      label: "密码",
                      type: "password",
                      "prepend-inner-icon": "mdi-lock"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createElementVNode("div", _hoisted_2, [
              _createVNode(_component_VBtn, {
                color: "primary",
                variant: "elevated",
                "prepend-icon": "mdi-lan-connect",
                loading: testing.value,
                onClick: testConnection
              }, {
                default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
                  _createTextVNode("立即检测", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              _cache[14] || (_cache[14] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "检测使用已保存的连接配置", -1))
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VCard, {
      variant: "tonal",
      class: "config-card"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCardTitle, null, {
          default: _withCtx(() => [
            _createVNode(_component_VIcon, {
              icon: "mdi-tune-variant",
              color: "success",
              class: "mr-2"
            }),
            _cache[15] || (_cache[15] = _createTextVNode("监控规则", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_VDivider),
        _createVNode(_component_VCardText, null, {
          default: _withCtx(() => [
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.interval,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.interval) = $event)),
                      modelModifiers: { number: true },
                      label: "监控间隔（秒）",
                      type: "number",
                      min: "10",
                      hint: "最小 10 秒",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.tag_filter,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.tag_filter) = $event)),
                      label: "标签过滤",
                      placeholder: "movie,tv",
                      hint: "逗号分隔，命中任一标签；留空处理全部",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSwitch, {
                      modelValue: config.value.force_organize,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.force_organize) = $event)),
                      label: "强制整理",
                      color: "warning",
                      inset: "",
                      hint: "传递 manual=True、force=True，忽略“已整理”标签和历史整理记录",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VCard, {
      variant: "tonal",
      class: "config-card"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCardTitle, null, {
          default: _withCtx(() => [
            _createVNode(_component_VIcon, {
              icon: "mdi-bug-outline",
              color: "warning",
              class: "mr-2"
            }),
            _cache[16] || (_cache[16] = _createTextVNode("调试设置", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_VDivider),
        _createVNode(_component_VCardText, null, {
          default: _withCtx(() => [
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSelect, {
                      modelValue: config.value.log_level,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.log_level) = $event)),
                      items: logLevels,
                      label: "日志级别"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSwitch, {
                      modelValue: config.value.enabled,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.enabled) = $event)),
                      label: "启用插件",
                      color: "primary",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VAlert, {
              type: "info",
              variant: "tonal"
            }, {
              default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
                _createTextVNode("启用时会把 qB 中所有现有种子作为启动基线，之后只整理新添加且下载完成的种子。", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VSnackbar, {
      modelValue: snackbar.value,
      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((snackbar).value = $event)),
      color: testSuccess.value ? 'success' : 'error',
      timeout: "5000"
    }, {
      actions: _withCtx(() => [
        _createVNode(_component_VBtn, {
          variant: "text",
          onClick: _cache[9] || (_cache[9] = $event => (snackbar.value = false))
        }, {
          default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
            _createTextVNode("关闭", -1)
          ]))]),
          _: 1
        })
      ]),
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(testMessage.value) + " ", 1)
      ]),
      _: 1
    }, 8, ["modelValue", "color"])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-09375a7c"]]);

export { Config as default };
