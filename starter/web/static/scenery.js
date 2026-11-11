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
  return function update(t) {
    for (const { cloud, x, y, phase } of clouds) {
      cloud.position.x = x + Math.sin(t * .03 + phase) * 70;
      cloud.position.y = y + Math.cos(t * .02 + phase) * 50;
    }
  };
}
