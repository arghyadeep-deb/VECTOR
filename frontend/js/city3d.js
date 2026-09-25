/* ============================================================================
   VECTOR · city3d.js  —  3D district city widget (Three.js, no React)
   Registers widget 'city3d'. Opens via:
     VECTOR.openWidget('city3d')
     terminal: open city3d
     voice: "show city" / "city view"
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  const D = global.VECTOR_DATA;
  if (!V) return;

  // ── wait for widgets.js to expose its open event ──────────────────────────
  // widgets.js listens to V.on('widget:open') and calls F[id](opts).
  // We inject into that by registering a factory on the F object — but F is
  // private. Instead we intercept the 'widget:open' event and build the DOM
  // ourselves before widgets.js can complain "no widget city3d".
  // We cancel propagation by pre-empting: register BEFORE widgets.js with
  // a global handler that builds and inserts the widget ourselves.

  const DISTRICTS = [
    'governance','security','coding','time_calendar','communications',
    'memory_curator','research','intelligence','skills','languages',
    'interview_prep','learning','finance','health','reflection',
    'startups','investment','content','agency','karpathy_lab',
    'projects','relationships','privacy','pattern_detective','news_trends',
    'calls','ops','data_analytics','personal_growth','documentation',
    'qa','chief_of_staff','marketing',
  ];

  // Preset grid positions for 33 districts (6×6 grid, offset for variety)
  const GRID = DISTRICTS.map((_, i) => {
    const col = i % 6, row = Math.floor(i / 6);
    return [(col - 2.5) * 3.2, 0, (row - 2.5) * 3.2];
  });

  // HP → colour
  function hpColor(hp) {
    if (hp >= 800) return 0x00cfff;  // cyan   ELITE
    if (hp >= 600) return 0x22c55e;  // green  STRONG
    if (hp >= 300) return 0xf59e0b;  // amber  HEALTHY/WEAK
    if (hp > 0)   return 0xef4444;  // red    CRITICAL
    return 0x334155;                 // slate  GHOST
  }
  function hpHeight(hp) { return Math.max(0.2, hp / 1000 * 4.0) + 0.4; }

  // ── Three.js scene ────────────────────────────────────────────────────────

  let scene, camera, renderer, controls, meshes = {}, arcs = [];
  let animId = null;

  function buildScene(canvas) {
    if (typeof THREE === 'undefined') {
      canvas.parentElement.innerHTML =
        '<div style="color:var(--txt-faint);padding:16px;font-size:11px">Three.js not loaded — add CDN to VECTOR.html</div>';
      return;
    }

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000a12);
    scene.fog = new THREE.Fog(0x000a12, 18, 40);

    camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 100);
    camera.position.set(0, 14, 18);
    camera.lookAt(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // Lights
    scene.add(new THREE.AmbientLight(0x001020, 1.0));
    const dir = new THREE.DirectionalLight(0x00cfff, 0.8);
    dir.position.set(5, 12, 8);
    scene.add(dir);

    // Ground grid
    const grid = new THREE.GridHelper(30, 20, 0x003344, 0x001a22);
    scene.add(grid);

    // OrbitControls — optional, degrades if not loaded
    if (THREE.OrbitControls) {
      controls = new THREE.OrbitControls(camera, canvas);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.minDistance = 6;
      controls.maxDistance = 35;
      controls.maxPolarAngle = Math.PI / 2.1;
    }

    // Build district buildings from D.agents
    buildBuildings();

    // Animate
    function loop() {
      animId = requestAnimationFrame(loop);
      if (controls) controls.update();
      // Pulse arcs
      arcs = arcs.filter(a => {
        a.life -= 0.016;
        if (a.life <= 0) { scene.remove(a.mesh); a.mesh.geometry.dispose(); return false; }
        a.mesh.material.opacity = Math.min(1, a.life * 2);
        return true;
      });
      renderer.render(scene, camera);
    }
    loop();

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (!canvas.clientWidth) return;
      camera.aspect = canvas.clientWidth / canvas.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(canvas.clientWidth, canvas.clientHeight);
    });
    ro.observe(canvas.parentElement);
    canvas._ro = ro;
  }

  function buildBuildings() {
    if (!scene) return;
    // Remove old
    Object.values(meshes).forEach(m => { scene.remove(m); m.geometry.dispose(); m.material.dispose(); });
    meshes = {};

    // Build one box per district
    const geo = new THREE.BoxGeometry(1.4, 1, 1.4);
    DISTRICTS.forEach((name, i) => {
      // find matching agent
      const agent = (D.agents || []).find(a => a.district === name);
      const hp = agent ? agent.health_points : 500;
      const h = hpHeight(hp);
      const col = hpColor(hp);

      const mat = new THREE.MeshLambertMaterial({
        color: col,
        emissive: col,
        emissiveIntensity: 0.15,
        transparent: true,
        opacity: hp > 0 ? 0.88 : 0.35,
      });

      const mesh = new THREE.Mesh(geo.clone(), mat);
      mesh.scale.y = h;
      const [x, , z] = GRID[i];
      mesh.position.set(x, h / 2, z);
      mesh.userData = { district: name, hp };
      scene.add(mesh);
      meshes[name] = mesh;
    });
  }

  function updateHP(districtName, hp) {
    const mesh = meshes[districtName];
    if (!mesh) return;
    const h = hpHeight(hp);
    mesh.scale.y = h;
    mesh.position.y = h / 2;
    mesh.material.color.setHex(hpColor(hp));
    mesh.material.emissive.setHex(hpColor(hp));
    mesh.material.opacity = hp > 0 ? 0.88 : 0.35;
  }

  function addFlightArc(fromDistrict, toDistrict) {
    if (!scene) return;
    const fi = DISTRICTS.indexOf(fromDistrict);
    const ti = DISTRICTS.indexOf(toDistrict);
    if (fi < 0 || ti < 0) return;

    const [x0, , z0] = GRID[fi];
    const [x1, , z1] = GRID[ti];
    const mid = new THREE.Vector3((x0 + x1) / 2, 5, (z0 + z1) / 2);

    const curve = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(x0, 0.5, z0),
      mid,
      new THREE.Vector3(x1, 0.5, z1)
    );

    const points = curve.getPoints(20);
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({ color: 0x00cfff, transparent: true, opacity: 0.9 });
    const line = new THREE.Line(geo, mat);
    scene.add(line);
    arcs.push({ mesh: line, life: 2.0 });
  }

  function updateAgents(agents) {
    (agents || []).forEach(a => {
      if (a.district) updateHP(a.district, a.health_points);
    });
  }

  function destroyScene(canvas) {
    if (animId) { cancelAnimationFrame(animId); animId = null; }
    if (controls) controls.dispose();
    if (renderer) renderer.dispose();
    if (canvas && canvas._ro) { canvas._ro.disconnect(); }
    meshes = {}; arcs = [];
    scene = camera = renderer = controls = null;
  }

  // ── Widget registration via widget:open interception ─────────────────────

  const CITY_ID = 'city3d';

  V.on('widget:open', function onCityOpen({ id, opts }) {
    if (id !== CITY_ID) return;

    // Build widget shell manually (mirrors widgets.js shell())
    const ws = document.getElementById('workspace');
    if (!ws) return;

    // Don't open twice
    if (document.querySelector(`[data-id="${CITY_ID}"]`)) {
      const existing = document.querySelector(`[data-id="${CITY_ID}"]`);
      existing.classList.add('grabbed');
      setTimeout(() => existing.classList.remove('grabbed'), 300);
      return;
    }

    const wrap = document.createElement('div');
    wrap.className = 'widget';
    wrap.dataset.id = CITY_ID;
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-label', 'District City 3D');
    wrap.setAttribute('tabindex', '-1');

    const pos = (opts && opts.pos) || [26, 20];
    wrap.style.left = pos[0] + '%';
    wrap.style.top = pos[1] + '%';

    wrap.innerHTML = `
      <div class="w-head">
        <span class="dotled"></span>
        <span class="w-title">DISTRICT CITY · 3D</span>
        <span class="spacer"></span>
        <button type="button" class="w-x" aria-label="Close District City 3D">✕</button>
      </div>
      <div class="w-body" style="padding:0;overflow:hidden">
        <canvas id="city3d-canvas" style="display:block;width:420px;height:320px"></canvas>
      </div>
      <div class="w-corner tr"></div>
      <div class="w-corner bl"></div>`;

    const returnFocus = document.activeElement;
    function closeCity() {
      destroyScene(wrap.querySelector('#city3d-canvas'));
      wrap.classList.remove('show');
      setTimeout(() => {
        wrap.remove();
        if (returnFocus && document.contains(returnFocus) && typeof returnFocus.focus === 'function') returnFocus.focus();
      }, 200);
    }
    wrap.querySelector('.w-x').addEventListener('click', e => {
      e.stopPropagation();
      closeCity();
    });
    wrap.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.stopPropagation(); closeCity(); }
    });

    ws.appendChild(wrap);
    if (V.cinemaPlace) V.cinemaPlace(wrap);
    V.on('widget:close-external', ({ id }) => { if (id === CITY_ID && wrap.isConnected) closeCity(); });
    requestAnimationFrame(() => wrap.focus({ preventScroll: true }));

    requestAnimationFrame(() => {
      const r = wrap.getBoundingClientRect();
      V.emit('widget:lock', { rect: { left: r.left, top: r.top, width: r.width, height: r.height } });
      setTimeout(() => {
        wrap.classList.add('show');
        const canvas = wrap.querySelector('#city3d-canvas');
        if (canvas) buildScene(canvas);
      }, 130);
    });
  });

  // Expose public API so backend.js can push live updates
  global.VectorCity = { updateAgents, updateAgentHP(id, hp) {
    const agent = (D.agents || []).find(a => a.id === id);
    if (agent) updateHP(agent.district, hp);
  }, addFlightArc };

  // Patch localReply to recognise "city" keywords
  const origAsk = V.ask;
  if (origAsk) {
    V.ask = function (text) {
      if (/\b(city|district.?map|3d.?map|city.?view)\b/i.test(text)) {
        V.openWidget(CITY_ID);
        V.say('City view online, sir. All thirty-three districts visible.');
        return;
      }
      origAsk.call(V, text);
    };
  }

})(window);
