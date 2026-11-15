/**
 * LOKI — Apple-Inspired Ambient Aura Engine
 * Smooth, ethereal ambient lighting inspired by Apple Intelligence & macOS dynamic wallpapers.
 * Dept of AIML, Zeal Polytechnic Pune
 */

(function () {
  'use strict';

  let canvas = null;
  let ctx = null;
  let width = 0;
  let height = 0;
  let animId = null;
  let mouseX = 0;
  let mouseY = 0;
  let targetMouseX = 0;
  let targetMouseY = 0;

  function resize() {
    if (!canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx = canvas.getContext('2d');
    if (ctx) ctx.scale(dpr, dpr);
  }

  // Apple-style soft ambient orbs (deep emerald, subtle teal, dark forest)
  const orbs = [
    {
      xRatio: 0.5,
      yRatio: 0.25,
      radiusRatio: 0.45,
      color: 'rgba(48, 209, 88, 0.12)', // Apple system green
      speedX: 0.0003,
      speedY: 0.0002,
      phase: 0,
      wobble: 60,
    },
    {
      xRatio: 0.2,
      yRatio: 0.45,
      radiusRatio: 0.35,
      color: 'rgba(10, 132, 255, 0.08)', // Apple system blue
      speedX: 0.00025,
      speedY: 0.00035,
      phase: 2.1,
      wobble: 80,
    },
    {
      xRatio: 0.8,
      yRatio: 0.5,
      radiusRatio: 0.4,
      color: 'rgba(48, 209, 88, 0.09)',
      speedX: 0.0002,
      speedY: 0.00025,
      phase: 4.2,
      wobble: 70,
    },
    {
      xRatio: 0.5,
      yRatio: 0.75,
      radiusRatio: 0.5,
      color: 'rgba(5, 70, 35, 0.12)',
      speedX: 0.00018,
      speedY: 0.00022,
      phase: 1.5,
      wobble: 90,
    },
  ];

  function render(timestamp) {
    targetMouseX += (mouseX - targetMouseX) * 0.03;
    targetMouseY += (mouseY - targetMouseY) * 0.03;

    if (ctx && width > 0 && height > 0) {
      ctx.clearRect(0, 0, width, height);

      // Deep Apple OLED black base
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, width, height);

      const mouseOffsetX = (targetMouseX - width / 2) * 0.05;
      const mouseOffsetY = (targetMouseY - height / 2) * 0.05;

      for (let i = 0; i < orbs.length; i++) {
        const orb = orbs[i];
        const t = timestamp;
        const ox = width * orb.xRatio + Math.sin(t * orb.speedX + orb.phase) * orb.wobble + mouseOffsetX * (i + 1) * 0.3;
        const oy = height * orb.yRatio + Math.cos(t * orb.speedY + orb.phase) * orb.wobble + mouseOffsetY * (i + 1) * 0.3;
        const r = Math.max(width, height) * orb.radiusRatio;

        const grad = ctx.createRadialGradient(ox, oy, 0, ox, oy, r);
        grad.addColorStop(0, orb.color);
        grad.addColorStop(0.5, orb.color.replace(/[\d\.]+\)$/, '0.04)'));
        grad.addColorStop(1, 'transparent');

        ctx.save();
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(ox, oy, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    }

    animId = requestAnimationFrame(render);
  }

  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', function (e) {
    mouseX = e.clientX;
    mouseY = e.clientY;
  });

  function init() {
    canvas = document.getElementById('loki-ribbon-canvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.id = 'loki-ribbon-canvas';
      const container = document.querySelector('.loki-bg-container') || document.body;
      container.insertBefore(canvas, container.firstChild);
    }
    Object.assign(canvas.style, {
      position: 'fixed',
      top: '0',
      left: '0',
      width: '100%',
      height: '100%',
      pointerEvents: 'none',
      zIndex: '0',
    });
    resize();
    if (!animId) animId = requestAnimationFrame(render);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
