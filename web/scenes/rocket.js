// Rocket: it shakes on the pad, lifts off and climbs faster and faster through the clouds as progress grows.
// Done: it shoots off the top and fireworks go off. Failed: the engine coughs, the rocket tips over and sinks.
export default {
  id: "rocket",
  calm: false,
  create({ THREE, scene, colors, view }) {
    const mat = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.6, flatShading: true });

    const rocket = new THREE.Group();
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.5, 1.7, 10), mat(colors.ink));
    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.42, 0.8, 10), mat(colors.hot));
    nose.position.y = 1.25;
    const windowPane = new THREE.Mesh(new THREE.SphereGeometry(0.2, 10, 8), mat(colors.zap));
    windowPane.position.set(0, 0.35, 0.4);
    rocket.add(body, nose, windowPane);
    for (const side of [-1, 1]) {
      const fin = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.7, 0.08), mat(colors.hot));
      fin.position.set(side * 0.6, -0.6, 0);
      fin.rotation.z = side * 0.5;
      rocket.add(fin);
    }
    const flame = new THREE.Mesh(new THREE.ConeGeometry(0.34, 1.3, 8), new THREE.MeshBasicMaterial({ color: colors.third }));
    flame.rotation.x = Math.PI;
    flame.position.y = -1.5;
    rocket.add(flame);
    scene.add(rocket);

    const pad = new THREE.Mesh(new THREE.BoxGeometry(3, 0.3, 1.6), mat(colors.muted));
    pad.position.y = -2.85;
    scene.add(pad);

    // Clouds rush past, downwards: that is what makes the climb feel fast.
    const clouds = [];
    const cloudGeometry = new THREE.SphereGeometry(0.6, 8, 6);
    for (let i = 0; i < 9; i++) {
      const cloud = new THREE.Mesh(cloudGeometry, mat(i % 3 ? colors.muted : colors.ink));
      cloud.scale.set(1.6 + Math.random(), 0.45, 0.6);
      cloud.userData = { x: Math.random() * 2 - 1, speed: 0.6 + Math.random() };
      cloud.position.set(0, -3.5 + i * 0.8, -2);
      scene.add(cloud);
      clouds.push(cloud);
    }

    // Smoke puffs from the engine, and the same pool doubles as fireworks at the end.
    const puffGeometry = new THREE.BoxGeometry(0.2, 0.2, 0.2);
    const puffs = [];
    for (let i = 0; i < 60; i++) {
      const puff = new THREE.Mesh(puffGeometry, mat([colors.third, colors.hot, colors.zap][i % 3]));
      puff.visible = false;
      puff.userData = { vx: 0, vy: 0, life: 9 };
      scene.add(puff);
      puffs.push(puff);
    }
    let nextPuff = 0, sincePuff = 0, burst = false, tilt = 0, sink = 0;
    const launch = (x, y, vx, vy) => {
      const puff = puffs[nextPuff++ % puffs.length];
      puff.visible = true;
      puff.position.set(x, y, 0.5);
      puff.scale.setScalar(1);
      puff.userData = { vx, vy, life: 0 };
    };

    return {
      update(state, dt, time) {
        const running = state.status === "running", done = state.status === "done", failed = state.status === "failed";
        const p = state.progress;
        const speed = 0.4 + p * 7;

        const shake = running ? Math.sin(time * 60) * 0.02 * (0.5 + p) : 0;
        let y = -1.6 + Math.min(p * 6, 1) * 0.9 + p * 0.9;
        if (done) y += state.ended * state.ended * 14;
        if (failed) {
          tilt = Math.min(1.35, tilt + dt * 1.2);
          sink += dt * 1.6;
          y = Math.max(-2.2, y - sink * sink * 0.8);
        }
        rocket.position.set(shake, y, 0);
        rocket.rotation.z = failed ? tilt : Math.sin(time * 2) * 0.03;
        flame.visible = !failed || Math.sin(time * 40) > 0.7;
        flame.scale.set(1, 0.6 + Math.random() * 0.5 + p * 0.6, 1);
        pad.position.y = -2.85 - Math.min(p * 6, 1) * 2;   // the pad drops away once it lifts off

        for (const cloud of clouds) {
          cloud.position.y -= cloud.userData.speed * speed * dt * (failed ? 0.1 : 1);
          if (cloud.position.y < -3.8) { cloud.position.y = 3.8; cloud.userData.x = Math.random() * 2 - 1; }
          cloud.position.x = cloud.userData.x * view.halfW;
          cloud.visible = p > 0.08;
        }

        sincePuff += dt;
        if (running && sincePuff > 0.04) {
          sincePuff = 0;
          launch(shake + (Math.random() - 0.5) * 0.3, y - 1.9, (Math.random() - 0.5) * 2, -2 - Math.random() * 3 - speed * 0.4);
        }
        if (done && !burst && state.ended > 0.55) {
          burst = true;
          for (let i = 0; i < 60; i++) {
            const angle = (i / 60) * Math.PI * 2, force = 2.5 + Math.random() * 4;
            launch(0, 0.6, Math.cos(angle) * force, Math.sin(angle) * force);
          }
        }
        for (const puff of puffs) {
          if (!puff.visible) continue;
          const d = puff.userData;
          d.life += dt;
          if (burst) d.vy -= 3 * dt;
          puff.position.x += d.vx * dt;
          puff.position.y += d.vy * dt;
          puff.rotation.x += dt * 6; puff.rotation.y += dt * 4;
          puff.scale.setScalar(Math.max(0.01, 1 - d.life / (burst ? 1.4 : 0.7)));
          if (d.life > (burst ? 1.4 : 0.7)) puff.visible = false;
        }
      },
    };
  },
};
