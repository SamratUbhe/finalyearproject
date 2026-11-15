/**
 * LOKI TVA Opener Animation (Silent Instant Engine)
 * 
 * Faithfully adapted from AI Studio reference:
 * - HTML5 Canvas 1920x1080 resolution
 * - Instant startup with pre-cached image memory (zero initial delay)
 * - Cathode phosphor beam (0 - 60ms instant flash)
 * - TV glitch with split B&W vs color cycling & phosphor chromatic drift (60 - 1960ms)
 * - Lock-in with frosted glass backplate & top bevel reflection (1960 - 3400ms)
 * - Seamless fade-out into live dashboard
 * - Completely silent (sound removed)
 * - Clean presentation (no skip button)
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.LokiOpener = factory();
  }
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  // Pre-instantiate images in memory immediately upon script load to eliminate network wait
  const preloadedPrimary = new Image();
  preloadedPrimary.src = '/assets/aistudio/IMG_20261107_230930_1a6db8c8.png';

  const preloadedFallback = new Image();
  preloadedFallback.src = '/static/assets/loki-logo.png';

  class LokiOpenerManager {
    constructor() {
      this.overlay = null;
      this.canvas = null;
      this.animFrameId = null;
      this.startTime = null;
      this.img = null;
      this.isFadingOut = false;
      this.durationMs = 3400;
      this.onCompleteCallback = null;
      this.handleKeyDown = null;
      this.handleClick = null;
    }

    init() {
      // No audio initialization needed (silent mode)
    }

    play(options = {}) {
      const {
        onComplete = null,
        imageSrc = '/assets/aistudio/IMG_20261107_230930_1a6db8c8.png',
        fallbackSrc = '/static/assets/loki-logo.png',
        durationMs = 3400,
      } = options;

      this.durationMs = durationMs;
      this.onCompleteCallback = onComplete;
      this.isFadingOut = false;
      this.startTime = null;

      // Clean up any existing overlay
      this.destroy();

      // Create full-screen fixed overlay
      this.overlay = document.createElement('div');
      this.overlay.id = 'loki-opener-overlay';
      Object.assign(this.overlay.style, {
        position: 'fixed',
        inset: '0',
        zIndex: '99999',
        backgroundColor: '#000000',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        opacity: '1',
        transition: 'opacity 500ms ease-in-out',
        pointerEvents: 'auto',
        cursor: 'default',
      });

      // Create high-res 1920x1080 canvas
      this.canvas = document.createElement('canvas');
      this.canvas.width = 1920;
      this.canvas.height = 1080;
      Object.assign(this.canvas.style, {
        width: '100%',
        height: '100%',
        objectFit: 'contain',
        backgroundColor: '#000000',
      });
      this.overlay.appendChild(this.canvas);

      // Subtle dismiss on click or keyboard (no visible button)
      this.handleClick = () => {
        this.dismiss();
      };
      this.overlay.addEventListener('click', this.handleClick);

      this.handleKeyDown = (e) => {
        if (e.key === 'Escape' || e.key === ' ') {
          this.dismiss();
        }
      };
      window.addEventListener('keydown', this.handleKeyDown);

      // Attach overlay immediately to DOM
      const parent = document.body || document.documentElement;
      parent.appendChild(this.overlay);

      // Select image immediately from preloaded cache
      if (preloadedPrimary.complete && preloadedPrimary.naturalWidth > 0) {
        this.img = preloadedPrimary;
      } else if (preloadedFallback.complete && preloadedFallback.naturalWidth > 0) {
        this.img = preloadedFallback;
      } else {
        this.img = preloadedPrimary;
        preloadedPrimary.onload = () => {
          this.img = preloadedPrimary;
        };
        preloadedPrimary.onerror = () => {
          this.img = preloadedFallback;
        };
      }

      // Start rendering IMMEDIATELY without waiting (zero 0.5s delay)
      this.startLoop();
    }

    startLoop() {
      const render = (time) => {
        if (!this.startTime) this.startTime = time;
        const elapsed = time - this.startTime;

        const canvas = this.canvas;
        const img = this.img;

        if (canvas) {
          const ctx = canvas.getContext('2d');
          if (ctx) {
            const width = canvas.width;
            const height = canvas.height;

            // Pure black CRT background
            ctx.fillStyle = '#000000';
            ctx.fillRect(0, 0, width, height);

            const hasImage = img && img.complete && img.naturalWidth > 0;
            const imgAspect = hasImage ? (img.naturalWidth / img.naturalHeight) : (16 / 9);
            const targetWidth = Math.min(width * 0.72, 1100);
            const targetHeight = targetWidth / imgAspect;
            const targetX = (width - targetWidth) / 2;
            const targetY = (height - targetHeight) / 2;

            if (elapsed < 60) {
              // Instant TV turn-on beam (0 - 60ms instant cathode flash)
              const beamProgress = Math.min(1, elapsed / 60);
              const beamHeight = Math.max(6, height * Math.pow(beamProgress, 2));
              ctx.fillStyle = 'rgba(255, 255, 255, 0.96)';
              ctx.fillRect(0, (height - beamHeight) / 2, width, beamHeight);
            } else if (elapsed < 1960) {
              // Television glitch with split Black & White vs Color (60ms - 1960ms)
              const glitchTime = elapsed - 60;
              const hJitter = Math.sin(glitchTime * 0.07) > 0.5 ? (Math.random() - 0.5) * 10 : 0;
              const vJitter = Math.sin(glitchTime * 0.02) > 0.85 ? (Math.random() - 0.5) * 8 : 0;
              const tvRgbOffset = Math.sin(glitchTime * 0.04) * 4;
              const splitCycle = Math.floor(glitchTime / 320) % 5;

              ctx.save();
              ctx.translate(hJitter, vJitter);

              if (hasImage) {
                // Phosphor chromatic drift
                if (Math.abs(tvRgbOffset) > 1.5) {
                  ctx.save();
                  ctx.globalCompositeOperation = 'screen';
                  ctx.fillStyle = '#00ffff';
                  ctx.globalAlpha = 0.45;
                  ctx.drawImage(img, targetX - tvRgbOffset, targetY, targetWidth, targetHeight);
                  ctx.fillStyle = '#ff2222';
                  ctx.globalAlpha = 0.45;
                  ctx.drawImage(img, targetX + tvRgbOffset, targetY, targetWidth, targetHeight);
                  ctx.restore();
                }

                // Draw split B&W / Color regions
                if (splitCycle === 0) {
                  // Top half B&W, Bottom half Color
                  ctx.save();
                  ctx.beginPath();
                  ctx.rect(targetX - 20, targetY - 20, targetWidth + 40, targetHeight / 2 + 20);
                  ctx.clip();
                  ctx.filter = 'grayscale(100%) contrast(1.25)';
                  ctx.drawImage(img, targetX, targetY, targetWidth, targetHeight);
                  ctx.restore();

                  ctx.save();
                  ctx.beginPath();
                  ctx.rect(targetX - 20, targetY + targetHeight / 2, targetWidth + 40, targetHeight / 2 + 20);
                  ctx.clip();
                  ctx.drawImage(img, targetX, targetY, targetWidth, targetHeight);
                  ctx.restore();
                } else if (splitCycle === 1) {
                  // Top half Color, Bottom half B&W
                  ctx.save();
                  ctx.beginPath();
                  ctx.rect(targetX - 20, targetY - 20, targetWidth + 40, targetHeight / 2 + 20);
                  ctx.clip();
                  ctx.drawImage(img, targetX, targetY, targetWidth, targetHeight);
                  ctx.restore();

                  ctx.save();
                  ctx.beginPath();
                  ctx.rect(targetX - 20, targetY + targetHeight / 2, targetWidth + 40, targetHeight / 2 + 20);
                  ctx.clip();
                  ctx.filter = 'grayscale(100%) contrast(1.25)';
                  ctx.drawImage(img, targetX, targetY, targetWidth, targetHeight);
                  ctx.restore();
                } else if (splitCycle === 2) {
                  // Left half B&W, Right half Color
                  ctx.save();
                  ctx.beginPath();
                  ctx.rect(targetX - 20, targetY - 20, targetWidth / 2 + 20, targetHeight + 40);
                  ctx.clip();
                  ctx.filter = 'grayscale(100%) contrast(1.25)';
                  ctx.drawImage(img, targetX, targetY, targetWidth, targetHeight);
                  ctx.restore();

                  ctx.save();
                  ctx.beginPath();
                  ctx.rect(targetX + targetWidth / 2, targetY - 20, targetWidth / 2 + 20, targetHeight + 40);
                  ctx.clip();
                  ctx.drawImage(img, targetX, targetY, targetWidth, targetHeight);
                  ctx.restore();
                } else {
                  // Left half Color, Right half B&W
                  ctx.save();
                  ctx.beginPath();
                  ctx.rect(targetX - 20, targetY - 20, targetWidth / 2 + 20, targetHeight + 40);
                  ctx.clip();
                  ctx.drawImage(img, targetX, targetY, targetWidth, targetHeight);
                  ctx.restore();

                  ctx.save();
                  ctx.beginPath();
                  ctx.rect(targetX + targetWidth / 2, targetY - 20, targetWidth / 2 + 20, targetHeight + 40);
                  ctx.clip();
                  ctx.filter = 'grayscale(100%) contrast(1.25)';
                  ctx.drawImage(img, targetX, targetY, targetWidth, targetHeight);
                  ctx.restore();
                }
              }

              ctx.restore();

              // CRT scanlines & static snow
              ctx.save();
              ctx.fillStyle = 'rgba(0, 0, 0, 0.26)';
              for (let y = 0; y < height; y += 3) {
                ctx.fillRect(0, y, width, 1.2);
              }

              ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
              for (let i = 0; i < 25; i++) {
                ctx.fillRect(Math.random() * width, Math.random() * height, Math.random() * 35 + 4, 1);
              }
              ctx.restore();
            } else {
              // Lock-in with refined Glassy Touch (1960ms - 3400ms)
              const lockTime = elapsed - 1960;
              const glassFade = Math.min(1, lockTime / 400);
              const gx = targetX - 35;
              const gy = targetY - 25;
              const gw = targetWidth + 70;
              const gh = targetHeight + 50;

              // Frosted glass backplate
              ctx.save();
              ctx.beginPath();
              if (typeof ctx.roundRect === 'function') {
                ctx.roundRect(gx, gy, gw, gh, 24);
              } else {
                ctx.rect(gx, gy, gw, gh);
              }
              ctx.fillStyle = `rgba(255, 255, 255, ${0.03 * glassFade})`;
              ctx.fill();
              ctx.shadowColor = `rgba(0, 0, 0, ${0.75 * glassFade})`;
              ctx.shadowBlur = 45;
              ctx.shadowOffsetY = 16;
              ctx.strokeStyle = `rgba(255, 255, 255, ${0.15 * glassFade})`;
              ctx.lineWidth = 1;
              ctx.stroke();
              ctx.restore();

              // Original high-res color image
              if (hasImage) {
                ctx.save();
                ctx.filter = 'none';
                ctx.drawImage(img, targetX, targetY, targetWidth, targetHeight);
                ctx.restore();
              }

              // Soft static top bevel glass reflection
              ctx.save();
              ctx.beginPath();
              if (typeof ctx.roundRect === 'function') {
                ctx.roundRect(gx, gy, gw, gh, 24);
              } else {
                ctx.rect(gx, gy, gw, gh);
              }
              ctx.clip();
              const topBevel = ctx.createLinearGradient(gx, gy, gx, gy + 32);
              topBevel.addColorStop(0, `rgba(255, 255, 255, ${0.13 * glassFade})`);
              topBevel.addColorStop(1, 'rgba(255, 255, 255, 0)');
              ctx.fillStyle = topBevel;
              ctx.fillRect(gx, gy, gw, 32);
              ctx.restore();
            }
          }
        }

        if (elapsed < this.durationMs) {
          this.animFrameId = requestAnimationFrame(render);
        } else {
          this.fadeOut(500);
        }
      };

      this.animFrameId = requestAnimationFrame(render);
    }

    dismiss() {
      this.fadeOut(250);
    }

    fadeOut(fadeDurationMs = 500) {
      if (this.isFadingOut) return;
      this.isFadingOut = true;

      if (this.overlay) {
        this.overlay.style.transition = `opacity ${fadeDurationMs}ms ease-in-out`;
        this.overlay.style.opacity = '0';
        this.overlay.style.pointerEvents = 'none';
      }

      setTimeout(() => {
        this.destroy();
        if (typeof this.onCompleteCallback === 'function') {
          this.onCompleteCallback();
          this.onCompleteCallback = null;
        }
      }, fadeDurationMs);
    }

    destroy() {
      if (this.animFrameId) {
        cancelAnimationFrame(this.animFrameId);
        this.animFrameId = null;
      }
      if (this.handleKeyDown) {
        window.removeEventListener('keydown', this.handleKeyDown);
        this.handleKeyDown = null;
      }
      if (this.handleClick && this.overlay) {
        this.overlay.removeEventListener('click', this.handleClick);
        this.handleClick = null;
      }
      if (this.overlay && this.overlay.parentNode) {
        this.overlay.parentNode.removeChild(this.overlay);
        this.overlay = null;
      }
      this.canvas = null;
    }
  }

  const manager = new LokiOpenerManager();
  return manager;
});
