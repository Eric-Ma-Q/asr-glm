
import { useState, useRef, useEffect, useCallback } from 'react';

export function useAudioProcessor(wsUrl) {
    const [isRecording, setIsRecording] = useState(false);
    const [isFinalizing, setIsFinalizing] = useState(false);
    const [transcript, setTranscript] = useState("");
    const [isConnected, setIsConnected] = useState(false);
    const [analyser, setAnalyser] = useState(null);

    // Refs to keep track of instances
    const ws = useRef(null);
    const audioContext = useRef(null);
    const processor = useRef(null);
    const stream = useRef(null);
    const stopCapture = useCallback(() => {
        if (stream.current) {
            stream.current.getTracks().forEach(track => track.stop());
            stream.current = null;
        }
        if (processor.current) {
            processor.current.disconnect();
            processor.current = null;
        }
        if (audioContext.current) {
            audioContext.current.close();
            audioContext.current = null;
        }
        setAnalyser(null);
        setIsRecording(false);
    }, []);

    const stopRecording = useCallback(() => {
        if (ws.current?.readyState === WebSocket.OPEN) {
            setIsFinalizing(true);
            ws.current.send(JSON.stringify({ type: 'stop' }));
        }
        stopCapture();
    }, [stopCapture]);

    const startRecording = useCallback(async () => {
        const socket = ws.current;
        if (socket?.readyState !== WebSocket.OPEN || audioContext.current) return;

        try {
            const Audio = window.AudioContext || window.webkitAudioContext;
            let context;
            try {
                context = new Audio({ sampleRate: 16000 });
            } catch (error) {
                if (error.name !== 'NotSupportedError') throw error;
                context = new Audio();
            }
            audioContext.current = context;
            const microphone = await navigator.mediaDevices.getUserMedia({ audio: true });
            if (audioContext.current !== context || socket.readyState !== WebSocket.OPEN) {
                microphone.getTracks().forEach(track => track.stop());
                return;
            }
            stream.current = microphone;

            const meter = context.createAnalyser();
            meter.fftSize = 512;
            const source = context.createMediaStreamSource(microphone);
            const node = context.createScriptProcessor(4096, 1, 1);
            processor.current = node;
            node.onaudioprocess = (event) => {
                if (socket.readyState === WebSocket.OPEN) {
                    socket.send(event.inputBuffer.getChannelData(0).buffer);
                }
            };
            socket.send(JSON.stringify({ type: 'start', sample_rate: context.sampleRate }));
            source.connect(meter);
            meter.connect(node);
            node.connect(context.destination);

            setAnalyser(meter);
            setIsRecording(true);
        } catch (error) {
            stopCapture();
            console.error("Error starting recording:", error);
        }
    }, [stopCapture]);

    useEffect(() => {
        if (!wsUrl) return;
        let reconnect;
        let socket;
        function connect() {
            socket = new WebSocket(wsUrl);
            ws.current = socket;
            socket.onopen = () => setIsConnected(true);
            socket.onmessage = ({ data }) => {
                if (data === '{"type":"stopped"}') {
                    setIsFinalizing(false);
                } else {
                    setTranscript(previous => previous ? previous + " " + data : data);
                }
            };
            socket.onclose = () => {
                setIsConnected(false);
                setIsFinalizing(false);
                stopCapture();
                reconnect = window.setTimeout(connect, 2000);
            };
        }
        connect();
        return () => {
            window.clearTimeout(reconnect);
            socket.onopen = socket.onclose = socket.onmessage = null;
            stopCapture();
            socket.close();
            ws.current = null;
        };
    }, [wsUrl, stopCapture]);

    const clearTranscript = useCallback(() => {
        setTranscript("");
    }, []);

    return {
        isRecording,
        isFinalizing,
        isConnected,
        transcript,
        startRecording,
        stopRecording,
        clearTranscript,
        analyser
    };
}
