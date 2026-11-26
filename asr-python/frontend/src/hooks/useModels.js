import { useEffect, useState } from 'react';

export function useModels() {
  const [models, setModels] = useState({});
  const [serviceStatus, setServiceStatus] = useState('checking');
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    let timer;

    async function poll() {
      try {
        const response = await fetch('/api/models', { signal: controller.signal });
        if (!response.ok) throw new Error();
        setModels(await response.json());
        setServiceStatus('online');
      } catch {
        if (!controller.signal.aborted) setServiceStatus('offline');
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(poll, 1200);
      }
    }

    poll();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, []);

  async function prepare(name) {
    setError('');
    try {
      const response = await fetch(`/api/models/${name}/prepare`, { method: 'POST' });
      if (!response.ok) throw new Error();
      const model = await response.json();
      setModels(current => ({ ...current, [name]: model }));
    } catch {
      setError('启动模型任务失败，请重试。');
    }
  }

  return { models, serviceStatus, error, prepare };
}
