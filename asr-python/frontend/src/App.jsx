
import { useState } from 'react';
import AudioVisualizer from './components/AudioVisualizer';
import RecordingList from './components/RecordingList';
import VoiceGallery from './components/VoiceGallery';
import ModelPanel from './components/ModelPanel';
import { useAudioProcessor } from './hooks/useAudioProcessor';
import { useModels } from './hooks/useModels';
import './App.css';

function App() {
  const { models, error, prepare } = useModels();
  const asrReady = models.asr?.state === 'ready';
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = asrReady ? `${wsProtocol}//${window.location.host}/ws/transcribe` : null;
  const { isRecording, isFinalizing, isConnected, transcript, startRecording, stopRecording, clearTranscript, analyser } = useAudioProcessor(wsUrl);
  const [activeTab, setActiveTab] = useState('transcribe');

  return (
    <div className="app-container">
      {/* Background Visualizer */}
      <AudioVisualizer analyser={analyser} isRecording={isRecording} />

      {/* Main Content Overlay */}
      <div className="content-overlay">
        <header className="header">
          <h1>GLM-ASR <span className="highlight">实时转录</span></h1>
          <div className="header-right">
            <div className="tab-switcher">
              <button
                className={`tab-btn ${activeTab === 'transcribe' ? 'active' : ''}`}
                onClick={() => setActiveTab('transcribe')}
              >
                实时转录
              </button>
              <button
                className={`tab-btn ${activeTab === 'recordings' ? 'active' : ''}`}
                onClick={() => setActiveTab('recordings')}
              >
                录音管理
              </button>
              <button
                className={`tab-btn ${activeTab === 'voices' ? 'active' : ''}`}
                onClick={() => setActiveTab('voices')}
              >
                我的声音
              </button>
              <button
                className={`tab-btn ${activeTab === 'models' ? 'active' : ''}`}
                onClick={() => setActiveTab('models')}
              >
                模型管理
              </button>
            </div>
            <div className={`status-badge ${isConnected ? 'online' : 'offline'}`}>
              {isConnected ? '转录已就绪' : asrReady ? '正在连接' : '转录模型未就绪'}
            </div>
          </div>
        </header>

        {activeTab === 'models' || (activeTab === 'transcribe' && !asrReady) ? (
          <main className="main-display model-view">
            <ModelPanel models={models} error={error} prepare={prepare} />
          </main>
        ) : activeTab === 'transcribe' ? (
          <>
            <main className="main-display">
              <div className="transcript-box">
                {transcript || <span className="placeholder">{isRecording ? '正在聆听…' : '开始录音后，转写会显示在这里。'}</span>}
              </div>
            </main>

            <footer className="controls">
              {!isRecording ? (
                <div className="button-group">
                  <button className="btn-primary start" onClick={startRecording} disabled={!isConnected || isFinalizing}>
                    {isFinalizing ? '正在保存…' : '开始录音'}
                  </button>
                  {transcript && (
                    <button className="btn-secondary clear" onClick={clearTranscript}>
                      清除文本
                    </button>
                  )}
                </div>
              ) : (
                <button className="btn-primary stop" onClick={stopRecording}>
                  停止录音
                </button>
              )}
            </footer>
          </>
        ) : activeTab === 'recordings' ? (
          <main className="main-display recordings-view">
            <RecordingList ttsLoaded={models.tts?.state === 'ready'} openModels={() => setActiveTab('models')} />
          </main>
        ) : (
          <main className="main-display voices-view">
            <VoiceGallery />
          </main>
        )}
      </div>
    </div>
  );
}

export default App;

