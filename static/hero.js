/* ============================================================================
   The signal field — the studio's signature.
   A live 3D wave of light standing in for view-velocity: the metric the whole
   app is built around. Crests glow bright cyan-white — "signals breaking out" —
   while troughs recede into indigo, and a detection sweep periodically scans
   the field. Purely decorative and progressively enhanced: if three.js can't
   load (offline / blocked), the CSS-gradient hero stands on its own. Honors
   reduced-motion, and idles when off-screen or backgrounded.
   ========================================================================== */
(() => {
  "use strict";

  const prefersReduced =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --- hero CTAs drive the existing rail nav (keeps app.js untouched) -------
  function wireNav() {
    document.querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const stage = document.querySelector(`.stage[data-stage="${btn.dataset.goto}"]`);
        if (stage) stage.click();               // app.js owns the click handler
        const rail = document.getElementById("rail");
        if (rail) rail.scrollIntoView({ behavior: prefersReduced ? "auto" : "smooth", block: "start" });
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wireNav);
  else wireNav();

  // --- the 3D field (progressive enhancement) -------------------------------
  const canvas = document.getElementById("signal-field");
  if (!canvas) return;

  const THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";

  const COLS = 190, ROWS = 82;          // ~15.6k points — the wave runs on the GPU, so this is cheap
  const SPAN_X = 72, SPAN_Z = 50;       // world-space footprint of the field
  const BG = 0x090b10;

  import(THREE_URL)
    .then((THREE) => initField(THREE))
    .catch(() => { /* CDN unreachable — the gradient hero is the fallback */ });

  // The travelling wave — shared shader source so JS + GLSL stay in lockstep.
  const WAVE_GLSL = `
    float wave(float x, float z, float t){
      return sin(x*0.16 + t*0.9)*1.15
           + cos(z*0.22 - t*0.7)*0.95
           + sin((x+z)*0.13 + t*1.15)*0.6
           + sin(x*0.31 - z*0.12 + t*1.5)*0.35;
    }`;

  const VERT = `
    uniform float uTime, uSize, uPixelRatio, uSweep;
    varying float vGlow, vSweep, vFade;
    ${WAVE_GLSL}
    void main(){
      vec3 p = position;
      float h = wave(p.x, p.z, uTime);
      p.y = h;
      float hn = clamp((h + 2.7) / 5.4, 0.0, 1.0);   // normalized crest height 0..1
      vGlow = hn;
      vSweep = smoothstep(4.0, 0.0, abs(p.z - uSweep)); // proximity to the scan line
      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      gl_Position = projectionMatrix * mv;
      vFade = smoothstep(52.0, 14.0, -mv.z);            // distance fade → melts into bg
      float size = uSize * (0.5 + hn*1.35 + vSweep*0.9);
      gl_PointSize = size * uPixelRatio * (240.0 / -mv.z);
    }`;

  const FRAG = `
    precision mediump float;
    uniform vec3 uLow, uHigh, uPeak;
    varying float vGlow, vSweep, vFade;
    void main(){
      vec2 uv = gl_PointCoord - 0.5;
      float d = length(uv);
      if (d > 0.5) discard;
      float disc = smoothstep(0.5, 0.0, d);
      vec3 col = mix(uLow, uHigh, smoothstep(0.12, 0.82, vGlow));
      col = mix(col, uPeak, smoothstep(0.66, 1.0, vGlow) * 0.85);
      col += uPeak * vSweep * 0.6;
      float a = disc * vFade * (0.30 + vGlow*0.7 + vSweep*0.45);
      gl_FragColor = vec4(col, a);
    }`;

  function initField(THREE) {
    const host = canvas.parentElement;    // .hero
    let W = host.clientWidth, H = host.clientHeight;

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    const PR = Math.min(window.devicePixelRatio || 1, 1.75);
    renderer.setPixelRatio(PR);
    renderer.setClearColor(BG, 0);        // transparent → CSS gradient shows through
    renderer.setSize(W, H, false);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(56, W / H, 0.1, 200);
    camera.position.set(0, 9, 22);
    camera.lookAt(0, -1.2, -8);

    // Flat grid of points on the XZ plane; the shader lifts y into the wave.
    const count = COLS * ROWS;
    const positions = new Float32Array(count * 3);
    let i = 0;
    for (let r = 0; r < ROWS; r++) {
      for (let col = 0; col < COLS; col++) {
        positions[i * 3]     = (col / (COLS - 1) - 0.5) * SPAN_X;
        positions[i * 3 + 1] = 0;
        positions[i * 3 + 2] = (r / (ROWS - 1) - 0.5) * SPAN_Z;
        i++;
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));

    const uniforms = {
      uTime: { value: 0 },
      uSize: { value: 8.5 },
      uPixelRatio: { value: PR },
      uSweep: { value: -999 },
      uLow:  { value: new THREE.Color(0x2b2f7a) },   // dim indigo — troughs recede
      uHigh: { value: new THREE.Color(0x3fe0da) },   // signal cyan — mid crests
      uPeak: { value: new THREE.Color(0xdafff9) },   // near-white — breaking-out peaks
    };
    const mat = new THREE.ShaderMaterial({
      uniforms, vertexShader: VERT, fragmentShader: FRAG,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });

    const field = new THREE.Points(geo, mat);
    field.rotation.x = -0.05;
    scene.add(field);

    // Subtle pointer parallax (canvas ignores pointer events; listen on window).
    const target = { x: 0, y: 0 }, cam = { x: 0, y: 0 };
    if (!prefersReduced) {
      window.addEventListener("pointermove", (e) => {
        const rect = host.getBoundingClientRect();
        target.x = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
        target.y = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
      }, { passive: true });
    }

    function resize() {
      W = host.clientWidth; H = host.clientHeight;
      if (!W || !H) return;
      renderer.setSize(W, H, false);
      camera.aspect = W / H;
      camera.updateProjectionMatrix();
    }
    if (window.ResizeObserver) new ResizeObserver(resize).observe(host);
    else window.addEventListener("resize", resize);

    // Idle when the hero is off-screen or the tab is hidden.
    let onScreen = true, raf = 0;
    if (window.IntersectionObserver) {
      new IntersectionObserver((entries) => {
        onScreen = entries[0].isIntersecting;
        if (onScreen) start(); else stop();
      }, { threshold: 0.01 }).observe(host);
    }
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stop(); else if (onScreen) start();
    });

    // Detection sweep: a bright band scans across z, then rests in darkness.
    const SWEEP_PERIOD = 7.5, SWEEP_TRAVEL = SPAN_Z + 26;
    function sweepAt(t) {
      const phase = (t % SWEEP_PERIOD) / SWEEP_PERIOD;
      return -SPAN_Z / 2 - 13 + phase * SWEEP_TRAVEL;   // starts/ends off-field → gap between sweeps
    }

    let t = prefersReduced ? 2.4 : 0, last = 0;
    function render() {
      uniforms.uTime.value = t;
      uniforms.uSweep.value = prefersReduced ? -999 : sweepAt(t);
      cam.x += (target.x - cam.x) * 0.04;
      cam.y += (target.y - cam.y) * 0.04;
      camera.position.x = cam.x * 2.6;
      camera.position.y = 9 - cam.y * 1.3;
      field.rotation.z = cam.x * 0.02;
      camera.lookAt(0, -1.2, -8);
      renderer.render(scene, camera);
    }
    function frame(now) {
      raf = requestAnimationFrame(frame);
      const dt = last ? Math.min((now - last) / 1000, 0.05) : 0.016;
      last = now;
      t += dt;
      render();
    }
    function start() { if (!raf) { last = 0; raf = requestAnimationFrame(frame); } }
    function stop() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }

    // First paint, then fade the canvas in. Use a timer (not rAF) for the
    // reveal so it fires even if the tab loads backgrounded (rAF is paused then).
    resize();
    render();
    setTimeout(() => canvas.classList.add("ready"), 30);

    if (prefersReduced) return;   // one static, lit frame — no loop
    start();
  }
})();
