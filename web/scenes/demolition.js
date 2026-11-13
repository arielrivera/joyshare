// Demolition: a small soldier on the left fires across the bar at a tower on the right.
// The tower loses bricks as progress grows and is gone at 100%. If the job fails, the gun jams and the tower stands.
const COLS = 4, ROWS = 7, BRICK = { w: 0.52, h: 0.42, d: 0.52 };
const GROUND = -2.3;

export default {
  id: "demolition",
  calm: false,
  create({ THREE, scene, colors, view }) {
    const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.7, flatShading: true, ...extra });
    const box = (w, h, d, material) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);

    const ground = box(40, 0.12, 2, mat(colors.muted));
    ground.position.y = GROUND - 0.06;
    scene.add(ground);

    // The soldier: boxes for body, head, helmet, legs, plus a rifle that kicks back when it fires.
    const soldier = new THREE.Group();
    const body = box(0.55, 0.7, 0.4, mat(colors.zap)); body.position.y = 0.85;
    const head = box(0.36, 0.34, 0.34, mat(colors.ink)); head.position.y = 1.4;
    const helmet = box(0.46, 0.18, 0.44, mat(colors.zap)); helmet.position.y = 1.62;
    const legL = box(0.2, 0.5, 0.25, mat(colors.muted)); legL.position.set(-0.15, 0.25, 0);
    const legR = legL.clone(); legR.position.x = 0.15;
    const rifle = new THREE.Group();
    const barrel = box(1.0, 0.1, 0.1, mat(colors.ink)); barrel.position.x = 0.5;
    const stock = box(0.3, 0.2, 0.12, mat(colors.muted)); stock.position.x = -0.05;
    const flash = new THREE.Mesh(new THREE.SphereGeometry(0.2, 8, 6), new THREE.MeshBasicMaterial({ color: colors.third }));
    flash.position.x = 1.1; flash.visible = false;
    const puff = new THREE.Mesh(new THREE.SphereGeometry(0.25, 8, 6), new THREE.MeshBasicMaterial({ color: colors.muted, transparent: true, opacity: 0 }));
    puff.position.set(0.9, 0.3, 0);
    rifle.add(barrel, stock, flash, puff);
    rifle.position.set(0.3, 0.95, 0.25);
    soldier.add(body, head, helmet, legL, legR, rifle);
    soldier.position.y = GROUND;
    soldier.scale.setScalar(1.25);
    scene.add(soldier);

    // The tower: bricks stacked in rows. They are knocked off from the top down.
    const tower = new THREE.Group();
    const bricks = [];
    for (let row = ROWS - 1; row >= 0; row--) {
      for (let col = 0; col < COLS; col++) {
        const brick = box(BRICK.w * 0.94, BRICK.h * 0.92, BRICK.d, mat((row + col) % 2 ? colors.hot : colors.third));
        const home = new THREE.Vector3((col - (COLS - 1) / 2) * BRICK.w + (row % 2 ? 0.08 : -0.08), row * BRICK.h + BRICK.h / 2, 0);
        brick.position.copy(home);
        tower.add(brick);
        bricks.push({ mesh: brick, home, flying: false, velocity: new THREE.Vector3(), spin: new THREE.Vector3(), life: 0 });
      }
    }
    tower.position.y = GROUND;
    scene.add(tower);

    const bulletGeometry = new THREE.SphereGeometry(0.07, 6, 5);
    const bulletMaterial = new THREE.MeshBasicMaterial({ color: colors.ink });
    const bullets = [];
    let sinceShot = 0, kick = 0, knocked = 0;

    return {
      update(state, dt, time) {
        const soldierX = -view.halfW + 1.3, towerX = view.halfW - 1.7;
        const running = state.status === "running", failed = state.status === "failed";
        tower.position.x = towerX;

        // Fire while the work is going on.
        sinceShot += dt;
        if (running && state.progress < 0.995 && sinceShot > 0.16) {
          sinceShot = 0;
          kick = 1;
          const bullet = new THREE.Mesh(bulletGeometry, bulletMaterial);
          bullet.position.set(soldierX + 1.8, GROUND + 1.19, 0.3);
          scene.add(bullet);
          bullets.push(bullet);
        }
        kick = Math.max(0, kick - dt * 9);
        flash.visible = kick > 0.6;
        rifle.position.x = 0.3 - kick * 0.12;
        for (let i = bullets.length - 1; i >= 0; i--) {
          bullets[i].position.x += dt * 16;
          if (bullets[i].position.x > towerX - 0.9 || !running) {
            scene.remove(bullets[i]);
            bullets.splice(i, 1);
          }
        }

        // Knock bricks off to match progress. A failed job leaves the rest standing.
        const goal = failed ? knocked : Math.floor((state.status === "done" ? 1 : state.progress) * bricks.length + 0.001);
        while (knocked < goal) {
          const b = bricks[knocked++];
          b.flying = true;
          b.velocity.set(1.5 + Math.random() * 2.5, 2 + Math.random() * 3, (Math.random() - 0.5) * 2);
          b.spin.set(Math.random() * 6, Math.random() * 6, Math.random() * 6);
        }
        for (const b of bricks) {
          if (!b.flying) continue;
          b.life += dt;
          b.velocity.y -= 14 * dt;
          b.mesh.position.addScaledVector(b.velocity, dt);
          b.mesh.rotation.x += b.spin.x * dt; b.mesh.rotation.y += b.spin.y * dt; b.mesh.rotation.z += b.spin.z * dt;
          b.mesh.visible = b.life < 1.6;
        }

        // The soldier: steady while firing, a victory hop when done, a frustrated shake when the gun jams.
        soldier.position.x = soldierX + (failed ? Math.sin(time * 38) * 0.04 * Math.max(0, 1 - state.ended / 1.2) : 0);
        soldier.position.y = GROUND + (state.status === "done" ? Math.abs(Math.sin(state.ended * 7)) * 0.5 * Math.max(0, 1 - state.ended / 1.6) : 0);
        if (failed) {
          puff.material.opacity = Math.max(0, 0.8 - state.ended * 0.6);
          puff.scale.setScalar(1 + state.ended * 1.8);
          puff.position.y = 0.3 + state.ended * 0.5;
          rifle.rotation.z = -0.5 * Math.min(1, state.ended * 3);
        }
      },
    };
  },
};
