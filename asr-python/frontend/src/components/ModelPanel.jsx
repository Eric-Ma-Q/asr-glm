const modelNames = {
  asr: ['GLM-ASR-Nano-2512', '实时转录'],
  tts: ['GLM-TTS', '语音克隆'],
};

export default function ModelPanel({ models, serviceStatus, error, prepare }) {
  return (
    <section className="model-panel" aria-labelledby="models-title">
      <header className="workspace-heading">
        <h2 id="models-title">本地模型</h2>
        <p>按需下载，录音与推理都在这台电脑上完成。</p>
      </header>
      {serviceStatus === 'offline' && (
        <div className="model-notice" role="alert">
          <p>在项目目录启动本地服务，页面会自动重连。</p>
          <code>python asr-python/backend/main.py</code>
        </div>
      )}
      {error && serviceStatus === 'online' && <p role="alert" className="model-error">{error}</p>}
      <div className="model-grid">
        {Object.entries(modelNames).map(([key, [name, use]]) => {
          const model = models[key];
          const state = serviceStatus === 'online' ? model?.state : undefined;
          const total = model?.total_bytes;
          const working = state === 'downloading' || state === 'loading';
          return (
            <article className="model-card" key={key} aria-labelledby={`model-${key}-title`}>
              <div className="model-card-heading">
                <h3 id={`model-${key}-title`}>{use}</h3>
                {total > 0 && <span className="model-size">{(total / 1e9).toFixed(1)} GB</span>}
              </div>
              <p className="model-name">{name}</p>
              <div className="model-card-actions">
                {!state ? (
                  <span className="model-waiting">{serviceStatus === 'online' ? '状态暂不可用' : '等待连接'}</span>
                ) : state === 'ready' ? (
                  <span className="model-ready">已就绪</span>
                ) : (
                  <button className="btn-secondary" disabled={working} onClick={() => prepare(key)}>
                    {state === 'downloading' ? '下载中…'
                      : state === 'loading' ? '加载中…'
                      : state === 'error' ? '重试'
                      : model.installed ? '加载模型' : '一键下载'}
                  </button>
                )}
              </div>
              {state === 'downloading' && (
                <div className="model-progress">
                  <progress value={model.downloaded_bytes} max={total} aria-label={`${name} 下载进度`} />
                  {model.file && <span>{((model.downloaded_bytes / total) * 100).toFixed(1)}% · {model.file}</span>}
                </div>
              )}
              {state === 'error' && model.error && <p role="alert" className="model-error">{model.error}</p>}
            </article>
          );
        })}
      </div>
    </section>
  );
}
