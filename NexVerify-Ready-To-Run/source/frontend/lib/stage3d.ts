// @ts-nocheck
// 3D hero: a phone showing a UPI payment request. NexVerify scans it, puts a "Don't pay" alert on
// the screen, and the verdict and reasons float out around the phone. Illustration only; the real
// score is computed by the backend's fixed rules.
import * as THREE from "three";

export function createStage(cv, REDUCED) {
  var T = THREE;
  var renderer = new T.WebGLRenderer({ canvas: cv, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.setClearColor(0x000000, 0);
  var scene = new T.Scene();
  var camera = new T.PerspectiveCamera(30, 1, 1, 300);
  var aniso = renderer.capabilities.getMaxAnisotropy();
  var FONT_UI = '"Figtree", "Noto Sans Devanagari", "Segoe UI", Arial, sans-serif';
  var FONT_DISPLAY = '"Bricolage Grotesque", "Figtree", "Noto Sans Devanagari", Arial, sans-serif';
  var FONT_RUPEE = '"Noto Sans Devanagari", "Figtree", Arial, sans-serif';

  function tex(w, h, draw) {
    var c = document.createElement("canvas"); c.width = w; c.height = h;
    var tx = new T.CanvasTexture(c); tx.anisotropy = aniso;
    tx.state = 0;
    tx.redraw = function () { var ctx = c.getContext("2d"); ctx.clearRect(0, 0, w, h); draw(ctx, w, h, tx.state); tx.needsUpdate = true; };
    tx.redraw();
    return tx;
  }
  function rr(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function roundedShape(w, h, r) {
    var s = new T.Shape(), x = -w / 2, y = -h / 2;
    s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r); s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r); s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
    return s;
  }
  function shapePlane(w, h, r) {
    var g = new T.ShapeGeometry(roundedShape(w, h, r), 24), uv = g.attributes.uv, p = g.attributes.position;
    for (var i = 0; i < p.count; i++) uv.setXY(i, (p.getX(i) + w / 2) / w, (p.getY(i) + h / 2) / h);
    return g;
  }

  // --- phone
  var PW = 8.2, PH = 16.8;
  var phone = new T.Group();
  var bodyGeo = new T.ExtrudeGeometry(roundedShape(PW, PH, 1.35), { depth: 0.7, bevelEnabled: true, bevelThickness: 0.28, bevelSize: 0.28, bevelSegments: 8, curveSegments: 24 });
  bodyGeo.center();
  var body = new T.Mesh(bodyGeo, new T.MeshPhysicalMaterial({ color: 0x1b2130, metalness: 0.55, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.18 }));
  phone.add(body);
  var bezel = new T.Mesh(shapePlane(PW - 0.1, PH - 0.1, 1.25), new T.MeshBasicMaterial({ color: 0x05070b }));
  bezel.position.z = 0.64; phone.add(bezel);
  [[4.25, 3.2, 1.6], [4.25, 0.9, 2.4], [-4.25, 2.6, 2.0]].forEach(function (b) {
    var btn = new T.Mesh(new T.BoxGeometry(0.16, b[2], 0.34), new T.MeshStandardMaterial({ color: 0x2a3142, metalness: 0.7, roughness: 0.3 }));
    btn.position.set(b[0], b[1], 0); phone.add(btn);
  });

  var screenTex = tex(760, 1600, function (ctx, w, h, state) {
    var g = ctx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "#0f1626"); g.addColorStop(1, "#0a0f1b");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#c9d3e6"; ctx.font = "600 30px " + FONT_UI; ctx.fillText("9:41", 60, 64);
    ctx.fillStyle = "#05070b"; rr(ctx, w / 2 - 90, 26, 180, 46, 23); ctx.fill();
    ctx.fillStyle = "#c9d3e6"; rr(ctx, w - 120, 42, 56, 24, 6); ctx.fill();
    ctx.fillStyle = "#8a96ad"; ctx.font = "600 28px " + FONT_UI; ctx.fillText("←  Pay with UPI", 52, 160);
    var ag = ctx.createLinearGradient(0, 230, 0, 390); ag.addColorStop(0, "#f2b14b"); ag.addColorStop(1, "#d9762f");
    ctx.fillStyle = ag; ctx.beginPath(); ctx.arc(w / 2, 310, 78, 0, 7); ctx.fill();
    ctx.fillStyle = "#1b1208"; ctx.font = "800 64px " + FONT_DISPLAY; ctx.textAlign = "center"; ctx.fillText("BS", w / 2, 333);
    ctx.fillStyle = "#eef2f8"; ctx.font = "700 44px " + FONT_UI; ctx.fillText("Bullvanta Signals", w / 2, 460);
    ctx.fillStyle = "#8a96ad"; ctx.font = "500 28px " + FONT_UI; ctx.fillText("bullvanta.vip@upi", w / 2, 506);
    ctx.fillStyle = "#eef2f8"; ctx.font = "800 150px " + FONT_DISPLAY; ctx.fillText("₹4,999", w / 2, 720);
    ctx.fillStyle = "#1a2337"; rr(ctx, 110, 770, w - 220, 74, 37); ctx.fill();
    ctx.fillStyle = "#c9d3e6"; ctx.font = "500 30px " + FONT_UI; ctx.fillText("VIP group fee · 300% returns", w / 2, 818);
    ctx.textAlign = "left";
    ctx.fillStyle = "#121a2b"; rr(ctx, 60, 900, w - 120, 220, 28); ctx.fill();
    ctx.fillStyle = "#8a96ad"; ctx.font = "500 27px " + FONT_UI;
    ctx.fillText("Pay from", 100, 958); ctx.fillText("Bank account •••• 4417", 100, 1004);
    ctx.fillText("“SEBI registered · guaranteed”", 100, 1074);
    var blocked = state === 1;
    ctx.fillStyle = blocked ? "#2a3040" : "#1fae6c"; rr(ctx, 60, 1330, w - 120, 130, 65); ctx.fill();
    ctx.fillStyle = blocked ? "#7f889b" : "#ffffff"; ctx.font = "700 46px " + FONT_UI; ctx.textAlign = "center";
    ctx.fillText(blocked ? "Payment paused" : "Pay ₹4,999", w / 2, 1412); ctx.textAlign = "left";
    if (blocked) {
      ctx.fillStyle = "rgba(255,93,98,0.96)"; rr(ctx, 36, 96, w - 72, 190, 34); ctx.fill();
      ctx.fillStyle = "#ffffff"; ctx.font = "800 24px " + FONT_UI; ctx.fillText("NEXVERIFY", 82, 150);
      ctx.font = "800 52px " + FONT_DISPLAY; ctx.fillText("Don't pay. High risk.", 82, 212);
      ctx.font = "500 26px " + FONT_UI; ctx.fillText("Fake SEBI claim · site is 12 days old", 82, 256);
    }
  });
  var screen = new T.Mesh(shapePlane(PW - 0.55, PH - 0.55, 1.0), new T.MeshBasicMaterial({ map: screenTex }));
  screen.position.z = 0.66; phone.add(screen);

  // scan beam
  var beamTex = tex(16, 128, function (ctx, w, h) {
    var g = ctx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "rgba(51,217,166,0)"); g.addColorStop(0.5, "rgba(120,220,255,0.95)"); g.addColorStop(1, "rgba(79,141,255,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  });
  var beam = new T.Mesh(new T.PlaneGeometry(PW - 0.4, 1.4), new T.MeshBasicMaterial({ map: beamTex, transparent: true, opacity: 0, blending: T.AdditiveBlending, depthWrite: false }));
  beam.position.z = 0.72; phone.add(beam);
  phone.rotation.set(0.06, -0.38, 0.04);
  scene.add(phone);

  // glow behind the phone
  var glowTex = tex(256, 256, function (ctx, w, h) {
    var g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2); g.addColorStop(0, "rgba(47,107,255,0.55)"); g.addColorStop(0.45, "rgba(47,107,255,0.16)"); g.addColorStop(1, "rgba(47,107,255,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  });
  var glow = new T.Mesh(new T.PlaneGeometry(21, 21), new T.MeshBasicMaterial({ map: glowTex, transparent: true, depthWrite: false, blending: T.AdditiveBlending }));
  glow.position.set(0, 0, -6); scene.add(glow);

  // floating cards
  function card(w, h, px, draw) {
    var tx = tex(Math.round(w * px), Math.round(h * px), draw);
    var m = new T.Mesh(new T.PlaneGeometry(w, h), new T.MeshBasicMaterial({ map: tx, transparent: true, depthWrite: false }));
    m.scale.setScalar(0.0001); scene.add(m); return m;
  }
  var verdictCard = card(9.6, 4.9, 90, function (ctx, w, h) {
    var g = ctx.createLinearGradient(0, 0, w, h); g.addColorStop(0, "#3a1218"); g.addColorStop(1, "#170a0e");
    ctx.fillStyle = g; rr(ctx, 6, 6, w - 12, h - 12, 46); ctx.fill();
    ctx.strokeStyle = "rgba(255,93,98,0.7)"; ctx.lineWidth = 4; rr(ctx, 6, 6, w - 12, h - 12, 46); ctx.stroke();
    ctx.fillStyle = "#ff5d62"; ctx.beginPath(); ctx.arc(110, 140, 52, 0, 7); ctx.fill();
    ctx.strokeStyle = "#2a0d12"; ctx.lineWidth = 12; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(88, 118); ctx.lineTo(132, 162); ctx.moveTo(132, 118); ctx.lineTo(88, 162); ctx.stroke();
    ctx.fillStyle = "#ffb3b5"; ctx.font = "700 30px " + FONT_UI; ctx.fillText("NEXVERIFY VERDICT", 192, 118);
    ctx.fillStyle = "#ffffff"; ctx.font = "800 92px " + FONT_DISPLAY; ctx.fillText("Don't pay", 188, 196);
    ctx.fillStyle = "#ffd0d1"; ctx.font = "500 34px " + FONT_UI; ctx.fillText("Score 0/100 · high risk", 70, 330);
    ctx.fillStyle = "rgba(255,255,255,0.14)"; rr(ctx, 70, 362, w - 140, 14, 7); ctx.fill();
    ctx.fillStyle = "#ff5d62"; rr(ctx, 70, 362, 30, 14, 7); ctx.fill();
  });
  var REASONS = ["Fake “SEBI registered” claim", "Website is only 12 days old", "Promises 300% guaranteed returns"];
  var reasonCards = REASONS.map(function (txt) {
    return card(8.0, 1.7, 100, function (ctx, w, h) {
      ctx.fillStyle = "rgba(20,26,40,0.94)"; rr(ctx, 4, 4, w - 8, h - 8, 40); ctx.fill();
      ctx.strokeStyle = "rgba(150,172,214,0.28)"; ctx.lineWidth = 3; rr(ctx, 4, 4, w - 8, h - 8, 40); ctx.stroke();
      ctx.fillStyle = "#3a1419"; ctx.beginPath(); ctx.arc(88, h / 2, 46, 0, 7); ctx.fill();
      ctx.strokeStyle = "#ff5d62"; ctx.lineWidth = 9; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(70, h / 2 - 18); ctx.lineTo(106, h / 2 + 18); ctx.moveTo(106, h / 2 - 18); ctx.lineTo(70, h / 2 + 18); ctx.stroke();
      var fs = 44; ctx.font = "600 " + fs + "px " + FONT_UI;
      while (ctx.measureText(txt).width > w - 200 && fs > 26) { fs -= 2; ctx.font = "600 " + fs + "px " + FONT_UI; }
      ctx.fillStyle = "#eef2f8"; ctx.fillText(txt, 160, h / 2 + fs * 0.35);
    });
  });
  var CARD_POS = [
    { m: verdictCard, from: [1, 0, 1], to: [4.4, 3.8, 4.0], ry: -0.22, at: 2.55 },
    { m: reasonCards[0], from: [0, 0, 0], to: [-4.9, 1.4, 3.6], ry: 0.26, at: 3.05 },
    { m: reasonCards[1], from: [0, 0, 0], to: [-5.4, -1.1, 4.6], ry: 0.26, at: 3.35 },
    { m: reasonCards[2], from: [0, 0, 0], to: [-4.7, -3.6, 3.2], ry: 0.26, at: 3.65 }
  ];
  var redGlowTex = tex(256, 256, function (ctx, w, h) {
    var g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2); g.addColorStop(0, "rgba(255,93,98,0.45)"); g.addColorStop(1, "rgba(255,93,98,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  });
  var redGlow = new T.Mesh(new T.PlaneGeometry(18, 12), new T.MeshBasicMaterial({ map: redGlowTex, transparent: true, opacity: 0, depthWrite: false, blending: T.AdditiveBlending }));
  scene.add(redGlow);

  // rupee coins
  var coinFace = tex(256, 256, function (ctx, w, h) {
    var g = ctx.createRadialGradient(w * 0.4, h * 0.35, 10, w / 2, h / 2, w / 2); g.addColorStop(0, "#f4d58f"); g.addColorStop(1, "#b88a3e");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(w / 2, h / 2, w / 2, 0, 7); ctx.fill();
    ctx.strokeStyle = "rgba(90,60,20,0.45)"; ctx.lineWidth = 6; ctx.beginPath(); ctx.arc(w / 2, h / 2, w / 2 - 16, 0, 7); ctx.stroke();
    ctx.fillStyle = "rgba(90,60,20,0.75)"; ctx.font = "800 140px " + FONT_RUPEE; ctx.textAlign = "center"; ctx.fillText("₹", w / 2, h / 2 + 50);
  });
  var gold = new T.MeshStandardMaterial({ color: 0xd9b36c, metalness: 0.65, roughness: 0.32, emissive: 0x2a1c06, emissiveIntensity: 0.4 });
  var faceMat = new T.MeshStandardMaterial({ map: coinFace, metalness: 0.5, roughness: 0.35 });
  function coin(x, y, z, s) {
    var c = new T.Mesh(new T.CylinderGeometry(1.7, 1.7, 0.3, 56), [gold, faceMat, faceMat]);
    c.position.set(x, y, z); c.scale.setScalar(s); c.rotation.x = Math.PI / 2; scene.add(c); return c;
  }
  var coins = [coin(5.6, -6.2, 2.0, 1.0), coin(-4.6, -7.4, -0.6, 0.8), coin(6.8, 6.6, -2.2, 0.65)];

  // dust
  var n = 160, pos = new Float32Array(n * 3);
  for (var i = 0; i < n; i++) { pos[i * 3] = (Math.random() - 0.5) * 40; pos[i * 3 + 1] = (Math.random() - 0.5) * 26; pos[i * 3 + 2] = (Math.random() - 0.5) * 16 - 4; }
  var pg = new T.BufferGeometry(); pg.setAttribute("position", new T.BufferAttribute(pos, 3));
  var dust = new T.Points(pg, new T.PointsMaterial({ color: 0x8fb0ff, size: 0.08, transparent: true, opacity: 0.6, depthWrite: false }));
  scene.add(dust);

  scene.add(new T.AmbientLight(0xffffff, 0.35));
  var key = new T.DirectionalLight(0xffffff, 0.9); key.position.set(-10, 14, 18); scene.add(key);
  var rim = new T.PointLight(0x3a7bff, 1.6, 120); rim.position.set(12, 6, -6); scene.add(rim);
  var warm = new T.PointLight(0xffb36b, 0.6, 90); warm.position.set(-14, -8, 10); scene.add(warm);
  var top = new T.DirectionalLight(0x9fc0ff, 0.5); top.position.set(4, 20, 4); scene.add(top);

  var start = performance.now(), raf = 0, visible = true, px = 0, py = 0, tx = 0, ty = 0, narrow = false;
  function easeOut(x) { x = Math.max(0, Math.min(1, x)); return 1 - Math.pow(1 - x, 3); }
  function backOut(x) { x = Math.max(0, Math.min(1, x)); var c1 = 1.7, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); }
  function layout() {
    var w = cv.clientWidth || 600, h = cv.clientHeight || 600;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; narrow = camera.aspect < 0.95;
    camera.position.set(0, 0, narrow ? 56 : 44);
    camera.updateProjectionMatrix();
  }
  function frame(now) {
    raf = requestAnimationFrame(frame);
    if (!visible || document.hidden) return;
    var t = REDUCED ? 99 : (now - start) / 1000;
    px += (tx - px) * 0.05; py += (ty - py) * 0.05;
    var float = REDUCED ? 0 : Math.sin(now / 1000 * 1.1) * 0.25;
    var inK = easeOut(t / 1.0);
    phone.position.set(0, -2.5 * (1 - inK) + float, 0);
    phone.rotation.y = -0.38 + px * 0.25 + (1 - inK) * 0.4;
    phone.rotation.x = 0.06 + py * 0.12;
    // scan
    var sk = (t - 1.05) / 1.35;
    if (sk > 0 && sk < 1) { beam.material.opacity = Math.sin(sk * Math.PI) * 0.9; beam.position.y = (PH / 2 - 0.8) - sk * (PH - 1.6); }
    else beam.material.opacity = 0;
    if (t >= 2.5 && screenTex.state !== 1) { screenTex.state = 1; screenTex.redraw(); }
    // cards
    CARD_POS.forEach(function (c) {
      var k = backOut((t - c.at) / 0.55), e = easeOut((t - c.at) / 0.55);
      var s = t < c.at ? 0.0001 : Math.max(0.0001, k);
      c.m.scale.setScalar(s);
      c.m.position.set(c.from[0] + (c.to[0] - c.from[0]) * e + px * 0.6, c.from[1] + (c.to[1] - c.from[1]) * e + float * 0.6 - py * 0.4, c.from[2] + (c.to[2] - c.from[2]) * e);
      c.m.rotation.y = c.ry + px * 0.15;
    });
    redGlow.position.set(verdictCard.position.x, verdictCard.position.y, verdictCard.position.z - 1.5);
    redGlow.material.opacity = t > 2.55 ? Math.min(1, (t - 2.55) / 0.5) * 0.9 : 0;
    coins.forEach(function (c, i) { c.rotation.z = (now / 1000) * (0.5 + i * 0.2); c.position.y += Math.sin(now / 900 + i * 2) * 0.004; });
    dust.rotation.y = now / 60000;
    renderer.render(scene, camera);
  }
  var onMove = function (e) { tx = (e.clientX / window.innerWidth) * 2 - 1; ty = (e.clientY / window.innerHeight) * 2 - 1; };
  window.addEventListener("pointermove", onMove, { passive: true });
  var io = "IntersectionObserver" in window ? new IntersectionObserver(function (es) { visible = es[0].isIntersecting; }) : null;
  if (io) io.observe(cv);
  var redrawAll = function () { [screenTex, verdictCard.material.map, coinFace].concat(reasonCards.map(function (r) { return r.material.map; })).forEach(function (x) { x.redraw(); }); };
  if (document.fonts && document.fonts.load) {
    Promise.all(['800 60px "Bricolage Grotesque"', '700 40px "Figtree"', '500 30px "Figtree"', '600 40px "Figtree"', '800 140px "Noto Sans Devanagari"']
      .map(function (f) { return document.fonts.load(f); })).then(redrawAll, function () {});
  }
  layout();
  raf = requestAnimationFrame(frame);
  return { layout: layout, wake: function () { visible = true; }, replay: function () { start = performance.now(); screenTex.state = 0; screenTex.redraw(); },
    dispose: function () { cancelAnimationFrame(raf); window.removeEventListener("pointermove", onMove); if (io) io.disconnect();
      scene.traverse(function (o) { if (o.geometry) o.geometry.dispose(); if (o.material) { (Array.isArray(o.material) ? o.material : [o.material]).forEach(function (m) { if (m.map) m.map.dispose(); m.dispose(); }); } });
      renderer.dispose(); } };
}
