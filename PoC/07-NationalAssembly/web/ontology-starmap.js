import * as THREE from "./vendor/three.module.js";

const TAU = Math.PI * 2;

function seededRandom(seed) {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

function glowTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const context = canvas.getContext("2d");
  const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(.14, "rgba(255,255,255,.72)");
  gradient.addColorStop(.42, "rgba(255,255,255,.16)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 128, 128);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function labelTexture(title, color, subtitle = "") {
  const canvas = document.createElement("canvas");
  canvas.width = 768;
  canvas.height = 160;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.textAlign = "center";
  context.shadowColor = color;
  context.shadowBlur = 22;
  context.fillStyle = "#f8fbff";
  context.font = "700 42px sans-serif";
  context.fillText(title, canvas.width / 2, 70);
  if (subtitle) {
    context.shadowBlur = 10;
    context.fillStyle = color;
    context.font = "700 20px sans-serif";
    context.fillText(subtitle, canvas.width / 2, 112);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  return texture;
}

function makeLabel(title, color, subtitle, scale = 5.4) {
  const material = new THREE.SpriteMaterial({
    map: labelTexture(title, color, subtitle),
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(scale * 3.2, scale * .67, 1);
  return sprite;
}

function pointsLayer(count, radius, size, color, seed) {
  const random = seededRandom(seed);
  const positions = new Float32Array(count * 3);
  for (let index = 0; index < count; index += 1) {
    const distance = radius * (.25 + random() * .75);
    const theta = random() * TAU;
    const phi = Math.acos(2 * random() - 1);
    positions[index * 3] = distance * Math.sin(phi) * Math.cos(theta);
    positions[index * 3 + 1] = distance * Math.cos(phi);
    positions[index * 3 + 2] = distance * Math.sin(phi) * Math.sin(theta);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const material = new THREE.PointsMaterial({
    color,
    size,
    sizeAttenuation: true,
    transparent: true,
    opacity: .72,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  return new THREE.Points(geometry, material);
}

function lineBetween(from, to, color, opacity = .32) {
  const geometry = new THREE.BufferGeometry().setFromPoints([from, to]);
  const material = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  return new THREE.Line(geometry, material);
}

function createStarmap(canvas, payload, callbacks = {}) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x02040b);
  scene.fog = new THREE.FogExp2(0x02040b, .021);

  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: false,
    powerPreference: "high-performance",
    preserveDrawingBuffer: true,
  });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.45;

  const camera = new THREE.PerspectiveCamera(48, 1, .1, 180);
  camera.position.set(0, 1.4, 37);
  const world = new THREE.Group();
  world.rotation.x = -.08;
  scene.add(world);

  scene.add(new THREE.AmbientLight(0x9bb7ff, .35));
  const cyanLight = new THREE.PointLight(0x5eead4, 85, 42, 1.65);
  cyanLight.position.set(0, 0, 4);
  scene.add(cyanLight);
  const warmLight = new THREE.PointLight(0xfbbf24, 46, 45, 1.5);
  warmLight.position.set(-13, 7, 10);
  scene.add(warmLight);
  const roseLight = new THREE.PointLight(0xfb7185, 38, 38, 1.5);
  roseLight.position.set(12, -8, 8);
  scene.add(roseLight);

  const stars = pointsLayer(1700, 68, .095, 0xa8c7ff, 7127);
  const dust = pointsLayer(520, 34, .15, 0x5eead4, 4391);
  scene.add(stars, dust);

  const glowMap = glowTexture();
  const coreGroup = new THREE.Group();
  world.add(coreGroup);
  const coreMaterial = new THREE.MeshPhysicalMaterial({
    color: 0x7fffea,
    emissive: 0x0b8d86,
    emissiveIntensity: 2.8,
    metalness: .25,
    roughness: .1,
    transmission: .32,
    transparent: true,
    opacity: .96,
  });
  const core = new THREE.Mesh(new THREE.IcosahedronGeometry(2.15, 3), coreMaterial);
  core.userData.record = { type: "root", key: "national-policy", title: payload.root?.title || "Ontology" };
  coreGroup.add(core);
  const coreWire = new THREE.Mesh(
    new THREE.IcosahedronGeometry(2.72, 2),
    new THREE.MeshBasicMaterial({ color: 0x9ffff5, wireframe: true, transparent: true, opacity: .28, blending: THREE.AdditiveBlending }),
  );
  coreGroup.add(coreWire);
  const coreGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowMap, color: 0x5eead4, transparent: true, opacity: .76, depthWrite: false, blending: THREE.AdditiveBlending }));
  coreGlow.scale.set(10.5, 10.5, 1);
  coreGroup.add(coreGlow);
  const coreLabel = makeLabel(payload.root?.title || "Ontology", "#8ffff2", "KNOWLEDGE CORE", 4.5);
  coreLabel.position.set(0, -3.25, 0);
  coreGroup.add(coreLabel);

  const orbitalRings = [];
  [3.25, 3.8, 4.45].forEach((radius, index) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(radius, index === 1 ? .035 : .02, 8, 150),
      new THREE.MeshBasicMaterial({ color: index === 1 ? 0x60a5fa : 0x5eead4, transparent: true, opacity: .34 - index * .06, blending: THREE.AdditiveBlending }),
    );
    ring.rotation.set(Math.PI / 2 + index * .45, index * .7, index * .3);
    coreGroup.add(ring);
    orbitalRings.push(ring);
  });

  const scanRing = new THREE.Mesh(
    new THREE.RingGeometry(5.2, 5.27, 160),
    new THREE.MeshBasicMaterial({ color: 0x5eead4, side: THREE.DoubleSide, transparent: true, opacity: .15, blending: THREE.AdditiveBlending }),
  );
  scanRing.rotation.x = Math.PI / 2;
  world.add(scanRing);

  const clickable = [core];
  const visualNodes = [];
  const domainObjects = new Map();
  const links = [];
  const pulses = [];
  const domainCount = Math.max(1, (payload.domains || []).length);

  (payload.domains || []).forEach((domain, domainIndex) => {
    const angle = -Math.PI / 2 + domainIndex * TAU / domainCount;
    const domainPosition = new THREE.Vector3(
      Math.cos(angle) * 10.8,
      Math.sin(angle * 2.15) * 3.6,
      Math.sin(angle) * 8.3,
    );
    const color = new THREE.Color(domain.color);
    const group = new THREE.Group();
    group.position.copy(domainPosition);
    world.add(group);

    const material = new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: 1.6,
      metalness: .45,
      roughness: .18,
      transparent: true,
      opacity: .95,
    });
    const mesh = new THREE.Mesh(new THREE.DodecahedronGeometry(1.02, 1), material);
    mesh.userData.record = { ...domain, type: "domain", domain_key: domain.key };
    group.add(mesh);
    clickable.push(mesh);

    const wire = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.5, 1),
      new THREE.MeshBasicMaterial({ color, wireframe: true, transparent: true, opacity: .34, blending: THREE.AdditiveBlending }),
    );
    group.add(wire);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowMap, color, transparent: true, opacity: .58, depthWrite: false, blending: THREE.AdditiveBlending }));
    glow.scale.set(5.2, 5.2, 1);
    group.add(glow);
    const label = makeLabel(domain.title, domain.color, `${Number(domain.topic_count || 0).toLocaleString()} SIGNALS`, 3.5);
    label.position.set(0, -1.8, 0);
    group.add(label);
    visualNodes.push({ mesh, wire, glow, label, domainKey: domain.key, baseScale: 1, phase: domainIndex * 1.7 });
    domainObjects.set(domain.key, { group, mesh, wire, glow, label, color, position: domainPosition });

    const coreLink = lineBetween(new THREE.Vector3(), domainPosition, color, .42);
    world.add(coreLink);
    links.push({ object: coreLink, domainKey: domain.key, baseOpacity: .42 });

    const pulse = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowMap, color, transparent: true, opacity: .88, depthWrite: false, blending: THREE.AdditiveBlending }));
    pulse.scale.set(.7, .7, 1);
    pulse.userData.from = new THREE.Vector3();
    pulse.userData.to = domainPosition.clone();
    pulse.userData.offset = domainIndex / domainCount;
    world.add(pulse);
    pulses.push({ object: pulse, domainKey: domain.key });
  });

  for (const domain of payload.domains || []) {
    const parent = domainObjects.get(domain.key);
    const children = (payload.groups || []).filter((item) => item.domain_key === domain.key);
    children.forEach((item, index) => {
      const fraction = (index + .5) / Math.max(1, children.length);
      const phi = Math.acos(1 - 2 * fraction);
      const theta = index * 2.399963229728653;
      const distance = 3.1 + (index % 3) * .54;
      const local = new THREE.Vector3(
        Math.cos(theta) * Math.sin(phi) * distance,
        Math.cos(phi) * distance * .78,
        Math.sin(theta) * Math.sin(phi) * distance,
      );
      const position = parent.position.clone().add(local);
      const color = parent.color;
      const radius = Math.min(.39, .2 + Math.log2(Number(item.topic_count || 0) + 1) * .026);
      const material = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .9, blending: THREE.AdditiveBlending });
      const mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(radius, 1), material);
      mesh.position.copy(position);
      mesh.userData.record = { ...item, type: "group", color: domain.color };
      world.add(mesh);
      clickable.push(mesh);
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowMap, color, transparent: true, opacity: .36, depthWrite: false, blending: THREE.AdditiveBlending }));
      glow.position.copy(position);
      glow.scale.set(radius * 4.5, radius * 4.5, 1);
      world.add(glow);
      const label = makeLabel(item.title, domain.color, `${Number(item.topic_count || 0).toLocaleString()} TOPICS`, 1.65);
      label.position.copy(position).add(new THREE.Vector3(0, -.68, 0));
      label.visible = false;
      label.userData.record = mesh.userData.record;
      world.add(label);
      clickable.push(label);
      visualNodes.push({ mesh, glow, label, domainKey: domain.key, baseScale: 1, phase: index * .43 });
      const link = lineBetween(parent.position, position, color, .18);
      world.add(link);
      links.push({ object: link, domainKey: domain.key, baseOpacity: .18 });
    });
  }

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2(2, 2);
  const pointerTarget = new THREE.Vector2();
  let hovered = null;
  let selected = null;
  let activeDomain = "";
  let frame = 0;
  let running = false;
  let dragging = false;
  let moved = false;
  let lastX = 0;
  let lastY = 0;
  let targetCameraZ = 37;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, width < 620 ? 1.45 : 2));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.fov = width < 620 ? 58 : 48;
    camera.updateProjectionMatrix();
  }

  function pick(event) {
    const rect = canvas.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    return raycaster.intersectObjects(clickable, false)[0]?.object || null;
  }

  function setFilter(domainKey = "") {
    activeDomain = domainKey;
    for (const item of visualNodes) {
      const active = !domainKey || item.domainKey === domainKey;
      const isGroup = item.mesh.userData.record?.type === "group";
      item.mesh.material.opacity = active ? (isGroup ? .9 : .95) : .08;
      if (item.wire) item.wire.material.opacity = active ? .34 : .035;
      if (item.glow) item.glow.material.opacity = active ? (isGroup ? .36 : .58) : .025;
      if (item.label) {
        item.label.visible = !isGroup || Boolean(domainKey && item.domainKey === domainKey);
        item.label.material.opacity = active ? 1 : .13;
      }
    }
    for (const link of links) {
      link.object.material.opacity = !domainKey || link.domainKey === domainKey ? link.baseOpacity : .025;
    }
    for (const pulse of pulses) pulse.object.material.opacity = !domainKey || pulse.domainKey === domainKey ? .88 : .035;
  }

  function reset() {
    world.rotation.set(-.08, 0, 0);
    targetCameraZ = 37;
    selected = null;
    setFilter("");
  }

  function selectByKey(key) {
    const object = clickable.find((item) => item.userData.record?.key === key);
    if (!object) return false;
    selected = object;
    const record = object.userData.record;
    setFilter(record.type === "root" ? "" : (record.domain_key || record.key));
    callbacks.onSelect?.(record);
    return true;
  }

  canvas.addEventListener("pointerdown", (event) => {
    dragging = true;
    moved = false;
    lastX = event.clientX;
    lastY = event.clientY;
  });
  canvas.addEventListener("pointermove", (event) => {
    const rect = canvas.getBoundingClientRect();
    pointerTarget.x = ((event.clientX - rect.left) / rect.width - .5) * 2;
    pointerTarget.y = ((event.clientY - rect.top) / rect.height - .5) * 2;
    if (dragging) {
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      world.rotation.y += dx * .006;
      world.rotation.x = Math.max(-.65, Math.min(.5, world.rotation.x + dy * .004));
      lastX = event.clientX;
      lastY = event.clientY;
      if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
      return;
    }
    hovered = pick(event);
    canvas.style.cursor = hovered ? "pointer" : "grab";
  });
  canvas.addEventListener("pointerup", (event) => {
    if (!moved) {
      const object = pick(event);
      if (object?.userData.record) {
        selected = object;
        const record = object.userData.record;
        setFilter(record.type === "root" ? "" : (record.domain_key || record.key));
        callbacks.onSelect?.(record);
      }
    }
    dragging = false;
  });
  canvas.addEventListener("pointerleave", () => {
    dragging = false;
    hovered = null;
    pointerTarget.set(0, 0);
  });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    targetCameraZ = Math.max(24, Math.min(49, targetCameraZ + event.deltaY * .018));
  }, { passive: false });

  const clock = new THREE.Clock();
  function animate() {
    if (!running) return;
    frame = requestAnimationFrame(animate);
    const elapsed = clock.getElapsedTime();
    if (!dragging) world.rotation.y += .00075;
    core.rotation.y = elapsed * .22;
    core.rotation.x = elapsed * .11;
    coreWire.rotation.y = -elapsed * .16;
    coreWire.rotation.z = elapsed * .1;
    orbitalRings.forEach((ring, index) => {
      ring.rotation.z += .0015 + index * .0007;
      ring.rotation.y += .0008 + index * .0004;
    });
    scanRing.scale.setScalar(1 + (elapsed % 3.2) * .12);
    scanRing.material.opacity = .18 * (1 - (elapsed % 3.2) / 3.2);
    visualNodes.forEach((item) => {
      const focus = item.mesh === hovered || item.mesh === selected;
      const pulse = 1 + Math.sin(elapsed * 1.8 + item.phase) * .07;
      const target = (focus ? 1.5 : 1) * pulse;
      item.mesh.scale.lerp(new THREE.Vector3(target, target, target), .12);
      if (item.wire) {
        item.wire.rotation.y += .004;
        item.wire.rotation.x += .002;
      }
    });
    pulses.forEach(({ object }) => {
      const progress = (elapsed * .17 + object.userData.offset) % 1;
      object.position.lerpVectors(object.userData.from, object.userData.to, progress);
      const scale = .55 + Math.sin(progress * Math.PI) * .55;
      object.scale.set(scale, scale, 1);
    });
    stars.rotation.y = elapsed * .0025;
    dust.rotation.y = -elapsed * .005;
    dust.rotation.x = elapsed * .002;
    camera.position.z += (targetCameraZ - camera.position.z) * .08;
    camera.position.x += (pointerTarget.x * 1.1 - camera.position.x) * .025;
    camera.position.y += (-pointerTarget.y * .7 + 1.4 - camera.position.y) * .025;
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  }

  resize();
  canvas.dataset.renderer = "three";
  return {
    start() {
      if (running) return;
      running = true;
      clock.start();
      animate();
    },
    stop() {
      running = false;
      cancelAnimationFrame(frame);
    },
    resize,
    reset,
    filter: setFilter,
    select: selectByKey,
    renderOnce() {
      resize();
      renderer.render(scene, camera);
    },
  };
}

window.AssemblyOntology3D = { create: createStarmap, version: THREE.REVISION };
