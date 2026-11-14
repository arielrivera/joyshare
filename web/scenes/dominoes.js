// Dominoes: a long winding line of them topples one after another, exactly as far as progress has gone.
// Done: the last one rings a bell and they all hop. Failed: the next one wobbles, and refuses to fall.
export default {
  id: "dominoes",
  calm: false,
  create({ THREE, scene, colors, view }) {
    const mat = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.55, flatShading: true });
    const COUNT = 26, HEIGHT = 1.25, LEAN = 1.2;            // LEAN: how far one tips before resting on the next
    const geometry = new THREE.BoxGeometry(0.16, HEIGHT, 0.62);
    geometry.translate(0, HEIGHT / 2, 0);                   // so it turns around its foot

    const dominoes = [];
    for (let i = 0; i < COUNT; i++) {
      const piece = new THREE.Mesh(geometry, mat([colors.hot, colors.ink, colors.zap, colors.third][i % 4]));
      scene.add(piece);
      dominoes.push(piece);
    }
    const bell = new THREE.Mesh(new THREE.SphereGeometry(0.42, 12, 10), mat(colors.zap));
    scene.add(bell);
    const floor = new THREE.Mesh(new THREE.BoxGeometry(40, 0.12, 3), mat(colors.muted));
    floor.position.y = -1.36;
    scene.add(floor);

    const sparkGeometry = new THREE.BoxGeometry(0.14, 0.14, 0.14);
    const sparks = [];
    for (let i = 0; i < 30; i++) {
      const spark = new THREE.Mesh(sparkGeometry, mat([colors.zap, colors.hot, colors.third][i % 3]));
      spark.visible = false;
      scene.add(spark);
      sparks.push(spark);
    }
    let rang = false;

    return {
      update(state, dt, time) {
        const done = state.status === "done", failed = state.status === "failed";
        const span = view.halfW * 0.86;
        const reach = state.progress * COUNT;                // how many have gone over, with a fraction
        dominoes.forEach((piece, i) => {
          const along = i / (COUNT - 1);
          piece.position.set(-span + along * span * 1.86, -1.3, Math.sin(along * Math.PI * 3) * 0.5);
          let tip = Math.min(Math.max(reach - i, 0), 1);
          tip = tip * tip * (3 - 2 * tip);                   // ease in and out
          let angle = -tip * LEAN;
          if (failed && i === Math.floor(reach)) angle = Math.sin(state.ended * 22) * 0.16 * Math.max(0, 1 - state.ended / 1.5);
          piece.rotation.z = angle;
          piece.position.y = -1.3 + (done ? Math.max(0, Math.sin(state.ended * 9 - i * 0.35)) * 0.5 * Math.max(0, 1 - state.ended / 1.6) : 0);
        });
        const end = -span + span * 1.86 + 0.75;
        const hit = done ? Math.min(state.ended * 4, 1) : 0;
        bell.position.set(end + hit * 0.25, -0.88 + Math.abs(Math.sin(state.ended * 10)) * hit * 1.5 * Math.max(0, 1 - state.ended / 1.6), 0);
        bell.rotation.z = Math.sin(time * 3) * 0.1 + (done ? Math.sin(state.ended * 30) * 0.4 : 0);

        if (done && !rang) {
          rang = true;
          sparks.forEach((spark) => {
            spark.visible = true;
            spark.position.set(end, -0.6, 0.5);
            spark.userData = { vx: -1 - Math.random() * 5, vy: 3 + Math.random() * 5, life: 0 };
          });
        }
        for (const spark of sparks) {
          if (!spark.visible) continue;
          const d = spark.userData;
          d.life += dt; d.vy -= 11 * dt;
          spark.position.x += d.vx * dt; spark.position.y += d.vy * dt;
          spark.rotation.x += dt * 9; spark.rotation.z += dt * 7;
          if (d.life > 1.5) spark.visible = false;
        }
      },
    };
  },
};
