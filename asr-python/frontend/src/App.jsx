
import { useState } from 'react';
import AudioVisualizer from './components/AudioVisualizer';
import RecordingList from './components/RecordingList';
import VoiceGallery from './components/VoiceGallery';
import ModelPanel from './components/ModelPanel';
import { useAudioProcessor } from './hooks/useAudioProcessor';
import { useModels } from './hooks/useModels';
import './App.css';

const tabs = [
  ['transcribe', '实时转录'],
  ['recordings', '录音管理'],
  ['voices', '我的声音'],
  ['models', '模型管理'],
];

function App() {
  const { models, serviceStatus, error, prepare } = useModels();
  const asrReady = models.asr?.state === 'ready';
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = asrReady ? `${wsProtocol}//${window.location.host}/ws/transcribe` : null;
  const { isRecording, isFinalizing, isConnected, transcript, startRecording, stopRecording, clearTranscript, analyser } = useAudioProcessor(wsUrl);
  const [activeTab, setActiveTab] = useState('transcribe');
  const view = activeTab === 'transcribe' && !asrReady ? 'models' : activeTab;
  const statusText = {
    checking: '正在连接本地服务',
    offline: '本地服务离线',
    online: isConnected ? '转录已就绪' : '本地服务在线',
  }[serviceStatus];

  return (
    <div className="app-container">
      <AudioVisualizer analyser={analyser} isRecording={isRecording} />

      <div className="content-overlay">
        <header className="workbench-header">
          <div className="workbench-top">
            <div className="workbench-brand">
              <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
              <h1>GLM-ASR <span>语音工作台</span></h1>
            </div>
            <div className={`service-status ${serviceStatus}`} role="status">
              {statusText}
            </div>
          </div>
          <nav className="tab-switcher" aria-label="工作台">
            {tabs.map(([id, label]) => (
              <button
                key={id}
                className="tab-btn"
                aria-current={activeTab === id ? 'page' : undefined}
                onClick={() => setActiveTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>
        </header>

        <main className={`main-display ${view}-view`} key={view}>
          {view === 'models' ? (
            <ModelPanel models={models} serviceStatus={serviceStatus} error={error} prepare={prepare} />
          ) : view === 'transcribe' ? (
            <section className="transcribe-panel" aria-labelledby="transcribe-title">
              <h2 id="transcribe-title">实时转录</h2>
              <div className="transcript-box">
                {transcript || (
                  <span className="placeholder">
                    {isRecording ? '正在聆听…' : isConnected ? '开始录音后，转写会显示在这里。' : '正在连接转录服务…'}
                  </span>
                )}
              </div>
              <footer className="controls">
                {isRecording ? (
                  <button className="btn-primary stop" onClick={stopRecording}>
                    停止录音
                  </button>
                ) : (
                  <button className="btn-primary start" onClick={startRecording} disabled={!isConnected || isFinalizing}>
                    {isFinalizing ? '正在保存…' : '开始录音'}
                  </button>
                )}
                {!isRecording && transcript && (
                  <button className="btn-secondary" onClick={clearTranscript}>
                    清除文本
                  </button>
                )}
              </footer>
            </section>
          ) : view === 'recordings' ? (
            <RecordingList ttsLoaded={models.tts?.state === 'ready'} openModels={() => setActiveTab('models')} />
          ) : (
            <VoiceGallery />
          )}
        </main>
      </div>
    </div>
  );
}

export default App;

