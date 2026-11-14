// Abduction: a flying saucer pulls a very surprised cow up its beam, as high as progress has gone.
// Done: the cow pops inside and the saucer zips away. Failed: the beam cuts out and the cow drops back, with a bounce.
export default {
  id: "ufo",
  calm: false,
  create({ THREE, scene, colors, view }) {
    const mat = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.55, flatShading: true });
    const GROUND = -2.25, TOP = 1.15;

    const saucer = new THREE.Group();
    const hull = new THREE.Mesh(new THREE.SphereGeometry(1.5, 18, 10), mat(colors.ink));
    hull.scale.y = 0.26;
    const dome = new THREE.Mesh(new THREE.SphereGeometry(0.62, 14, 10), mat(colors.zap));
    dome.position.y = 0.3;
    saucer.add(hull, dome);
    const lamps = [];
    for (let i = 0; i < 8; i++) {
      const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.11, 8, 6), new THREE.MeshBasicMaterial({ color: colors.hot }));
      saucer.add(lamp);
      lamps.push(lamp);
    }
    scene.add(saucer);

    const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 1.5, 4.2, 20, 1, true),
      new THREE.MeshBasicMaterial({ color: colors.zap, transparent: true, opacity: 0.32, side: THREE.DoubleSide, depthWrite: false }));
    scene.add(beam);

    // A cow made of boxes.
    const cow = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.62, 0.6), mat(colors.ink));
    const head = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.42, 0.44), mat(colors.ink));
    head.position.set(0.72, 0.22, 0);
    const nose = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.2, 0.36), mat(colors.hot));
    nose.position.set(0.98, 0.14, 0);
    const spot = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.3, 0.62), mat(colors.muted));
    spot.position.set(-0.2, 0.12, 0);
    cow.add(body, head, nose, spot);
    const legs = [];
    for (const [x, z] of [[-0.42, -0.2], [-0.42, 0.2], [0.42, -0.2], [0.42, 0.2]]) {
      const legGeometry = new THREE.BoxGeometry(0.14, 0.5, 0.14);
      legGeometry.translate(0, -0.25, 0);
      const leg = new THREE.Mesh(legGeometry, mat(colors.ink));
      leg.position.set(x, -0.28, z);
      cow.add(leg);
      legs.push(leg);
    }
    scene.add(cow);

    const grass = new THREE.Mesh(new THREE.BoxGeometry(40, 0.3, 3), mat(colors.third));
    grass.position.y = GROUND - 0.7;
    scene.add(grass);
    const posts = [];
    for (let i = 0; i < 8; i++) {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.7, 0.12), mat(colors.muted));
      scene.add(post);
      posts.push(post);
    }
    let dropSpeed = 0, dropY = null;

    return {
      update(state, dt, time) {
        const running = state.status === "running", done = state.status === "done", failed = state.status === "failed";
        const p = state.progress;

        const away = done ? Math.max(0, state.ended - 0.45) : failed ? Math.max(0, state.ended - 0.9) * 0.4 : 0;
        saucer.position.set(Math.sin(time * 1.3) * 0.25 + away * away * 30, 2.05 + Math.sin(time * 2.2) * 0.1 + away * away * 12, 0);
        saucer.rotation.z = Math.sin(time * 1.7) * 0.06 - Math.min(away * 4, 0.5) + (failed ? Math.sin(time * 9) * 0.08 : 0);
        lamps.forEach((lamp, i) => {
          const angle = time * 2.5 + (i / lamps.length) * Math.PI * 2;
          lamp.position.set(Math.cos(angle) * 1.32, -0.12, Math.sin(angle) * 1.32);
          lamp.visible = Math.sin(angle) > -0.2;
        });

        const beamOn = running || (done && state.ended < 0.45) || (failed && state.ended < 0.5 && Math.sin(time * 45) > 0);
        beam.visible = beamOn;
        beam.position.set(saucer.position.x, -0.25, 0);
        beam.material.opacity = 0.24 + Math.sin(time * 9) * 0.07;

        let y = GROUND + (TOP - GROUND) * p;
        let size = 1;
        if (done) {
          const pull = Math.min(state.ended / 0.45, 1);
          y += (1.9 - y) * pull;
          size = 1 - pull;
        }
        if (failed) {
          if (dropY === null) dropY = y;
          dropSpeed -= 14 * dt;
          dropY += dropSpeed * dt;
          if (dropY < GROUND) { dropY = GROUND; dropSpeed = Math.abs(dropSpeed) * 0.45; if (dropSpeed < 0.6) dropSpeed = 0; }
          y = dropY;
        }
        const lifted = y > GROUND + 0.05;
        cow.position.set(saucer.position.x * (failed || done ? 0 : 0.6) + (lifted && running ? Math.sin(time * 3) * 0.12 : 0), y, 0);
        cow.rotation.z = lifted && !failed ? Math.sin(time * 2.1) * 0.35 : 0;
        cow.rotation.y = lifted && !failed ? time * 1.2 : 0;
        cow.scale.setScalar(Math.max(size, 0.001));
        legs.forEach((leg, i) => { leg.rotation.z = lifted && !failed ? Math.sin(time * 14 + i * 1.7) * 0.7 : 0; });

        posts.forEach((post, i) => post.position.set(-view.halfW + (i + 0.5) * (view.halfW * 2 / posts.length), GROUND - 0.25, -0.9));
      },
    };
  },
};
