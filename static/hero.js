/* ============================================================================
   The signal field — the studio's signature.
   A live GPGPU N-body accretion disc (three.js "protoplanet" gpgpu example,
   ported): thousands of debris particles orbit a common centre, tug on each
   other by gravity, and aggregate into brighter bodies over time — a literal
   picture of scattered signal collapsing into something that breaks out.
   All the physics runs on the GPU (position + velocity textures, ping-ponged
   by GPUComputationRenderer), so the cloud is cheap to animate.

   Purely decorative and progressively enhanced: if three.js can't load
   (offline / blocked / no float-texture support), the CSS-gradient hero stands
   on its own. Honors reduced-motion, and idles when off-screen or backgrounded.
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

  const WIDTH = 48;                 // sim texture is WIDTH×WIDTH; one texel = one particle
  const PARTICLES = WIDTH * WIDTH;  // ~2.3k debris — the O(N²) gravity runs on the GPU

  // Simulation tuning (ported from the three.js protoplanet example).
  const effect = {
    gravityConstant: 100.0,
    density: 0.45,
    radius: 300,
    height: 8,
    exponent: 0.4,
    maxMass: 15.0,
    velocity: 70,
    velocityExponent: 0.2,
    randVelocity: 0.001,
  };

  // --- GPU compute shaders (GPUComputationRenderer injects `resolution`,
  //     `texturePosition` and `textureVelocity`) ------------------------------
  const computePosition = `
    #define delta ( 1.0 / 60.0 )
    void main() {
      vec2 uv = gl_FragCoord.xy / resolution.xy;
      vec4 tmpPos = texture2D( texturePosition, uv );
      vec3 pos = tmpPos.xyz;
      vec4 tmpVel = texture2D( textureVelocity, uv );
      vec3 vel = tmpVel.xyz;
      float mass = tmpVel.w;
      if ( mass == 0.0 ) { vel = vec3( 0.0 ); }
      pos += vel * delta;
      gl_FragColor = vec4( pos, 1.0 );
    }`;

  const computeVelocity = `
    #include <common>
    #define delta ( 1.0 / 60.0 )
    uniform float gravityConstant;
    uniform float density;
    const float width = resolution.x;
    const float height = resolution.y;
    float radiusFromMass( float mass ) {
      return pow( ( 3.0 / ( 4.0 * PI ) ) * mass / density, 1.0 / 3.0 );
    }
    void main() {
      vec2 uv = gl_FragCoord.xy / resolution.xy;
      float idParticle = uv.y * resolution.x + uv.x;
      vec4 tmpPos = texture2D( texturePosition, uv );
      vec3 pos = tmpPos.xyz;
      vec4 tmpVel = texture2D( textureVelocity, uv );
      vec3 vel = tmpVel.xyz;
      float mass = tmpVel.w;
      if ( mass > 0.0 ) {
        float radius = radiusFromMass( mass );
        vec3 acceleration = vec3( 0.0 );
        for ( float y = 0.0; y < height; y++ ) {
          for ( float x = 0.0; x < width; x++ ) {
            vec2 secondParticleCoords = vec2( x + 0.5, y + 0.5 ) / resolution.xy;
            vec3 pos2 = texture2D( texturePosition, secondParticleCoords ).xyz;
            vec4 velTemp2 = texture2D( textureVelocity, secondParticleCoords );
            vec3 vel2 = velTemp2.xyz;
            float mass2 = velTemp2.w;
            float idParticle2 = secondParticleCoords.y * resolution.x + secondParticleCoords.x;
            if ( idParticle == idParticle2 ) { continue; }
            if ( mass2 == 0.0 ) { continue; }
            vec3 dPos = pos2 - pos;
            float dist = length( dPos );
            float radius2 = radiusFromMass( mass2 );
            if ( dist == 0.0 ) { continue; }
            if ( dist < radius + radius2 ) {
              if ( idParticle < idParticle2 ) {
                vel = ( vel * mass + vel2 * mass2 ) / ( mass + mass2 );
                mass += mass2;
                radius = radiusFromMass( mass );
              } else {
                mass = 0.0; radius = 0.0; vel = vec3( 0.0 ); break;
              }
            }
            float distanceSq = dist * dist;
            float gravityField = gravityConstant * mass2 / distanceSq;
            gravityField = min( gravityField, 1000.0 );
            acceleration += gravityField * normalize( dPos );
          }
          if ( mass == 0.0 ) { break; }
        }
        vel += delta * acceleration;
      }
      gl_FragColor = vec4( vel, mass );
    }`;

  // --- particle draw shaders — recoloured to the Signal Desk palette:
  //     light debris glows indigo, aggregated bodies burn to cyan-white -------
  const particleVertex = `
    #include <common>
    uniform sampler2D texturePosition;
    uniform sampler2D textureVelocity;
    uniform float cameraConstant;
    uniform float density;
    uniform vec3 uColorLo;
    uniform vec3 uColorHi;
    varying vec4 vColor;
    float radiusFromMass( float mass ) {
      return pow( ( 3.0 / ( 4.0 * PI ) ) * mass / density, 1.0 / 3.0 );
    }
    void main() {
      vec4 posTemp = texture2D( texturePosition, uv );
      vec3 pos = posTemp.xyz;
      vec4 velTemp = texture2D( textureVelocity, uv );
      float mass = velTemp.w;
      float m = clamp( mass / 90.0, 0.0, 1.0 );
      vColor = vec4( mix( uColorLo, uColorHi, m ), mass );
      vec4 mvPosition = modelViewMatrix * vec4( pos, 1.0 );
      float radius = radiusFromMass( mass );
      if ( mass == 0.0 ) { gl_PointSize = 0.0; }
      else { gl_PointSize = max( radius * cameraConstant / ( - mvPosition.z ), 1.0 ); }
      gl_Position = projectionMatrix * mvPosition;
    }`;

  const particleFragment = `
    precision mediump float;
    varying vec4 vColor;
    void main() {
      if ( vColor.a == 0.0 ) discard;                 // massless → aggregated away
      float d = length( gl_PointCoord - vec2( 0.5 ) );
      if ( d > 0.5 ) discard;
      float glow = smoothstep( 0.5, 0.0, d );          // soft round falloff
      gl_FragColor = vec4( vColor.rgb, glow );
    }`;

  // --- load three + the GPGPU addon (via the page's importmap) --------------
  Promise.all([
    import("three"),
    import("three/addons/misc/GPUComputationRenderer.js"),
  ])
    .then(([THREE, mod]) => initField(THREE, mod.GPUComputationRenderer))
    .catch(() => { /* CDN unreachable — the gradient hero is the fallback */ });

  function initField(THREE, GPUComputationRenderer) {
    const host = canvas.parentElement;                 // .hero
    let W = host.clientWidth, H = host.clientHeight;
    if (!W || !H) return;

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    const PR = Math.min(window.devicePixelRatio || 1, 1.75);
    renderer.setPixelRatio(PR);
    renderer.setClearColor(0x05070b, 0);               // transparent → CSS hero shows through
    renderer.setSize(W, H, false);

    const camera = new THREE.PerspectiveCamera(62, W / H, 5, 15000);
    camera.position.set(0, 165, 430);
    camera.lookAt(0, 0, 0);

    const scene = new THREE.Scene();

    // The debris lives in a group we can slowly spin + shove off-centre so the
    // disc sits to the right, clear of the left-aligned hero copy.
    const disc = new THREE.Group();
    disc.position.set(70, -6, 0);
    disc.rotation.x = -0.32;
    scene.add(disc);

    function cameraConstant() {
      return H / (Math.tan(THREE.MathUtils.DEG2RAD * 0.5 * camera.fov) / camera.zoom);
    }

    // --- GPU compute setup ---------------------------------------------------
    const gpu = new GPUComputationRenderer(WIDTH, WIDTH, renderer);
    if (renderer.capabilities.isWebGL2 === false) gpu.setDataType(THREE.HalfFloatType);

    const dtPosition = gpu.createTexture();
    const dtVelocity = gpu.createTexture();
    fillTextures(dtPosition, dtVelocity);

    const velocityVar = gpu.addVariable("textureVelocity", computeVelocity, dtVelocity);
    const positionVar = gpu.addVariable("texturePosition", computePosition, dtPosition);
    gpu.setVariableDependencies(velocityVar, [positionVar, velocityVar]);
    gpu.setVariableDependencies(positionVar, [positionVar, velocityVar]);
    velocityVar.material.uniforms.gravityConstant = { value: effect.gravityConstant };
    velocityVar.material.uniforms.density = { value: effect.density };

    const gpuError = gpu.init();
    if (gpuError !== null) { console.warn("[hero] GPGPU unavailable:", gpuError); return; }

    // --- the drawable points -------------------------------------------------
    const positions = new Float32Array(PARTICLES * 3);
    const uvs = new Float32Array(PARTICLES * 2);
    let p = 0;
    for (let j = 0; j < WIDTH; j++) {
      for (let i = 0; i < WIDTH; i++) {
        uvs[p * 2] = i / (WIDTH - 1);
        uvs[p * 2 + 1] = j / (WIDTH - 1);
        p++;
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));

    const particleUniforms = {
      texturePosition: { value: null },
      textureVelocity: { value: null },
      cameraConstant: { value: cameraConstant() },
      density: { value: effect.density },
      uColorLo: { value: new THREE.Color(0x6e7bff) },  // indigo — scattered debris
      uColorHi: { value: new THREE.Color(0xeafffb) },  // cyan-white — bright aggregates
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: particleUniforms,
      vertexShader: particleVertex,
      fragmentShader: particleFragment,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const points = new THREE.Points(geo, mat);
    points.frustumCulled = false;
    disc.add(points);

    // --- pointer parallax (canvas ignores pointer events; listen on window) --
    const targetP = { x: 0, y: 0 }, camP = { x: 0, y: 0 };
    if (!prefersReduced) {
      window.addEventListener("pointermove", (e) => {
        const rect = host.getBoundingClientRect();
        targetP.x = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
        targetP.y = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
      }, { passive: true });
    }

    function resize() {
      W = host.clientWidth; H = host.clientHeight;
      if (!W || !H) return;
      renderer.setSize(W, H, false);
      camera.aspect = W / H;
      camera.updateProjectionMatrix();
      particleUniforms.cameraConstant.value = cameraConstant();
    }
    if (window.ResizeObserver) new ResizeObserver(resize).observe(host);
    else window.addEventListener("resize", resize);

    // --- idle when off-screen or backgrounded --------------------------------
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

    function render() {
      gpu.compute();
      particleUniforms.texturePosition.value = gpu.getCurrentRenderTarget(positionVar).texture;
      particleUniforms.textureVelocity.value = gpu.getCurrentRenderTarget(velocityVar).texture;
      camP.x += (targetP.x - camP.x) * 0.04;
      camP.y += (targetP.y - camP.y) * 0.04;
      camera.position.x = camP.x * 26;
      camera.position.y = 165 - camP.y * 22;
      camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
    }
    function frame() {
      raf = requestAnimationFrame(frame);
      disc.rotation.y += 0.0016;                       // slow accretion-disc spin
      render();
    }
    function start() { if (!raf && !prefersReduced) raf = requestAnimationFrame(frame); }
    function stop() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }

    // First paint, then fade the canvas in (timer, not rAF, so it fires even if
    // the tab loaded backgrounded).
    resize();
    render();
    setTimeout(() => canvas.classList.add("ready"), 30);

    if (prefersReduced) return;   // one static, lit frame — no loop
    start();
  }

  function fillTextures(texturePosition, textureVelocity) {
    const posArray = texturePosition.image.data;
    const velArray = textureVelocity.image.data;
    const radius = effect.radius, height = effect.height, exponent = effect.exponent;
    const maxMass = (effect.maxMass * 1024) / PARTICLES;
    const maxVel = effect.velocity, velExponent = effect.velocityExponent, randVel = effect.randVelocity;

    for (let k = 0, kl = posArray.length; k < kl; k += 4) {
      let x, z, rr;
      do { x = Math.random() * 2 - 1; z = Math.random() * 2 - 1; rr = x * x + z * z; } while (rr > 1);
      rr = Math.sqrt(rr);
      const rExp = radius * Math.pow(rr, exponent);
      const vel = maxVel * Math.pow(rr, velExponent);
      const vx = vel * z + (Math.random() * 2 - 1) * randVel;
      const vy = (Math.random() * 2 - 1) * randVel * 0.05;
      const vz = -vel * x + (Math.random() * 2 - 1) * randVel;
      x *= rExp; z *= rExp;
      const y = (Math.random() * 2 - 1) * height;
      const mass = Math.random() * maxMass + 1;
      posArray[k] = x; posArray[k + 1] = y; posArray[k + 2] = z; posArray[k + 3] = 1;
      velArray[k] = vx; velArray[k + 1] = vy; velArray[k + 2] = vz; velArray[k + 3] = mass;
    }
  }
})();
