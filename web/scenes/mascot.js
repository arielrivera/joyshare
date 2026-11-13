// Mascots: the small characters from the progress scenes, on their own.
// One of them floats next to the pencil button now and then, to point out that the name and look can be changed.
// Each is built like a scene: create(ctx) returns { update(state, dt, time) }.

const ship = {
  id: "ship",
  create({ THREE, scene, colors }) {
    const mat = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.6, flatShading: true });
    const group = new THREE.Group();
    const hull = new THREE.Mesh(new THREE.ConeGeometry(0.75, 2.8, 8), mat(colors.ink));
    hull.rotation.z = -Math.PI / 2;
    const wings = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.14, 2.3), mat(colors.hot));
    wings.position.x = -0.7;
    const fin = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.1, 0.14), mat(colors.hot));
    fin.position.set(-0.8, 0.5, 0);
    const flame = new THREE.Mesh(new THREE.ConeGeometry(0.42, 1.6, 8), new THREE.MeshBasicMaterial({ color: colors.third }));
    flame.rotation.z = Math.PI / 2;
    flame.position.x = -2.1;
    group.add(hull, wings, fin, flame);
    group.rotation.y = -0.5;
    scene.add(group);
    return {
      update(_state, _dt, time) {
        group.position.y = Math.sin(time * 2.2) * 0.45;
        group.rotation.z = 0.5 + Math.sin(time * 1.6) * 0.18;     // nose up, toward the pencil
        flame.scale.y = 0.75 + Math.sin(time * 38) * 0.25;
      },
    };
  },
};

const soldier = {
  id: "soldier",
  create({ THREE, scene, colors }) {
    const mat = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.7, flatShading: true });
    const box = (w, h, d, color) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color));
    const group = new THREE.Group();
    const body = box(1.5, 1.9, 1.0, colors.hot); body.position.y = -0.2;
    const head = box(1.0, 0.95, 0.9, colors.ink); head.position.y = 1.3;
    const helmet = box(1.25, 0.5, 1.15, colors.hot); helmet.position.y = 1.9;
    const legL = box(0.55, 1.2, 0.6, colors.muted); legL.position.set(-0.4, -1.75, 0);
    const legR = legL.clone(); legR.position.x = 0.4;
    const arm = new THREE.Group();
    const limb = box(0.45, 1.5, 0.45, colors.hot); limb.position.y = 0.75;
    arm.add(limb);
    arm.position.set(0.95, 0.5, 0);
    group.add(body, head, helmet, legL, legR, arm);
    group.rotation.y = -0.4;
    scene.add(group);
    return {
      update(_state, _dt, time) {
        group.position.y = Math.abs(Math.sin(time * 3.2)) * 0.5 - 0.1;   // little hops
        arm.rotation.z = -0.6 + Math.sin(time * 6) * 0.35;               // pointing up at the pencil, waving
      },
    };
  },
};

const block = {
  id: "block",
  create({ THREE, scene, colors }) {
    const cube = new THREE.Mesh(new THREE.BoxGeometry(2.6, 2.6, 2.6),
      new THREE.MeshStandardMaterial({ color: colors.hot, roughness: 0.6, flatShading: true }));
    scene.add(cube);
    return {
      update(_state, _dt, time) {
        const squash = 1 - 0.28 * (0.5 + 0.5 * Math.sin(time * 3));       // squeezed and released, like in the press
        cube.scale.set(1 + (1 - squash) * 0.5, squash, 1 + (1 - squash) * 0.5);
        cube.rotation.y = time * 0.9;
        cube.position.y = Math.sin(time * 1.5) * 0.25;
      },
    };
  },
};

export default [ship, soldier, block];
