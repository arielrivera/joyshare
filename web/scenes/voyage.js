// Voyage: a small spaceship flies from one planet to another as progress grows, and lands at 100%.
// Failed: the engine cuts out and the ship drifts off course.
export default {
  id: "voyage",
  calm: false,
  create({ THREE, scene, colors, view }) {
    const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.6, flatShading: true, ...extra });

    const home = new THREE.Mesh(new THREE.IcosahedronGeometry(1.5, 1), mat(colors.third));
    const goal = new THREE.Mesh(new THREE.IcosahedronGeometry(1.9, 1), mat(colors.hot));
    const ringMesh = new THREE.Mesh(new THREE.TorusGeometry(2.7, 0.09, 6, 40), mat(colors.zap));
    ringMesh.rotation.x = 1.25;
    const pulse = new THREE.Mesh(new THREE.TorusGeometry(1, 0.06, 6, 40),
      new THREE.MeshBasicMaterial({ color: colors.zap, transparent: true, opacity: 0 }));
    scene.add(home, goal, ringMesh, pulse);

    // The ship points along +x.
    const ship = new THREE.Group();
    const hull = new THREE.Mesh(new THREE.ConeGeometry(0.3, 1.1, 8), mat(colors.ink));
    hull.rotation.z = -Math.PI / 2;
    const wingGeometry = new THREE.BoxGeometry(0.45, 0.06, 0.9);
    const wings = new THREE.Mesh(wingGeometry, mat(colors.zap));
    wings.position.x = -0.3;
    const fin = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.45, 0.06), mat(colors.zap));
    fin.position.set(-0.35, 0.2, 0);
    const flame = new THREE.Mesh(new THREE.ConeGeometry(0.17, 0.7, 8), new THREE.MeshBasicMaterial({ color: colors.third }));
    flame.rotation.z = Math.PI / 2;
    flame.position.x = -0.85;
    ship.add(hull, wings, fin, flame);
    scene.add(ship);

    // Stars drifting past.
    const COUNT = 90;
    const positions = new Float32Array(COUNT * 3);
    for (let i = 0; i < COUNT; i++) {
      positions[i * 3] = (Math.random() * 2 - 1) * 16;
      positions[i * 3 + 1] = (Math.random() * 2 - 1) * 3;
      positions[i * 3 + 2] = -4 - Math.random() * 3;
    }
    const starGeometry = new THREE.BufferGeometry();
    starGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const stars = new THREE.Points(starGeometry, new THREE.PointsMaterial({ color: colors.ink, size: 0.09 }));
    scene.add(stars);

    let driftY = 0, driftSpin = 0;

    return {
      update(state, dt, time) {
        const running = state.status === "running", done = state.status === "done", failed = state.status === "failed";
        const fromX = -view.halfW + 0.5, toX = view.halfW - 0.9;
        home.position.set(fromX, -0.4, -1);
        goal.position.set(toX, 0.2, -1);
        ringMesh.position.copy(goal.position);
        home.rotation.y = time * 0.2;
        goal.rotation.y = -time * 0.15;

        const p = state.progress;
        const startX = fromX + 2.1, endX = toX - 2.7;
        ship.position.x = startX + (endX - startX) * p;
        ship.position.y = Math.sin(p * Math.PI) * 1.2 + (running ? Math.sin(time * 2.4) * 0.12 : 0) + driftY;
        ship.rotation.z = Math.cos(p * Math.PI) * 0.35 + driftSpin;

        flame.visible = running;
        flame.scale.y = 0.8 + Math.sin(time * 40) * 0.25;

        if (done) {
          // Land: slide into the planet and shrink, with a ring of light spreading out.
          const land = Math.min(1, state.ended * 1.4);
          ship.position.x = endX + (toX - endX) * land;
          ship.position.y *= 1 - land;
          ship.scale.setScalar(1 - land * 0.95);
          pulse.position.copy(goal.position);
          pulse.rotation.x = 1.25;
          pulse.scale.setScalar(2 + state.ended * 3.5);
          pulse.material.opacity = Math.max(0, 0.9 - state.ended * 0.7);
        }
        if (failed) {
          driftY += dt * 1.3;
          driftSpin += dt * 2.2;
        }

        // Stars move only while we are travelling.
        if (running) {
          const speed = 2 + p * 3;
          for (let i = 0; i < COUNT; i++) {
            positions[i * 3] -= speed * dt;
            if (positions[i * 3] < -16) positions[i * 3] = 16;
          }
          starGeometry.attributes.position.needsUpdate = true;
        }
      },
    };
  },
};
