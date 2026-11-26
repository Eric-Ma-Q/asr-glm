import { useCallback, useState, useEffect, useRef } from 'react';
import './RecordingList.css';

const IMPORT_FORMATS = '.wav,.mp3,.m4a,.mp4,.aac,.amr,.flac,.ogg,.webm';

function RecordingList({ ttsLoaded, openModels }) {
    const [recordings, setRecordings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expandedId, setExpandedId] = useState(null);
    const [cloneModal, setCloneModal] = useState(null);
    const [cloneProgress, setCloneProgress] = useState(null);
    const [importing, setImporting] = useState(false);
    const [importError, setImportError] = useState('');
    const [editingId, setEditingId] = useState(null);  // 正在编辑的录音ID
    const [editingText, setEditingText] = useState(""); // 编辑中的文本
    const audioRefs = useRef({});
    const importInput = useRef(null);

    // 获取录音列表
    const fetchRecordings = useCallback((signal) => {
        return fetch('/api/recordings', { signal })
            .then(res => res.json())
            .then(data => setRecordings((data.recordings || []).sort((a, b) => b.created_at.localeCompare(a.created_at))))
            .catch(err => {
                if (!signal?.aborted) console.error('Failed to fetch recordings:', err);
            })
            .finally(() => {
                if (!signal?.aborted) setLoading(false);
            });
    }, []);

    const importAudio = async (event) => {
        const file = event.currentTarget.files?.[0];
        event.currentTarget.value = '';
        if (!file) return;

        setImporting(true);
        setImportError('');
        const form = new FormData();
        form.append('file', file);
        try {
            const res = await fetch(`/api/recordings`, { method: 'POST', body: form });
            const data = await res.json().catch(() => null);
            if (!res.ok || !data?.id) {
                throw new Error(typeof data?.detail === 'string' ? data.detail : '导入失败，请重试。');
            }
            setRecordings(prev => [data, ...prev]);
        } catch (error) {
            setImportError(error.message);
        } finally {
            setImporting(false);
        }
    };

    useEffect(() => {
        const request = new AbortController();
        fetchRecordings(request.signal);
        return () => request.abort();
    }, [fetchRecordings]);

    // 格式化时间
    const formatDuration = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    // 格式化日期
    const formatDate = (isoString) => {
        const date = new Date(isoString);
        return date.toLocaleString('zh-CN');
    };

    // 播放/暂停音频
    const togglePlay = (id) => {
        const audio = audioRefs.current[id];
        if (audio) {
            if (audio.paused) {
                // 暂停其他音频
                Object.values(audioRefs.current).forEach(a => {
                    if (a && a !== audio) a.pause();
                });
                audio.play();
            } else {
                audio.pause();
            }
        }
    };

    // 删除录音
    const deleteRecording = async (id) => {
        if (!confirm('确定要删除这条录音吗？')) return;
        try {
            await fetch(`/api/recordings/${id}`, { method: 'DELETE' });
            fetchRecordings();
        } catch (err) {
            alert('删除失败: ' + err.message);
        }
    };

    // 开始编辑转写文本
    const startEditing = (rec, e) => {
        e.stopPropagation();
        setEditingId(rec.id);
        setEditingText(rec.prompt_text || "");
    };

    // 保存转写文本
    const saveTranscript = async (id, e) => {
        e.stopPropagation();
        try {
            await fetch(`/api/recordings/${id}/prompt_text`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt_text: editingText })
            });
            // 更新本地状态
            setRecordings(prev => prev.map(rec =>
                rec.id === id ? { ...rec, prompt_text: editingText } : rec
            ));
            setEditingId(null);
            setEditingText("");
        } catch (err) {
            alert('保存失败: ' + err.message);
        }
    };

    // 取消编辑
    const cancelEditing = (e) => {
        e.stopPropagation();
        setEditingId(null);
        setEditingText("");
    };

    // 打开克隆模态框
    const openCloneModal = (recording) => {
        if (!ttsLoaded) {
            alert('请先加载 TTS 模型');
            return;
        }
        setCloneModal({
            recording,
            promptText: recording.prompt_text || '',
            synText: ''
        });
    };

    // 开始克隆
    const startClone = async () => {
        if (!cloneModal.promptText.trim()) {
            alert('请输入录音中说的话');
            return;
        }
        if (!cloneModal.synText.trim()) {
            alert('请输入要合成的文本');
            return;
        }

        try {
            // 先更新 prompt_text
            await fetch(`/api/recordings/${cloneModal.recording.id}/prompt_text`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt_text: cloneModal.promptText })
            });

            // 启动克隆任务
            const res = await fetch(`/api/clone_voice`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    recording_id: cloneModal.recording.id,
                    prompt_text: cloneModal.promptText,
                    syn_text: cloneModal.synText
                })
            });
            const data = await res.json();

            if (data.task_id) {
                setCloneProgress({ taskId: data.task_id, progress: 0, message: '准备中...' });
                pollProgress(data.task_id);
            }
        } catch (err) {
            alert('启动克隆失败: ' + err.message);
        }
    };

    // 轮询进度
    const pollProgress = async (taskId) => {
        try {
            const res = await fetch(`/api/clone_voice/${taskId}/progress`);
            const data = await res.json();

            setCloneProgress({
                taskId,
                progress: data.progress,
                message: data.message,
                status: data.status,
                outputUrl: data.output_url
            });

            if (data.status === 'running') {
                setTimeout(() => pollProgress(taskId), 500);
            } else if (data.status === 'completed') {
                fetchRecordings();
                setTimeout(() => {
                    setCloneModal(null);
                    setCloneProgress(null);
                }, 2000);
            } else if (data.status === 'error') {
                alert('克隆失败: ' + data.message);
            }
        } catch (err) {
            console.error('Poll progress error:', err);
        }
    };

    if (loading) {
        return <div className="recording-list loading">加载中...</div>;
    }

    return (
        <div className="recording-list">
            <div className="list-header">
                <h2>录音列表</h2>
                <div className="header-actions">
                    <input ref={importInput} type="file" accept={IMPORT_FORMATS} onChange={importAudio} hidden />
                    <button className="btn-import" onClick={() => importInput.current.click()} disabled={importing}>
                        {importing ? '导入中…' : '导入音频'}
                    </button>
                    <button className="btn-refresh" onClick={() => fetchRecordings()} disabled={importing}>
                        刷新
                    </button>
                    {!ttsLoaded ? (
                        <button
                            className="btn-load-tts"
                            onClick={openModels}
                        >
                            管理 TTS 模型
                        </button>
                    ) : (
                        <span className="tts-status online">TTS 已就绪</span>
                    )}
                </div>
            </div>

            {importError && <p role="alert" className="import-error">{importError}</p>}

            {recordings.length === 0 ? (
                <div className="empty-state">
                    <p>暂无录音</p>
                    <p className="hint">录音会自动保存到这里，也可以导入已有音频</p>
                </div>
            ) : (
                <div className="recordings">
                    {recordings.map(rec => (
                        <div
                            key={rec.id}
                            className={`recording-item ${expandedId === rec.id ? 'expanded' : ''}`}
                        >
                            <div className="recording-main" onClick={() => setExpandedId(expandedId === rec.id ? null : rec.id)}>
                                {/* 顶部行：文件信息 + 操作按钮 */}
                                <div className="recording-header">
                                    <div className="recording-info">
                                        <span className="recording-name">{rec.source_filename || rec.filename}</span>
                                        <span className="recording-meta">
                                            {formatDuration(rec.duration)} · {formatDate(rec.created_at)}
                                        </span>
                                    </div>
                                    <div className="recording-actions">
                                        <button
                                            className="btn-play"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                togglePlay(rec.id);
                                            }}
                                        >
                                            ▶ 播放
                                        </button>
                                        <button
                                            className="btn-clone"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                openCloneModal(rec);
                                            }}
                                        >
                                            克隆音色
                                        </button>
                                        <button
                                            className="btn-delete"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                deleteRecording(rec.id);
                                            }}
                                        >
                                            删除
                                        </button>
                                    </div>
                                </div>

                                {/* 转写文本区域 */}
                                {editingId === rec.id ? (
                                    <div className="recording-transcript editing" onClick={e => e.stopPropagation()}>
                                        <span className="transcript-label">转写文本：</span>
                                        <textarea
                                            className="transcript-edit"
                                            value={editingText}
                                            onChange={e => setEditingText(e.target.value)}
                                            placeholder="输入转写文本..."
                                            rows={3}
                                            autoFocus
                                        />
                                        <div className="transcript-actions">
                                            <button className="btn-save" onClick={(e) => saveTranscript(rec.id, e)}>
                                                保存
                                            </button>
                                            <button className="btn-cancel-edit" onClick={cancelEditing}>
                                                取消
                                            </button>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="recording-transcript" onClick={e => e.stopPropagation()}>
                                        <div className="transcript-header">
                                            <span className="transcript-label">转写文本：</span>
                                            <button className="btn-edit" onClick={(e) => startEditing(rec, e)}>
                                                编辑
                                            </button>
                                        </div>
                                        <span className="transcript-text">
                                            {rec.prompt_text || <em className="no-transcript">暂无转写文本，点击编辑添加</em>}
                                        </span>
                                    </div>
                                )}
                                <audio
                                    ref={el => audioRefs.current[rec.id] = el}
                                    src={`/audio/recordings/${rec.filename}`}
                                />
                            </div>

                            {/* 展开的克隆音频列表 */}
                            {expandedId === rec.id && rec.cloned_audios && rec.cloned_audios.length > 0 && (
                                <div className="cloned-list">
                                    <h4>克隆生成的音频</h4>
                                    {rec.cloned_audios.map(cloned => (
                                        <div key={cloned.id} className="cloned-item">
                                            <div className="cloned-info">
                                                <span className="cloned-text">"{cloned.text}"</span>
                                                <span className="cloned-date">{formatDate(cloned.created_at)}</span>
                                            </div>
                                            <button
                                                className="btn-play-small"
                                                onClick={() => {
                                                    const audio = new Audio(`/audio/tts/${cloned.filename}`);
                                                    audio.play();
                                                }}
                                            >
                                                ▶ 播放
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* 克隆模态框 */}
            {cloneModal && (
                <div className="modal-overlay" onClick={() => !cloneProgress && setCloneModal(null)}>
                    <div className="modal-content" onClick={e => e.stopPropagation()}>
                        <h3>语音克隆</h3>

                        <div className="form-group">
                            <label>录音中说的话（用于音色提取）:</label>
                            <textarea
                                value={cloneModal.promptText}
                                onChange={e => setCloneModal({ ...cloneModal, promptText: e.target.value })}
                                placeholder="请输入你在录音中说的话..."
                                rows={3}
                                disabled={!!cloneProgress}
                            />
                        </div>

                        <div className="form-group">
                            <label>要合成的文本:</label>
                            <textarea
                                value={cloneModal.synText}
                                onChange={e => setCloneModal({ ...cloneModal, synText: e.target.value })}
                                placeholder="请输入要用克隆的声音说的话..."
                                rows={3}
                                disabled={!!cloneProgress}
                            />
                        </div>

                        {cloneProgress && (
                            <div className="progress-section">
                                <div className="progress-bar">
                                    <div
                                        className="progress-fill"
                                        style={{ width: `${cloneProgress.progress}%` }}
                                    />
                                </div>
                                <div className="progress-text">
                                    {cloneProgress.message} ({cloneProgress.progress}%)
                                </div>
                                {cloneProgress.status === 'completed' && cloneProgress.outputUrl && (
                                    <div className="success-message">
                                        <button
                                            className="btn-play-result"
                                            onClick={() => {
                                                const audio = new Audio(`${cloneProgress.outputUrl}`);
                                                audio.play();
                                            }}
                                        >
                                            ▶ 试听结果
                                        </button>
                                    </div>
                                )}
                            </div>
                        )}

                        <div className="modal-actions">
                            {!cloneProgress && (
                                <>
                                    <button className="btn-cancel" onClick={() => setCloneModal(null)}>
                                        取消
                                    </button>
                                    <button className="btn-start" onClick={startClone}>
                                        开始克隆
                                    </button>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default RecordingList;
