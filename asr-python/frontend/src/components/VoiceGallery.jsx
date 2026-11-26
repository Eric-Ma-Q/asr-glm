import { useCallback, useState, useEffect, useRef } from 'react';
import './VoiceGallery.css';

function VoiceGallery() {
    const [voices, setVoices] = useState([]);
    const [loading, setLoading] = useState(true);
    const [playingId, setPlayingId] = useState(null);
    const [playProgress, setPlayProgress] = useState({});
    const audioRef = useRef(null);

    // 获取克隆音频列表
    const fetchVoices = useCallback((signal) => {
        return fetch('/api/cloned_voices', { signal })
            .then(res => res.json())
            .then(data => setVoices(data.cloned_voices || []))
            .catch(err => {
                if (!signal?.aborted) console.error('Failed to fetch cloned voices:', err);
            })
            .finally(() => {
                if (!signal?.aborted) setLoading(false);
            });
    }, []);

    useEffect(() => {
        const request = new AbortController();
        fetchVoices(request.signal);
        return () => request.abort();
    }, [fetchVoices]);

    // 格式化日期
    const formatDate = (isoString) => {
        const date = new Date(isoString);
        return date.toLocaleString('zh-CN');
    };

    // 播放音频
    const playVoice = (voice) => {
        if (playingId === voice.id) {
            // 暂停当前播放
            audioRef.current?.pause();
            setPlayingId(null);
            return;
        }

        // 播放新的
        if (audioRef.current) {
            audioRef.current.pause();
        }

        const audio = new Audio(`/audio/tts/${voice.filename}`);
        audioRef.current = audio;

        audio.addEventListener('timeupdate', () => {
            const progress = (audio.currentTime / audio.duration) * 100;
            setPlayProgress(prev => ({ ...prev, [voice.id]: { progress, currentTime: audio.currentTime, duration: audio.duration } }));
        });

        audio.addEventListener('ended', () => {
            setPlayingId(null);
        });

        audio.play();
        setPlayingId(voice.id);
    };

    // 进度条跳转
    const handleSeek = (e, voiceId) => {
        if (!audioRef.current || playingId !== voiceId) return;

        const track = e.currentTarget;
        const rect = track.getBoundingClientRect();
        const offsetX = e.clientX - rect.left;
        const percentage = Math.min(Math.max(0, offsetX / rect.width), 1);

        const duration = audioRef.current.duration;
        if (duration) {
            audioRef.current.currentTime = duration * percentage;
            // 更新进度
            setPlayProgress(prev => ({
                ...prev,
                [voiceId]: {
                    ...prev[voiceId],
                    progress: percentage * 100,
                    currentTime: duration * percentage
                }
            }));
        }
    };

    // 删除克隆音频
    const deleteVoice = async (id) => {
        if (!confirm('确定要删除这个克隆语音吗？')) return;
        try {
            await fetch(`/api/cloned_voices/${id}`, { method: 'DELETE' });
            fetchVoices();
        } catch (err) {
            alert('删除失败: ' + err.message);
        }
    };

    // 下载音频
    const downloadVoice = (voice) => {
        const link = document.createElement('a');
        link.href = `/audio/tts/${voice.filename}`;
        link.download = voice.filename;
        link.click();
    };

    // 格式化时间
    const formatTime = (seconds) => {
        if (!seconds || isNaN(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    if (loading) {
        return <div className="voice-gallery loading">加载中...</div>;
    }

    return (
        <div className="voice-gallery">
            <div className="gallery-header">
                <h2>🎙️ 我的克隆声音</h2>
                <button className="btn-refresh" onClick={() => fetchVoices()}>
                    刷新
                </button>
            </div>

            {voices.length === 0 ? (
                <div className="empty-state">
                    <div className="empty-icon">🔊</div>
                    <p>暂无克隆声音</p>
                    <p className="hint">在「录音管理」中选择录音并克隆音色</p>
                </div>
            ) : (
                <div className="voices-grid">
                    {voices.map(voice => (
                        <div key={voice.id} className={`voice-card ${playingId === voice.id ? 'playing' : ''}`}>
                            {/* 左侧：控制区 */}
                            <div className="voice-card-left">
                                <div className="voice-header-info">
                                    <div className="voice-date">{formatDate(voice.created_at)}</div>
                                    <div className="voice-source">
                                        <span className="source-label">源:</span>
                                        <span className="source-file" title={voice.source_recording.filename}>
                                            {voice.source_recording.filename}
                                        </span>
                                    </div>
                                </div>

                                {/* 播放器 */}
                                <div className="voice-player">
                                    <button
                                        className={`btn-play-large ${playingId === voice.id ? 'active' : ''}`}
                                        onClick={() => playVoice(voice)}
                                    >
                                        {playingId === voice.id ? '⏸' : '▶'}
                                    </button>
                                    <div className="player-track" onClick={(e) => handleSeek(e, voice.id)}>
                                        <div
                                            className="player-progress"
                                            style={{ width: `${playProgress[voice.id]?.progress || 0}%` }}
                                        />
                                    </div>
                                    <span className="player-time">
                                        {playProgress[voice.id]
                                            ? `${formatTime(playProgress[voice.id].currentTime)}`
                                            : '--:--'
                                        }
                                    </span>
                                </div>

                                {/* 操作按钮 */}
                                <div className="voice-actions">
                                    <button className="btn-action download" onClick={() => downloadVoice(voice)}>
                                        ⬇ 下载
                                    </button>
                                    <button className="btn-action delete" onClick={() => deleteVoice(voice.id)}>
                                        🗑 删除
                                    </button>
                                </div>
                            </div>

                            {/* 右侧：文本区 */}
                            <div className="voice-card-right">
                                <div className="voice-text">
                                    {voice.text}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

export default VoiceGallery;
