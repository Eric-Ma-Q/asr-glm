
import { useRef, useEffect } from 'react';

const MAX_CANVAS_PIXELS = 1280 * 720;

function createGlowSprite(hue) {
    const sprite = document.createElement('canvas');
    const radius = 24;
    sprite.width = sprite.height = radius * 2;

    const ctx = sprite.getContext('2d');
    const glow = ctx.createRadialGradient(radius, radius, 0, radius, radius, radius);
    glow.addColorStop(0, `hsl(${hue}, 90%, 70%)`);
    glow.addColorStop(0.15, `hsla(${hue}, 90%, 60%, 0.85)`);
    glow.addColorStop(0.45, `hsla(${hue}, 90%, 60%, 0.18)`);
    glow.addColorStop(1, `hsla(${hue}, 90%, 60%, 0)`);
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, sprite.width, sprite.height);
    return sprite;
}

const AudioVisualizer = ({ analyser, isRecording }) => {
    const canvasRef = useRef(null);

    useEffect(() => {
        if (!canvasRef.current) return;
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d', { alpha: false });
        if (!ctx) return;
        let animationId;
        let width;
        let height;

        const resize = () => {
            const parent = canvas.parentElement;
            width = Math.max(1, parent.clientWidth);
            height = Math.max(1, parent.clientHeight);
            // Bound the raster cost of the full-screen background on high-DPI displays.
            const scale = Math.min(window.devicePixelRatio || 1, Math.sqrt(MAX_CANVAS_PIXELS / (width * height)));
            canvas.width = Math.max(1, Math.round(width * scale));
            canvas.height = Math.max(1, Math.round(height * scale));
            ctx.setTransform(canvas.width / width, 0, 0, canvas.height / height, 0, 0);
            ctx.fillStyle = '#050510';
            ctx.fillRect(0, 0, width, height);
        };
        window.addEventListener('resize', resize);
        resize();

        const sprites = [200, 213, 226, 239].map(createGlowSprite);
        const particles = Array.from({ length: 180 }, () => ({
            x: Math.random() * width,
            y: Math.random() * height,
            vx: (Math.random() - 0.5) * 0.8,
            vy: (Math.random() - 0.5) * 0.8,
            size: Math.random() * 1.5 + 0.5,
            baseAlpha: Math.random() * 0.5 + 0.2,
            sprite: sprites[Math.floor(Math.random() * sprites.length)],
        }));

        const dataArray = new Uint8Array(analyser && isRecording ? analyser.frequencyBinCount : 0);

        const draw = () => {
            // Clear with longer trail effect for smoothness
            ctx.fillStyle = 'rgba(5, 5, 16, 0.15)';
            ctx.fillRect(0, 0, width, height);

            if (dataArray.length > 0) {
                analyser.getByteFrequencyData(dataArray);
            }

            // Global composite operation for glow effect
            ctx.globalCompositeOperation = 'lighter';

            // Update and draw particles
            particles.forEach((p) => {
                // Audio reactivity
                // Map x position to frequency index
                const freqIndex = Math.floor((p.x / width) * dataArray.length);
                const audioValue = dataArray[freqIndex] || 0;

                // Gentler reaction
                const scale = 1 + (audioValue / 255) * 2.5;
                const speedBoost = 1 + (audioValue / 255) * 2;

                p.x += p.vx * speedBoost;
                p.y += p.vy * speedBoost;

                // Wrap around instead of bounce for flow feel
                if (p.x < 0) p.x = width;
                if (p.x > width) p.x = 0;
                if (p.y < 0) p.y = height;
                if (p.y > height) p.y = 0;

                const radius = (p.size + 8) * scale;
                ctx.globalAlpha = p.baseAlpha;
                ctx.drawImage(p.sprite, p.x - radius, p.y - radius, radius * 2, radius * 2);
            });

            ctx.globalAlpha = 1;
            ctx.globalCompositeOperation = 'source-over'; // Reset

            // Waveform Line - More subtle
            if (isRecording && dataArray.length > 0) {
                ctx.beginPath();
                ctx.strokeStyle = 'rgba(0, 230, 255, 0.4)'; // Lower opacity
                ctx.lineWidth = 1.5;

                const sliceWidth = width / dataArray.length;
                let x = 0;

                // Move to first point
                ctx.moveTo(0, height / 2);

                for (let i = 0; i < dataArray.length; i++) {
                    const v = dataArray[i] / 128.0; // 0..2
                    const y = (height / 2) + (v - 1) * (height / 6); // Reduced amplitude

                    // Quadratic curve for smoothness
                    if (i === 0) {
                        ctx.moveTo(x, y);
                    } else {
                        const prevX = x - sliceWidth;
                        const prevY = (height / 2) + (dataArray[i - 1] / 128.0 - 1) * (height / 6);
                        const cpX = (prevX + x) / 2;
                        ctx.quadraticCurveTo(cpX, prevY, x, y);
                    }
                    x += sliceWidth;
                }
                ctx.stroke();
            }

            animationId = requestAnimationFrame(draw);
        };

        draw();

        return () => {
            window.removeEventListener('resize', resize);
            cancelAnimationFrame(animationId);
        };
    }, [analyser, isRecording]);

    return <canvas ref={canvasRef} className="visualizer-canvas" />;
};

export default AudioVisualizer;
