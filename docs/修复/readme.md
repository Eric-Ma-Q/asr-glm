# 修复记录

本文档记录项目修复历史。

## 1. 前端依赖问题

### 1.1 @rollup/rollup-win32-x64-msvc 模块缺失

**问题描述**：运行 `npm run dev` 时报错 `Cannot find module @rollup/rollup-win32-x64-msvc`。

**原因分析**：
- npm 在 Windows 上处理 `optionalDependencies` 存在已知 bug ([#4828](https://github.com/npm/cli/issues/4828))。
- `rollup` 的 Windows 原生模块被标记为可选依赖，npm 可能跳过安装。
- Node.js v22+ 与部分 Vite/Rollup 版本存在兼容性问题。

**解决方案**：
强制安装对应版本的原生模块：
```bash
npm install @rollup/rollup-win32-x64-msvc@4.53.3 --save-dev --force
```

**注意**：版本号需与项目中 `rollup` 版本一致，可通过 `npm ls rollup` 查看。

更新: 2025-12-13

## 2. 界面显示异常

### 2.1 按钮无法点击与背景遮挡

**问题描述**：界面交互按钮不可见/不可点击，粒子背景覆盖在内容之上，且粒子效果模糊。

**原因分析**：
- `AudioVisualizer` 组件依赖的 CSS 类失效，导致 Canvas 挤占布局空间。
- 缺少 HiDPI (High DPI) 适配导致在高分屏下粒子渲染模糊。

**解决方案**：
- 在 `App.css` 中强制指定 Canvas 为 `position: absolute; z-index: 0`。
- 重写 `AudioVisualizer` 渲染逻辑，加入 `window.devicePixelRatio` 缩放支持。
- 优化粒子绘制算法，增加光晕效果。

更新: 2025-12-13

## 3. 模型加载问题

### 3.1 WhisperFlashAttention2 导入错误

**问题描述**：启动后端时报错 `ImportError: cannot import name 'WhisperFlashAttention2' from 'transformers.models.whisper.modeling_whisper'`。

**原因分析**：
- HuggingFace 上的 GLM-ASR 模型代码更新，引用了 `WhisperFlashAttention2` 类。
- 该类在 transformers 4.53+ 版本中被重构移除（改为统一的 attention 实现）。
- HuggingFace 缓存中下载了不兼容的模型代码版本。

**解决方案**：
1. 降级 transformers 到兼容版本：
   ```bash
   pip install transformers==4.45.0
   ```
2. 清除 HuggingFace 缓存：
   ```bash
   Remove-Item -Recurse -Force "C:\Users\<用户名>\.cache\huggingface\modules\transformers_modules\zai_hyphen_org"
   ```
3. 重新启动后端，模型代码会自动重新下载。

更新: 2025-12-13

### 3.2 LlamaForCausalLM dtype 参数错误

**问题描述**：TTS 模型加载时报错 `TypeError: LlamaForCausalLM.__init__() got an unexpected keyword argument 'dtype'`。

**原因分析**：
- `tts_service.py` 中使用了错误的参数名 `dtype`。
- transformers 的 `from_pretrained` 方法使用 `torch_dtype` 作为参数名。

**解决方案**：
修改 `tts_service.py` 第 225 行：
```python
# 错误
self.llm.llama = LlamaForCausalLM.from_pretrained(llama_path, dtype=torch.float32)
# 正确
self.llm.llama = LlamaForCausalLM.from_pretrained(llama_path, torch_dtype=torch.float32)
```

更新: 2025-12-13

## 4. 布局显示问题

### 4.1 录音管理页面头部被隐藏

**问题描述**：录音管理页面的"录音列表"标题、"刷新"和"加载TTS模型"按钮不显示。

**原因分析**：
- `.recordings-view` 的 CSS 使用了 `align-items: center` 继承自 `.main-display`，导致内容居中。
- 缺少 `justify-content: flex-start` 导致内容没有从顶部开始排列。

**解决方案**：
修改 `App.css` 中 `.recordings-view` 样式：
```css
.recordings-view {
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;  /* 新增 */
  overflow-y: auto;
  padding: 0;
  margin-top: 0;  /* 新增 */
}
```

更新: 2025-12-13

