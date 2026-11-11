export function addScenery(scene, THREE) {
  const cube = new THREE.BoxGeometry(1, 1, 1);
  const edges = new THREE.EdgesGeometry(cube);
  const outline = new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: .35 });
  const bark = new THREE.MeshLambertMaterial({ color: 0x86512e });
  const leaves = new THREE.MeshLambertMaterial({ color: 0x319b46 });
  const white = new THREE.MeshLambertMaterial({ color: 0xffffff });
  const yellow = new THREE.MeshLambertMaterial({ color: 0xffdb35, emissive: 0x614000 });
  function block(parent, material, size, position) {
    const mesh = new THREE.Mesh(cube, material);
    mesh.scale.set(...size);
    mesh.position.set(...position);
    mesh.add(new THREE.LineSegments(edges, outline));
    parent.add(mesh);
  }
  for (let i = 0; i < 12; i++) {
    const angle = i * Math.PI / 6, radius = 1180 + i % 3 * 80;
    const tree = new THREE.Group();
    tree.position.set(Math.cos(angle) * radius, Math.sin(angle) * radius, 0);
    block(tree, bark, [28, 28, 90], [0, 0, 45]);
    const size = 90 + i % 3 * 12;
    block(tree, leaves, [size, size, size], [0, 0, 90 + size / 2 - 10]);
    scene.add(tree);
  }
  const clouds = [];
  for (let i = 0; i < 8; i++) {
    const angle = i * Math.PI / 4;
    const cloud = new THREE.Group();
    const x = Math.cos(angle) * 1600, y = Math.sin(angle) * 1600;
    cloud.position.set(x, y, 580 + Math.sin(i) * 50);
    block(cloud, white, [160, 65, 50], [0, 0, 0]);
    block(cloud, white, [80, 80, 65], [-70, 0, 15]);
    block(cloud, white, [100, 75, 65], [80, 0, 10]);
    scene.add(cloud);
    clouds.push({ cloud, x, y, phase: i });
  }
  block(scene, yellow, [240, 240, 240], [1700, 1700, 1500]);

  // --- block town ringing the case area: everything static is instanced, outlines are one merged line mesh
  const boxes = [], glows = [], studs = [], wins = [];  // wins: house-window indices into glows, lit one by one
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), v = new THREE.Vector3(), sc = new THREE.Vector3(), Z = new THREE.Vector3(0, 0, 1), col = new THREE.Color();
  const at = (r, deg) => { const a = deg * Math.PI / 180; return { x: Math.cos(a) * r, y: Math.sin(a) * r, a }; };  // local +x points away from the centre
  function put(list, color, [w, d, h], [lx, ly, z0], f, stud) {
    const c = Math.cos(f.a), s = Math.sin(f.a), x = f.x + lx * c - ly * s, y = f.y + lx * s + ly * c;
    list.push({ color, w, d, h, x, y, z: z0 + h / 2, a: f.a });
    if (!stud) return;
    const nx = Math.max(1, Math.floor(w / 14)), ny = Math.max(1, Math.floor(d / 14));
    for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) {
      const sx = lx + (i - (nx - 1) / 2) * 14, sy = ly + (j - (ny - 1) / 2) * 14;
      studs.push({ color, w: 4, d: 4, h: 4, x: f.x + sx * c - sy * s, y: f.y + sx * s + sy * c, z: z0 + h + 2, a: f.a });
    }
  }
  const WALLS = [0xe8dcc0, 0x8fb7d9, 0xe6c86e, 0xb5cfa0, 0xd9a87c, 0xc9c1e0, 0xf0e6d2, 0x9ccfc4];
  const ROOFS = [0x5f6b7a, 0x7a5c44, 0x4f7a6a, 0x6a6488];
  [20, 100, 140, 180, 220, 260, 300, 340].forEach((deg, i) => {  // eight houses; the newsroom takes 60 degrees
    const f = at(1055, deg), D = 60, W = 70 + i % 3 * 8, H = 44 + i % 2 * 14, roof = ROOFS[i % 4];
    put(boxes, WALLS[i], [D, W, H], [0, 0, 0], f);
    [D + 8, D - 10, D - 28, 14].forEach((rw, k) => put(boxes, roof, [rw, W + 8, 10], [0, 0, H + k * 10], f, k === 3));  // stepped pitched roof
    put(boxes, 0x6b4a33, [3, 14, 24], [-D / 2 - 1, 0, 0], f);
    for (const ly of [-W / 4 - 4, W / 4 + 4]) wins.push(glows.length), put(glows, 0xffe9a0, [3, 13, 13], [-D / 2 - 1, ly, H - 26], f);
    for (const ly of [-36, -12, 12, 36]) put(boxes, 0xf0e6d2, [5, 5, 16], [-D / 2 - 24, ly, 0], f);
    put(boxes, 0xf0e6d2, [3, 76, 4], [-D / 2 - 24, 0, 9], f);
    for (const ly of [-W / 2 - 16, W / 2 + 16]) put(boxes, 0x4e8a4b, [18, 18, 16], [-D / 2 + 8, ly, 0], f, true);
  });
  const nr = at(1085, 60);  // the newsroom, with a NEWS sign of blocks on the roof
  put(boxes, 0xa7b4c2, [90, 110, 160], [0, 0, 0], nr);
  put(boxes, 0x5f6b7a, [96, 116, 8], [0, 0, 160], nr, true);
  for (let r = 0; r < 5; r++) for (let k = 0; k < 4; k++) put(glows, 0xffe9a0, [3, 14, 16], [-46, (k - 1.5) * 24, 22 + r * 27], nr);
  put(boxes, 0x34506e, [3, 26, 30], [-46, 0, 0], nr);
  for (const ly of [-40, 40]) put(boxes, 0x4a4f57, [6, 6, 20], [-20, ly, 168], nr);
  put(boxes, 0x34506e, [8, 118, 44], [-20, 0, 188], nr);
  const FONT = { N: ['101', '111', '111', '111', '101'], E: ['111', '100', '110', '100', '111'], W: ['101', '101', '101', '111', '101'], S: ['111', '100', '111', '001', '111'] };
  [...'NEWS'].forEach((ch, n) => FONT[ch].forEach((row, r) => [...row].forEach((px, c) => px === '1'
    && put(glows, 0xffe08a, [3, 6, 6], [-25, 45 - (n * 4 + c) * 6.4, 222 - r * 6.4], nr))));
  const road = new THREE.Mesh(new THREE.RingGeometry(925, 975, 120), new THREE.MeshLambertMaterial({ color: 0x6d6f73 }));
  road.position.z = .5; scene.add(road);
  for (let k = 0; k < 60; k++) put(boxes, 0xf2efe6, [3, 18, 1], [0, 0, .5], at(950, k * 6));
  for (let k = 0; k < 12; k++) {  // lamp posts on the outer kerb
    const f = at(992, 15 + k * 30);
    put(boxes, 0x4a4f57, [6, 6, 60], [0, 0, 0], f);
    put(glows, 0xfff1b8, [12, 12, 8], [0, 0, 60], f);
  }
  let glowMesh;
  const cubeMat = new THREE.MeshLambertMaterial({ color: 0xffffff }), glowMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const stud = new THREE.CylinderGeometry(1, 1, 1, 10).rotateX(Math.PI / 2);
  for (const [list, geo, mat] of [[boxes, cube, cubeMat], [glows, cube, glowMat], [studs, stud, cubeMat]]) {
    const im = new THREE.InstancedMesh(geo, mat, list.length);
    list.forEach((b, i) => {
      im.setMatrixAt(i, m4.compose(v.set(b.x, b.y, b.z), q.setFromAxisAngle(Z, b.a), sc.set(b.w, b.d, b.h)));
      im.setColorAt(i, col.set(b.color));
    });
    scene.add(im);
    if (list === glows) glowMesh = im;
  }
  const ep = edges.attributes.position.array, all = boxes.concat(glows), lines = new Float32Array(all.length * ep.length);
  all.forEach((b, i) => {
    m4.compose(v.set(b.x, b.y, b.z), q.setFromAxisAngle(Z, b.a), sc.set(b.w, b.d, b.h));
    for (let k = 0; k < ep.length; k += 3) lines.set(v.set(ep[k], ep[k + 1], ep[k + 2]).applyMatrix4(m4).toArray(), i * ep.length + k);
  });
  const lineGeo = new THREE.BufferGeometry(); lineGeo.setAttribute('position', new THREE.BufferAttribute(lines, 3));
  scene.add(new THREE.LineSegments(lineGeo, outline));
  const tyre = new THREE.MeshLambertMaterial({ color: 0x2b2b2e }), glass = new THREE.MeshLambertMaterial({ color: 0xcfe3ee });
  const cars = [[0x5b8fc7, 0, 940, .05], [0xe0b84a, 2.1, 960, -.04], [0x7fae8a, 4.2, 940, .05]].map(([color, a0, r, speed]) => {
    const car = new THREE.Group(), body = new THREE.MeshLambertMaterial({ color });
    block(car, body, [34, 18, 10], [0, 0, 9]);
    block(car, glass, [16, 15, 9], [-3, 0, 18.5]);
    for (const [x, y] of [[-11, -10], [-11, 10], [11, -10], [11, 10]]) block(car, tyre, [8, 4, 8], [x, y, 4]);
    scene.add(car);
    return { car, a0, r, speed };
  });
  // pedestrians on both pavements: 4 instanced parts each, posed every frame
  const PEDS = [0x8fb7d9, 0xe6c86e, 0xb5cfa0, 0xc9c1e0, 0x9ccfc4, 0xd9a87c, 0x6a8fb5, 0xe8dcc0].map((color, i) => (
    { color, r: i % 2 ? 893 : 911, a0: i * .8, speed: (i % 2 ? -1 : 1) * (.012 + i % 3 * .003) }));
  const pedMesh = new THREE.InstancedMesh(cube, cubeMat, PEDS.length * 4);
  PEDS.forEach(({ color }, i) => [0x3d4a5c, 0x3d4a5c, color, 0xf5cd30].forEach((c, k) => pedMesh.setColorAt(i * 4 + k, col.set(c))));
  scene.add(pedMesh);
  const frame = new THREE.Matrix4(), part = new THREE.Matrix4(), swing = new THREE.Matrix4(), Y = new THREE.Vector3(0, 1, 0);
  const birds = [[0, 330, 240], [2.1, 760, 430], [4.2, 760, 430]].map(([a0, r, z]) => {  // the first bird circles inside the camera's view
    const bird = new THREE.Group(), wings = [];
    block(bird, tyre, [16, 6, 5], [0, 0, 0]);
    for (const side of [-1, 1]) { const w = new THREE.Group(); block(w, glass, [8, 14, 2], [0, side * 7, 0]); bird.add(w); wings.push(w); }
    bird.scale.setScalar(2); scene.add(bird);
    return { bird, wings, a0, r, z };
  });
  const DARK = new THREE.Color(0x3a3f4a), LIT = new THREE.Color(0xffe9a0);
  return function update(t) {
    PEDS.forEach(({ r, a0, speed }, i) => {
      const a = a0 + t * speed, step = Math.sin(t * 7 + i) * .5;
      frame.compose(v.set(Math.cos(a) * r, Math.sin(a) * r, Math.abs(step) * 4), q.setFromAxisAngle(Z, a + Math.sign(speed) * Math.PI / 2), sc.set(2.5, 2.5, 2.5));
      for (const [k, side] of [[0, -1], [1, 1]]) {  // legs swing about the hip
        swing.makeRotationAxis(Y, side * step).premultiply(part.makeTranslation(0, side * 2.2, 9));
        pedMesh.setMatrixAt(i * 4 + k, part.copy(frame).multiply(swing).multiply(m4.compose(v.set(0, 0, -4.5), q.identity(), sc.set(4, 4, 9))));
      }
      pedMesh.setMatrixAt(i * 4 + 2, part.copy(frame).multiply(m4.compose(v.set(0, 0, 13.5), q.identity(), sc.set(5, 9, 9))));
      pedMesh.setMatrixAt(i * 4 + 3, part.copy(frame).multiply(m4.compose(v.set(0, 0, 21), q.identity(), sc.set(6, 6, 6))));
    });
    pedMesh.instanceMatrix.needsUpdate = true;
    for (const { bird, wings, a0, r, z } of birds) {
      const a = a0 - t * .08, flap = Math.sin(t * 9 + a0) * .6;
      bird.position.set(Math.cos(a) * r, Math.sin(a) * r, z + Math.sin(t + a0) * 20);
      bird.rotation.z = a - Math.PI / 2;
      wings[0].rotation.x = -flap; wings[1].rotation.x = flap;
    }
    wins.forEach((g, i) => {  // each window warms up in turn, sputtering as it comes on
      const on = Math.min(1, Math.max(0, (t - 1 - i * .6) / 2.5)), sputter = on < 1 && Math.sin(t * 23 + i * 5) > .3 ? .35 : 1;
      glowMesh.setColorAt(g, col.copy(DARK).lerp(LIT, on * sputter));
    });
    glowMesh.instanceColor.needsUpdate = true;

    for (const { cloud, x, y, phase } of clouds) {
      cloud.position.x = x + Math.sin(t * .03 + phase) * 70;
      cloud.position.y = y + Math.cos(t * .02 + phase) * 50;
    }
    for (const { car, a0, r, speed } of cars) {
      const a = a0 + t * speed;
      car.position.set(Math.cos(a) * r, Math.sin(a) * r, 0);
      car.rotation.z = a + Math.sign(speed) * Math.PI / 2;
    }
  };
}
