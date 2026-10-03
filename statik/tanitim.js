/* Ritmeva landing page: word rotator, sticky nav border, 3D orbit (three.js r128, vendored in statik/vendor/).
   Without WebGL or three.js the static SVG mark in .stage stays visible. */
(function () {
  "use strict";
  /* hero word rotator */
  var rot = document.getElementById("rot");
  if (rot && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var words = rot.children, k = 0;
    setInterval(function () { words[k].classList.remove("on"); k = (k + 1) % words.length; words[k].classList.add("on"); }, 2200);
  }
  /* nav border after scroll */
  var nav = document.getElementById("nav");
  addEventListener("scroll", function () { nav.classList.toggle("scrolled", scrollY > 8); }, { passive: true });

  /* 3D orbit: members circle the studio; one amber member drifts off the orbit */
  var stage = document.getElementById("stage");
  if (!stage || typeof THREE === "undefined") return;
  var renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); } catch (e) { return; }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  stage.insertBefore(renderer.domElement, stage.firstChild);
  stage.classList.add("webgl");

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  camera.position.set(0, 0, 9.2);

  function glowTex(rgb) {
    var c = document.createElement("canvas"); c.width = c.height = 128;
    var g = c.getContext("2d"), gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, "rgba(" + rgb + ",1)"); gr.addColorStop(0.25, "rgba(" + rgb + ",.55)"); gr.addColorStop(1, "rgba(" + rgb + ",0)");
    g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  }
  var tealGlow = glowTex("52,195,165"), amberGlow = glowTex("245,165,74");

  var world = new THREE.Group();
  world.rotation.x = -1.08; world.rotation.y = 0.18;
  scene.add(world);

  /* studio core */
  var core = new THREE.Mesh(new THREE.SphereGeometry(0.42, 48, 48), new THREE.MeshBasicMaterial({ color: 0x7be3c9 }));
  world.add(core);
  var coreGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: tealGlow, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.9 }));
  coreGlow.scale.set(3.2, 3.2, 1); world.add(coreGlow);

  /* orbit rings */
  var R = 2.6;
  [[R, 0.012, 0.5], [R + 0.55, 0.006, 0.18], [R - 0.7, 0.006, 0.14]].forEach(function (o) {
    var ring = new THREE.Mesh(new THREE.TorusGeometry(o[0], o[1], 8, 220), new THREE.MeshBasicMaterial({ color: 0x34c3a5, transparent: true, opacity: o[2] }));
    world.add(ring);
  });

  /* members */
  var N = 34, members = [], sphere = new THREE.SphereGeometry(0.085, 20, 20);
  for (var i = 0; i < N; i++) {
    var a = (i / N) * Math.PI * 2 + (Math.random() - 0.5) * 0.12;
    var r = R + (Math.random() - 0.5) * 0.22;
    var m = new THREE.Mesh(sphere, new THREE.MeshBasicMaterial({ color: 0xbff3e6 }));
    var s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tealGlow, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.55 }));
    s.scale.set(0.55, 0.55, 1);
    var g = new THREE.Group(); g.add(m); g.add(s); world.add(g);
    members.push({ g: g, s: s, a: a, r: r, z: (Math.random() - 0.5) * 0.18 });
  }

  /* the leaving member */
  var leaver = new THREE.Group();
  leaver.add(new THREE.Mesh(new THREE.SphereGeometry(0.12, 24, 24), new THREE.MeshBasicMaterial({ color: 0xf5a54a, transparent: true })));
  var lg = new THREE.Sprite(new THREE.SpriteMaterial({ map: amberGlow, blending: THREE.AdditiveBlending, depthWrite: false }));
  lg.scale.set(1.1, 1.1, 1); leaver.add(lg);
  var halo = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.245, 48), new THREE.MeshBasicMaterial({ color: 0xf5a54a, transparent: true, side: THREE.DoubleSide }));
  leaver.add(halo);
  world.add(leaver);
  var trailGeo = new THREE.BufferGeometry(); var trailPts = new Float32Array(3 * 40);
  trailGeo.setAttribute("position", new THREE.BufferAttribute(trailPts, 3));
  var trail = new THREE.Line(trailGeo, new THREE.LineDashedMaterial({ color: 0xf5a54a, dashSize: 0.06, gapSize: 0.08, transparent: true, opacity: 0.6 }));
  world.add(trail);

  var mx = 0, my = 0;
  stage.addEventListener("pointermove", function (e) { var b = stage.getBoundingClientRect(); mx = ((e.clientX - b.left) / b.width - 0.5); my = ((e.clientY - b.top) / b.height - 0.5); });
  stage.addEventListener("pointerleave", function () { mx = my = 0; });

  function size() { var w = stage.clientWidth, h = stage.clientHeight; if (!w || !h) return; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
  size();
  if (window.ResizeObserver) new ResizeObserver(size).observe(stage); else addEventListener("resize", size);

  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var visible = true, t0 = performance.now(), spin = 0;
  if (window.IntersectionObserver) new IntersectionObserver(function (es) { visible = es[0].isIntersecting; }).observe(stage);

  var CYCLE = 9; /* seconds per leave-and-return loop */
  function frame(now) {
    var t = (now - t0) / 1000;
    if (!reduce) spin += 0.0022;
    for (var i = 0; i < members.length; i++) {
      var o = members[i], ang = o.a + spin;
      o.g.position.set(Math.cos(ang) * o.r, Math.sin(ang) * o.r, o.z);
      var pulse = Math.max(0, Math.sin(t * 2.2 - o.a * 3)); /* a rhythm wave running around the orbit */
      var sc = 1 + 0.45 * pulse * pulse;
      o.g.scale.setScalar(sc); o.s.material.opacity = 0.35 + 0.45 * pulse;
    }
    var p = reduce ? 0.55 : (t % CYCLE) / CYCLE;                /* 0..1 */
    var drift = Math.min(1, Math.max(0, (p - 0.15) / 0.6));      /* holds, drifts, then fades */
    var ease = drift * drift * (3 - 2 * drift);
    var la = 0.6 + spin * 0.6;
    var lr = R + ease * 1.7;
    leaver.position.set(Math.cos(la) * lr, Math.sin(la) * lr, ease * 0.5);
    var fade = p > 0.85 ? 1 - (p - 0.85) / 0.15 : (p < 0.08 ? p / 0.08 : 1);
    leaver.children[0].material.opacity = fade; lg.material.opacity = fade;
    halo.material.opacity = fade * (0.5 + 0.5 * Math.sin(t * 5));
    halo.scale.setScalar(1 + 0.25 * Math.sin(t * 5));
    halo.lookAt(camera.position.clone().applyMatrix4(new THREE.Matrix4().copy(world.matrixWorld).invert()));
    for (var j = 0; j < 40; j++) { var q = j / 39, rr = R + ease * 1.7 * q, aa = la; trailPts[j * 3] = Math.cos(aa) * rr; trailPts[j * 3 + 1] = Math.sin(aa) * rr; trailPts[j * 3 + 2] = ease * 0.5 * q; }
    trailGeo.attributes.position.needsUpdate = true; trail.computeLineDistances(); trail.material.opacity = 0.6 * fade * Math.min(1, ease * 3);
    world.rotation.y += ((0.18 + mx * 0.35) - world.rotation.y) * 0.05;
    world.rotation.x += ((-1.08 + my * 0.25) - world.rotation.x) * 0.05;
    renderer.render(scene, camera);
  }
  function loop(now) { if (visible && !document.hidden) frame(now); if (!reduce) requestAnimationFrame(loop); }
  if (reduce) frame(performance.now() + 4000); else requestAnimationFrame(loop);
})();
