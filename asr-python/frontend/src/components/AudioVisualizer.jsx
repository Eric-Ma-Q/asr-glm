import { useEffect, useRef } from 'react';

const MAX_CANVAS_PIXELS = 1280 * 720;
const WAVE_OPACITIES = [0.28, 0.62, 0.38, 0.18];
const TAU = Math.PI * 2;
const fraction = value => value - Math.floor(value);
const particles = Array.from({ length: 64 }, (_, index) => ({
    x: fraction(index * 0.618 + 0.13),
    lane: index % WAVE_OPACITIES.length,
    offset: (fraction(index * 0.414) - 0.5) * 48,
    speed: 0.003 + fraction(index * 0.73) * 0.004,
    phase: index * 2.4,
    size: index % 7 === 0 ? 7 : 4,
    warm: index % 3 === 0,
}));

function createGlowSprite(color) {
    const sprite = document.createElement('canvas');
    sprite.width = sprite.height = 32;
    const ctx = sprite.getContext('2d');
    const glow = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
    glow.addColorStop(0, 'rgba(255, 250, 237, 1)');
    glow.addColorStop(0.13, `rgba(${color}, 0.9)`);
    glow.addColorStop(0.32, `rgba(${color}, 0.25)`);
    glow.addColorStop(1, `rgba(${color}, 0)`);
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, 32, 32);
    return sprite;
}

function waveY(x, lane, height, time, level) {
    const amplitude = Math.min(height * 0.095, 78) * (1 + level * 0.6);
    const wave = Math.sin((x * 1.12 - 0.12) * TAU + Math.sin(time * 0.18) * 0.48);
    const spread = 5 + 12 * Math.sin(x * Math.PI);
    return height * 0.76 + wave * amplitude + (lane - 1.5) * spread;
}

const AudioVisualizer = ({ analyser, isRecording }) => {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext('2d');
        if (!ctx) return;

        const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
        const coolGlow = createGlowSprite('147, 181, 245');
        const warmGlow = createGlowSprite('246, 210, 151');
        const samples = analyser && isRecording ? new Uint8Array(analyser.fftSize) : null;
        let width;
        let height;
        let gradient;
        let animationId;
        let lastFrame = -Infinity;
        let level = 0;

        const draw = time => {
            ctx.clearRect(0, 0, width, height);
            ctx.strokeStyle = gradient;
            ctx.lineWidth = 1;

            for (const [lane, opacity] of WAVE_OPACITIES.entries()) {
                ctx.globalAlpha = opacity;
                ctx.beginPath();
                ctx.moveTo(0, waveY(0, lane, height, time, level));
                for (let step = 1; step <= 80; step++) {
                    const x = step / 80;
                    ctx.lineTo(x * width, waveY(x, lane, height, time, level));
                }
                ctx.stroke();
            }

            const count = Math.min(particles.length, Math.max(20, Math.round(width / 20)));
            for (let i = 0; i < count; i++) {
                const particle = particles[i];
                const x = fraction(particle.x + time * particle.speed);
                const y = waveY(x, particle.lane, height, time, level) + particle.offset;
                const shimmer = 0.7 + 0.17 * Math.sin(time * 0.6 + particle.phase);
                const radius = particle.size * (1 + level * 0.24);
                ctx.globalAlpha = Math.sin(x * Math.PI) * shimmer * (0.85 + level * 0.15);
                ctx.drawImage(particle.warm ? warmGlow : coolGlow, x * width - radius, y - radius, radius * 2, radius * 2);
            }
            ctx.globalAlpha = 1;
        };

        const animate = timestamp => {
            const elapsed = timestamp - lastFrame;
            if (elapsed >= 32) {
                if (samples) {
                    analyser.getByteTimeDomainData(samples);
                    let energy = 0;
                    for (const sample of samples) energy += ((sample - 128) / 128) ** 2;
                    const target = Math.min(1, Math.sqrt(energy / samples.length) * 4);
                    level += (target - level) * (1 - Math.exp(-elapsed / 180));
                }
                lastFrame = timestamp;
                draw(timestamp / 1000);
            }
            animationId = requestAnimationFrame(animate);
        };

        const resize = () => {
            width = Math.max(1, canvas.clientWidth);
            height = Math.max(1, canvas.clientHeight);
            // Keep the full-screen canvas within the raster budget on high-DPI displays.
            const scale = Math.min(window.devicePixelRatio || 1, Math.sqrt(MAX_CANVAS_PIXELS / (width * height)));
            canvas.width = Math.max(1, Math.round(width * scale));
            canvas.height = Math.max(1, Math.round(height * scale));
            ctx.setTransform(canvas.width / width, 0, 0, canvas.height / height, 0, 0);
            gradient = ctx.createLinearGradient(0, 0, width, 0);
            gradient.addColorStop(0, 'rgba(83, 124, 211, 0)');
            gradient.addColorStop(0.18, 'rgba(83, 124, 211, 0.65)');
            gradient.addColorStop(0.53, 'rgba(224, 193, 146, 0.78)');
            gradient.addColorStop(0.82, 'rgba(133, 161, 225, 0.6)');
            gradient.addColorStop(1, 'rgba(83, 124, 211, 0)');
            draw(motion.matches ? 0 : performance.now() / 1000);
        };

        const updateMotion = () => {
            cancelAnimationFrame(animationId);
            if (motion.matches) {
                level = 0;
                draw(0);
            } else {
                lastFrame = -Infinity;
                animationId = requestAnimationFrame(animate);
            }
        };

        const observer = new ResizeObserver(resize);
        observer.observe(canvas);
        motion.addEventListener('change', updateMotion);
        resize();
        updateMotion();

        return () => {
            observer.disconnect();
            motion.removeEventListener('change', updateMotion);
            cancelAnimationFrame(animationId);
        };
    }, [analyser, isRecording]);

    return <canvas ref={canvasRef} className="visualizer-canvas" aria-hidden="true" />;
};

export default AudioVisualizer;
