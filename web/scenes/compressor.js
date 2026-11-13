// Compressor: a press squeezes a big block down to a tiny one as progress grows.
// Done: the press opens and the little block does a happy spin. Failed: the block springs back to full size.
export default {
  id: "compressor",
  calm: false,
  create({ THREE, scene, colors }) {
    const mat = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.6, flatShading: true });
    const SIZE = 2.6;

    const block = new THREE.Mesh(new THREE.BoxGeometry(SIZE, SIZE, SIZE), mat(colors.hot));
    block.rotation.y = 0.5;
    scene.add(block);

    const plateGeometry = new THREE.BoxGeometry(4.2, 0.38, 3.2);
    const top = new THREE.Mesh(plateGeometry, mat(colors.ink));
    const bottom = new THREE.Mesh(plateGeometry, mat(colors.ink));
    top.rotation.y = bottom.rotation.y = 0.5;
    const rodGeometry = new THREE.CylinderGeometry(0.22, 0.22, 6, 10);
    const rodTop = new THREE.Mesh(rodGeometry, mat(colors.muted));
    const rodBottom = new THREE.Mesh(rodGeometry, mat(colors.muted));
    scene.add(top, bottom, rodTop, rodBottom);

    // Little bits squeezed out of the sides.
    const bitGeometry = new THREE.BoxGeometry(0.14, 0.14, 0.14);
    const bits = [];
    let sinceBit = 0, squeeze = 0, springSpeed = 0;

    return {
      update(state, dt, time) {
        const running = state.status === "running", done = state.status === "done", failed = state.status === "failed";

        if (failed) {
          // Spring back toward full size, with a bounce.
          springSpeed += (0 - squeeze) * 60 * dt;
          springSpeed *= Math.pow(0.02, dt);
          squeeze = Math.max(0, squeeze + springSpeed * dt);
        } else {
          squeeze = state.progress;
        }
        const height = 1 - 0.86 * squeeze;                 // 1 = full height, 0.14 = fully pressed
        const bulge = 1 + 0.22 * squeeze;
        const shake = running && squeeze > 0.02 ? Math.sin(time * 55) * 0.012 : 0;

        // When done the press opens up and the small block lifts and spins.
        const open = done ? Math.min(1, state.ended * 2.2) : 0;
        const half = (SIZE * height) / 2;
        block.scale.set(bulge, height, bulge);
        block.position.y = shake + (done ? Math.abs(Math.sin(state.ended * 6)) * 0.7 * Math.max(0, 1 - state.ended / 1.8) : 0);
        block.rotation.y = 0.5 + (done ? state.ended * 5 : 0);
        block.material.color.copy(done ? colors.zap : colors.hot);

        top.position.y = half + 0.19 + open * 1.6 + shake;
        bottom.position.y = -half - 0.19 - open * 1.6 + shake;
        rodTop.position.y = top.position.y + 3.19;
        rodBottom.position.y = bottom.position.y - 3.19;

        sinceBit += dt;
        if (running && squeeze > 0.03 && squeeze < 0.99 && sinceBit > 0.07) {
          sinceBit = 0;
          const bit = new THREE.Mesh(bitGeometry, mat(Math.random() < 0.5 ? colors.third : colors.hot));
          const side = Math.random() < 0.5 ? -1 : 1;
          bit.position.set(side * (SIZE * bulge) / 2, (Math.random() - 0.5) * SIZE * height, (Math.random() - 0.5));
          bit.userData = { vx: side * (2 + Math.random() * 3), vy: 1 + Math.random() * 2.5, life: 0 };
          scene.add(bit);
          bits.push(bit);
        }
        for (let i = bits.length - 1; i >= 0; i--) {
          const bit = bits[i], d = bit.userData;
          d.life += dt;
          d.vy -= 12 * dt;
          bit.position.x += d.vx * dt;
          bit.position.y += d.vy * dt;
          bit.rotation.x += dt * 8; bit.rotation.z += dt * 6;
          if (d.life > 1.2) { scene.remove(bit); bit.material.dispose(); bits.splice(i, 1); }
        }
      },
    };
  },
};
