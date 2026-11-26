const modelNames = {
  asr: ['GLM-ASR-Nano-2512', '实时转录'],
  tts: ['GLM-TTS', '语音克隆'],
};

export default function ModelPanel({ models, error, prepare }) {
  return (
    <section className="model-panel" aria-label="本地模型">
      <h2>本地模型</h2>
      <p>首次使用按需下载。录音与推理均在这台电脑上完成。</p>
      {error && <p role="alert" className="model-error">{error}</p>}
      {Object.entries(modelNames).map(([key, [name, use]]) => {
        const model = models[key];
        if (!model) return null;
        const { state, total_bytes: total, downloaded_bytes: downloaded } = model;
        const working = state === 'downloading' || state === 'loading';
        const ready = state === 'ready';
        return (
          <article className="model-row" key={key}>
            <div className="model-label">
              <h3>{name}</h3>
              <p>{use} · {(total / 1e9).toFixed(1)} GB</p>
            </div>
            {ready ? <span className="model-ready">已就绪</span> : (
              <button className="btn-secondary" disabled={working} onClick={() => prepare(key)}>
                {state === 'downloading' ? '下载中…'
                  : state === 'loading' ? '加载中…'
                    : state === 'error' ? '重试'
                      : model.installed ? '加载模型' : '一键下载'}
              </button>
            )}
            {state === 'downloading' && (
              <div className="model-progress">
                <progress value={downloaded} max={total} aria-label={`${name} 下载进度`} />
                <span>{model.file ? `${((downloaded / total) * 100).toFixed(1)}% · ${model.file}` : '准备下载…'}</span>
              </div>
            )}
            {model.error && <p role="alert" className="model-error">{model.error}</p>}
          </article>
        );
      })}
    </section>
  );
}
