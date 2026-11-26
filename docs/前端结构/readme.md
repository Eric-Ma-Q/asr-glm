# 前端结构

本文档记录前端项目的结构和变更。

## 1. 目录结构
```text
asr-python/frontend/
├── src/
│   ├── components/
│   │   ├── AudioVisualizer.jsx  # 粒子波形可视化组件
│   │   ├── RecordingList.jsx    # 录音管理与语音克隆组件
│   │   ├── RecordingList.css    # 录音管理样式
│   │   ├── VoiceGallery.jsx     # 克隆声音库组件
│   │   └── VoiceGallery.css     # 声音库样式
│   └── hooks/
│       └── useAudioProcessor.js # 音频处理与WebSocket通信Hook
├── App.jsx                      # 主界面（含Tab切换）
├── App.css                      # 主要样式
└── index.css                    # 全局重置
```

## 2. 变更记录

### 2.1 实时转录界面
新增 React 前端界面，集成 WebSocket 实时通信与 Canvas 粒子动效。
- **AudioVisualizer.jsx**: 使用 HTML5 Canvas 实现声波粒子效果。
- **useAudioProcessor.js**: 获取麦克风流 -> Float32 转换 -> WebSocket 发送。
- **App.jsx**: 暗色玻璃拟态 UI，显示实时转录文本。

更新: 2025-12-13

### 2.2 清除文本功能
在录音停止状态下，增加清除当前转录文本的能力。
- **App.jsx**: 增加"清除文本"按钮，仅在有文本且非录音状态显示。
- **useAudioProcessor.js**: 暴露 `clearTranscript` 方法重置状态。

更新: 2025-12-13

### 2.3 Tab 切换功能
支持在"实时转录"和"录音管理"两个视图之间切换。
- **App.jsx**: 新增 `activeTab` 状态，控制当前显示视图。
- **App.css**: 新增 `.tab-switcher`、`.tab-btn` 样式。

更新: 2025-12-13

### 2.4 录音管理组件
新增 `RecordingList.jsx` 组件，提供录音列表管理与语音克隆功能。

#### 功能列表
1. **录音列表**: 显示所有保存的录音，包含文件名、时长、创建时间
2. **播放录音**: 点击播放按钮可直接播放录音
3. **删除录音**: 支持删除单条录音
4. **TTS 模型加载**: 手动加载 GLM-TTS 模型（显示加载状态）

#### 文件
- `components/RecordingList.jsx`: 组件逻辑
- `components/RecordingList.css`: 组件样式

更新: 2025-12-13

### 2.5 语音克隆模态框
点击"克隆音色"按钮打开模态框，支持语音克隆任务。

#### 功能
1. **输入提示文本**: 填写录音中说的话（用于音色提取）
2. **输入合成文本**: 填写要用克隆声音合成的新内容
3. **进度条**: 实时显示克隆任务进度
4. **试听结果**: 克隆完成后可直接播放

#### 克隆结果展示
- 每条录音可展开查看其克隆生成的音频列表
- 支持播放历史克隆结果

更新: 2025-12-13

### 2.6 声音库组件
新增 `VoiceGallery.jsx` 组件，展示所有克隆生成的语音。

#### 功能
1. **卡片式布局**: 每个克隆音频一张卡片，网格自适应排列
2. **内联播放器**: 带进度条和时间显示，支持播放/暂停
3. **来源追溯**: 显示使用的原始录音文件名
4. **操作按钮**: 支持下载、删除

#### 文件
- `components/VoiceGallery.jsx`: 组件逻辑
- `components/VoiceGallery.css`: 组件样式

#### Tab 扩展
`App.jsx` 新增「我的声音」Tab，支持三视图切换：
- 实时转录
- 录音管理
- 我的声音

更新: 2025-12-13

### 2.7 转写文本保存与编辑功能
录音时的实时转写文本可以随录音一起保存，并支持在录音管理中编辑。

#### 功能
1. **自动保存转写文本**: 停止录音时，当前转写文本自动保存到录音的 `prompt_text` 字段
2. **显示转写文本**: 录音管理列表中显示每条录音的转写文本
3. **编辑转写文本**: 点击"编辑"按钮可修改转写文本，支持保存/取消
4. **无文本提示**: 无转写文本时显示"暂无转写文本，点击编辑添加"

#### 相关修改
- **useAudioProcessor.js**: 新增 `transcriptRef` 追踪最新文本，`stopRecording` 时发送转写文本
- **RecordingList.jsx**: 新增 `editingId`、`editingText` 状态，`startEditing`、`saveTranscript`、`cancelEditing` 方法
- **RecordingList.css**: 新增 `.transcript-edit`、`.btn-edit`、`.btn-save`、`.btn-cancel-edit` 等样式

#### 布局优化
录音项布局调整为上下结构：
- 顶部：文件名、时长、时间 + 操作按钮（播放、克隆音色、删除）
- 下方：可编辑的转写文本区域

更新: 2025-12-13

